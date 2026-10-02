# Florence Court Schools Portal

Web portal for Florence Court International Schools. It provides public
admissions information and online applications, student access to school
services, and staff tools for managing school records and fees.

## Technology

- Python and Flask
- Flask-SQLAlchemy with MySQL/PyMySQL
- Gunicorn for production hosting

## Run locally on Windows

Install Python, Git, and MySQL, then open PowerShell in this project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Set the database connection and administrator credentials in the same
PowerShell window. Replace the example values with your own local MySQL
credentials and database name:

```powershell
$env:DATABASE_URL = "mysql+pymysql://username:password@localhost:3306/studentportal"
$env:ADMIN_ID = "your-admin-id"
$env:ADMIN_PASSWORD = "your-private-password"
```

Start the development server:

```powershell
.\.venv\Scripts\python.exe app.py
```

Open <http://127.0.0.1:5000/> in a browser. To stop the server, press
`Ctrl+C`. These environment variable settings apply only to the current
PowerShell window.

If PowerShell blocks virtual-environment activation scripts, use the
`.venv\Scripts\python.exe` commands above without activating the environment.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Deployment

For Railway and other production setup guidance, required environment
variables, database and persistent storage configuration, see
[DEPLOYMENT.md](DEPLOYMENT.md). Configure outgoing email using
[MAIL_SETUP.md](MAIL_SETUP.md).

Never commit `.env` files, database passwords, SMTP credentials, or production
secrets. Use the hosting provider's private environment-variable settings for
production configuration.
