# StellerCart

An e-commerce web app built with Django. Users can sign up or log in (email/password or Google), browse products, read and write reviews, add items to a cart, choose delivery options, and check out with **Cash on Delivery** or **Razorpay** (test mode).

**Live demo:** https://steller-cart.vercel.app/login/

> Note: Google sign-in only works for accounts added as *Test users* in Google Cloud while the OAuth app is in Testing mode. Anyone can still use **Create account** with a username and password.

---

## Features

- Email/password signup and login, plus **Sign in with Google** (`django-allauth`)
- Product catalog with categories, search, images, ratings and reviews
- Shopping cart with quantity limits and per-item delivery options
- Server-side price, tax (10%) and shipping calculation
- Shipping details form with Indian mobile number and PIN code / city / state validation
- **Cash on Delivery** checkout
- **Razorpay** online payment with server-side signature verification
- Order history grouped by date, with a snapshot of the shipping address at order time
- Contact form
- Secrets kept out of the repo via environment variables

## Tech stack

| Area | Tool |
|------|------|
| Backend | Django 5.0.3 |
| Auth | django-allauth (Google OAuth) |
| Payments | Razorpay (test mode) |
| Database | SQLite locally, PostgreSQL (Neon) in production |
| Config | python-decouple (`.env`) |
| Hosting | Vercel |

---

## Run locally

### 1. Clone and enter the project

```bash
git clone https://github.com/Ritikakalia1/StellerCart.git
cd StellerCart
```

(Use the folder that contains `manage.py`.)

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
SECRET_KEY=your-django-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=

# Leave empty to use local SQLite. On Vercel, use your Neon Postgres URL.
DATABASE_URL=
```

Never commit your real `.env` file. It is already in `.gitignore`.

### 5. Set up the database

```bash
python manage.py migrate
python manage.py createcachetable
python manage.py createsuperuser   # optional, for /admin
```

`createcachetable` is required: the app caches PIN code lookups in a database table called `django_cache`.

### 6. Start the server

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000/

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django secret key (required) |
| `DEBUG` | `True` locally, `False` in production |
| `ALLOWED_HOSTS` | Comma-separated hosts, e.g. `.vercel.app` |
| `DATABASE_URL` | Postgres connection string. Empty means local SQLite |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth credentials |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | Razorpay keys (use **test** keys, both from the same account) |
| `PINCODE_STRICT` | `True` (default) blocks saving an address if the PIN code can't be verified |
| `CSRF_TRUSTED_ORIGINS` | Defaults to `https://*.vercel.app` |

Paste values with no spaces or quotes. After changing a variable on Vercel, **redeploy** for it to take effect.

---

## Google sign-in setup (free)

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select your project. Google may ask you to turn on 2-step verification first.
2. Go to **APIs & Services → OAuth consent screen** (Google Auth Platform) and set up the app.
3. Under **Audience → Test users**, add the Gmail addresses that should be able to sign in (up to 100). Or click **Publish app** to allow any Google account. Only basic `profile` and `email` scopes are used.
4. Go to **APIs & Services → Credentials**, create an **OAuth client ID** of type *Web application*, and add:

   **Authorized JavaScript origins**
   ```
   http://127.0.0.1:8000
   https://steller-cart.vercel.app
   ```

   **Authorized redirect URIs**
   ```
   http://127.0.0.1:8000/accounts/google/login/callback/
   https://steller-cart.vercel.app/accounts/google/login/callback/
   ```
5. Put the client ID and secret in `.env` (and in Vercel's environment variables).

No billing account is needed for Google sign-in.

## Razorpay setup (test mode)

1. Create a free [Razorpay](https://razorpay.com/) account and switch the dashboard to **Test mode**.
2. Generate test API keys and set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
3. At checkout, choose **Make Online Payment** and use Razorpay's [test payment details](https://razorpay.com/docs/payments/payments/test-card-details/).

---

## Deploy to Vercel

1. Create a free Postgres database on [Neon](https://neon.tech) and copy its connection string.
2. (Optional) Export local products: `python manage.py dumpdata home --indent 2 -o data.json`
3. With `DATABASE_URL` pointing at Neon, run:
   ```bash
   python manage.py migrate
   python manage.py createcachetable
   python manage.py loaddata data.json
   python manage.py createsuperuser
   ```
4. Import the repo on [vercel.com/new](https://vercel.com/new).
5. Add the environment variables: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=.vercel.app`, `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`.
6. Add your production redirect URI in Google Cloud (see above).
7. Always open the app from your main domain (`https://steller-cart.vercel.app`). Vercel's per-deployment preview URLs are different addresses and will fail Google sign-in with `redirect_uri_mismatch`.

> Images uploaded later through the admin panel will not persist on Vercel (read-only filesystem). Use Cloudinary or S3 for uploads.

---

## Troubleshooting

| Problem | Cause and fix |
|---------|---------------|
| `Error 400: redirect_uri_mismatch` | The URL you opened isn't registered in Google Cloud. Add the exact `https://<domain>/accounts/google/login/callback/` (with trailing `/`) and open the site from that domain. |
| `Access blocked` / `access_denied` | The app is in Testing mode and your Gmail isn't a Test user. Add it, or publish the app. |
| Google login says an account already exists | Add `SOCIALACCOUNT_EMAIL_AUTHENTICATION = True` and `SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True` to `settings.py`. |
| Cash on Delivery or payment fails, orders stay empty | On PostgreSQL, locking a cart query that joins a nullable column fails (`FOR UPDATE cannot be applied to the nullable side of an outer join`). SQLite hides this. The fix is `select_for_update(of=('self',))` in `place_orders_from_cart` (already applied). |
| "Payment verification failed" | `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` don't match, or contain extra spaces. Use both test keys from the same account, then redeploy. |
| "We couldn't verify your PIN code" | The PIN lookup service was unreachable. Retry, or set `PINCODE_STRICT=False`. |
| Cash on Delivery / payment buttons disabled | Save your shipping details first. |

---

## Project structure

```
StellerCart/
├── home/               # Main app: models, views, forms, validators, migrations
├── my_site/            # Project settings, URLs, WSGI/ASGI
├── templates/          # HTML templates
├── static/             # CSS and images
├── media/              # Product images
├── manage.py
├── requirements.txt
└── .env.example
```

## License

This project is for educational purposes only.
