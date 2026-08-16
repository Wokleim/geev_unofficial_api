# Geev library — detailed API maps

Companion to the README: maps every library method back to its HTTP endpoint
and documents the raw payload shapes observed live, so future scripts can
consume fields the library does not wrap yet.

## Endpoint → method

| HTTP | Endpoint | Library method |
|------|----------|----------------|
| POST | `/v3/auth/email/check` | `GeevClient.check_email` |
| POST | `/v3/accounts/local` (multipart) | `GeevClient.signup` |
| POST | `/v3/accounts/{accountId}/resend-validation` | `GeevClient.resend_validation` |
| POST | `/v3/accounts/{accountId}/validate` | `GeevClient.validate_account` |
| POST | `/v3/auth/local/login` | `GeevClient.login` |
| POST | `/v3/auth/logout` | `GeevClient.logout` |
| POST | `/v3/search/items` | `GeevClient.search_articles` |
| GET | `/v3/items/{articleId}` | `GeevClient.get_article`, `Article.details` |
| POST | `/v3/reservations` | `GeevClient.reserve_article`, `Article.reserve` |
| GET | `/v3/items/{id}/related` | `Article.related` |
| GET | `/v3/users/{userId}` | `User.profile` |
| GET | `/v3/users/{userId}/items` | `User.articles`, `User.iter_articles` |
| GET | `/v3/users/{userId}/reviews` | `User.reviews` |
| GET | `/v3/users/{id}/carbonSummary` | `User.carbon_summary` |
| POST | `/v3/items/{articleId}/contact` | `GeevClient.contact_article`, `Article.contact` |
| POST | `/v3/adoptions` | `GeevClient.request_adoption`, `Article.request_adoption` |
| GET | `/v3/self/conversations` | `GeevClient.list_conversations`, `Conversation.list_open` |
| GET | `/v3/conversations/{conversationId}` | `GeevClient.get_conversation`, `Conversation.fetch` |
| POST | `/v3/conversations/{conversationId}/message` | `Conversation.send_message` |

## Request bodies the library sends

Only bodies with a payload are HMAC-signed (`body ‖ timestamp_ms`).

### Sign-up multipart fields

`POST /v3/accounts/local` — multipart/form-data, each part `text/plain`
unless noted:

| Part name | Value |
|-----------|-------|
| `firstName` | string |
| `lastName` | string |
| `email` | string |
| `password` | string |
| `marketingAndPixelConsentGranted` | `"true"` / `"false"` |
| `optedOut` | `"true"` / `"false"` |
| `pixelConsentGranted` | `"true"` / `"false"` |
| `picture` *(optional)* | image bytes, `Content-Type: image/jpg`, filename `<uuid>.jpg` |

### Validate / login / logout

| Method | Endpoint | Body |
|--------|----------|------|
| validate | `POST /accounts/{accountId}/validate` | `{"code": "123456"}` |
| login | `POST /auth/local/login` | `{"login": email, "password": …}` |
| logout | `POST /auth/logout` | none |
| reserve | `POST /reservations` | `{"itemId": …, "reserveToUserId": …}` |
| contact | `POST /items/{articleId}/contact` | `{"message": "…"}` (+ `"confirm": true` to ack the 428 phone check) |
| adoption | `POST /adoptions` | `{"itemIds": […], "message": "…"}` |
| send message | `POST /conversations/{id}/message` | `{"message": "…"}` (reply: empty 200) |

`?dryRun=true` is accepted on `contact` and `adoptions` to probe without
creating state (a prior contact then answers 409).

### Search

`POST /v3/search/items`:

```json
{
  "mode": "standard",
  "placement": "top_categories",
  "filters": {
    "text": "chaise",
    "type": "donation",
    "states": ["AVAILABLE"],
    "categories": ["table"],
    "distance": 10,
    "latitude": 48.8566,
    "longitude": 2.3522
  },
  "pagination": {"limit": 20, "skip": 1}
}
```

Constraints observed live:
- `skip` must be ≥ 1 (`0` → 400).
- `placement` must be one of: `home_listing`, `top_categories`,
  `home_exclusivities`, `home_near_you`, `home_sales`,
  `my_formula_contact_advantages`, `not_found`, `explorer`,
  `favorites_carousel`. Only `top_categories` accepted a `text` filter in
  probes; other placements returned empty lists or 500 with text.
- `mode`: `standard` or `carrousel`.

## Observed response shapes (2026-08, v3)

### `GET /users/{userId}/items`

```json
{
  "data": [
    {
      "id": "…",
      "title": "…",
      "type": "donation",
      "status": "AVAILABLE",
      "category": "table",
      "universe": "object",
      "available": true,
      "savings": 20,
      "location": {"latitude": …, "longitude": …, "obfuscated": true, "radius": 100},
      "picture": "<picture-id>",
      "picturePaths": {"default": "https://…", "squares600": "…", …},
      "author": {"id": "<user-id>", "picture": "…", "picturePaths": {…}},
      "stats": {"views": 67, "favorites": 0},
      "_links": […]
    }
  ],
  "after": "<cursor-article-id>",
  "total": 283,
  "options": {"publicProfile": {"hideDonations": false}}
}
```

### `GET /items/{articleId}` (details)

