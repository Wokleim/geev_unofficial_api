"""Low-level synchronous HTTP stack for the Geev API.

This module reproduces exactly what the Geev Android app sends on the wire:

* 13 static/global headers (User-Agent, device, app version, timezone, ...);
* ``x-geev-timestamp`` + ``x-geev-request-signature`` (HMAC-SHA256) computed
  over ``body_bytes || timestamp_ms`` whenever the request *has a body*;
* hand-built ``multipart/form-data`` bodies so the signed bytes are exactly the
  bytes sent (the app signs the raw body before OkHttp writes it to the wire).

Everything here is transport-only. Business logic lives in ``auth``, ``users``
and ``articles``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Iterable, Mapping, Optional

import requests

from .exceptions import AuthenticationError, BadRequest, ServerError

# HMAC key extracted from the app's SignatureInterceptor.
SIGNING_KEY = "d24dd4009e5429b9997984ecc03b38aa19bdd30dc70df4b2272fd6d47e620585"

DEFAULT_BASE_URL = "https://prod.geev.fr"

# V3 API prefix appended to the base URL.
DEFAULT_API_V3 = DEFAULT_BASE_URL + "/v3"

# Global headers injected by the app's OkHttp interceptors on every request.
STATIC_HEADERS = {
    "User-Agent": ("Geev/8.6.2 (fr.geev.application; build:6003; Android SDK 34) "
                   "Okhttp/4.12.0 AOSP on IA Emulator"),
    "x-geev-device-model": "AOSP on IA Emulator",
    "geev-app-version": "8.6.2",
    "geev-device": "Android",
    "timezone": "Europe/Paris",
}

BOUNDARY = "--geev-rb7f42a1c9e3d5f0"


class SigningConfig:
    """Active request-signing parameters (key + base URL)."""

    def __init__(self, *, base_url: str = DEFAULT_API_V3,
                 signing_key: str = SIGNING_KEY,
                 static_headers: Optional[Mapping[str, str]] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.signing_key = signing_key
        self.static_headers = dict(STATIC_HEADERS if static_headers is None
                                   else static_headers)


class HttpEndpoints:
    """Stateless helper exposing one method per raw HTTP primitive."""

    def __init__(self, config: SigningConfig,
                 token_provider: Optional[Any] = None) -> None:
        self.config = config
        # token_provider is a callable/object whose `token` attribute or
        # __call__() returns the current X-Geev-Token (may be None).
        self._token_provider = token_provider
        self._session = requests.Session()

    # ------------------------------------------------------------------ auth

    def _token(self) -> Optional[str]:
        if self._token_provider is None:
            return None
        if hasattr(self._token_provider, "token"):
            return self._token_provider.token  # type: ignore[union-attr]
        return self._token_provider()

    def _headers(self, body: Optional[bytes], token: Optional[str],
                 language: str, extra: Optional[Mapping[str, str]]) -> dict:
        headers = dict(self.config.static_headers)
        headers["language"] = language
        if token:
            headers["X-Geev-Token"] = token
        if extra:
            headers.update(extra)
        if body:
            ts = str(int(time.time() * 1000))  # Instant.now().toEpochMilli()
            mac = hmac.new(
                self.config.signing_key.encode("utf-8"),
                body + ts.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["x-geev-timestamp"] = ts
            headers["x-geev-request-signature"] = mac
        return headers

    def _url(self, path: str) -> str:
        path = "" if path is None else str(path)
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.config.base_url + ("/" + path.lstrip("/") if path else "")

    # ------------------------------------------------------------- transport

    def send(self, method: str, path: str, *,
             body: Optional[bytes] = None,
             json_body: Any = None,
             params: Optional[Mapping[str, Any]] = None,
             token: Optional[str] = None,
             language: str = "fr",
             content_type: str = "application/json",
             headers: Optional[Mapping[str, str]] = None) -> Any:
        """Perform a request and return the parsed JSON response (or raw text).

        Raises :class:`BadRequest` on 4xx, :class:`ServerError` on 5xx, and
        :class:`AuthenticationError` when a 401/403 is received.
        """
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        if body is not None:
            headers = {**(headers or {}), "Content-Type": content_type,
                       "Accept": "application/json"}
        final_headers = self._headers(body, token if token is not None
                                      else self._token(), language, headers)
        url = self._url(path)
        resp = self._session.request(
            method.upper(), url, data=body, params=params,
            headers=final_headers, timeout=60,
        )
        return self._decode(resp, method, url)

    def get(self, path: str, **kw: Any) -> Any:
        return self.send("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.send("POST", path, **kw)

    def put(self, path: str, **kw: Any) -> Any:
        return self.send("PUT", path, **kw)

    def patch(self, path: str, **kw: Any) -> Any:
        return self.send("PATCH", path, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.send("DELETE", path, **kw)

    # ------------------------------------------------------------- decoding

    @staticmethod
    def _decode(resp: requests.Response, method: str, url: str) -> Any:
        text = resp.text
        try:
            payload: Any = resp.json()
        except ValueError:
            payload = text

        if resp.status_code == 401 or resp.status_code == 403:
            raise AuthenticationError(
                f"Geev authentication failed ({resp.status_code}).",
                status_code=resp.status_code, payload=payload,
                method=method, url=url,
            )
        if 500 <= resp.status_code < 600:
            raise ServerError(
                f"Geev server error ({resp.status_code}).",
                status_code=resp.status_code, payload=payload,
                method=method, url=url,
            )
        if resp.status_code >= 400:
            msg = payload.get("message") if isinstance(payload, dict) else None
            raise BadRequest(
                msg or f"Request failed ({resp.status_code}).",
                status_code=resp.status_code, payload=payload,
                method=method, url=url,
            )
        return payload

    # ------------------------------------------------------------- multipart

    def post_multipart(self, path: str, fields: Mapping[str, str], *,
                       files: Optional[Mapping[str, bytes]] = None,
                       token: Optional[str] = None,
                       language: str = "fr",
                       headers: Optional[Mapping[str, str]] = None) -> Any:
        """POST a manually built multipart/form-data body (OkHttp-compatible).

        ``fields`` maps each part name -> its plain-string value (each part is
        sent with ``Content-Type: text/plain``). ``files`` maps each part name
        to the raw file bytes (filename + image/jpg are chosen automatically,
        matching the app's picture upload behaviour).
        """
        body = build_multipart(fields, files)
        content_type = f"multipart/form-data; boundary={BOUNDARY}"
        return self.send("POST", path, body=body, token=token, language=language,
                         content_type=content_type, headers=headers)


def part_stream(name: str, value: str, buf: bytearray, *,
                content_type: str = "text/plain") -> bytearray:
    buf.extend(f"--{BOUNDARY}\r\n".encode("utf-8"))
    buf.extend(
        f'Content-Disposition: form-data; name="{name}"\r\n'.encode("utf-8"))
    buf.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    buf.extend(value.encode("utf-8"))
    buf.extend(b"\r\n")
    return buf


def file_part(name: str, data: bytes, buf: bytearray, *,
              filename: Optional[str] = None,
              content_type: str = "image/jpg") -> bytearray:
    buf.extend(f"--{BOUNDARY}\r\n".encode("utf-8"))
    buf.extend(
        (f'Content-Disposition: form-data; name="{name}"; '
         f'filename="{filename or uuid.uuid4()}.jpg"\r\n').encode("utf-8"))
    buf.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    buf.extend(data)
    buf.extend(b"\r\n")
    return buf


def build_multipart(fields: Mapping[str, str],
                    files: Optional[Mapping[str, bytes]] = None) -> bytes:
    """Serialize fields + files into a multipart/form-data body, exactly as
    OkHttp would (shared loop, ``--BOUNDARY`` delimiters, trailing ``--``)."""
    buf = bytearray()
    for name, value in fields.items():
        part_stream(name, str(value), buf)
    if files:
        for name, data in files.items():
            file_part(name, data, buf)
    buf.extend(f"--{BOUNDARY}--\r\n".encode("utf-8"))
    return bytes(buf)