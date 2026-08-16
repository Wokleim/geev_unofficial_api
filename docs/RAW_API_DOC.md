# Geev API — Unofficial HTTP API documentation

Reverse-engineered from the Android application **Geev `8.6.2`** (`fr.geev.application`, build `6003`, production variant, R8-obfuscated).
App package: `fr.geev.application`. App gRPC/experimentation traffic (Octopus) is out of scope; everything below is plain HTTPS/REST (Retrofit + Gson).

The goal of this document is to be **self-contained**: a script or website can implement the whole client from it.

This document have been produced by DeepSeek-V4-Flash, some informations may to be incorrect.

---

## 1. Base URLs

The app ships 3 environments, selected at build time. Production is the default.

| Env | Root |
|-----|------|
| Development | `https://dev.geev.fr/` |
| Staging | `https://stage.geev.fr/` |
| Production (default) | `https://prod.geev.fr/` |

The API is split into 5 Retrofit services sharing the same `OkHttpClient` (=> same global headers) and the same `Gson`:

| Service | Base (relative to root) | Full production example | Endpoints |
|---------|------------------------|-------------------------|-----------|
| v1 (`ApiService`) | `v1/api/v0.19/` | `https://prod.geev.fr/v1/api/v0.19/…` | 50 |
| v2 (`ApiV2Service`) | `v2/` | `https://prod.geev.fr/v2/…` | 26 |
| v3 (`ApiV3Service`) | `v3/` | `https://prod.geev.fr/v3/…` | 94 |
| GAS (`ApiGasService`) | `gas/` | `https://prod.geev.fr/gas/…` | 4 |
| Partner (`ApiPartnerService`) | `v3/` (reuses the v3 base) | `https://prod.geev.fr/v3/…` | 2 |

Endpoint paths below are given **without** the base prefix. Replace `{…}` placeholders and always URL-encode values.

---

## 2. Global request headers (sent on EVERY call)

These are injected by OkHttp interceptors and are not listed per endpoint. A compliant client should reproduce them.

| Header | Value | Notes |
|--------|-------|-------|
| `User-Agent` | `Geev/8.6.2 (fr.geev.application; build:6003; Android SDK <api_level>) Okhttp/<okhttp_version> <manufacturer> <model>` | e.g. `... Okhttp/4.12.0 sdk google_panther` |
| `x-geev-device-model` | `<manufacturer> <model>` | e.g. `sdk google_panther` |
| `geev-app-version` | `8.6.2` | |
| `geev-device` | `Android` | |
| `timezone` | `ZoneId.systemDefault()` IANA name | e.g. `Europe/Paris` |
| `x-geev-location` | `<latitude>,<longitude>` | only if user location is saved |
| `x-geev-real-location` | `<latitude>,<longitude>` | only if real GPS location is available |
| `X-Geev-Referer` | current screen name (`Amplitude` event page) | only if non-empty |
| `X-GEEV-PARTNER-EMPLOYEE-ID` | OIDC client identifier | SSO-employee flow |
| `x-geev-timestamp` | epoch milli (string) | **only when the request has a body** |
| `x-geev-request-signature` | hex HMAC-SHA256 | **only when the request has a body** |

### 2.1 Request signing

Only for requests **with a non-empty body**:

```
timestamp = String.valueOf(System.currentTimeMillis())   // x-geev-timestamp
mac  = HMAC_SHA256(key, message)
key     = UTF-8 bytes of "d24dd4009e5429b9997984ecc03b38aa19bdd30dc70df4b2272fd6d47e620585"
message = raw request body bytes  ||  UTF-8 bytes of timestamp   (body first, then timestamp)
x-geev-request-signature = lower-case hex(mac)
```

### 2.2 Per-request headers (declared on the endpoints)

- `language` (header, e.g. `fr`, `en`) — most endpoints; part of client locale.
- `X-Geev-Token` — the user auth token (returned by `/v3/auth/local/login` as `appToken`). Nullable on public endpoints (login, sign-up, password reset, geocode, categories, alive…).
- `Content-type: application/json` and `Accept: application/json` — class-level on nearly every v1/v2/v3/gas/partner method. Endpoints that send **multipart** do NOT send these (only `language` + `X-Geev-Token`).
- `x-geev-idfa`,`x-geev-consent-string` — only on `GET /v1/api/v0.19/user/self/light`.