```json
{
  "id": "…",
  "title": "…",
  "description": "…",
  "type": "donation",
  "state": "…",
  "status": "AVAILABLE",
  "creditCost": 0,
  "savings": 20,
  "carbonValue": 5.2,
  "pictures": {"default": "https://…", …},
  "availability": {…},
  "userAvailabilities": "…",
  "userAvailability": "…",
  "donator": { "id": "<user-id>", … },
  "location": {…},
  "stats": {…},
  "validatedAt": "…",
  "risenAt": "…",
  "categoryLvl1": "…",
  "categoryLvl2": "…",
  "metadata": {…},
  "viewerContext": {…},
  "_links": […]
}
```

### `GET /users/{userId}` (profile)

```json
{
  "id": "<user-id>",
  "firstName": "…",
  "lastName": "…",
  "picture": "<picture-id>",
  "language": "fr",
  "gender": "…",
  "reviewCount": 3,
  "reviewSum": 14,
  "isProfessional": false,
  "isPremium": false,
  "isInvestor": false,
  "isAmbassador": false,
  "reliabilityScore": 100,
  "joinedAt": "…"
}
```

### `GET /users/{userId}/reviews`

```json
{
  "data": [
    {"id": "…", "score": 5, "type": "…", "message": "…", "createdAt": "…", "reviewer": {…}}
  ],
  "after": "…",
  "total": 3,
  "rating": 4.7
}
```

### `GET /users/{id}/carbonSummary`

```json
{"carbonValue": 12.3, "adoptions": 2, "donations": 5, "equivalences": […]}
```

`temporality` query param ∈ `ever`, `thisYear`, `thisMonth` (enum `getValue()`).

### `POST /items/{articleId}/contact`

```json
{"conversationId": "<id>", "dryRun": false, "replayed": true}
```

Returns 200 even if a thread already exists — `replayed: true` then signals
the existing conversation was reused. `confirm: true` adds
`"confirm": true` to the body to satisfy the 428 precondition below.

### `POST /adoptions`

```json
{"adoptionId": "<id>", "conversationId": "<id>", "rejectedItemIds": [],
 "replayed": true}
```

`{"itemId": …}` instead of `{"itemIds": […]}` → 400, errorCode
`ValidationError`, message `"itemIds" is required`.

### `GET /self/conversations` (item summaries)

Without filters (one entry per item you have a thread on):

```json
[
  {
    "_id": "<user-id>",
    "latest_conversation_id": "<conversation-id>",
    "unread_message_count": 0,
    "status": "CONTACTED",
    "item": {"id": "<article-id>", "pictures": {"default": "…"}, "author": {…}},
    "_links": []
  }
]
```

With `?itemId=<article-id>` (also the vendor perspective) the shape changes:
each entry is the *item* summary with a nested array of every conversation on
it:

```json
[
  {
    "_id": "<article-id>",
    "id": "<article-id>",
    "item_id": "<article-id>",
    "title": "…",
    "picture": "<picture-id>",
    "type": "donation",
    "reserved": false,
    "given": false,
    "acquired": false,
    "closed": false,
    "selected_recipient": null,
    "author": {"_id": "<donator-id>", …},
    "status": "…",
    "conversations": [
      {"_id": "<conversation-id>", "respondent": {…}, "created_on": …,
       "last_activity_timestamp": …, "active": true, "closed": false,
       "closed_by_respondent": false, "closed_by_author": false,
       "suggested": false, …}
    ]
  }
]
```

`GeevClient.list_conversations` returns whichever raw shape the server sends;
use `latest_conversation_id` for the flat list and
`entry["conversations"][0]["_id"]` for the item-filtered one.

### `GET /conversations/{conversationId}`

Messages are newest-first; the first element carries the item snapshot too:

```json
{
  "id": "<conversation-id>",
  "item": {"id": "<article-id>", "donator": {…}},
  "status": "CONTACTED",
  "messages": [
    {"_id": "…", "authorId": "<sender>", "sentTimestamp": 1755…,
     "status": "validated", "message": "Bonjour…", "readByReceiver": true,
     "messageType": "user"}
  ]
}
```

Error handling observed live on `contact`:
- **409** `CannotContactItemMultipleTimesError` after a thread already exists:
  `The item … has already been contacted by adopter …` (payload `data` still
  carries `adoptionId` + `conversationId`).
- **428** `PhoneNumberWarningRequestAConfirmation`: `The adopter … needs to
  confirm the contact for item … as they have 2 conversations without
  verified phone number.` — `_links[]` advertises `rel = confirmContact`
  (schema `{"confirm": true}`) and `startPhoneNumberVerification`.
- **415** if the contact body is posted as `multipart/form-data` instead of
  JSON.

## Article status enum

`ArticleStatus`: `PENDING`, `EXTRA_APPROVAL`, `VALIDATED`, `AVAILABLE`,
`RESERVED`, `GIVEN`, `ACQUIRED`, `CLOSED`.

## Notes

- Auth is **in-memory only**: tokens never persist to disk (explicit design
  choice — no session file).
- The library does not implement article *creation* (donating/selling posts)
  or Octopus gRPC — those are out of scope for the MVP but the documented
  endpoints exist in `/tmp/decoded/GEEV_API.md`.
- `a.raw` / `page.raw` hold the untouched server JSON for forward
  compatibility with new server fields.