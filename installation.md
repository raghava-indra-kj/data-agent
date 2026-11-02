# Data Agent — Windows Installation Guide

Set up Data Agent on a new Windows machine. Five pieces of system software, then the
application and its PostgreSQL database. Allow about 60 minutes on a clean machine.

**Redis and WSL are not required.** The `stable` branch runs entirely on PostgreSQL.

---

## 1. Downloads

Every link below was checked on 2 November 2026. The **direct download** column starts the
file immediately; the **download page** always shows the current release if the pinned
version has moved on.

| # | Software | Pinned version | Direct download (x64) | Download page |
| --- | --- | --- | --- | --- |
| 1 | Python | 3.13.15 | [python-3.13.15-amd64.exe](https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe) | [python.org/downloads/windows](https://www.python.org/downloads/windows/) |
| 2 | Node.js | 24.22.2 LTS | [node-v24.22.2-x64.msi](https://nodejs.org/dist/v24.22.2/node-v24.22.2-x64.msi) | [nodejs.org/en/download](https://nodejs.org/en/download) |
| 3 | PostgreSQL | 16, 17 or 18 | *(choose on the page)* | [enterprisedb.com/downloads/postgres-postgresql-downloads](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads) |
| 4 | ODBC Driver for SQL Server | 18.7.1.1 | [msodbcsql18 x64](https://go.microsoft.com/fwlink/?linkid=2378279) | [Microsoft download page](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) |
| 5 | Visual C++ Redistributable *(usually already present)* | latest | [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe) | [Latest supported downloads](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) |

### Version requirements

| Software | Minimum the project enforces | Where that comes from |
| --- | --- | --- |
| Python | `>=3.12` | `backend/pyproject.toml` |
| Node.js | `>=22.22.2` | `frontend/package.json` |
| PostgreSQL | 14+ | migrations use `SKIP LOCKED` and `LISTEN`/`NOTIFY` |
| ODBC Driver | 18 | default in the MSSQL datasource config |

Newer patch releases are fine. The pinned versions are what this guide was verified
against, and pinning them keeps every developer machine identical.

**Not x64?** Use [x86](https://go.microsoft.com/fwlink/?linkid=2378646) or
[ARM64](https://go.microsoft.com/fwlink/?linkid=2378647) for the ODBC driver, and pick the
matching installer on each download page for the rest.

---

## 2. Before you begin

Have these ready before you start:

- **Local Administrator rights** — every installer below needs them.
- **Read access to the Git repository**, and the `stable` branch.
- **PostgreSQL superuser password**, or a database user that already has `CREATEDB`.
- **SQL Server connection details**: host, port (default `1433`), database name, schema
  (usually `dbo`), and a SQL login username and password.
- **An OpenAI-compatible model endpoint**: base URL and API key. The application cannot
  answer questions without one. This is configured inside the app, not in a file.

Run every command below in **Windows PowerShell**. Open it with "Run as administrator"
only where a step says so.

---

## 3. Step 1 — Visual C++ Redistributable

**Most machines can skip this.** Windows usually has it already, and ODBC Driver **18.7
and later no longer require it** — Microsoft removed the prerequisite in 18.7.

Do this step only if the check below finds nothing, or if you are installing ODBC Driver
18.6 or earlier, where the installer fails without it and the error does not say why.

### Check

```powershell
Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*, HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "*Visual C++*Redistributable*" } | Select-Object -ExpandProperty DisplayName -Unique
```

If you see a line containing `Visual C++` and `(x64)`, you already have it — skip to
step 2. Most Windows machines do.

### Install

Download and run [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe),
accept the licence, then restart if prompted.

### Verify

Run the check command again. You should now see something like:

```
Microsoft Visual C++ v14 Redistributable (x64) - 14.51.36247
```

---

## 4. Step 2 — Python

### Check

```powershell
python --version
```

Expected: `Python 3.12.x` or `Python 3.13.x`.

If you see `Python was not found` or a Microsoft Store page opens, Python is not properly
installed. Continue to Install.

> **Note on Microsoft Store Python.** The Store version works, but installs to a sandboxed
> path and can behave oddly with virtual environments and PATH. For a shared machine,
> prefer the python.org installer below.

### Install

1. Download the **Windows installer (64-bit)** for Python 3.13.x from
   [python.org/downloads/windows](https://www.python.org/downloads/windows/).
2. On the first screen, tick **"Add python.exe to PATH"**. This is the single most
   commonly missed step.
3. Choose **Install Now**.
4. If offered at the end, click **Disable path length limit**.

### Verify

**Close your PowerShell window and open a new one** — PATH changes do not apply to windows
that are already open.

```powershell
python --version
```

```powershell
python -m pip --version
```

Both must return a version. Confirm it is the 64-bit build:

```powershell
python -c "import platform, sys; print(platform.architecture()[0], sys.executable)"
```

Expected: `64bit` followed by the install path.

### Fix PATH if the check still fails

List what the Python launcher can see:

```powershell
py -0p
```

Then add the folder it reports (and its `Scripts` subfolder) to your user PATH:

```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\Python313;C:\Program Files\Python313\Scripts", "User")
```

Open a new PowerShell window and check again.

---

## 5. Step 3 — Node.js

### Check

```powershell
node --version
```

Expected: `v22.22.2` or higher.

### Install

1. Download the **Windows Installer (.msi, 64-bit)** LTS build from
   [nodejs.org/en/download](https://nodejs.org/en/download).
2. Accept the defaults. The installer adds Node to PATH automatically.
3. You do **not** need the "Tools for Native Modules" option — every Python and Node
   dependency this project uses ships a prebuilt binary.

### Verify

In a **new** PowerShell window:

```powershell
node --version; npm.cmd --version
```

Expected: a Node version of `v22.22.2` or higher, and an npm version.

> Use `npm.cmd` rather than `npm` in PowerShell. It calls the Windows executable directly
> and avoids the script execution policy prompt.

---

## 6. Step 4 — PostgreSQL

This stores the application's own data: accounts, datasource definitions, conversations,
knowledge and the job queue.

### Check

```powershell
Get-Service -Name postgresql*
```

Expected: a service such as `postgresql-x64-18` with status `Running`.

### Install

Download the installer from
[postgresql.org/download/windows](https://www.postgresql.org/download/windows/) and accept
the defaults. **Record the `postgres` superuser password you set** — you need it in the
next step.

### Create the application database and user

Every machine uses the same names and password, so one `.env` works everywhere:

| Setting | Value |
| --- | --- |
| Database | `data_agent` |
| Role | `data_agent_admin` |
| Password | `root` |

> **Local development only.** This password is deliberately trivial so every developer
> machine matches. PostgreSQL here listens on `127.0.0.1` and holds no production data. For
> any shared, hosted or internet-reachable server, use a real password and a role without
> `CREATEDB`.

Run this as administrator. It prompts for the `postgres` password:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h 127.0.0.1 -c "CREATE ROLE data_agent_admin LOGIN PASSWORD 'root';" -c "CREATE DATABASE data_agent OWNER data_agent_admin;"
```

Setting `OWNER` matters — it gives the application full rights on its own database, so no
further grants are needed.

### Verify

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U data_agent_admin -h 127.0.0.1 -d data_agent -c "SELECT current_database(), current_user;"
```

Expected: one row showing `data_agent` and `data_agent_admin`.

---

## 7. Step 5 — Microsoft ODBC Driver 18 for SQL Server

Required for SQL Server datasources. Install it on **every machine that runs the API or
the worker**, since both open database connections.

### Check

```powershell
Get-OdbcDriver -Platform 64-bit | Where-Object { $_.Name -like "*SQL Server*" } | Select-Object -ExpandProperty Name
```

Expected to include `ODBC Driver 18 for SQL Server`.

### Install

1. Download **msodbcsql18.msi**, version 18.7.1.1, released 7 September 2026:
   [x64](https://go.microsoft.com/fwlink/?linkid=2378279) ·
   [x86](https://go.microsoft.com/fwlink/?linkid=2378646) ·
   [ARM64](https://go.microsoft.com/fwlink/?linkid=2378647)
2. Run it, accept the licence, and keep the default feature set (the ODBC driver itself).
   The SDK component is optional.

Installing 18.7.x upgrades any earlier 18.x in place. Driver 17 can stay installed
alongside; they do not conflict.

> **18.7 dropped the Visual C++ prerequisite.** If you install 18.7.1.1 or later you can
> skip step 1 entirely. Only 18.6 and earlier need the redistributable preinstalled.

The x64 and ARM64 installers each install both the 64-bit and 32-bit drivers.

### Verify

```powershell
Get-OdbcDriver -Name "ODBC Driver 18 for SQL Server" -Platform 64-bit
```

A result means Windows has it registered. An error means it is not installed.

To inspect drivers in the Windows UI, run `odbcad32.exe` and open the **Drivers** tab.

You do not need to create a DSN. The application builds its own connection string, so
step 12's **Test connection** is the real check that the driver can reach your server.

---

## 8. Step 6 — Install the application

### Get the code

```powershell
git clone https://github.com/raghavendra-jayaramu-thermofisher/data-agent-poc.git C:\Projects\data-agent
```

```powershell
Set-Location C:\Projects\data-agent; git checkout stable
```

### Create the virtual environment and install dependencies

```powershell
Set-Location C:\Projects\data-agent\backend; python -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

This takes a few minutes. It installs FastAPI, SQLAlchemy, the SQL Server drivers
(`pyodbc`, `aioodbc`), MySQL, DuckDB, Excel support and the agent stack. No compiler is
needed — every package ships a prebuilt wheel for Windows.

### Verify

```powershell
.\.venv\Scripts\python.exe -c "import fastapi, sqlalchemy, pyodbc, asyncpg; print('backend dependencies OK')"
```

---

## 9. Step 7 — Configure the backend

One command. Nothing to edit.

```powershell
Copy-Item .env.example .env
```

`.env.example` ships working development values for everything, including the database URL
built from the names in step 4. If you used `data_agent` / `data_agent_admin` / `root`,
this file is already correct and you can go straight to step 8.

`.env` is excluded from Git, so each machine keeps its own copy and nothing secret is ever
committed.

### What the shipped defaults are

| Setting | Shipped value | What it does |
| --- | --- | --- |
| `JWT_SECRET` | a fixed development string | Signs sign-in tokens |
| `SECRET_ENCRYPTION_KEYS` | `{"v1":"IKDwa…"}` | Encrypts saved datasource passwords |
| `SECRET_ENCRYPTION_CURRENT_VERSION` | `v1` | Names the key above to encrypt with |

These are deliberately shared so a new machine works immediately. The application refuses
to start with them when `APP_ENV=production`, so they cannot reach a real deployment by
accident.

> **One thing to know before connecting a production SQL Server.** The shipped encryption
> key is in this repository, so any datasource password saved on a default install can be
> decrypted by anyone who has both the repo and that database. For test and read-only
> logins that is fine. If you save credentials for a real server, generate your own key
> first — see below.

### Generating your own secrets

Only needed for a shared host, or before saving credentials you care about.

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

```powershell
.\.venv\Scripts\python.exe -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Put the first in `JWT_SECRET` and the second in `SECRET_ENCRYPTION_KEYS` as
`{"v1":"<key>"}`. The key must decode to exactly 32 bytes, and
`SECRET_ENCRYPTION_CURRENT_VERSION` must name a key present in the map, or the application
refuses to start.

> **Do not change `SECRET_ENCRYPTION_KEYS` once datasources have been saved.** Changing it
> makes every stored credential unreadable.

---

## 10. Step 8 — Run the database migrations

```powershell
Set-Location C:\Projects\data-agent\backend; .\.venv\Scripts\python.exe -m alembic upgrade head
```

This creates all tables from an empty database.

### Verify

```powershell
.\.venv\Scripts\python.exe -m alembic current
```

Expected: the latest revision, ending in `(head)`.

---

## 11. Step 9 — Install the frontend

```powershell
Set-Location C:\Projects\data-agent\frontend; npm.cmd install
```

Create `frontend\.env.local` containing:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:12201
```

```powershell
"VITE_API_BASE_URL=http://127.0.0.1:12201" | Out-File -Encoding ascii .env.local
```

---

## 12. Step 10 — Start the application

Three PowerShell windows, each left open.

**Window 1 — API** (port 12201):

```powershell
Set-Location C:\Projects\data-agent\backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 12201 --timeout-graceful-shutdown 3
```

**Window 2 — Worker** (background jobs and analyses):

```powershell
Set-Location C:\Projects\data-agent\backend; .\.venv\Scripts\python.exe -m app.worker
```

Wait for `worker_started`.

**Window 3 — Frontend** (port 12200):

```powershell
Set-Location C:\Projects\data-agent\frontend; npm.cmd run dev
```

---

## 13. Step 11 — Verify the installation

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:12201/ready | ConvertTo-Json -Depth 4
```

Expected: `status` is `ready` and `components.postgres` is `ready`.

There is no `redis` component. If you see one, you are running an older branch.

```powershell
(Invoke-WebRequest -Uri http://127.0.0.1:12200 -UseBasicParsing).StatusCode
```

Expected: `200`.

Then open <http://127.0.0.1:12200> and choose **Sign up** to create the first account. The
first account becomes the workspace owner.

Finally, configure your model provider in the application: **Settings → Models**, where you
enter the base URL and API key of your OpenAI-compatible endpoint.

---

## 14. Step 12 — Connect a SQL Server datasource

This uses **SQL authentication** — a SQL Server login and password, stored encrypted.

1. In the application, go to **Data sources → Add data source**.
2. Choose **Microsoft SQL Server**.
3. Select **SQL authentication**.
4. Fill in:

| Field | Value |
| --- | --- |
| Host | your SQL Server hostname or IP |
| Port | `1433` unless changed |
| Database | the database to query |
| Schema | `dbo` unless yours differs |
| Username | the SQL login |
| Password | the login's password |
| ODBC driver | `ODBC Driver 18 for SQL Server` |
| Encrypt | on (default) |
| Trust server certificate | off, unless the server uses a self-signed certificate |

5. Click **Test connection**. It must succeed before you continue.
6. Choose the tables to expose, then **generate knowledge**.

> **On "Trust server certificate".** Driver 18 encrypts by default and validates the
> server's certificate. If your SQL Server uses a self-signed certificate, the test fails
> with a certificate chain error until you turn this on. Prefer installing a trusted
> certificate on the server where you can.

The SQL login needs only `SELECT` on the tables you expose. A read-only account is
recommended — the application never writes to your data sources.

---

## 15. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Python was not found` | Not on PATH, or a Store alias | Reinstall with "Add python.exe to PATH" ticked, then open a new window |
| `node` or `npm.cmd` not recognised | PATH not refreshed | Open a new PowerShell window |
| `npm : cannot be loaded ... execution policy` | PowerShell script policy | Use `npm.cmd` instead of `npm` |
| ODBC driver installer fails immediately | Visual C++ Redistributable missing (only affects 18.6 and earlier) | Complete step 1, or install 18.7.1.1 which does not need it |
| `Data source name not found and no default driver specified` | Driver 18 not installed, or name misspelled | Run the step 5 check; the name must match exactly |
| `SSL Provider: The certificate chain was issued by an authority that is not trusted` | Self-signed certificate on SQL Server | Enable "Trust server certificate" on the datasource |
| `Login failed for user` | Wrong SQL credentials, or SQL auth disabled on the server | Verify in SSMS; the server must allow SQL Server authentication |
| API exits with `SECRET_ENCRYPTION_CURRENT_VERSION must exist in SECRET_ENCRYPTION_KEYS` | Version name does not match a key | Make sure the version (e.g. `v1`) appears in the JSON map |
| `Encryption key v1 must decode to exactly 32 bytes` | Key generated wrongly | Regenerate with the command in step 7 |
| API fails on a missing column | Migrations not run | Run step 8 |
| Jobs stay queued forever | Worker not running | Start window 2 and look for `worker_started` |
| Port 12200 or 12201 already in use | Another instance is running | Stop it, or change the port |
| Browser cannot reach the API | `VITE_API_BASE_URL` or CORS mismatch | Check `frontend\.env.local` and `CORS_ORIGINS` in `backend\.env` |

To find and stop stray processes:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn app.main|app\.worker|vite' } | Select-Object ProcessId, CommandLine
```

---

## 16. Reference machine

This guide was verified against:

| Component | Version |
| --- | --- |
| Windows | 11 Enterprise 26200 |
| Python | 3.13.14 (64-bit) |
| Node.js | v24.19.0 |
| npm | 11.17.0 |
| PostgreSQL | 18 |
| ODBC Driver for SQL Server | 18 (17 also present) |
| Visual C++ Redistributable | v14 (x64) 14.51.36247 |

---

## 17. Stopping the application

Press **Ctrl+C** in each window, in this order: frontend, worker, API.

PostgreSQL can keep running; it starts with Windows by default. There is no Redis service
and no WSL instance to shut down.
