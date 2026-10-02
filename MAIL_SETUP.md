# Email configuration

Email delivery is optional while developing locally. When it is not configured, application, admission, and staff account changes still complete; the portal displays a warning and logs that the email could not be sent.

Configure these environment variables before starting Flask:

- `MAIL_SERVER`: SMTP server host name.
- `MAIL_PORT`: SMTP port (defaults to `587`).
- `MAIL_USERNAME`: SMTP account username.
- `MAIL_PASSWORD`: SMTP account password or provider app password.
- `MAIL_FROM`: sender address (or use `MAIL_SENDER`); defaults to `MAIL_USERNAME`.
- `MAIL_USE_TLS`: set to `true` for STARTTLS (defaults to `true`); set to `false` only when the mail server explicitly provides an unencrypted connection.
- `MAIL_USE_SSL`: set to `true` for implicit SSL, commonly used on port `465` (defaults to `false`). Do not enable both SSL and STARTTLS.

For PowerShell, set the values in the current terminal before starting the app:

```powershell
$env:MAIL_SERVER = "smtp.example.com"
$env:MAIL_PORT = "587"
$env:MAIL_USERNAME = "your-smtp-user"
$env:MAIL_PASSWORD = "your-smtp-password"
$env:MAIL_SENDER = "admissions@example.com"
$env:MAIL_USE_TLS = "true"
```

Alternatively, put these settings in a local `.env` file in the project root. The app loads mail settings from that file without overriding environment variables; `.env` is excluded from source control.

Use the credentials provided by your email service. Keep them out of source control and do not paste them into application code.
