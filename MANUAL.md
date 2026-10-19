# SaaS Analytics Dashboard: Manual (Windows, Roman Urdu)

Is manual mein project chalane aur har API test karne ke steps ek ek karke likhe hain.
Har command **alag line** mein chalayein. Lambi multi-line paste na karein.

---

## 1. Project kya hai (2 line mein)
Multi-tenant analytics SaaS: har company (tenant) ka alag subdomain (`acme.localhost`) aur alag database schema hota hai.
Company ki app API key se data bhejti hai, aur dashboard par live charts, alerts, reports aur billing milti hai.

## 2. Zaroori cheezein
| Cheez | Status |
|---|---|
| Python 3.12 | Install hona chahiye |
| PostgreSQL (aap ke paas 18, port 5432) | Chalta hua |
| Redis / Docker | **Zaroori nahi** (sirf Celery ke liye) |

Postgres mein ye ek baar ban chuka hona chahiye: user `analytics` (password `analytics`) aur database `analytics`.

## 3. Pehli baar setup (ek hi baar)
Project folder mein jayein (jahan `manage.py` hai):
```
cd C:\Users\BareeraAnam\Desktop\saas_analytics\saas_analytics
```
Venv aur packages (agar venv bahar wale folder mein hai to `..\venv\Scripts\activate` use karein):
```
py -3.12 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py check
```
Database tables (public schema):
```
python manage.py migrate_schemas --shared
```
Public tenant (ek baar): `python manage.py shell` kholein, phir ek ek line type karein:
```
from apps.tenants.models import Client, Domain
t = Client(schema_name="public", name="Public")
t.save()
Domain(domain="localhost", tenant=t, is_primary=True).save()
exit()
```
Main superuser:
```
python manage.py createsuperuser
```

## 4. Har din server kaise chalayein
```
cd C:\Users\BareeraAnam\Desktop\saas_analytics\saas_analytics
..\venv\Scripts\activate
python manage.py runserver
```
Is terminal ko khula rehne dein. Band karna ho to `Ctrl+C`.
Test commands ke liye **naya terminal** kholein aur wahan bhi folder mein jayein aur venv activate karein.

## 5. Addresses
| Kaam | Address |
|---|---|
| Main admin | http://localhost:8000/admin/ |
| Company banana (POST) | http://localhost:8000/api/signup/ |
| Company admin | http://acme.localhost:8000/admin/ |
| Dashboard (live) | http://acme.localhost:8000/ |

`localhost` use karein, `127.0.0.1` nahi (tenant hostname se pehchana jata hai).

## 6. Nayi company banana (tenants)
Naye terminal mein, ek line:
```
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/signup/ -ContentType "application/json" -Body '{"company":"Beta","subdomain":"beta","email":"b@beta.com","password":"secret1234"}'
```
Phir `http://beta.localhost:8000/admin/` par `b@beta.com` / `secret1234` se login.
Qaide: password 8+ characters; `www`, `admin`, `api`, `public` subdomain nahi ban sakte; subdomain dobara nahi ban sakta.

## 7. API key banana (accounts)
1. Browser mein `http://acme.localhost:8000/admin/` par login karein.
2. `http://acme.localhost:8000/api/keys/` kholein.
3. Name mein `test` likh kar **POST** dabayein.
4. Jawab mein `key` (`sk_...`) milti hai. **Copy kar ke save kar lein**, dobara nahi dikhti.

Key disable karna: `/api/keys/<id>/` par PATCH `{"is_active": false}`.

## 8. Data bhejna (ingestion)
Terminal mein ek ek line:
```
$key = "sk_YAHAN_APNI_KEY"
Set-Content body.json '{"name":"error","value":1}'
Set-Content bulk.json '[{"name":"error","value":2},{"name":"signup","value":3}]'
```
Ek event:
```
curl.exe -i --resolve acme.localhost:8000:127.0.0.1 -X POST http://acme.localhost:8000/api/ingest/ -H "Authorization: Api-Key $key" -H "Content-Type: application/json" -d "@body.json"
```
Sahi jawab: `201 Created`, `{"received":1}`.

Bulk:
```
curl.exe -i --resolve acme.localhost:8000:127.0.0.1 -X POST http://acme.localhost:8000/api/ingest/ -H "Authorization: Api-Key $key" -H "Content-Type: application/json" -d "@bulk.json"
```
Sahi jawab: `{"received":2}`.

