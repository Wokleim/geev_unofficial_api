"""The public `GeevClient` facade.

A single client owns the base URL, request signing, the current auth token and
exposes every operation as a method. Object-level operations are exposed via
:class:`geev.users.User` and :class:`geev.articles.Article` returned by this
client.

Typical usage (synchronous):

    from geev import GeevClient

    geev = GeevClient()
    geev.login(email, password)          # -> Session, also stored on client
    user = geev.get_user("6a81e587e99a89cd2cbad9ac")
    articles = user.articles()           # list raw article dicts
    article = geev.get_article(articles[0]["id"])
    print(article.title, article.is_reservable)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import auth
from ._http import HttpEndpoints, SigningConfig
from .articles import Article, search_articles
from .conversations import Conversation
from .exceptions import BadRequest
from .models import Reservation, Session
from .users import User


class GeevClient:
    """Synchronous client for the Geev HTTP API (v3)."""

    def __init__(self, *, base_url: str = None, language: str = "fr",
                 token: Optional[str] = None, session: Optional[Session] = None
                 ) -> None:
        """Create a client.

        ``base_url`` defaults to the production API
        (``https://prod.geev.fr/v3``); pass ``https://dev.geev.fr/v3`` or
        ``https://stage.geev.fr/v3`` to target other environments.
        ``token`` / ``session`` let you restore an existing authenticated
        session without calling :meth:`login` again.
        """
        if base_url is None:
            config = SigningConfig()
        else:
            config = SigningConfig(base_url=base_url)
        self.language = language
        self.token: Optional[str] = token
        self.session: Optional[Session] = session
        self.http = HttpEndpoints(config, token_provider=self)

    # ------------------------------------------------------------------ auth

    def signup(self, *, first_name: str, last_name: str, email: str,
               password: str, marketing_consent: bool = False,
               picture_path: Optional[str] = None):
        """Create an account; returns a :class:`Registration`.\n\n        You still have to validate the emailed code:\n\n            reg = geev.signup(first_name=\"Jane\", last_name=\"Doe\",\n                              email=\"jane@example.com\", password=\"S3cret!\")\n            session = geev.validate_account(reg.accountId, \"123456\")\n        """
        return auth.signup(
            self.http,
            first_name=first_name, last_name=last_name, email=email,
            password=password, marketing_consent=marketing_consent,
            picture_path=picture_path,
        )

    def check_email(self, email: str) -> bool:
        """Return True if ``email`` looks available for sign-up."""
        return auth.check_email(self.http, email)

    def resend_validation(self, account_id: str) -> None:
        """Ask Geev to resend the sign-up validation email."""
        auth.resend_validation(self.http, account_id)

    def validate_account(self, account_id: str, code: str) -> Session:
        """Validate a freshly created account -> authenticated :class:`Session`."""
        return auth.validate_account(self.http, account_id, code)

    def login(self, email: str, password: str) -> Session:
        """Sign in with email + password; stores the token on the client."""
        return auth.login(self.http, email, password)

    def logout(self) -> None:
        """Log out: invalidate the token (destructive) and clear the session."""
        auth.logout(self.http)

    # -------------------------------------------------------------- articles

    def search_articles(self, *, text: str = None,
                        article_type: str = None,
                        states: List[str] = None,
                        categories: List[str] = None,
                        distance: float = None,
                        latitude: float = None,
                        longitude: float = None,
                        placement: str = "top_categories",
                        mode: str = "standard",
                        limit: int = 20,
                        skip: int = 1) -> List[Article]:
        """Full-text search over offers/requests.

        Returns a list of :class:`Article`. ``skip`` is 1-based (the server
        rejects 0). ``placement`` is one of the server-accepted values
        (``top_categories`` supports keyword ``text`` filters):
        ``home_listing``, ``top_categories``, ``home_exclusivities``,
        ``home_near_you``, ``home_sales``, ``my_formula_contact_advantages``,
        ``not_found``, ``explorer``, ``favorites_carousel``.
        ``mode`` is ``standard`` or ``carrousel``.
        """
        raw = search_articles(
            self.http, text=text, article_type=article_type, states=states,
            categories=categories, distance=distance, latitude=latitude,
            longitude=longitude, mode=mode, placement=placement,
            limit=limit, skip=skip,
        )
        return [Article(self, item) for item in raw]

    def get_article(self, article_id: str) -> Article:
        """Fetch a single article's listing payload and wrap it.

        For the richer details use :meth:`Article.details()`.
        """
        payload = self.http.get(f"/items/{article_id}")
        return Article(self, payload if isinstance(payload, dict)
                       else {"id": article_id, **payload})

    # ------------------------------------------------------------ messaging

    def get_conversation(self, conversation_id: str) -> Conversation:
        """Open an existing conversation (``GET /v3/conversations/{id}``).

        Returns a :class:`Conversation` whose details have been fetched
        (messages, participants, status).
        """
        return Conversation(self, conversation_id).fetch()

    def contact_article(self, article_id: str, message: str, *,
                        dry_run: bool = False, confirm: bool = False) -> Conversation:
        """Contact the vendor of an article.

        ``POST /v3/items/{articleId}/contact`` creates (or reuses) the
        conversation with the author and returns the resulting
        :class:`Conversation`. ``dry_run`` only validates the contact
        (capping limits, protected contact) without creating a thread.

        If the account has too many conversations without a verified phone
        number the server answers 428 and advertises a ``confirmContact``
        link; retry with ``confirm=True`` to acknowledge it.
        """
        if not message:
            raise BadRequest("contact_article needs a non-empty message.")
        path = f"/items/{article_id}/contact"
        if dry_run:
            path += "?dryRun=true"
        body: Dict[str, Any] = {"message": message}
        if confirm:
            body["confirm"] = True
        resp = self.http.post(path, json_body=body)
        conversation_id = resp.get("conversationId") if isinstance(resp, dict) \
            else None
        if dry_run or not conversation_id:
            return Conversation(self, conversation_id or "")
        # Server created/reused a thread; load its details.
        return self.get_conversation(conversation_id)

    def request_adoption(self, article_id: str, message: str, *,
                         dry_run: bool = False) -> Dict[str, Any]:
        """Request a donation adoption (``POST /v3/adoptions``).

        Payload: ``POST /adoptions`` with ``{"itemIds": [..], "message": …}``.
        Returns the raw response ``{"adoptionId", "conversationId", …}``.
        """
        if not message:
            raise BadRequest("request_adoption needs a non-empty message.")
        path = "/adoptions?dryRun=true" if dry_run else "/adoptions"
        return self.http.post(
            path, json_body={"itemIds": [article_id], "message": message})

    def list_conversations(self, *, item_id: Optional[str] = None,
                           with_archived: bool = False) -> List[Any]:
        """List the logged-in user's conversations (``GET /v3/self/conversations``).

        Returns one article summary per item with a thread, including
        ``latest_conversation_id`` and ``unread_message_count``.
        """
        return Conversation.list_open(
            self, item_id=item_id, with_archived=with_archived)

    def reserve_article(self, article_id: str, *,
                        recipient_user_id: Optional[str] = None) -> Reservation:
        """Reserve an article for the logged-in user (or ``recipient_user_id``).

        Returns a :class:`Reservation` carrying the ``reservationId``.
        """
        recipient_user_id = recipient_user_id or (self.session.userId
                                                  if self.session else None)
        if not recipient_user_id:
            raise BadRequest("reserve_article needs recipient_user_id "
                             "(login first or pass it explicitly).")
        body = {"itemId": article_id, "reserveToUserId": recipient_user_id}
        resp = self.http.post("/reservations", json_body=body)
        if not isinstance(resp, dict):
            raise BadRequest("Unexpected reservation response.", payload=resp)
        return Reservation(reservationId=resp.get("reservationId", ""),
                           itemId=article_id, raw=resp)

    # ------------------------------------------------------------------ users

    def get_user(self, user_id: str) -> User:
        """Create a :class:`User` handle (no network call yet)."""
        return User(self, user_id)