### 2.3 Response-side interceptor behaviour (client only)

- 2xx responses with an **empty body** are rewritten client-side to `{}` with status 200 (`NoContentInterceptor`, code 204/205 treated as empty).
- A `401` triggers local logout (`UserAuthenticationInterceptor`) — no retry.
- Non-2xx JSON error bodies carry an `errorCode` field; sign-up validation failures include it (server-side client handling).

---

## 3. Authentication flow (v3)

1. `GET /v3/auth/…` public; obtain account:
   - `POST /v3/accounts/local` **multipart sign-up** (fields: `firstName`, `lastName`, `email`, `password`, `marketingAndPixelConsentGranted`, `optedOut`, `pixelConsentGranted` — all `text/plain` parts; plus one `picture` image part, `image/jpg`) → `SignUpRemote` `{accountId, userId}`.
   - `POST /v3/auth/email/check` body `SignUpEmailValidationRemote{email}` → validates email is free.
   - `POST /v3/accounts/{accountId}/validate` body `AccountValidationRemote{code}` → `AccountAuthenticatedRemote`.
   - `POST /v3/accounts/{accountId}/resend-validation` — resend code.
2. `POST /v3/auth/local/login` — body `LoginWithEmailRemote{login, password}` → `AccountAuthenticatedRemote`. **No `X-Geev-Token` required.**
3. `POST /v3/auth/logout` with `X-Geev-Token`.
4. Social sign-in: `POST /v3/auth/facebook/login`, `POST /v3/auth/google/login` (body `SignInWithProviderRemote`), `POST /v3/auth/apple/login` (**multipart**: provider `token` part + optional profile parts) → `AccountAuthenticatedRemote`.
5. Passwords: `POST /v3/accounts/request-password-reset` body `ForgottenPasswordRemote{email}`; `PATCH /v3/accounts/{accountId}/reset-password` body `ResetPasswordRemote{password, token}`.
6. SSO/OIDC is a separate client (not Retrofit): it posts to the `openidConfigurationUri`/`/token` endpoint obtained from the account's `sso` block, using `Authorization: Basic base64(clientId:clientSecret)` where `clientId`/`clientSecret` come from `AccountAuthenticatedRemote.sso`.
7. `X-Geev-Token` for all subsequent calls = `appToken` from `AccountAuthenticatedRemote`.

`AccountAuthenticatedRemote`:
```
appToken: string   // -> X-Geev-Token header
userId:   string
sso: {
  clientId: string, clientSecret: string,
  openidConfigurationUri: string, redirectUri: string
}
```

---

## 4. Endpoint reference

Legend:
- **R** return payload (JSON body of the DTO; `void` = empty/`{}` body).
- Headers shown only when they differ from `language` + `X-Geev-Token` (+ global headers).
- Multipart = `multipart/form-data`.

### 4.1 v3 API — `https://prod.geev.fr/v3/` (94 endpoints)

#### Auth & account
| Method | Path | Request | R |
|--------|------|---------|---|
| POST | `auth/local/login` | JSON `LoginWithEmailRemote{login,password}` | `AccountAuthenticatedRemote` |
| POST | `auth/logout` | – | void |
| POST | `auth/email/check` | `SignUpEmailValidationRemote{email}` | `SignUpEmailValidatedRemote` |
| POST | `auth/facebook/login` | `SignInWithProviderRemote{token, firstname, lastname, marketingAndPixelConsentGranted, optedOut, pixelConsentGranted}` | `AccountAuthenticatedRemote` |
| POST | `auth/google/login` | same | `AccountAuthenticatedRemote` |
| POST | `auth/apple/login` | multipart (token + optional profile + consent fields) | `AccountAuthenticatedRemote` |
| POST | `accounts/local` | multipart `firstName,lastName,email,password,marketingAndPixelConsentGranted,optedOut,pixelConsentGranted,picture` | `SignUpRemote{accountId,userId}` |
| POST | `accounts/{accountId}/validate` | `AccountValidationRemote{code}` | `AccountAuthenticatedRemote` |
| POST | `accounts/{accountId}/resend-validation` | – | void |
| POST | `accounts/request-password-reset` | `ForgottenPasswordRemote{email}` | void |
| PATCH | `accounts/{accountId}/reset-password` | `ResetPasswordRemote{password,token}` | void |
| PATCH | `sessions/start` | – (auth) | void |
| PATCH | `sessions/pause` | – (auth) | void |
| PATCH | `sessions/resume` | – (auth) | void |
| PATCH | `sessions/stop` | – (auth) | void |
| GET | `octopus/auth/sso` | – | `AccountSsoTokenRemote{token}` |
| GET | `users/me` | – | `UserDetailsRemote` |

