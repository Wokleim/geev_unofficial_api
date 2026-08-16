# python-geev-class

A **synchronous** Python client library for the Geev API (`https://prod.geev.fr`).
It reproduces exactly what the Geev Android app (v8.6.2) sends on the wire -
headers, HMAC request signing and multipart bodies - so it works against the
live service without scraping the website.

The library is object-oriented: `GeevClient` is the entry point, and the
network-accessing entities are `User` and `Article`. **Nothing is fetched at
object construction** - every method performs its own HTTP request only when
you call it.

```python
from geev import GeevClient

geev = GeevClient()
geev.login("you@example.com", "s3cret")          # returns Session, stored on client

# A User handle (no network call yet) …
user = geev.get_user("618287b1fafd81627a9ad69d")
profile = user.profile()                          # GET /v3/users/{id}  (lazy)
page    = user.articles(operation="donations")    # GET /v3/users/{id}/items

# … and Articles
article = geev.get_article(page.items[0]["id"])
print(article.title, article.is_reservable)
article.details()                                 # GET /v3/items/{id}  (lazy)
```

## Table of contents

1. [Install](#1-install)
2. [Quick examples](#2-quick-examples)
3. [API reference](#3-api-reference)
   - [GeevClient](#31-geevclient)
   - [User](#32-user)
   - [Article](#33-article)
   - [Auth flow](#34-auth-flow--signup-signin-logout)
4. [Models](#4-models)
5. [Errors](#5-errors)
6. [How it matches the app](#6-how-it-matches-the-app)
7. [Testing](#7-testing)
8. [Project layout](#8-project-layout)

---

## 1. Install

```bash
cd /tmp/python_geev_class
pip install -e .
# optional, for tests
pip install -e ".[tests]"
```

Requires Python ≥ 3.11 and `requests`.

---

## 2. Quick examples

### Sign in and explore a user's donations

```python
from geev import GeevClient

geev = GeevClient()                                        # prod API by default
session = geev.login("jane@example.com", "s3cret")

user = geev.get_user("618287b1fafd81627a9ad69d")
page = user.articles(operation="donations", limit=10)
print(len(page.items), "articles; next cursor:", page.next_after)

for raw in page.items:
    print(raw["id"], raw["title"], raw.get("status"))
```

### Search offers

```python
geev = GeevClient()
geev.login(email, password)

results = geev.search_articles(text="chaise", limit=20)   # placement defaults to top_categories
for article in results:
    print(article.id, article.title, article.city, article.is_reservable)
```

### Reserve / order an article

While the API has a reservation endpoint, ordering another user's item is a
**destructive side effect** on the platform - use with care and only with
accounts you control:

```python
session = geev.login(email, password)
article = geev.get_article(ARTICLE_ID)
reservation = article.reserve()               # recipient = logged-in user
print(reservation.reservationId)
```

### Lazy user methods

```python
user = geev.get_user("618287b1fafd81627a9ad69d")
user.profile()          # first call does the network round-trip
user.articles()         # …
user.carbon_summary()   # … on demand, not at construction
```

---

## 3. API reference

### 3.1 `GeevClient`

`geev.GeevClient(base_url=None, language="fr", token=None, session=None)`

| Arg | Default | Meaning |
|-----|---------|---------|
| `base_url` | `https://prod.geev.fr/v3` | also `https://dev.geev.fr/v3`, `https://stage.geev.fr/v3` |
| `language` | `"fr"` | value of the `language` header on every call |
| `token` | `None` | skip login if you already have an `appToken` |
| `session` | `None` | a pre-built `Session` (userId + token) |

The client stores the current token on `.token` and the full session on
`.session`, and passes the token to every authenticated request.

**Auth**

| Method | Endpoint | Notes |
|--------|----------|-------|
| `check_email(email) -> bool` | `POST /auth/email/check` | True if available |
| `signup(first_name, last_name, email, password, marketing_consent=False, opted_out=False, pixel_consent=False, picture_path=None) -> Registration` | `POST /accounts/local` (multipart) | returns `accountId`/`userId`; account not yet active |
| `resend_validation(account_id)` | `POST /accounts/{accountId}/resend-validation` | - |
| `validate_account(account_id, code) -> Session` | `POST /accounts/{accountId}/validate` | activates account, stores token |
| `login(email, password) -> Session` | `POST /auth/local/login` | stores token |
| `logout()` | `POST /auth/logout` | **destructive**: invalidates the token |

`signup` returns a `Registration`; you then validate with the 6-digit code
emailed by Geev:

```python
reg = geev.signup(first_name="Jane", last_name="Doe",
                  email="jane@example.com", password="S3cret!")
geev.validate_account(reg.accountId, "123456")      # code from the email
```

**Articles**

| Method | Endpoint | Notes |
|--------|----------|-------|
| `search_articles(text=None, article_type=None, states=None, categories=None, distance=None, latitude=None, longitude=None, placement="top_categories", mode="standard", limit=20, skip=1) -> List[Article]` | `POST /search/items` | `skip` is 1-based (0 is rejected); `placement` is one of the server's accepted values, see below |
| `get_article(article_id) -> Article` | `GET /items/{articleId}` | wraps the payload |
| `reserve_article(article_id, recipient_user_id=None) -> Reservation` | `POST /reservations` | defaults the recipient to the logged-in user |

`placement` values accepted by the server: `home_listing`, `top_categories`,
`home_exclusivities`, `home_near_you`, `home_sales`,
`my_formula_contact_advantages`, `not_found`, `explorer`,
`favorites_carousel`. `top_categories` supports keyword `text` filters.

**Messaging / contact the vendor**

| Method | Endpoint | Notes |
|--------|----------|-------|
| `get_conversation(conversation_id) -> Conversation` | `GET /conversations/{conversationId}` | fetch thread + history |
| `contact_article(article_id, message, dry_run=False, confirm=False) -> Conversation` | `POST /items/{articleId}/contact` | starts/reuses the chat with the author |
| `request_adoption(article_id, message, dry_run=False) -> dict` | `POST /adoptions` | `{itemIds, message}` - expresses intent, does **not** reserve |
| `list_conversations(item_id=None, with_archived=False) -> list` | `GET /self/conversations` | one article summary per thread |

**Users**

| Method | Endpoint | Notes |
|--------|----------|-------|
| `get_user(user_id) -> User` | – | no network call |

### 3.2 `User`

`geev.users.User` is created via `client.get_user(user_id)` and fetches on
demand. All listing/profile calls require the client to be logged in.

| Method | Endpoint | Return |
|--------|----------|--------|
| `profile()` | `GET /v3/users/{userId}` | raw dict (`firstName`, `lastName`, `firstIntention`, `_links`, …) |
| `first_name`, `last_name` (properties) | – | called `profile()` lazily |
| `articles(operation="donations", status=None, after=None, limit=50) -> Page` | `GET /v3/users/{userId}/items` | `Page{items, next_after, raw}` |
| `iter_articles(operation="donations", status=None, page_size=50) -> Iterator[dict]` | same, cursor-following | yields every item across pages |
| `reviews(type=None, after=None, limit=20) -> List[Review]` | `GET /v3/users/{userId}/reviews` | - |
| `carbon_summary(temporality=None, light=False) -> CarbonSummary` | `GET /v3/users/{id}/carbonSummary` | `temporality` ∈ `ever`, `thisYear`, `thisMonth` |

`operation` is **required** by the server: `donations` or `requests`. For
`donations`, pass `status=["AVAILABLE"]` to see only what can be ordered
today; the app's default is `["AVAILABLE","RESERVED","GIVEN","ACQUIRED"]`.
The response exposes a cursor in `Page.next_after` (an article id) for the
next page.

### 3.3 `Article`

`geev.articles.Article` wraps a listing/search payload. Convenience read-only
properties (`id`, `title`, `description`, `type`, `state`, `status`,
`category`, `universe`, `picture`, `pictures`, `city`, `author_id`,
`author_name`, `carbon_value`, `savings`, `price`, `stock`, `validated`,
`is_reservable`) never hit the network - they read the payload that created
the object.

| Method | Endpoint | Return |
|--------|----------|--------|
| `details()` | `GET /v3/items/{articleId}` | raw dict with `description`, `status`, `creditCost`, `donator`, `pictures` |
| `reserve(recipient_user_id=None) -> Reservation` | `POST /v3/reservations` | **destructive**; defaults to logged-in user |
| `related() -> List[Article]` | `GET /v3/items/{id}/related` | similar articles |
| `contact(message, dry_run=False, confirm=False) -> Conversation` | `POST /v3/items/{id}/contact` | message the vendor; thread is fetched |
| `request_adoption(message, dry_run=False) -> dict` | `POST /v3/adoptions` | `{itemIds, message}`; intent, no reserve |

Example - start a conversation with the vendor of an article:

```python
article = geev.get_article(ARTICLE_ID)
conversation = article.contact("Bonjour, c'est encore disponible ?")
print(conversation.status)           # e.g. CONTACTED
send = conversation.send_message("Parfait, merci !")
```

If the account has several conversations without a verified phone number, the
server answers `428` and the payload advertises a `confirmContact` link -
retry with `**contact(..., confirm=True)**`.

### 3.4 `Conversation`

`geev.conversations.Conversation` wraps a messaging thread. Created via
`client.get_conversation(id)`, `article.contact(...)`, or implicitly by
`client.contact_article(...)`; details are fetched once (populating `.raw`,
`.item_id`, `.status` and `.messages`).

| Field / method | Meaning |
|----------------|---------|
| `conversation_id` | thread id |
| `item_id`, `status`, `messages` | fetched fields (after `fetch()`) |
| `fetch() -> Conversation` | `GET /v3/conversations/{id}` |
| `send_message(text) -> Message` | `POST /v3/conversations/{id}/message` |
| `list_open(client, item_id=None, with_archived=False) -> list` | `GET /v3/self/conversations` |

### 3.5 Auth flow - signup, signin, logout

The sign-up flow mirrors the app:

1. `check_email(email)` - optional pre-check.
2. `signup(...)` - multipart `POST /accounts/local`, returns `Registration`.
3. `validate_account(account_id, code)` - `POST /accounts/{accountId}/validate`;
   the response carries the `appToken` = `X-Geev-Token` used afterwards.
4. `login(email, password)` - `POST /auth/local/login`, same token mechanism.
5. `logout()` - `POST /auth/logout`; invalidates the current token
   (subsequent requests will 401).

There is **no persistence** in the library: tokens live only in memory on the
client object. To reuse a session across runs, capture `session.appToken` and
`session.userId` yourself and build a new client with
`GeevClient(token=..., session=...)`.

> There is **no user-lookup-by-name** endpoint in the Geev API. Users are
> identified solely by their `userId` (the last path segment of a profile URL
> like `https://www.geev.fr/profile/<id>`).

---

## 4. Models

| Class | Fields |
|-------|--------|
| `Session` | `appToken`, `userId`, `sso`, `userType` |
| `Registration` | `accountId`, `userId` |
| `Reservation` | `reservationId`, `itemId`, `raw` |
| `Page` | `items`, `next_after`, `raw` |
| `Review` | `id`, `grade`, `message`, `raw` |
| `CarbonSummary` | `year`, `month`, `carbonValue`, `donations`, `adoptions`, `equivalences`, `raw` |
| `Location` | `label`, `city`, `postalCode`, `latitude`, `longitude`, `radius`, `obfuscated` |
| `Message` | `id`, `author_id`, `timestamp`, `text`, `read_by_receiver`, `raw` |
| `Conversation` | handle class; see §3.4 |

Every model also carries the raw server payload in `.raw` so you can access
fields the library does not wrap yet.

---

## 5. Errors

All exceptions derive from `geev.exceptions.GeevError`.

| Exception | Raised when |
|-----------|-------------|
| `BadRequest` | HTTP 4xx, or a malformed/unexpected body |
| `ServerError` | HTTP 5xx |
| `AuthenticationError` | HTTP 401/403, incl. wrong validation code |
| `ValidationError` | client-side argument validation |

`BadRequest` and its subclasses expose `.status_code`, `.payload`, `.method`
and `.url`.

```python
from geev import GeevClient, AuthenticationError

try:
    geev.login("jane@example.com", "wrong-password")
except AuthenticationError as e:
    print(e)                      # includes HTTP status and payload
```

---

## 6. How it matches the app

The library reproduces the exact wire behaviour of Geev 8.6.2:

- **Global headers** on every request: `User-Agent`,
  `x-geev-device-model`, `geev-app-version`, `geev-device`, `timezone`,
  plus per-call `language`, `X-Geev-Token` (when logged in), `Content-type`
  and `Accept`.
- **Request signing** (`x-geev-timestamp` + `x-geev-request-signature`):
  HMAC-SHA256 over `body_bytes || timestamp_ms` with the key extracted from
  the app's `SignatureInterceptor`. Only present when the request has a body.
  In this library the body is serialized *before* signing, so the signed
  bytes are exactly the bytes on the wire.
- **Multipart** sign-up body is built manually (OkHttp byte-for-byte
  compatible) so signing stays exact.

Reverse-engineered from the decompiled APK; the endpoint reference doc is
`/tmp/decoded/GEEV_API.md`.

---

## 7. Testing

The test suite runs against the **live** production API (`prod.geev.fr`). It
is marked `live`; destructive operations (reserve, logout) are **not**
executed automatically.

```bash
cd /tmp/python_geev_class
pytest tests/test_live.py -m live -v
```

Defaults for the provided test account are embedded in `tests/conftest.py`;
override with environment variables:

| Variable | Default |
|----------|---------|
| `GEEV_TEST_TOKEN` | the provided `appToken` |
| `GEEV_TEST_USER` | `6a11e587ef4a89cd2c8ad9ac` |
| `GEEV_TARGET_USER` | `618287b1fafd81627a9ad69d` |

---

## 8. Project layout

```
python_geev_class/
├── pyproject.toml
├── README.md                  # this document
├── geev/
│   ├── __init__.py            # public exports
│   ├── _http.py               # headers, signing, multipart, transport
│   ├── exceptions.py          # error types
│   ├── models.py              # value objects (Session, Page, …)
│   ├── auth.py                # signup / signin / logout / validate
│   ├── users.py               # User class + user operations
│   ├── articles.py            # Article class + search / reserve
│   └── client.py              # GeevClient facade
└── tests/
    ├── conftest.py            # fixtures (live API credentials)
    └── test_live.py           # live API tests
```