Ghalat key (rejection test): `-H "Authorization: Api-Key sk_galat"` laga kar wohi command. Jawab `401`/`403`.

Webhook (HMAC signature ke saath):
```
$body = '{"name":"webhook_event","value":5}'
[IO.File]::WriteAllText("$PWD\hook.json", $body)
$h = New-Object System.Security.Cryptography.HMACSHA256
$h.Key = [Text.Encoding]::UTF8.GetBytes($key)
$sig = ($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($body)) | ForEach-Object { $_.ToString("x2") }) -join ""
curl.exe -i --resolve acme.localhost:8000:127.0.0.1 -X POST http://acme.localhost:8000/api/webhook/ -H "X-Api-Key: $key" -H "X-Signature: $sig" -H "Content-Type: application/json" --data-binary "@hook.json"
```

Natija dekhna: admin mein **Ingestion > Events**.

## 9. Dashboard
- Summary JSON: `http://acme.localhost:8000/api/dashboard/summary/`
- Live page: `http://acme.localhost:8000/` (login zaroori). Page khula rakh kar section 8 ka ingest chalayein; chart bina refresh ke update hona chahiye.

## 10. Alerts
`http://acme.localhost:8000/api/alerts/rules/` par POST (Raw data):
```
{"name":"Zyada errors","metric":"error","operator":"gt","threshold":3,"window_minutes":5,"notify_email":"a@acme.com","cooldown_minutes":30,"is_active":true}
```
`operator`: `gt`, `lt`, `gte`, `lte`. Trigger hui alerts: `/api/alerts/logs/`.
Rule automatic tab check hota hai jab Celery Beat chale (Redis chahiye).

## 11. Reports
`http://acme.localhost:8000/api/reports/` par POST:
```
{"name":"Daily Report","frequency":"daily","file_format":"csv","recipients":"a@acme.com","is_active":true}
```
Download (Celery ke bagair chalta hai):
- CSV: `http://acme.localhost:8000/api/reports/download/?fmt=csv&frequency=daily`
- PDF: `http://acme.localhost:8000/api/reports/download/?fmt=pdf&frequency=weekly`

## 12. Billing
- Roz ke calls: `http://acme.localhost:8000/api/billing/usage/`
- Stripe checkout: POST `/api/billing/subscribe/` (`.env` mein `STRIPE_SECRET_KEY` aur `STRIPE_METERED_PRICE_ID` chahiye)

## 13. Redis aur Celery
Abhi `USE_REDIS=0` hai, is liye cache aur WebSocket memory mein chalte hain. Ye sab Redis ke bagair chalta hai: signup, keys, ingest, dashboard, live chart, alert rules banana, report download, billing usage.
**Nahi chalta:** Celery se automatic reports, alerts aur Stripe usage report.

Redis install karne ke baad `.env` mein `USE_REDIS=1` likhein, phir:
```
celery -A config worker -l info --pool=solo
celery -A config beat -l info
```

## 14. Aam errors aur hal
| Error | Wajah | Hal |
|---|---|---|
| `Could not open requirements file` | Ghalat folder | `dir` se check karein, `requirements.txt` wale folder mein jayein |
| `password authentication failed for user "analytics"` | Postgres mein user nahi | psql mein `CREATE USER analytics WITH PASSWORD 'analytics';` |
| `No tenant for hostname` | Domain register nahi | `localhost` use karein, public tenant banayein |
| Admin bina design ke | staticfiles missing | `settings.py` mein `django.contrib.staticfiles` (comma ke saath) |
| `Not available for global schema` | Normal | Company ke subdomain par admin kholein |
| `acme.localhost` PowerShell mein resolve nahi | Windows hosts | `curl.exe --resolve ...` use karein |
| `Failed to connect port 8000` | Server band | Terminal 1 mein `runserver` chalayein |
| `Redis ... 10061` | Redis nahi chal raha | `USE_REDIS=0` (default) rakhein |
| 404 on `/api/signup/` | Subdomain par kholi | Signup sirf `localhost` par hota hai |

## 15. Project structure
- `apps/tenants` (shared): company, domain, signup
- `apps/accounts`: API keys
- `apps/ingestion`: events, ingest, webhook
- `apps/dashboard`: summary, cache, WebSocket, Plotly page
- `apps/reports`: schedules, CSV/PDF, email task
- `apps/alerts`: rules, logs, check task
- `apps/billing`: usage, Stripe
- `config/`: settings, urls, asgi, celery