#### Users, profile, blocking
| Method | Path | Request | R |
|--------|------|---------|---|
| GET | `users/{userId}` | – | `UserDetailsRemote` |
| GET | `users/{userId}/items` | Query: `after, operation, status, savings, sort[] (multi), limit` | `NewListArticlesRemote` |
| GET | `users/{userId}/reviews` | Query: `type, after, limit` | `ReviewsRemote` |
| PATCH | `users/me` | `UserDetailsRemote{firstName,lastName,firstIntention,_links[]}` | void |
| POST | `users/{userId}/optout-mail` | – (no token) | void |
| POST | `users/me/pixel-consent` | `PixelConsentRemote{campaignId,sendId,consentGranted}` | void |
| GET | `users/me/perks` | – | `UserPerksRemote` |
| GET | `users/me/savings` | – | `UserSavingsRemote` |
| GET | `users/me/subscription-benefits` | Query: `fromDate,toDate` | `List<UserBenefitsRemote>` |
| GET | `users/me/achievements/{achievementId}/rewards` | – | `AchievementRemote` |
| GET | `users/{id}/carbonSummary` | Query: `temporality, light` | `CarbonSummaryRemote` |
| GET | `blocking/user/{id}` | – | `UserBlockingStatusRemote` |
| POST | `users/{id}/block` | – | void |
| DELETE | `users/{id}/block` | – | void |
| POST | `blocking` | `BlockedItemsRemote{limit, next, users[]}` | `BlockedItemsRemote` |

#### Search & articles
| Method | Path | Request | R |
|--------|------|---------|---|
| GET | `items/{articleId}` | – | `ArticleDetailsRemote` |
| GET | `items/favorites` | – | `DynamicContentComponentResultRemote<List<NewArticleRemote>>` |
| POST | `items/searchMap` | `FetchMapArticlesRemote{filters{FetchGeoFiltersArticlesRemote}}` | `ListMapArticlesRemote` |
| GET | `items/{ad_id}/related` | – | `List<SalesRelatedArticleRemote>` |
| POST | `search/items` | `FetchArticlesRemote{mode,placement,filters{FetchFiltersArticlesRemote},pagination{limit,skip}}` | `NewCarouselArticlesRemote` |
| POST | `search/suggestions` | `SuggestedSearchesRequest{filters{SuggestedFiltersRequest}}` | `SuggestedSearchesRemote` |
| POST | `feature-flippings/sale` | `LocationRemote{location{LocationDataRemote}}` | `SaleFeatureFlagRemote` |
| PATCH | `items/{itemId}` | `RiseArticleRemote{action}` (rise) | void |
| GET | `pickup-points/search` | Query: `categoryLvl2, latitude, longitude, maxDistance` | `List<ArticlePickUpPointRemote>` |
| GET | `take-back-partners` | Query: `category` | `List<FetchTakeBackPartnersResponse>` |
| GET | `categories/carbonSummary` | Query: `temporality` | `CommunityCarbonValuesRemote` |
| GET | `locations/autocomplete` | Query: `search` | `List<ApiAddress>` |
| GET | `locations/reverse` | Query: `latitude, longitude` | `ApiAddress` |
| POST | `items/donation` | multipart: `title, description, category, latitude, longitude, userAvailability, itemState, isFood, isSeller, foodExpirationDate, {provider}.pickUpPointId, takeBackPartner` + `pictures[]` (files) | `ArticleCreatedRemote{id,validated}` |
| POST | `items/request` | multipart: `title, description, category, latitude, longitude, isFood` + `pictures[]` | `ArticleCreatedRemote` |
| POST | `items/sale` | multipart: `title, description, category, latitude, longitude, initialPrice, discountedPrice, eanCode, stock, reservable, productType, takeBackPartner` + `pictures[]` | `ArticleCreatedRemote` |
| POST | `items/geevshop-donation` | multipart: `title, category, description, itemState, eanCode` + `pictures[]` | `ArticleCreatedRemote` |
| POST | `draft-items` | multipart: `itemType, lvl2Category, withAi("true")` + `pictures[]` | `DynamicComponentLinksRemote` |

