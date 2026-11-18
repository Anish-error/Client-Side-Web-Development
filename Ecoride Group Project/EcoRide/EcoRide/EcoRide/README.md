# EcoRide Pune

EcoRide is a Django bicycle-sharing application for Pune. It uses the supplied Eco-Ride website design, a Google Maps JavaScript map, live station availability, rider accounts, Razorpay checkout in INR, and staff fleet-management tools.

## Features

- Pune station map with clickable station markers, search/filter, live bike counts, and Google Maps directions.
- Sample stations: Swargate, Shivajinagar, Pune Railway Station, Deccan Gymkhana, Kothrud Depot, and Viman Nagar.
- Signup, sign-in, rider history, bike return workflows, and a staff operations dashboard.
- Razorpay test-mode orders in INR, server-side payment-signature verification, captured-amount verification, and signed payment webhooks.
- PostgreSQL with Docker Compose; SQLite for local development.

The sample fare is **₹50 per ride** (`RENTAL_PRICE_PAISE` in `core/views.py`). Update both the configured fare and displayed fare if you change the price.

## Run locally

Requires Python 3.11+ and pip.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Visit `http://127.0.0.1:8000`. Configure Maps and Razorpay keys below before using the interactive map and test checkout. If `.env` already exists, add the new Google Maps and Razorpay settings to it; don’t overwrite existing environment settings. You can still open individual station directions in Google Maps without a Maps API key.

## Google Maps setup

1. In [Google Cloud Console](https://console.cloud.google.com/), select or create a project and attach a billing account.
2. Enable **Maps JavaScript API** for that project.
3. Create an API key in **APIs & Services → Credentials**.
4. Restrict the key: use **Websites (HTTP referrers)**, add both `http://localhost:8000/*` and `http://127.0.0.1:8000/*` for local use, plus your exact HTTPS site domain for deployment; under API restrictions, allow only **Maps JavaScript API**.
5. Add it to the root `.env` file:

   ```dotenv
   GOOGLE_MAPS_API_KEY=your-restricted-browser-key
   ```

The Maps JavaScript key is sent to the browser so Maps can load. This is expected: keep it protected with Google Cloud's website and API restrictions, monitor usage, and do not commit `.env`. Restart Django after changing the key. If the key is missing or restricted incorrectly, station links still open Google Maps directions.

## Razorpay test payments

1. Sign in to the [Razorpay Dashboard](https://dashboard.razorpay.com/) and switch to **Test Mode**.
2. Generate test API keys and add them to `.env`:

   ```dotenv
   RAZORPAY_KEY_ID=rzp_test_your_key_id
   RAZORPAY_KEY_SECRET=your_test_key_secret
   APP_BASE_URL=http://127.0.0.1:8000
   ```

3. Ensure automatic payment capture is enabled for your Razorpay test account, then restart the Django server. Reserve a bicycle and complete checkout using the test payment methods shown by Razorpay. No live charge is made with test credentials.
4. For payment-status updates if a browser closes after a successful payment, configure a Razorpay webhook for `payment.captured` pointing to `https://YOUR_PUBLIC_HOST/payments/razorpay/webhook/`, then add its webhook secret:

   ```dotenv
   RAZORPAY_WEBHOOK_SECRET=your_webhook_signing_secret
   ```

   A local server is not publicly reachable by Razorpay; use a trusted HTTPS tunnel for webhook development. The browser checkout callback is independently signature-verified and the payment is fetched from Razorpay before the bike becomes active.

Never use test credentials for live transactions. Before going live, configure Razorpay production credentials, HTTPS, domain restrictions for Maps, correct allowed hosts/CSRF origins, and a production-grade database.

## Staff and fleet setup

Create a superuser with `manage.py createsuperuser`. Staff can access **Operations** and `/admin/` to manage stations and bicycles. `manage.py seed_demo` creates or updates the six Pune demo stations and three demo bikes at each station. The example coordinates are approximate station-area locations and can be adjusted in Django admin.

## Docker deployment

Copy `.env.example` to `.env`, set a unique `DJANGO_SECRET_KEY`, configure your domain in `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`, set `DJANGO_DEBUG=False`, and add production Maps/Razorpay keys. Start:

```powershell
docker compose up --build
```

The web container applies migrations on startup. PostgreSQL data is stored in the `postgres_data` named volume. Terminate HTTPS at a trusted reverse proxy/load balancer; set `DJANGO_TRUSTED_PROXY=True` only if that proxy strips and sets `X-Forwarded-Proto`.

## Checks and tests

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```
