"""Live tests against the real prod.geev.fr API.

These make real HTTP requests and are useful for validating that the library
still matches the server contract. Run with:

    pytest tests/test_live.py -m live

Destructive actions (reservation, logout) are NOT exercised here by default:
set the flags below to enable them.
"""

from __future__ import annotations

import pytest

from geev import GeevClient, AdoptionConfirmed, ConversationSummary

pytestmark = pytest.mark.live


class TestClientSetup:
    def test_client_default_base_url(self):
        c = GeevClient()
        assert c.http.config.base_url == "https://prod.geev.fr/v3"

    def test_client_custom_base_url(self):
        c = GeevClient(base_url="https://dev.geev.fr/v3")
        assert c.http.config.base_url == "https://dev.geev.fr/v3"

    def test_token_injected_via_constructor(self):
        c = GeevClient(token="abc")
        assert c.token == "abc"
        assert c.http._token() == "abc"


class TestUserInfo:
    def test_user_profile_has_expected_fields(self, client, target_user):
        user = client.get_user(target_user)
        profile = user.profile()
        assert isinstance(profile, dict)
        assert "firstName" in profile or "lastName" in profile or "_links" in profile

    def test_user_first_last_name(self, client, target_user):
        user = client.get_user(target_user)
        first = user.first_name
        last = user.last_name
        assert isinstance(first, str) or first is None
        assert isinstance(last, str) or last is None

    def test_user_articles_list(self, client, target_user):
        user = client.get_user(target_user)
        page = user.articles(operation="donations", limit=5)
        assert isinstance(page.items, list)
        for it in page.items:
            assert isinstance(it, dict)

    def test_user_articles_requires_operation(self, client, target_user):
        # The API rejects omitting `operation` (we saw the 400 during reverse
        # engineering). The library always sends it, so this must succeed.
        user = client.get_user(target_user)
        page = user.articles(operation="donations", limit=1)
        assert isinstance(page.items, list)

    def test_user_articles_offers_available_items(self, client, target_user):
        user = client.get_user(target_user)
        page = user.articles(operation="donations",
                             status=["AVAILABLE"], limit=3)
        assert isinstance(page.items, list)

    def test_user_carbon_summary(self, client, target_user):
        user = client.get_user(target_user)
        summary = user.carbon_summary()
        # The payload shape varies; only require it not to blow up.
        assert summary.raw is not None

    def test_user_reviews(self, client, target_user):
        user = client.get_user(target_user)
        reviews = user.reviews()
        assert isinstance(reviews, list)

    def test_user_reviews_type_enum(self, client, target_user):
        # The server accepts only ADOPTION / DONATION here.
        user = client.get_user(target_user)
        for review_type in ("ADOPTION", "DONATION"):
            reviews = user.reviews(type=review_type)
            assert isinstance(reviews, list)


class TestArticleInfo:
    def test_get_article_wraps_payload(self, client, target_user):
        user = client.get_user(target_user)
        page = user.articles(operation="donations", limit=1)
        assert page.items
        article = client.get_article(page.items[0]["id"])
        assert article.id == page.items[0]["id"]
        assert article.raw

    def test_article_properties(self, client, target_user):
        user = client.get_user(target_user)
        page = user.articles(operation="donations", limit=1)
        if not page.items:
            pytest.skip("no articles to inspect")
        a = client.get_article(page.items[0]["id"])
        assert a.id
        # These are harmless attribute reads
        a.title
        a.type
        a.status
        a.picture
        a.author_id

    def test_article_details_fetch(self, client, target_user):
        user = client.get_user(target_user)
        page = user.articles(operation="donations", limit=1)
        if not page.items:
            pytest.skip("no articles to inspect")
        a = client.get_article(page.items[0]["id"])
        details = a.details()
        assert isinstance(details, dict)