#### Reservations / sales / appointments
| Method | Path | Request | R |
|--------|------|---------|---|
| POST | `reservations` | `AddReservationRequest{itemId, reserveToUserId}` | `ReservationRemote{reservationId}` |
| POST | `reservations` | `ConfirmationOrderRemote{itemId, reserveToUserId, contactInfo{firstname,lastname}}` (confirm order) | `OrderConfirmedDataRemote` |
| DELETE | `reservations/{reservationId}` | – (cancel) | `DynamicComponentRemote` |
| GET | `reservations/{reservationId}/give` | – | `AdGivenDate` |
| PATCH | `reservations/{reservationId}/give` | – (pick up confirmed) | void |
| PATCH | `reservations/{reservationId}/give` | `ReviewRequest{communicationGrade, punctualityGrade, feedbackMessage}` (send review) | void |
| PATCH | `reservations/{reservationId}/confirm-adoption` | `ReviewNotationRemote{communicationGrade,punctualityGrade,feedbackMessage}` | `AdoptionConfirmedRemote` |
| PATCH | `reservations/{reservationId}/confirm-adoption` | `ReviewRequest{…}` (acknowledge reception) | void |
| PATCH | `reservations/{reservationId}/justify-cancellation` | `RemoveReservationReasonRequest{reason}` | void |
| POST | `reservations/{reservationId}/appointments` | `AppointmentDataRemote{date}` | `AppointmentRemote` |
| PATCH | `reservations/{reservationId}/appointments/{appointmentId}` | `AppointmentDataRemote{date}` | `AppointmentRemote` |
| PATCH | `reservations/{reservationId}/appointments/{appointmentId}/{action}` | – | void |

#### Messaging / chat
| Method | Path | Request | R |
|--------|------|---------|---|
| GET | `self/conversations` | Query: `itemId, withArchived` | `List<MessagingConversationSummaryListResponse>` |
| GET | `self/conversations` | Query: `withArchived` | `List<MessagingSummaryResponse>` |
| POST | `self/conversations/items/{articleId}/activate` | – | `List<MessagingConversationSummaryListResponse>` |
| GET | `conversations/{conversationId}` | – | `MessagingDetailsResponse` |
| DELETE | `conversations/{conversationId}` | – or body `CloseConversationReasonRequest{reason}` | void |
| POST | `conversations/{conversationId}/message` | `SentMessageRequest{message}` | void |
| GET | `self/messages/unread-count` | – | `UnreadCountResponse{count}` |
| GET | `self/notifications` | – | `NotificationValues{data[],total}` |
| GET | `self/notifications?count=true` | Query: `unread` | `UnreadCountResponse` |
| GET | `chat/quick-messages` | Query: `displayFor[]` | `QuickMessagesListingRemote` |
| POST | `chat/quick-messages` | `QuickMessageDataRemote{id,title,content,displayFor[]}` | `QuickMessageRemote` |
| PUT | `chat/quick-messages/{messageId}` | same | `QuickMessageRemote` |
| DELETE | `chat/quick-messages/{messageId}` | – | void |
| DELETE | `items/{articleId}/conversations` | – or body `CloseConversationReasonRequest{reason}` | void |

