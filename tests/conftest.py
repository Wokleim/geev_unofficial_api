"""Shared fixtures for the live API tests.

Credentials come from environment variables, defaulting to the provided test
account:

    GEEV_TEST_TOKEN   appToken of a logged-in account
    GEEV_TEST_USER    the account's own userId
    GEEV_TARGET_USER  another (existing) user who has posted articles
"""

from __future__ import annotations

import os

import pytest

from geev import GeevClient

TOKEN = os.environ.get("GEEV_TEST_TOKEN", "YOUR-TOKEN-HERE")
ACCOUNT_USER = "6a81e587e99a89cd2cbad9ac"
TARGET_USER = "6f7fa696171a56d34aa10da0"


def env_or(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


@pytest.fixture(scope="session")
def account_user() -> str:
    return env_or("GEEV_TEST_USER", ACCOUNT_USER)


@pytest.fixture(scope="session")
def target_user() -> str:
    return env_or("GEEV_TARGET_USER", TARGET_USER)


@pytest.fixture(scope="session")
def test_token() -> str:
    return env_or("GEEV_TEST_TOKEN", DEFAULT_TOKEN)


@pytest.fixture(scope="session")
def client(test_token: str) -> GeevClient:
    """A client authenticated with the provided token."""
    c = GeevClient(token=test_token)
    c.session = __import__("geev").Session(appToken=test_token,
                                           userId=ACCOUNT_USER)
    return c


@pytest.fixture(scope="session")
def authless_client() -> GeevClient:
    """A client with no token (for authless endpoints)."""
    return GeevClient()


@pytest.fixture(scope="session")
def sample_article(client, target_user):
    """Grab the first article id of the target user (read-only)."""
    user = client.get_user(target_user)
    page = user.articles(limit=1, operation="donations")
    assert page.items, "target user has no listed donations"
    return page.items[0]
