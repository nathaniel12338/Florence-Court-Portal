# Production deployment readiness

The app now has a WSGI entry point (`wsgi:app`), a Railway configuration,
a Gunicorn Procfile, a dependency manifest, a database health endpoint
(`/healthz`), configurable upload directories, and production startup checks.

## Required before starting a production instance

1. Create a Railway project with a Python web service and a MySQL service.
   Railway will install `requirements.txt`; MySQL uses the pure-Python PyMySQL
   driver and does not require system MySQL build libraries. The current PDF
   result lookup uses PyPDF2. If PDF
   generation is added, install and configure `wkhtmltopdf` separately.
2. Set every variable listed in `.env.example` as a private host secret.
   `APP_ENV` must be `production`; production startup will reject a missing
   secret, database URL, admin login, or SMTP account. Use a unique
   `SECRET_KEY` of at least 32 characters and an administrator password of at
   least 12 characters.
3. Set `DATABASE_URL` on the web service to the private connection URL
   provided by Railway's MySQL service. Back up the database before the first
   deploy; the app currently creates missing tables and applies a few
   ad-hoc column migrations during startup, rather than using a migration tool.
4. Add a Railway volume mounted at `/data`. Keep the three storage variables
   pointed at `/data/uploads`, `/data/library`, and `/data/results`. Back up
   the volume too; container-local files are not durable.
5. Add the Railway public domain or a custom domain, keep HTTPS enabled, and
   verify `/healthz` returns `{"status":"ok"}` after deployment.
6. Rotate any SMTP app password that has been shared outside the hosting
   provider, then test admission, staff welcome, password reset, and fee
   notification emails.
7. Before opening registration, add CSRF protection to all state-changing
   forms and establish database backups/restore testing, error monitoring,
   login rate limiting, and an admin-password rotation process.

The app currently creates its tables on startup. For a live school database,
take a backup before deploying code that changes the schema, and move schema
changes to reviewed migrations before routine production releases. Do not run
the development server or enable `FLASK_DEBUG` on the public host.

For local development, omit `APP_ENV=production` and run `python app.py`.
Development-only fallback admin credentials are not accepted in production.