#### Preferences, subscription, misc
| Method | Path | Request | R |
|--------|------|---------|---|
| GET | `user-preferences` | – | `UserPreferencesRemote` |
| PATCH | `user-preferences` | `UserPreferencesRemote{aiItemCreationEnabled, pauseMode, availabilityTemplate}` | `UserPreferencesRemote` |
| GET | `credits-origins` | – | `CreditsPacksRemote` |
| GET | `plans` | – | `StorePlansRemote` |
| GET | `subscriptions` | – | `UserSubscriptionsRemote` |
| GET | `screens/{screen}` | – | `DynamicComponentsRemote` |
| GET | `support-links` | – | `UriSupportRemote` |
| GET | `shop/menu` | – | `UserGeevShopDataRemote` |
| GET | `complaints/reasons` | Query: `type` | `ComplaintReasonsDataRemote` |
| GET | `achievements/{achievementId}` | Query: `userId` | `AchievementRemote` |
| GET | `alerts` | – | `List<SavedSearchRemote>` |
| POST | `alerts` | `SavedSearchRemote{_id,userId,keywords,categories[],state[],type[],distance,location,activeNotifications}` | void |
| GET | `slot-machines` | – | `SlotMachineGameStatsRemote` |
| GET | `sponsorings` | – | `SponsorTokenRemote` / `SponsoringsRemote` |
| PUT | `users/me/sponsor` | `SponsorshipCodeRemote{sponsorshipToken}` | `SponsorshipCodeValidatedRemote` |
| POST | `promotional-codes` | `PromotionalCodeRemote{code, ply{}}` | `PromotionalCodeRemote` |
| GET | `cappings` | – | `UserCappingsRemote` |
| GET | `take-back-partners` | Query `category` | `List<FetchTakeBackPartnersResponse>` |

#### News/edito (GAS API) — `https://prod.geev.fr/gas/`
| Method | Path | Request | R |
|--------|------|---------|---|
| GET | `editos` | Query: `placement, longitude, latitude, distance` | `EditoRemote` |
| GET | `partners/campaign` | – (no token) | `PartnerCampaignRemote` / `PartnershipsCampaignResponse{_id,title,body,ctaLabel,picture,type,isEmpty}` |
| GET | `partners` | – (no token) | `PartnersRemote` |

#### Partner API — `https://prod.geev.fr/v3/`
| Method | Path | Request | R |
|--------|------|---------|---|
| GET | `partners/{name}` | – | `PartnerDataRemote` |
| POST | `partners/{name}/users` | `PartnerSourceRemote{source, userId}` | void |
Note: `PartnerSourceRemote` carries an additional `redirectionLink` value used for the OAuth callback.

---

### 4.2 v2 API — `https://prod.geev.fr/v2/` (26 endpoints)

| Method | Path | Request | R |
|--------|------|---------|---|
| GET | `categories` | – | `AdCategoryParent` |
| POST | `search/items/geo` | body `AdListRequest`; Query variant A: `after,limit`; variant B (food/sales): `component, after, limit`; getAdsList: Query `after,limit` | `GeevAdResponse{data[],paging,page,page_count}` / `List` |
| GET | `users/{id}/professionalData` | – | – |
| GET | `users/me/stats` | – | stats map |
| GET | `users/{id}/follows/resume` | – | – |
| GET | `users/{id}/following` | Query: `page` | – |
| POST | `following` | `FollowUserRequest{userId, notification}` | – |
| DELETE | `following/{id}` | – | – |
| PATCH | `following/{id}` | `FollowUserRequest` | – |
| GET | `alert/self` | – | `GeevSavedSearch` |
| POST | `alert/new` | `GeevSavedSearch{type[],distance,location}` | `GeevSavedSearch` |
| PATCH | `alert/{savedSearch_id}/update` | `GeevSavedSearch` | void |
| DELETE | `alert/{savedSearch_id}/delete` | – | void |
| POST | `sponsor/check` | `CheckSponsorshipCodeRequest{sponsorCode}` | `GeevProfileResponseV2` |
| POST | `sponsor/set` | `SendSponsorshipCodeRequest{sponsorCode}` | `GeevProfileResponseV2` |
| GET | `campaigns/impact/current` | – | `ImpactByGeevCampaign` |
| POST | `campaigns/impact/{campaign_id}/contribution` | `ImpactByGeevParticipationRequest{creditGiven}` | void |
| GET | `items/{ad_id}/{user_id}/reservations/cancellations` | – | `ReservationRemoval` |
| POST | `users/me/delete` | – | `AccountDeletionResponse` |
| DELETE | `users/me/delete` | – (cancel deletion) | void |

`AdListRequest` JSON:
```
consumptionRule, distance(Integer), category(List), donationState(List),
id(String), text(String), latitude(Double), longitude(Double),
state(List), type(List), universe(List), userGroups(List)
```

---

### 4.3 v1 API — `https://prod.geev.fr/v1/api/v0.19/` (50 endpoints; legacy)

