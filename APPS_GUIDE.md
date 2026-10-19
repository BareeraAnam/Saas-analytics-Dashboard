# Apps Guide

Shared (public schema): `tenants`.

Tenant (one schema per company): `accounts`, `ingestion`, `dashboard`, `reports`, `alerts`, `billing`. `auth`, `sessions`, `admin` and `messages` are installed in both, so each tenant's admin log points at that tenant's users.

| App | Role |
|---|---|
| tenants | Client and Domain. `POST /api/signup/` stores a pending signup and emails a confirmation link. The schema is created by a Celery task after the link is opened. |
| accounts | API keys (hash plus a separate signing secret), session login, roles (owner, member, viewer) and invites. |
| ingestion | Events. `POST /api/ingest/` takes a capped batch. `POST /api/webhook/` checks a timestamped HMAC made with the signing secret. |
| dashboard | 24 hour summary, short cache, WebSocket `/ws/metrics/` for a signed-in user of that tenant. |
| reports | CSV and PDF. Monthly means the previous calendar month. Recipients must be users of the tenant. |
| alerts | Threshold checks every minute. Email stays inside the tenant. Webhook URLs must be public. |
| billing | Daily API call counts. Stripe meter events use an idempotency key. Subscription status changes only from the Stripe webhook. |
| config | Settings, URLs, ASGI, Celery. |

Flow: ingest saves events, adds usage, and publishes one summary to the tenant's websocket group.

`docs/rls_example.sql` is a row-level security example. The running project does not apply it.
