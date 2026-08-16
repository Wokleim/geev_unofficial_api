"""User objects + profile/listing summary operations.

A :class:`User` is created only with its ``userId`` (like the app does —
there is **no** user-lookup-by-name endpoint). Nothing is fetched at
construction; each method performs its own request when called, so callers can
leave expensive or irrelevant calls unexecuted.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from ._http import HttpEndpoints
from .exceptions import BadRequest
from .models import CarbonSummary, Page, Review


class User:
    """A Geev user identified by ``userId``.

    The public profile endpoints available are keyed by this id:

    * :meth:`profile`            -> ``GET /v3/users/{userId}``
    * :meth:`articles`           -> ``GET /v3/users/{userId}/items``
    * :meth:`reviews`            -> ``GET /v3/users/{userId}/reviews``
    * :meth:`carbon_summary`     -> ``GET /v3/users/{id}/carbonSummary``

    ``X-Geev-Token`` is required for these calls.
    """

    def __init__(self, client, user_id: str) -> None:
        self._client = client
        self._http: HttpEndpoints = client.http
        self.user_id = user_id

    # ------------------------------------------------------------ operations

    def profile(self) -> Dict[str, Any]:
        """Fetch the public profile payload (``GET /v3/users/{userId}``).

        Returns ``UserDetailsRemote``: ``firstName``, ``lastName``,
        ``firstIntention``, ``_links``.
        """
        self._require_logged_in()
        return self._http.get(f"/users/{self.user_id}")

    # Convenience accessors backed by `profile()`.
    @property
    def first_name(self) -> Optional[str]:
        return self.profile().get("firstName")

    @property
    def last_name(self) -> Optional[str]:
        return self.profile().get("lastName")

    def articles(self, *, operation: str = "donations",
                 status: Optional[List[str]] = None,
                 after: Optional[str] = None,
                 limit: int = 50) -> List[Any]:
        """List a user's posted items (``GET /v3/users/{userId}/items``).

        ``operation`` must be one of ``donations`` / ``requests`` (the API
        rejects calls without it). For donations the app passes a comma-joined
        status list; you can override it with ``status=[...]`` or pass
        ``status=["AVAILABLE"]`` to see only what can be ordered today.
        ``after`` pages using the cursor from a previous call.

        Returns the raw article payloads (each is a ``NewArticleRemote``
        dict), wrapped in a :class:`Page` when you pass a ``limit`` — call
        ``.items`` / ``.next_after`` to inspect pagination and iterate.
        """
        self._require_logged_in()
        params: Dict[str, Any] = {"operation": operation, "limit": limit}
        if status is not None:
            params["status"] = ",".join(status)
        if after:
            params["after"] = after
        payload = self._http.get(f"/users/{self.user_id}/items", params=params)
        items = payload.get("data") or payload.get("articles") \
            or payload.get("items") or [] if isinstance(payload, dict) \
            else payload or []
        page = Page(items=list(items), next_after=payload.get("after")
                    if isinstance(payload, dict) else None, raw=payload
                    if isinstance(payload, dict) else {})
        return page

    def iter_articles(self, *, operation: str = "donations",
                      status: Optional[List[str]] = None,
                      page_size: int = 50) -> "Iterator[Any]":
        """Lazily iterate over every article of the user, following ``after``
        cursors until exhaustion.

        By default this iterates the whole history (including closed items);
        pass ``status=["AVAILABLE"]`` to restrict it.
        """
        if page_size < 1:
            page_size = 1
        after = None
        while True:
            page = self.articles(operation=operation, status=status,
                                 after=after, limit=page_size)
            yield from page.items
            if not page.next_after:
                break
            after = page.next_after

    def reviews(self, *, type: Optional[str] = None,
                after: Optional[str] = None,
                limit: int = 20) -> List[Review]:
        """Fetch the user's reviews (``GET /v3/users/{userId}/reviews``).

        ``type`` must be either ``"ADOPTION"`` or ``"DONATION"`` (the server
        rejects anything else); when omitted, every review type is returned.
        ``after`` is the cursor for the next page.
        """
        self._require_logged_in()
        params: Dict[str, Any] = {"limit": limit}
        if type:
            params["type"] = type
        if after:
            params["after"] = after
        payload = self._http.get(f"/users/{self.user_id}/reviews", params=params)
        items = payload.get("data") or payload.get("reviews") or [] \
            if isinstance(payload, dict) else payload or []
        reviews = [Review.from_server(item) for item in items]
        return reviews

    def carbon_summary(self, *, temporality: Optional[str] = None,
                       light: bool = False) -> CarbonSummary:
        """Fetch the user's carbon-footprint summary.

        ``GET /v3/users/{id}/carbonSummary?temporality=…&light=…``
        """
        self._require_logged_in()
        params: Dict[str, Any] = {}
        if temporality:
            params["temporality"] = temporality
        if light:
            params["light"] = "true"
        payload = self._http.get(f"/users/{self.user_id}/carbonSummary",
                                 params=params or None)
        return CarbonSummary.from_server(payload)

    # ------------------------------------------------------------- internal

    def _require_logged_in(self) -> None:
        if not self._client.token:
            raise BadRequest("This call requires an authenticated session "
                             "(login first).")

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<User id={self.user_id!r}>"