All methods send `Content-type: application/json` / `Accept: application/json` unless multipart.

| Method | Path | Request | R |
|--------|------|---------|---|
| GET | `/alive` | – | boolean (health) |
| GET | `version/check` | – | `AppUpdateCheckResponse` |
| POST | `user/auth/local/register` | multipart (like `/accounts/local`) | `UserInformationResponse` |
| POST | `user/auth/logout` | – | void |
| PATCH | `user/validation` | `UserEmailValidationRequest{user_id, token}` | `UserEmailValidationResponse` |
| POST | `user/validation/resend` | `SendToEmailRequest{email}` or `UserIdActivationRequest{user_id}` | void |
| POST | `user/password/reset` | `SendToEmailRequest{email}` | void |
| PATCH | `user/password` | `PasswordChangeRequest{password, token, user_id}` | void |
| GET | `user/self` PATCH | `UpdateSelfUserRequest{appsflyer_id,birth_date,current_device_location,first_name,gender,idfa,active_notifications,last_name}` | void |
| PATCH | `user/self` | `UpdateDeviceInfoRequest{current_device_version,current_device_model}` | void |
| PATCH | `user/self` | `UpdateDevicePushTokenRequest{current_device_type,current_device_push_token}` | void |
| PATCH | `user/self` | multipart (profile image) | void |
| GET | `user/self/light` | Headers: `x-geev-idfa`, `x-geev-consent-string` | `UserInformationResponse{current_device{_id,address,app_token,location,user_id}, user{GeevProfileResponse}}` |
| GET | `user/self/credits` | – | `CreditsFetcherSuccess` |
| GET | `user/self/device` | – | `PushDeviceInfoResponse` |
| GET | `user/self/campus` | – | `SelfCampus` |
| GET | `user/self/ranking` | Query: `info(GamificationDataType), badge_ordering(GamificationBadgeOrdering)` | `GamificationSuccessfulResponse` |
| GET | `user/self/favorites/ad` | – | `GeevFavoriteResponse` |
| GET | `user/self/favorites/ad/{ad_id}` | – | `GeevCheckFavoriteResponse` |
| POST | `user/self/favorites/ad/{ad_id}` / `{articleId}` | – | void |
| DELETE | `user/self/favorites/ad/{ad_id}` / `{articleId}` | – | void |
| GET | `user/{user_id}/light` | – | `UserInformationResponse` |
| GET | `user/{user_id}/stats` | – | `UserProfileStatsResponse` |
| GET | `user/{user_id}/reviews` | Query: `page, limit, type(ReviewType)` | `GeevReviewListResponse` |
| GET | `user/{user_id}/reviews/count` | – | `ReviewsCount` |
| GET | `user/{user_id}/articles` | Query: `order, sort, type, status, page, limit` | `UserArticlesResponse` |
| GET | `user/{user_id}/articles?order=-1&sort=creation_timestamp&status=free` | Query: `type, page, limit` | `UserArticlesResponse` |
| GET | `user/{user_id}/articles/count?status=pending` | – | `UserPendingAdsResponse` |
| GET | `user/{user_id}/missed_appointments` | – | `GeevMissedAppointment` |
| GET | `articles/{ad_id}` | – | `GeevAd` |
| GET | `articles/{articleId}` | – | `NewArticleRemote` |
| GET | `premium/campus/subscribe` | Query: `code` | void |
| GET | `notice/self` | Query: `limit` | `PagedNoticeList` |
| PATCH | `ad/{ad_id}/confirmation` | – | void |
| PATCH | `ad/{ad_id}` | multipart (update ad) | void |
| PATCH | `ad/{articleId}` | multipart (update article) | void |
| POST | `email/check` | `CheckEmailExistRequest{email}` | void |
| POST | `complaint/conversation/{conversation_id}` | `ComplaintRequest{description,type}` | void |
| POST | `complaint/conversation/{message_id}` | `ComplaintRequest` | void |
| POST | `complaint/user/{user_id}` | `UserComplaintRequest{description,reason}` | void |
| POST | `video/token` | `VideoGenerateRequest{item_id}` | `VideoGenerateResponse` |
| POST | `user/auth/logout` | – | void |

---

## 5. Key response models (top-level fields)

