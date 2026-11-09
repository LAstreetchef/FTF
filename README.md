# Food Truck Fundraiser

A Flask app for community food-truck fundraisers. An organizer picks an approved truck, sets a menu markup, and publishes an event. Supporters pledge meal tickets. Cards are authorized up front and captured only if the event reaches its goal, or immediately if the event is already approved. Truck owners keep their own menu, registration, and payout details. Admins approve events and record payouts.

This copy last ran on Replit (about September 2025). It now runs as a normal Python app with environment variables, SQLite for local development, and Postgres for production.

## What it does today

- Public pages: home, event list (active / completed / past), event detail, Los Angeles and Houston landing pages, English and Spanish.
- **Organizers** register, create an event, pay a $1.95 publish fee, and watch pledges. Events are created by organizers, not by the truck account.
- **Food truck owners** register, add a truck and menu, pay a $25 registration fee, and track payouts.
- **Supporters** pledge from an event page. Stripe PaymentIntents use manual capture, so a pending event does not capture the card until the goal is met and an admin approves it. Approved events capture immediately.
- **Admins** manage trucks, events, payouts, and the support inbox.
- Auth is a server session. Organizers also get a 24-hour database token so the old Squarespace embed can stay logged in. It is not JWT.
- Email is optional. Pledge and goal mail is skipped until SMTP credentials are set.
- The support chat calls OpenAI only when `OPENAI_API_KEY` is set.

Payments:

- `STRIPE_TEST_MODE` defaults to **true**. Live keys are refused while test mode is on, including in production, so a first deploy cannot charge real cards by accident.
- With `sk_test_` / `pk_test_` keys, pledges and fees use Stripe test mode. Test card `4242 4242 4242 4242`, any future expiry, any CVC.
- With no keys, outside production, fees and pledges are labeled **local simulation** and no card is charged. Production will not boot without Stripe keys.

## Run locally

Python 3.11 or 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`. For a first look, this is enough:

```bash
APP_ENV=development
SESSION_SECRET=any-long-random-string
SEED_DEMO_DATA=true
DEMO_OWNER_EMAIL=owner@example.com
DEMO_OWNER_PASSWORD=choose-a-password
DEMO_ORGANIZER_EMAIL=organizer@example.com
DEMO_ORGANIZER_PASSWORD=choose-a-password
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=choose-a-password
```

Leave the Stripe keys blank to use local simulation, or paste test keys from the [Stripe dashboard](https://dashboard.stripe.com/test/apikeys).

```bash
python main.py
```

Open http://127.0.0.1:5000 . The demo seed creates a Green Truck, one future event, and the three logins above. It does not load the historical JSON backups.

| Who | URL |
| --- | --- |
| Supporter | `/` and `/events` |
| Truck owner | `/food-truck/login` |
| Organizer | `/organizer/login` then `/organizer/create-event` |
| Admin | `/admin/login` |

Production should use gunicorn, which is what the Procfile runs:

```bash
gunicorn --bind 0.0.0.0:5000 main:app
```

## Tests

```bash
pip install -r requirements.txt
pytest
```

`tests/test_smoke.py` covers health, the public pages, truck-owner registration and login, organizer event creation, a Stripe test-mode pledge (the Stripe API is mocked), admin login, and the old unauthenticated repair URLs returning 404. Tests use a temporary SQLite file and do not touch `instance/app.db`.

## Configuration

Every variable is listed in [`.env.example`](.env.example). The ones that matter:

| Variable | Required | Purpose |
| --- | --- | --- |
| `APP_ENV` | yes in production | `development`, `testing`, or `production` |
| `SESSION_SECRET` | yes in production | Signs session cookies |
| `DATABASE_URL` | yes in production | Postgres URL. Empty locally uses SQLite at `instance/app.db` |
| `STRIPE_SECRET_KEY` | yes in production | `sk_test_...` or, only with test mode off, `sk_live_...` |
| `STRIPE_PUBLISHABLE_KEY` | yes in production | Matching `pk_test_...` or `pk_live_...` |
| `STRIPE_TEST_MODE` | recommended | Defaults to `true` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | to create an admin | Seeded once if the account does not exist |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` | to send mail | SMTP. Blank credentials skip sending |
| `OPENAI_API_KEY` | no | Support chat only |
| `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` | no | Admin PayPal payout buttons |
| `SEED_DEMO_DATA` and `DEMO_*` | no | Local sample truck and event. Ignored in production |
| `RESTORE_EVENT_BACKUP` | no | Load `data_backups/` into an empty database. Leave false |
| `IFRAME_EMBED` | no | `true` only for the Squarespace embed. Forces `Secure` cookies, which break `http://localhost` |

`postgres://` URLs are rewritten to `postgresql://` for SQLAlchemy. Do not commit `.env`.

## Historical event backups

`data_backups/` is a September 14, 2025 snapshot of **two events** (Culver Skate Park and a tennis tournament). It is not a full database: organizers, trucks, pledges, and passwords are not in those files. One row includes the organizer email and a Stripe PaymentIntent id.

The files are kept. Startup does **not** import them unless `RESTORE_EVENT_BACKUP=true`, because the related truck and organizer rows are missing and importing them alone would create broken events. New backups are written to `instance/backups/`, which is gitignored.

## Deploy on Render

This is the smallest production path: one web service and one managed Postgres database.

