# StellerCart

An e-commerce web application built with Django. Includes user authentication (email + Google sign-in), product browsing with reviews, a shopping cart, delivery options, and Razorpay-powered checkout.

## Features

- Email and Google OAuth login/signup via `django-allauth`
- Product catalog with images, reviews, and ratings
- Shopping cart and order placement
- Delivery option selection
- Razorpay payment integration
- Environment-based configuration (no secrets committed to the repo)

## Tech Stack

- **Backend:** Django 5.0
- **Auth:** django-allauth (Google social login)
- **Payments:** Razorpay
- **Database:** SQLite (default, easy to swap for Postgres/MySQL)
- **Config:** python-decouple (`.env` file)

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Ritikakalia1/StellerCart.git
cd StellerCart/my_site
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example file and fill in your own values:

```bash
cp .env.example .env
```

Then edit `.env`:

```
SECRET_KEY=your-django-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
```

> Never commit your real `.env` file — it's already excluded via `.gitignore`.

### 5. Apply migrations

```bash
python manage.py migrate
```

### 6. Create a superuser (optional, for admin access)

```bash
python manage.py createsuperuser
```

### 7. Run the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` in your browser.

## Deploying to Vercel

1. Create a Postgres database (e.g. [Neon](https://neon.tech)) and copy its connection string.
2. Export your local products: `python manage.py dumpdata home --indent 2 -o data.json`
3. With `DATABASE_URL` set to the Neon string, run:
   ```bash
   python manage.py migrate
   python manage.py loaddata data.json
   python manage.py createsuperuser
   ```
4. Import the repo on [vercel.com/new](https://vercel.com/new) and set **Root Directory** to `my_site`.
5. Add environment variables: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=.vercel.app`, `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`.
6. In Google Cloud Console, add `https://<your-app>.vercel.app/accounts/google/login/callback/` as an authorized redirect URI.

> Images uploaded later via the admin won't persist on Vercel (read-only filesystem). Use Cloudinary/S3 for that.

## Project Structure

```
my_site/
├── home/               # Main app: models, views, cart, orders, reviews
├── my_site/            # Project settings, URLs, WSGI/ASGI config
├── static/             # CSS and images
├── media/              # Uploaded product images
├── templates/          # HTML templates
├── manage.py
├── requirements.txt
└── .env.example
```

## Notes

- Google login requires setting up OAuth credentials in the [Google Cloud Console](https://console.cloud.google.com/) and adding them to `.env`.
- Razorpay requires a [Razorpay account](https://razorpay.com/) and test/live API keys added to `.env`.
- `DEBUG` should always be set to `False` in production, and `CSRF_COOKIE_SECURE` will automatically be enforced when `DEBUG=False`.

## License

This project is for educational purposes only.