class TestMessaging:
    """Contact-the-vendor + conversation operations (creates a thread).

    These use the dediated test article so the account does not trip the
    428 phone-verification threshold while poking random articles.
    """

    TEST_ARTICLE_ID = "6a81e3123df5d3f7becda15f"

    def test_contact_article_creates_conversation(self, client):
        article = client.get_article(self.TEST_ARTICLE_ID)
        conversation = article.contact(
            "Bonjour, ceci est un test automatique, merci de l'ignorer.",
            confirm=True)
        assert conversation.conversation_id
        assert conversation.status
        assert conversation.item_id == article.id

    def test_conversation_send_message(self, client):
        article = client.get_article(self.TEST_ARTICLE_ID)
        conversation = article.contact("Test sending a message from the library.",
                                       confirm=True)
        sent = conversation.send_message("Second message from the library.")
        assert sent.text

    def test_list_and_fetch_conversation(self, client):
        conversations = client.list_conversations()
        assert isinstance(conversations, list)
        if not conversations:
            pytest.skip("no conversations on this account")
        first = conversations[0]
        cid = first.get("latest_conversation_id") or first.get("conversationId") \
            or first.get("_id")
        assert cid
        conversation = client.get_conversation(cid)
        assert conversation.conversation_id == cid

    def test_request_adoption_validates(self, client):
        article = client.get_article(self.TEST_ARTICLE_ID)
        result = client.request_adoption(
            article.id, "Test adoption request from the library.")
        assert isinstance(result, dict)
        assert "adoptionId" in result or "conversationId" in result


class TestSelfAndOrders:
    """Self profile, inbox, reserved collections and delivery confirmation."""

    def test_get_me(self, client):
        me = client.get_me()
        assert me.user_id
        assert me.user_id == client.session.userId
        profile = me.profile()
        assert isinstance(profile, dict)

    def test_get_inbox(self, client):
        inbox = client.get_inbox()
        assert isinstance(inbox, list)
        for summary in inbox:
            assert isinstance(summary, ConversationSummary)
            assert summary.conversation_id

    def test_get_reserved_collections(self, client):
        reserved = client.get_reserved_collections()
        assert isinstance(reserved, list)
        for summary in reserved:
            assert summary.reserved is True

    def test_confirm_adoption_when_deliverable(self, client):
        """Confirm delivery of a reserved deal left in the GIVEN state.

        The deal is closed once confirmed; when the account has already
        confirmed (or never reached the given state), skip instead.
        """
        deal = next((s for s in client.get_reserved_collections()
                     if s.given and not s.acquired), None)
        if not deal:
            pytest.skip("no reserved deal awaiting delivery confirmation")
        conversation = client.get_conversation(deal.conversation_id)
        assert conversation.reservation_id
        result = client.confirm_adoption(
            conversation.reservation_id,
            communication_grade=5.0,
            punctuality_grade=5.0,
            feedback="Test de confirmation depuis la librairie.",
        )
        assert isinstance(result, AdoptionConfirmed)
        assert "savings" in result.raw or "carbonValue" in result.raw

    def test_confirm_order_requires_session(self, client):
        from geev.exceptions import BadRequest
        anonymous = GeevClient()
        with pytest.raises(BadRequest):
            anonymous.confirm_order("6a81e3123df5d3f7becda15f")


class TestSearch:
    def test_search_text(self, client):
        articles = client.search_articles(text="table", placement="top_categories")
        assert isinstance(articles, list)

    def test_search_no_text(self, client):
        articles = client.search_articles(limit=3)
        assert isinstance(articles, list)

    def test_search_type_and_geo(self, client):
        articles = client.search_articles(text="chaise", article_type="donation",
                                          limit=3)
        assert isinstance(articles, list)

    def test_search_states(self, client):
        # states must use the GeevObjectState values (lowercase `value`).
        for state in ("good", "like_new", "worn", "broken"):
            articles = client.search_articles(states=[state], limit=3)
            assert isinstance(articles, list)


class TestLiveDestructiveSkippedByDefault:
    def test_reservation_and_logout_are_exposed(self, client):
        # Ordering/logout are implemented but intentionally not exercised
        # automatically (they mutate state on prod).
        from geev.client import GeevClient
        assert callable(GeevClient.reserve_article)
        assert callable(GeevClient.logout)