### Auth / profile
- `GeevProfileResponse` (v1 user info / sponsor check): `_id, email, first_name, last_name, gender, birth_date, phoneNumber, picture, type, credits, score, rank, rank_details, review_sum, review_count, sponsorship_token, sponsor, sponsor_total, achievements[], donations[], requests[], streets[], devices[], creation_time_ms, deletion_date_ms, premium_expiration_timestamp, subscription, login_service, active_notifications, streets_count, adoption_total, donation_total, donation_count, request_count, street_count, is_investor, reliabilityScore, user_deleted, stats, attribution`.
- `UserInformationResponse`: `{current_device: GeevSelfDevice{_id,address,app_token,location,user_id}, user: GeevProfileResponse}`.
- `UserDetailsRemote`: `{firstName, lastName, firstIntention, _links[]}`.
- `SignUpRemote`: `{accountId, userId}` · `AccountSsoTokenRemote`: `{token}` · `UnreadCountResponse`: `{count}` · `NotificationValues`: `{data[], total}`.

### Article
- `NewArticleRemote`: `id, title, description, type, category, universe, state, status, statusDetail, author, location, city, pictureUrl, pictures, picturePaths, availability, user_availability, consumptionRule, carbonValue, savings, bigSavings, creditsCost(creditCost), stock, availableStock, productType, eanCode/long, randomCode, reserved, available, acquired, given, closed, validated, isReservable, isRisable, unlocked, fromShopKeeper, viewsCount, favoritesCount, reservationCount, acquiredCount, totalContact, conversationId, creditsCost, _links, createdAt, creationDateMs, risenDate, risenTimestampMs, validationDateMs, validatedAt, consumptionLimitDateMs, sellingInfo`.
- `ArticleCreatedRemote`: `{id, validated}`.
- `GeevAd` (v1): `_id, title, description, type, category, universe, author, location, city, pictures, user_availability, consumption_rule, food_expiration_timestamp_ms, ean_code, validated, validation_status, validation_timestamp, creation_timestamp, last_update_timestamp, risenTimestampMs, state, available, closed, reserved, given, acquired, unlocked, favorite, reservable, bigSavings, savings, carbonValue, stats, stock, availableStock, viewsCount, reservedCount, acquiredCount, url, circles, randomCode, productType, contestButtonText, contestTitleText, awaiting_confirmation, is_seller, unlocked_counter, unlocked_counter_obfuscated, sellingData, takeBackPartner, pickUpPoint(pictures)`.
- `GeevAdResponse`: `{data[], paging, page, page_count}`.
- `ArticleDetailsRemote`: `{status, creditCost, donator, availablePickupProviders[], _links[]}`.

### Messaging
- `MessagingConversationSummaryListResponse`: `_id, type, category, title, description, picture, status, acquired, closed, given, reserved, selected_recipient, author, conversations[]`.
- `MessagingDetailsResponse`: `_id, active, waitingList, suggested, status(ConversationStatus), adopterId, donatorId, reservationId, reservation, item, recipient, messages[], adopterAvailabilities, commonAvailabilities, closedByAdopter, closedByDonator, _links`.

### Reservation
- `AddReservationRequest`: `{itemId, reserveToUserId}` → `ReservationRemote{reservationId}`.

### Location / search
- `LocationDataRemote`: `{label, city, postalCode, latitude, longitude, radius, obfuscated}`.
- `ApiAddress`: geocoded address (autocomplete list / reverse).

---

## 6. Notes / caveats

- Return payloads are serialized with Gson using the JSON keys listed (`SerializedName`). Unknown/extra server fields are ignored by the app.
- Most endpoints are Kotlin coroutines; the trailing `Continuation` parameter is not an HTTP argument. `Lgha`/`Ltb7` are RxJava/Call wrappers — the payload is the listed model.
- Social logins (Facebook/Google/Apple) require provider identity tokens passed in the body/parts.
- The multipart field `{provider}.pickUpPointId` uses the pickup-provider code (e.g. relay providers) as key prefix.
- `startSession`/`pauseSession`/`resumeSession`/`stopSession` are used to track user session lifecycle.
- The OIDC/SSO token endpoint is out of the Retrofit stack; credentials are issued per-account via `AccountAuthenticatedRemote.sso`.
