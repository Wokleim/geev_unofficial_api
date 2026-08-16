"""Synchronous client library for the Geev API.

Quick start:

    from geev import GeevClient

    geev = GeevClient()
    geev.login("you@example.com", "s3cret")   # Session stored on client

    user = geev.get_user("6a11e587ef4a89cd2c8ad9ac")
    items = user.articles()                   # raw article dicts
    article = geev.get_article(items[0]["id"])
    print(article.title, article.is_reservable)

See the README for the full reference.
"""

from .client import GeevClient
from .exceptions import (
    AuthenticationError,
    BadRequest,
    GeevError,
    ServerError,
    ValidationError,
)
from .models import (
    CarbonSummary,
    Message,
    Registration,
    Reservation,
    Review,
    Session,
)
from .articles import Article
from .conversations import Conversation
from .users import User

__all__ = [
    "GeevClient",
    "Article",
    "User",
    "Conversation",
    "Message",
    "Session",
    "Registration",
    "Reservation",
    "Review",
    "CarbonSummary",
    "GeevError",
    "BadRequest",
    "AuthenticationError",
    "ServerError",
    "ValidationError",
]

__version__ = "0.1.0"
