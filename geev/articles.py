"""Article objects + listing/search/reservation operations.

An :class:`Article` is a light wrapper around a `NewArticleRemote` payload
(listing / search result). Only the fields returned by the list/search
endpoints are available immediately; the richer detail endpoint is fetched on
demand via :meth:`Article.details`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._http import HttpEndpoints
from .conversations import Conversation
from .exceptions import BadRequest
from .models import Reservation


class Article:
    """A single Geev article (offer/request).

    Instantiated from a listing payload; never fetched lazily in ``__init__``.
    Use :meth:`details`, :meth:`reserve`, :meth:`related` to hit the API.
    """

    def __init__(self, client, payload: Dict[str, Any]) -> None:
        self._client = client
        self._http: HttpEndpoints = client.http
        self.raw = payload

    # ------------------------------------------------------------------ data

    @property
    def id(self) -> Optional[str]:
        return self.raw.get("id")

    @property
    def title(self) -> Optional[str]:
        return self.raw.get("title")

    @property
    def description(self) -> Optional[str]:
        return self.raw.get("description")

    @property
    def type(self) -> Optional[str]:
        """'donation' | 'request' | 'sale' (and variants)."""
        return self.raw.get("type")

    @property
    def state(self) -> Optional[str]:
        return self.raw.get("state")

    @property
    def status(self) -> Optional[str]:
        return self.raw.get("status")

    @property
    def category(self) -> Optional[str]:
        return self.raw.get("category")

    @property
    def universe(self) -> Optional[str]:
        return self.raw.get("universe")

    @property
    def picture(self) -> Optional[str]:
        """Primary picture URL (or id)."""
        url = self.raw.get("pictureUrl") or self.raw.get("picture")
        if url is None:
            paths = self.raw.get("picturePaths") or {}
            if isinstance(paths, dict):
                url = paths.get("default") or paths.get("squares600") \
                    or paths.get("squares300")
        if not url and isinstance(self.raw.get("pictures"), dict):
            url = (self.raw.get("pictures") or {}).get("default")
        return url

    @property
    def pictures(self) -> List[str]:
        pics = self.raw.get("pictures")
        if isinstance(pics, dict):
            keys = ("default", "squares600", "squares300", "resizes1000")
            return [pics[k] for k in keys if pics.get(k)]
        if isinstance(pics, list):
            return list(pics)
        paths = self.raw.get("picturePaths") or {}
        if isinstance(paths, dict):
            return list(paths.values())
        return []

    @property
    def city(self) -> Optional[str]:
        return self.raw.get("city") or (
            self.raw.get("location") or {}).get("city")

    @property
    def author_id(self) -> Optional[str]:
        author = self.raw.get("author") or {}
        if isinstance(author, dict):
            return author.get("id") or author.get("_id")
        return None

    @property
    def author_name(self) -> Optional[str]:
        author = self.raw.get("author") or {}
        if isinstance(author, dict):
            return (author.get("firstName") or author.get("lastName")
                    or author.get("name"))
        return None

    @property
    def carbon_value(self) -> Optional[float]:
        return self.raw.get("carbonValue")

    @property
    def savings(self) -> Optional[float]:
        return self.raw.get("savings")

    @property
    def price(self) -> Optional[float]:
        """Current (discounted) price for sale articles."""
        selling = self.raw.get("sellingInfo") or {}
        if isinstance(selling, dict):
            return (selling.get("discountedPrice")
                    or selling.get("initialPrice"))
        return self.raw.get("discountedPrice")

    @property
    def stock(self) -> Optional[int]:
        return self.raw.get("availableStock", self.raw.get("stock"))

    @property
    def validated(self) -> Optional[bool]:
        return self.raw.get("validated")

    @property
    def is_reservable(self) -> bool:
        res = self.raw.get("isReservable")
        if res is not None:
            return bool(res)
        avail = self.raw.get("isAvailable") or self.raw.get("available")
        if avail is not None:
            return bool(avail) and self.raw.get("status") != "CLOSED"
        # Details payload: derive from lifecycle status when no flag is set.
        status = self.raw.get("status") or self.raw.get("adoptionState")
        if status == "AVAILABLE":
            return True
        return self.raw.get("reserved") is False

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Article id={self.id!r} title={self.title!r} type={self.type!r}>"

    # ------------------------------------------------------------ operations

    def details(self) -> Dict[str, Any]:
        """Fetch the full detail payload (``GET /v3/items/{articleId}``).

        Includes ``description``, ``status``, ``creditCost``, ``donator``,
        ``pictures`` and ``availablePickupProviders``. Returns the raw dict.
        """
        if not self.id:
            raise BadRequest("Article has no id; cannot fetch details.")
        return self._http.get(f"/items/{self.id}")

    def reserve(self, *, recipient_user_id: Optional[str] = None) -> Reservation:
        """Reserve / order this article for a user.

        ``recipient_user_id`` defaults to the logged-in user. Returns a
        :class:`Reservation` with the ``reservationId``.

        This is a *destructive* action against other users' items.
        """
        if not self.id:
            raise BadRequest("Article has no id; cannot reserve.")
        return self._client.reserve_article(
            self.id, recipient_user_id=recipient_user_id)

    def related(self) -> List["Article"]:
        """Fetch related/similar articles (``GET /v3/items/{id}/related``)."""
        if not self.id:
            raise BadRequest("Article has no id.")
        payload = self._http.get(f"/items/{self.id}/related")
        items = payload if isinstance(payload, list) else payload.get("articles") or []
        return [Article(self._client, item) for item in items]

    def contact(self, message: str, *, dry_run: bool = False,
                confirm: bool = False) -> Conversation:
        """Message the vendor / start a conversation (``POST /v3/items/{id}/contact``).

        Creates (or reuses) the conversation thread with the article author
        and returns a :class:`Conversation` handle for it. The conversation is
        immediately fetched so ``.messages`` / ``.status`` are populated.
        ``dry_run`` validates the contact without creating anything.
        ``confirm`` acknowledges the 428 phone-verification requirement.
        """
        if not self.id:
            raise BadRequest("Article has no id; cannot contact the vendor.")
        return self._client.contact_article(
            self.id, message, dry_run=dry_run, confirm=confirm)

    def request_adoption(self, message: str, *, dry_run: bool = False
                         ) -> Dict[str, Any]:
        """Ask to adopt/donate this item (``POST /v3/adoptions``).

        Sends ``{"itemIds": [id], "message": …}`` and returns the raw
        ``{"adoptionId", "conversationId", …}`` payload. This expresses
        intent; it does not reserve the item.
        """
        if not self.id:
            raise BadRequest("Article has no id; cannot request adoption.")
        return self._client.request_adoption(self.id, message, dry_run=dry_run)

    # -------------------------------------------------------------- statics

    @classmethod
    def list_from(cls, client, payload: Dict[str, Any]) -> List["Article"]:
        """Build Article instances from a listing response.

        ``NewListArticlesRemote`` wraps items in ``{"articles": [...]}``;
        ``NewCarouselArticlesRemote`` wraps them in ``{"articles": [...]}``
        with carousel metadata, and ``ListMapArticlesRemote`` in ``{"items": …}``.
        """
        items = payload.get("articles") or payload.get("items") or []
        return [cls(client, item) for item in items]


def search_articles(http: HttpEndpoints, *,
                    text: Optional[str] = None,
                    article_type: Optional[str] = None,
                    states: Optional[List[str]] = None,
                    categories: Optional[List[str]] = None,
                    distance: Optional[float] = None,
                    latitude: Optional[float] = None,
                    longitude: Optional[float] = None,
                    mode: str = "standard",
                    placement: str = "top_categories",
                    limit: int = 20,
                    skip: int = 1) -> List[Dict[str, Any]]:
    """Run a full-text search (``POST /v3/search/items``).

    Returns the raw article payloads. Building the response into
    :class:`Article` objects is left to the client so it can pass itself.

    ``skip`` is 1-based: the API rejects ``skip=0`` (must be a positive
    number). ``placement`` must be one of the values accepted by the server:
    ``home_listing``, ``top_categories``, ``home_exclusivities``,
    ``home_near_you``, ``home_sales``, ``my_formula_contact_advantages``,
    ``not_found``, ``explorer``, ``favorites_carousel``. ``top_categories``
    supports keyword ``text`` filtering.

    ``states`` filters by the object's condition and must use the server's
    ``GeevObjectState`` values: ``"good"``, ``"like_new"``, ``"worn"`` or
    ``"broken"`` (the app sends the lowercase ``value``, not the enum
    ``name()`` — e.g. ``LIKE_NEW`` is rejected).
    """
    filters: Dict[str, Any] = {}
    if text is not None:
        filters["text"] = text
    if article_type is not None:
        filters["type"] = article_type
    if states:
        filters["states"] = list(states)
    if categories:
        filters["categories"] = list(categories)
    if distance is not None:
        filters["distance"] = distance
    if latitude is not None:
        filters["latitude"] = latitude
    if longitude is not None:
        filters["longitude"] = longitude

    body = {
        "mode": mode,
        "placement": placement,
        "filters": filters,
        "pagination": {"limit": limit, "skip": skip},
    }
    payload = http.post("/search/items", json_body=body)
    if isinstance(payload, dict):
        return payload.get("data") or payload.get("articles") or payload.get("items") or []
    return payload if isinstance(payload, list) else []