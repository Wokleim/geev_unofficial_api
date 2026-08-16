"""Conversation objects + messaging operations.

A :class:`Conversation` is a messaging thread about an article (contacting
the vendor). It is created lazily: no network call happens at construction;
:meth:`Conversation.fetch` / :meth:`Conversation.send_message` hit the API
on demand.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._http import HttpEndpoints
from .exceptions import BadRequest
from .models import Conversation as ConversationData
from .models import Message


class Conversation:
    """A thread of messages about an article.

    Identified by ``conversation_id``. The server payload is fetched via
    ``GET /v3/conversations/{conversationId}`` when :meth:`fetch` is called.

    ``X-Geev-Token`` is required for all messaging operations.
    """

    def __init__(self, client, conversation_id: str) -> None:
        self._client = client
        self._http: HttpEndpoints = client.http
        self.conversation_id = conversation_id
        self.data: Optional[ConversationData] = None

    # ------------------------------------------------------------------ data

    @property
    def id(self) -> Optional[str]:
        return self.conversation_id

    @property
    def item_id(self) -> Optional[str]:
        return self.data.item_id if self.data else None

    @property
    def status(self) -> Optional[str]:
        return self.data.status if self.data else None

    @property
    def reservation_id(self) -> Optional[str]:
        return self.data.reservation_id if self.data else None

    @property
    def reservation(self) -> Optional[Dict[str, Any]]:
        return self.data.reservation if self.data else None

    @property
    def messages(self) -> List[Message]:
        return self.data.messages if self.data else []

    @property
    def raw(self) -> Dict[str, Any]:
        return self.data.raw if self.data else {}

    # ------------------------------------------------------------ operations

    def fetch(self) -> "Conversation":
        """Fetch the conversation details (``GET /v3/conversations/{id}``).

        Fills in the item, the other party (``recipient``) and the message
        history. Returns ``self`` for chaining.
        """
        payload = self._http.get(f"/conversations/{self.conversation_id}")
        self.data = ConversationData.from_server(payload)
        return self

    def send_message(self, text: str) -> Message:
        """Post a new message (``POST /v3/conversations/{id}/message``).

        The server answers 200 with an empty body; the sent message is
        built locally from the input.
        """
        if not text:
            raise BadRequest("Message text must not be empty.")
        self._http.post(
            f"/conversations/{self.conversation_id}/message",
            json_body={"message": text},
        )
        return Message.from_server({
            "message": text,
            "authorId": self._client.session.userId
            if getattr(self._client, "session", None) else None,
        })

    @classmethod
    def list_open(cls, client, *, item_id: Optional[str] = None,
                   with_archived: bool = False) -> List[Dict[str, Any]]:
        """List the client's conversations (``GET /v3/self/conversations``).

        Each item is an article summary carrying ``latest_conversation_id``,
        ``unread_message_count`` and the author. Pass ``item_id`` to filter
        to one article.
        """
        params: Dict[str, Any] = {}
        if item_id:
            params["itemId"] = item_id
        if with_archived:
            params["withArchived"] = "true"
        payload = client.http.get("/self/conversations", params=params or None)
        if isinstance(payload, dict):
            return payload.get("data") or payload.get("conversations") or []
        return payload if isinstance(payload, list) else []

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Conversation id={self.conversation_id!r}>"