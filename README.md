# Paw Protectors — React JS + common backend

The React JS website and [React Native app](https://github.com/Vivek-pateriya/paw-protectors-App-react-native) use **one FastAPI service and one PostgreSQL database**. This repository provides that common backend, migrations and the React JS client. The legacy Java application is not included.

Features: authentication/recovery, pet profiles/photos, veterinary appointments, vaccination/medication reminders, moderated adoption, admin-managed Pet Shop, shared carts, INR/COD orders, notifications and reports. Admin pet screens show owner names/IDs. Photos display completely in centered frames.

## First setup on Windows

Requirements: Python 3.12+, Node.js 22.14+ with npm, and Git. Open PowerShell in your preferred projects folder:

```powershell
git clone https://github.com/Vivek-pateriya/paw-protectors-web.git
cd paw-protectors-web
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
cd website
npm.cmd ci
npm.cmd run build
cd ..
```

Setup creates a private `.venv`, downloads project-local PostgreSQL, creates `.env` and the database, applies all six migrations, and seeds initial accounts only when the users table is empty. Existing accounts/data are preserved. Do not copy `.env.example` over an existing `.env`.

Initial emails: `owner@paw.local`, `vet@paw.local`, `admin@paw.local`. Their generated password is in your own gitignored `artifacts/demo-credentials.txt`. Passwords/database records from the original laptop are not included. Public registration creates owners; an admin can assign roles through Administration → User accounts.

## Start backend and website

From the repository directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Keep this terminal open. It starts PostgreSQL if needed, applies missing migrations without reseeding, and starts FastAPI.

- Website: **http://127.0.0.1:8000/app** (also `/` in a standalone clone)
- API documentation: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health
- Database: `127.0.0.1:55432`

FastAPI serves the built React website, so normal use needs no separate frontend server. Stop the API with **Ctrl+C**. Stop this project's database afterward with `powershell -ExecutionPolicy Bypass -File .\scripts\stop_db.ps1`.

Inside the original `PET-SHOP/github-ready` workspace, setup/run reuse the workspace-root backend and database. A standalone clone uses this repository's backend. Run only one instance on port 8000.

## Edit the website

Keep the backend running. In a second PowerShell window:

```powershell
cd paw-protectors-web\website
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. Vite forwards API calls to port 8000. Run `npm.cmd run build` after edits to update the website served at `/app`.

## Connect the React Native app

Clone the mobile repository beside this one:

```text
Projects/
  paw-protectors-web/                 # common backend/database + React JS
  paw-protectors-App-react-native/    # mobile client
```

Follow the mobile README to build/open Paw Protectors RN. For USB, forward port 8000 and use `http://127.0.0.1:8000` in Account → Server connection. The installed standalone app needs the common backend but does not need Metro.

For trusted Wi-Fi development, use `run.ps1 -ListenAddress 0.0.0.0`, connect laptop and phone to the same network, and enter `http://LAPTOP_IPV4:8000` in the app. Allow that port on the private network if Windows prompts. Public hosting requires HTTPS, PostgreSQL and persistent uploaded-photo storage. Never put database credentials in the mobile app.

## Use an existing PostgreSQL server

Create a private `.env` from `.env.example`, set your own `DATABASE_URL` and random `TOKEN_SECRET` (at least 32 characters), then use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -ExternalDatabase
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1 -ExternalDatabase
```

Build the website before starting. Create a separate `paw_test` database for verification.

## Verification

```powershell
.\.venv\Scripts\python.exe -m scripts.verify
.\.venv\Scripts\python.exe -m scripts.backup_restore_test
```

Verification uses disposable PostgreSQL schemas in `paw_test`, not application records. The GitHub publication check passed 44 backend tests from a clean checkout, 22 mobile client tests, TypeScript, the web build and the mobile Android bundle. The mobile API integration also passed against this packaged common backend. Earlier APK, phone and browser checks are documented separately.

## Data and documentation

GitHub contains source, migrations and public reference configuration. `.env`, password lists/mailbox, databases/backups, uploaded photos, generated APKs, build output and downloaded tools are excluded. A new clone creates its own data. Back up PostgreSQL and `uploads/` separately.

- [Optional illustrated demo catalogue](docs/DEMO_CATALOGUE.md)
- [Adoption](docs/ADOPTION_MODULE.md)
- [Pet Shop](docs/PET_SHOP_MODULE.md)
- [Care modules](docs/CARE_MODULES.md)
- [Measured phone acceptance and remaining checks](docs/PHONE_ACCEPTANCE_2026-11-03.md)
