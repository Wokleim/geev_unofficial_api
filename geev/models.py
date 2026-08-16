"""Value objects returned by the Geev API and wrapped by this library.

These are plain dataclasses: they hold the data returned by the server but
never *trigger* network calls on their own. Network access lives on
:class:`geev.client.GeevClient`, :class:`geev.users.User` and
:class:`geev.articles.Article`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Session:
    """Authenticated session (returned by login / account validation)."""
    appToken: str
    userId: str
    sso: Optional[Dict[str, Any]] = None
    userType: Optional[str] = None

    @classmethod
    def from_server(cls, payload: Dict[str, Any]) -> "Session":
        return cls(
            appToken=payload["appToken"],
            userId=payload["userId"],
            sso=payload.get("sso"),
            userType=payload.get("userType"),
        )


@dataclass
class Registration:
    """Pending sign-up (email validation code still required)."""
    accountId: str
    userId: str


@dataclass
class Location:
    """Geographic reference used by search filters."""
    label: Optional[str] = None
    city: Optional[str] = None
    postalCode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius: Optional[float] = None
    obfuscated: Optional[bool] = None

    @classmethod
    def from_server(cls, payload: Any) -> "Location":
        if not isinstance(payload, dict):
            return cls()
        return cls(
            label=payload.get("label"),
            city=payload.get("city"),
            postalCode=payload.get("postalCode"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            radius=payload.get("radius"),
            obfuscated=payload.get("obfuscated"),
        )


@dataclass
class Reservation:
    """A reservation created against an article."""
    reservationId: str
    itemId: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CarbonSummary:
    """User carbon-footprint summary."""
    year: Optional[int] = None
    month: Optional[int] = None
    carbonValue: Optional[float] = None
    donations: Optional[int] = None
    adoptions: Optional[int] = None
    equivalences: List[Any] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_server(cls, payload: Any) -> "CarbonSummary":
        if not isinstance(payload, dict):
            return cls(raw={} if payload is None else {"value": payload})
        return cls(
            year=payload.get("year"),
            month=payload.get("month"),
            carbonValue=payload.get("carbonValue"),
            donations=payload.get("donations"),
            adoptions=payload.get("adoptions"),
            equivalences=list(payload.get("equivalences") or []),
            raw=payload,
        )


@dataclass
class Review:
    """A single user review."""
    id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    # Convenience accessors for the most common fields (may be absent).
    grade: Optional[float] = None
    message: Optional[str] = None

    @classmethod
    def from_server(cls, payload: Any) -> "Review":
        if not isinstance(payload, dict):
            return cls(raw={} if payload is None else {"value": payload})
        return cls(
            id=payload.get("_id") or payload.get("id"),
            raw=payload,
            grade=payload.get("grade")
                or payload.get("communicationGrade")
                or payload.get("punctualityGrade"),
            message=payload.get("message") or payload.get("feedbackMessage"),
        )


@dataclass
class Page:
    """Cursor pagination over a list of items."""
    items: List[Any]
    # Request cursor to use for the *next* page (empty string when no more).
    next_after: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """A single chat message inside a :class:`Conversation`."""
    id: Optional[str] = None
    author_id: Optional[str] = None
    timestamp: Optional[int] = None
    text: Optional[str] = None
    read_by_receiver: Optional[bool] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_server(cls, payload: Any) -> "Message":
        if not isinstance(payload, dict):
            return cls(raw={} if payload is None else {"value": payload})
        return cls(
            id=payload.get("_id") or payload.get("id") or payload.get("messageId"),
            author_id=payload.get("authorId") or payload.get("author_id"),
            timestamp=payload.get("sentTimestamp")
                or payload.get("timestamp") or payload.get("createdTimestamp"),
            text=payload.get("message") or payload.get("text"),
            read_by_receiver=payload.get("readByReceiver"),
            raw=payload,
        )


@dataclass
class Conversation:
    """A messaging thread about an article.

    Wraps the ``MessagingDetailsResponse`` returned by
    ``GET /v3/conversations/{conversationId}``: the two participants
    (``recipient`` is the other party), the ``item`` they're chatting about,
    the ``messages`` so far and the thread ``status``
    (``CONTACTED`` / ``RESERVED`` / ...).
    """
    id: Optional[str] = None
    item_id: Optional[str] = None
    donator_id: Optional[str] = None
    adopter_id: Optional[str] = None
    recipient: Optional[Dict[str, Any]] = None
    item: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    active: Optional[bool] = None
    messages: List[Message] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_server(cls, payload: Any) -> "Conversation":
        if not isinstance(payload, dict):
            return cls(raw={} if payload is None else {"value": payload})
        messages = payload.get("messages") or payload.get("data") or []
        if isinstance(messages, dict):
            messages = messages.get("messages") or []
        if not isinstance(messages, list):
            messages = []
        return cls(
            id=payload.get("_id") or payload.get("conversationId"),
            item_id=payload.get("itemId") or payload.get("item_id"),
            donator_id=payload.get("donatorId"),
            adopter_id=payload.get("adopterId"),
            recipient=payload.get("recipient"),
            item=payload.get("item"),
            status=payload.get("status"),
            active=payload.get("active"),
            messages=[Message.from_server(m) for m in messages],
            raw=payload,
        )