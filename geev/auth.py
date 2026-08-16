"""Account lifecycle: sign-up, login (sign-in), logout.

All methods operate on a :class:`geev.client.GeevClient` via the ``http``
object it owns, so they automatically inherit its base URL, headers and
request signing.
"""

from __future__ import annotations

from typing import Optional, Tuple

from ._http import HttpEndpoints
from .exceptions import AuthenticationError, BadRequest, ValidationError
from .models import Registration, Session


def check_email(http: HttpEndpoints, email: str) -> bool:
    """Verify an email is not already used (``POST /v3/auth/email/check``).

    The API always answers 200 with ``{"available": bool, "kinds": [...]}``
    for already-registered emails (``available`` is ``false``) rather than a
    4xx, so this trusts the ``available`` field. Returns True when the email
    looks free.
    """
    payload = http.post("/auth/email/check", json_body={"email": email})
    if isinstance(payload, dict):
        return bool(payload.get("available"))
    return True


def signup(http: HttpEndpoints, *, first_name: str, last_name: str,
           email: str, password: str,
           marketing_consent: bool = False,
           picture_path: Optional[str] = None) -> Registration:
    """Create a Geev account (``POST /v3/accounts/local``, multipart).

    Returns a :class:`Registration` (``accountId`` + ``userId``). The account
    is *not* active yet: the email must be validated with a code sent by Geev
    (see :func:`validate_account` / :func:`resend_validation`).
    """
    for value, name in ((first_name, "first_name"), (last_name, "last_name"),
                        (email, "email"), (password, "password")):
        if not value:
            raise ValidationError(f"{name} must not be empty.")
    if len(password) < 6:  # app enforces a minimum via the forms
        raise ValidationError("password must be at least 6 characters.")

    fields = {
        "firstName": first_name,
        "lastName": last_name,
        "email": email,
        "password": password,
        "marketingAndPixelConsentGranted": str(marketing_consent).lower(),
    }
    files = None
    if picture_path:
        try:
            with open(picture_path, "rb") as fh:
                files = {"picture": fh.read()}
        except OSError as exc:  # pragma: no cover - trivial
            raise ValidationError(f"Cannot read picture: {exc}") from exc

    payload = http.post_multipart("/accounts/local", fields, files=files)
    if not isinstance(payload, dict) or not payload.get("accountId"):
        raise BadRequest("Unexpected sign-up response.", payload=payload)
    return Registration(accountId=payload["accountId"],
                        userId=payload.get("userId") or "")


def resend_validation(http: HttpEndpoints, account_id: str) -> None:
    """Ask Geev to re-send the email validation code."""
    http.post(f"/accounts/{account_id}/resend-validation")


def validate_account(http: HttpEndpoints, account_id: str, code: str) -> Session:
    """Confirm the sign-up with the emailed code -> authenticated Session.

    The token is stored on the client after this call.
    """
    payload = http.post(f"/accounts/{account_id}/validate",
                        json_body={"code": code})
    _write_session(http, payload)
    return _read_session(http)


def login(http: HttpEndpoints, email: str, password: str) -> Session:
    """Sign in with email + password (``POST /v3/auth/local/login``).

    No ``X-Geev-Token`` is required for this call; the returned ``appToken``
    is stored on the client and used for every subsequent request.
    """
    payload = http.post("/auth/local/login",
                        json_body={"login": email, "password": password},
                        token=None)
    _write_session(http, payload)
    return _read_session(http)


def logout(http: HttpEndpoints) -> None:
    """Invalidate the current token (``POST /v3/auth/logout``).

    This is a *destructive* operation: the appToken becomes unusable and the
    user has to log in again. The client's session is cleared afterwards.
    """
    http.post("/auth/logout")
    _clear_session(http)


# --------------------------------------------------------------------------
# Helpers to read/write the session on the client object. The token lives on
# the client (so HttpEndpoints can pick it up); the full Session object is
# also cached there for convenience.
# --------------------------------------------------------------------------

def _write_session(http: HttpEndpoints, payload) -> None:
    if not isinstance(payload, dict) or not payload.get("appToken"):
        raise AuthenticationError("Unexpected login response.", payload=payload)
    session = Session.from_server(payload)
    owner = _owner(http)
    if owner is not None:
        owner.session = session
        owner.token = session.appToken


def _read_session(http: HttpEndpoints) -> Session:
    owner = _owner(http)
    if owner is not None and getattr(owner, "session", None) is not None:
        return owner.session  # type: ignore[return-value]
    raise AuthenticationError("Not logged in (no session).")


def _clear_session(http: HttpEndpoints) -> None:
    owner = _owner(http)
    if owner is not None:
        owner.session = None
        owner.token = None


def _owner(http: HttpEndpoints):
    # The token provider we wired into HttpEndpoints is the client itself.
    return getattr(http, "_token_provider", None) or None