1. Push this repo to GitHub.
2. In Render, choose **New +** → **Blueprint**, point it at the repo, and apply `render.yaml`. That creates the web service and a Postgres database named `food-truck-fundraiser-db`, and sets `DATABASE_URL`, `APP_ENV=production`, and a generated `SESSION_SECRET`.
3. If you would rather click it together yourself: **New +** → **PostgreSQL** (name `food-truck-fundraiser-db`), then **New +** → **Web Service**. Runtime Python, build command `pip install -r requirements.txt`, start command `gunicorn --bind 0.0.0.0:$PORT main:app`, health check path `/health`.
4. Set these environment variables on the web service:
   - `APP_ENV` = `production`
   - `DATABASE_URL` = the Internal Database URL from the Postgres instance
   - `SESSION_SECRET` = a long random string
   - `STRIPE_TEST_MODE` = `true`
   - `STRIPE_SECRET_KEY` = `sk_test_...`
   - `STRIPE_PUBLISHABLE_KEY` = `pk_test_...`
   - `SESSION_COOKIE_SECURE` = `true`
   - `ADMIN_EMAIL` and `ADMIN_PASSWORD`
   - `SEED_DEMO_DATA` = `false`
   - `RESTORE_EVENT_BACKUP` = `false`
5. Add SMTP when you want real mail (`MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`). SendGrid, Amazon SES, or any TLS SMTP server works. The old Network Solutions host is not assumed.
6. Deploy. Open `/health` and expect `{"status":"healthy"}`. Log in at `/admin/login` with `ADMIN_EMAIL`.
7. Run a pledge with the Stripe test card on a published event. In the Stripe test dashboard you should see a PaymentIntent in `requires_capture` (manual capture). Do not set `STRIPE_TEST_MODE=false` until that path is correct and you are ready to charge real cards. Live mode needs `sk_live_` / `pk_live_` keys and `STRIPE_TEST_MODE=false`.

`render.yaml` marks the Stripe, admin, and mail values as values you type in the dashboard. It does not contain secrets.

Railway and Fly are the same shape: a Python web process running the Procfile command, plus a Postgres plugin whose URL you put in `DATABASE_URL`, plus the variables above. Fly needs `fly.toml` with `internal_port` matching `$PORT`; the start command stays `gunicorn --bind 0.0.0.0:8080 main:app` if you pin port 8080.

## Accounts you need

- **Stripe** account. Use test keys until a real event is ready. Webhooks are not required for the current pledge flow; capture is done by the app when a goal is met or an admin approves the event.
- **Postgres** such as Render Postgres, Neon, Railway, or Fly Postgres. SQLite is only for local development.
- **SMTP** provider for pledge confirmations, goal emails, and e-tickets. Optional for a first boot.
- **OpenAI** only if you want the support chat to answer.
- **PayPal** REST app only if admins will send PayPal payouts from the dashboard. Bank payouts in this app are records, not automated transfers.
- An **admin password** you choose via `ADMIN_PASSWORD`. The app no longer creates `support@foodtruckfundraiser.com` / `password`.

## Layout

- `main.py` starts the app. `app.py` loads configuration. `routes.py` is the HTTP surface. `models.py` is the schema. `utils.py` sends mail and talks to Stripe.
- Tables are created with `db.create_all()` on boot. That adds missing tables. It does not migrate columns that already exist. There is no Alembic history yet.
- `.replit`, `replit.md`, and the Squarespace HTML files are leftover from the Replit deploy. The embed snippets still point at a dead `worf.replit.dev` host. Point them at the new URL before using the embed, and set `IFRAME_EMBED=true` only on that HTTPS deployment.

## Holiday campaign pages

Green Truck uses `/c/<slug>` as the first page a prospect sees from a December 2026 email. Each page is Green Truck only: the truck in their lot, or a drop-off, a note from Kam, and a quote form. There is no truck picker. Quote requests are stored for admin. If `CAMPAIGN_NOTIFY_EMAIL` (or `ADMIN_EMAIL`) is set and SMTP is configured, Kam also gets an email. With mail suppressed, the request still shows under Admin → Holiday campaigns.

Create the pages from a CSV. In `/admin/campaigns`, upload a file with this header:

```
company,contact_name,contact_email,personal_note,logo_url,suggested_dates,give_back_cause,slug
```

`company` is required. Dates are `YYYY-MM-DD` separated by `|`. `logo_url` must be `https` if you set it. Re-uploading the same `slug` updates the page and keeps its view count. A sample download on that screen uses fictional companies (`@northwind.example` and similar). Do not commit a CSV of real clients. This repository is public.

Photographs live in `static/images/green-truck/`. `manifest.json` lists each file, a category, and a one-line description. `img/` holds the JPEGs plus responsive WebP (`name-800.webp`, `name-1600.webp`). The 2008 desert shot, `truck-desert-vintage-01.jpg`, is only the small “since 2006” frame. Gallery images use `loading="lazy"`; the hero is preloaded. To swap a picture, replace the file (keep the filename) or upload a replacement in the admin screen. Uploads go to `instance/campaign_photos/` and are not committed. On Render, prefer files in the repo so they survive a new deploy. Set `CAMPAIGN_NOTIFY_EMAIL` on the web service when you want quote mail.

Local demo companies (Northwind Labs, Harbor & Pine, Lumen Desk) are fiction, seeded only when `SEED_DEMO_DATA=true`.

## Suggested next steps

- Put the real Green Truck menu in through `/food-truck/register` instead of the demo seed.
- Confirm a test-mode pledge, a goal-reached capture, and the organizer and truck fee payments in the Stripe test dashboard.
- Add Alembic (or a small SQL migration) before changing columns on a database that already has events.
- Delete the disabled repair routes in `routes.py` once you are sure nothing external calls them. They return 404.
- Rotate the Stripe live publishable key that used to be in this repo's history, and set a new `SESSION_SECRET` for production. See the pull request notes for what was found. Git history still contains the old files.
