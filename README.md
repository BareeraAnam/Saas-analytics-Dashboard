# SaaS Analytics Dashboard

Multi-tenant analytics API. Each company gets its own Postgres schema. The same commands work on Windows PowerShell and on a Unix shell.

Python 3.12 or newer. Docker must be running for Postgres and Redis.

When you zip this folder, leave out `venv` and `__pycache__`. The included `.env` is local-only: database `analytics`, Redis on, and email printed in the server terminal. It does not use Gmail. The employee creates a new virtualenv and runs the steps below. Do not point `.env` at a different database name unless Postgres was created with that same name.

1. Create a virtualenv and install dependencies.

```bash
python -m venv venv
```

Windows: `venv\Scripts\activate`

Unix: `source venv/bin/activate`

```bash
pip install -r requirements.txt
```

2. Copy the environment file and start Postgres and Redis.

```bash
copy .env.example .env
```

Unix: `cp .env.example .env`

```bash
docker compose up -d
```

3. Create tables and the public tenant. Redis is on by default because cache and websocket groups are shared across processes.

```bash
python manage.py migrate_schemas --shared
python manage.py setup_public_tenant
```

4. Run the app, the worker, and the scheduler in three terminals.

```bash
python manage.py runserver
celery -A config worker -l info --pool=solo
celery -A config beat -l info
```

On Unix you can drop `--pool=solo`.

## Create a tenant

Signup does not create the schema immediately. It sends a confirmation link, and the worker creates the schema after that link is opened.

```bash
curl -X POST http://localhost:8000/api/signup/ -H "Content-Type: application/json" -d "{\"company\":\"Acme\",\"subdomain\":\"acme\",\"email\":\"a@acme.com\",\"password\":\"secret1234\"}"
```

The server terminal prints `Signup confirmation link: ...`. Open that exact link while the Celery worker is running. The worker creates the company. Then sign in at http://acme.localhost:8000/login/ and open http://acme.localhost:8000/admin/ with the same email and password.

A second company is the same call with another subdomain, for example `beta`. An API key from Acme is rejected on `beta.localhost`.

## Send data

1. `POST /api/keys/` with `{"name":"test"}` while signed in. The response includes `key`, `key_id` and `signing_secret` once.
2. Ingest with the raw key:

```bash
curl -X POST http://acme.localhost:8000/api/ingest/ -H "Authorization: Api-Key sk_xxx" -H "Content-Type: application/json" -d "{\"name\":\"error\",\"value\":1}"
```

3. Webhooks do not send the API key. Sign `{timestamp}.{raw body}` with the signing secret:

`X-Key-Id: ak_...`

`X-Signature: t=1710000000,v1=<hex hmac sha256>`

The same signature is rejected the second time. A signature older than 5 minutes is also rejected.

4. Turn a key off while signed in: `PATCH /api/keys/<id>/` with `{"is_active": false}`. Ingest with that key then returns 401.

5. Dashboard: http://acme.localhost:8000/ . After login the page says live, and a new event increases the total without a refresh.

6. Reports, while signed in: `GET /api/reports/download/?fmt=csv` and `GET /api/reports/download/?fmt=pdf`.

7. Alert webhook URLs must be public. `http://169.254.169.254/` and `http://localhost/` are rejected.

Stripe subscription updates are received at `http://localhost:8000/api/billing/webhook/` on the public host.

## Tests

```bash
python manage.py test
```

See APPS_GUIDE.md for what each app does.

`docs/rls_example.sql` is an example of row-level security. This project does not use it. Isolation is one Postgres schema per tenant.

After pulling these changes, run `python manage.py migrate_schemas` so existing tenants get the new tables (admin, sessions, API key fields).
