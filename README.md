# Paw Protectors — React website + Python backend

Smart Pet Care and Management System with Advanced Database Transaction Processing.

This repository contains the **React website**, **FastAPI backend**, **PostgreSQL schema**, database demonstrations and tests. It contains **no Android application**. The companion repository is named `paw-protectors-android`.

## Requirements on Windows

- Python 3.12 with Python added to PATH: https://www.python.org/downloads/windows/
- Node.js 24 LTS (includes npm): https://nodejs.org/
- Git: https://git-scm.com/downloads/win
- Internet access for the first dependency downloads. No Docker or emulator is needed.

## First-time setup

1. Open the Windows Start menu, type **PowerShell**, and open it. Administrator mode is not required for these project commands.
2. Clone this repository:

```powershell
New-Item -ItemType Directory -Force "$HOME\Projects" | Out-Null
Set-Location "$HOME\Projects"
git clone https://github.com/Vivek-pateriya/paw-protectors-web.git
Set-Location .\paw-protectors-web
python --version
node --version
npm --version
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
Set-Location .\website
npm ci
npm run build
Set-Location ..
```

`setup.ps1` creates `.venv`, downloads PostgreSQL binaries into `.tools`, starts a private database on `127.0.0.1:55432`, applies migrations, seeds sample data, and generates `.env` and `artifacts/demo-credentials.txt`. It preserves existing user records. Do **not** copy `.env.example` to `.env` before this local setup; the script generates actual credentials. If `python` is unavailable but `py -3.12` works, use `py -3.12 -m venv .venv` first and then run the setup command above.

For an already installed/configured PostgreSQL server, create `.env` using `.env.example`, provide your own database URL and random signing secret, and use `setup.ps1 -ExternalDatabase`. Create a separate `paw_test` database before running PostgreSQL tests. This mode does not download or start the private cluster.

## Run the website

In PowerShell, open the cloned repository directory and run:

```powershell
Set-Location "$HOME\Projects\paw-protectors-web"
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Keep this terminal open. Open **http://127.0.0.1:8000/** in Chrome or Edge. The built React website and REST API use the same server. API documentation is at **http://127.0.0.1:8000/docs**; health is at `/health`.

For your own PostgreSQL server use `run.ps1 -ExternalDatabase`. If another Paw Protectors backend already listens on port 8000, use it for React development rather than starting a second server. To share the same database with Android, configure both backends with the same `DATABASE_URL` and `TOKEN_SECRET`, or run only one backend. Do not initialize two local clusters on port 55432 simultaneously.

## Edit React during development

Keep the backend terminal running. Open a **second PowerShell window**:

```powershell
Set-Location "$HOME\Projects\paw-protectors-web\website"
npm ci
npm run dev
```

Open **http://127.0.0.1:5173/**. Vite forwards API requests to port 8000; no permissive CORS configuration is required. After changes, run `npm run build` and restart the backend to serve the new build on port 8000. Do not open `index.html` directly from File Explorer.

## Login and features

Register a pet owner, or use `owner@paw.local`, `vet@paw.local`, or `admin@paw.local`. Find the generated password locally:

```powershell
Get-Content .\artifacts\demo-credentials.txt
```

Owner: pet profiles/photos, vaccination history, medical history, vet listings, bookings/cancellation and reminders. Veterinarian: assigned patients, clinical records, availability/slots and appointment completion. Admin: user roles/access, vet profiles, appointment monitoring, analytics and transaction audits. Backend roles and ownership protect all API operations. Photos use authenticated requests; passwords are hashed; sessions are revocable.

## Tests and faculty demonstrations

From the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
.\.venv\Scripts\python.exe -m scripts.http_smoke
.\.venv\Scripts\python.exe -m scripts.backup_restore_test
.\.venv\Scripts\python.exe -m scripts.inspect_db
Set-Location .\website
npm run build
```

`verify.ps1` runs real PostgreSQL integration/security tests, 100 simultaneous booking attempts (one success, 99 conflicts), rollback, READ COMMITTED, SERIALIZABLE, locking/deadlock recovery and a measured 200,000-row indexing benchmark. Results are written to ignored `artifacts/`. See `docs/DBMS_DEMO.md` for SQL demonstration commands and `docs/VERIFICATION.md` for executed checks. Tests use an isolated schema and preserve application records. Socket HTTP smoke tests need the running backend.

## Stop

Press **Ctrl+C** in the backend terminal (and the Vite terminal if used). Then, from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_db.ps1
```

Stop the private database only after all clients using it have stopped. Do not run this command for an external PostgreSQL server.

## Repository contents and security

`website/` — React/Vite source and package lockfile. `backend/` — FastAPI/Psycopg. `database/` — migrations, constraints, functions, triggers and views. `tests/`, `scripts/`, `docs/` — verification and Windows helpers.

`.env`, generated account credentials, photos, database files, `.venv`, downloaded tools, `node_modules`, build outputs and APKs are excluded from Git. Commit `.env.example` only. Local development uses loopback HTTP; remote deployment requires HTTPS and deployment configuration. The website is not automatically deployed by pushing this repository.
