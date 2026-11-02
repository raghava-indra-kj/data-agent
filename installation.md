# Data Agent — Windows Installation Guide

Set up Data Agent on a new Windows machine. Five pieces of system software, then the
application and its PostgreSQL database. Allow about 60 minutes on a clean machine.

**Redis and WSL are not required.** The `stable` branch runs entirely on PostgreSQL.

---

## 1. Versions at a glance

| # | Software | Install this | Minimum enforced | Where |
| --- | --- | --- | --- | --- |
| 1 | Visual C++ Redistributable | Latest x64 (14.4x+) | — | [aka.ms/vs/17/release/vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| 2 | Python | 3.13.x (64-bit) | `>=3.12` | [python.org/downloads/windows](https://www.python.org/downloads/windows/) |
| 3 | Node.js | 22.x LTS or 24.x LTS | `>=22.22.2` | [nodejs.org/en/download](https://nodejs.org/en/download) |
| 4 | PostgreSQL | 16, 17 or 18 | 14+ | [postgresql.org/download/windows](https://www.postgresql.org/download/windows/) |
| 5 | ODBC Driver for SQL Server | **18** (18.6.2.1) | 18 | [Microsoft download page](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) |

**Install in this order.** Item 1 is a prerequisite for item 5 — the ODBC driver installer
fails without it.

Only the *minimum* column is enforced by the project. Patch releases newer than the
"install this" column are fine.

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

The Microsoft ODBC driver is built against the Visual C++ runtime. Install this first or
step 5 fails.

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

Run this as administrator. It prompts for the `postgres` password:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h 127.0.0.1 -c "CREATE ROLE dataagent LOGIN PASSWORD 'choose-a-strong-password';"
```

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h 127.0.0.1 -c "CREATE DATABASE dbassistant OWNER dataagent;"
```

Setting `OWNER` matters — it gives the application full rights on its own database, so no
further grants are needed.

### Verify

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U dataagent -h 127.0.0.1 -d dbassistant -c "SELECT current_database(), current_user;"
```

Expected: one row showing `dbassistant` and `dataagent`.

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

1. Confirm step 1 is done. The installer fails without the Visual C++ Redistributable.
2. Download **msodbcsql18.msi (x64)**, currently version 18.6.2.1, from the
   [Microsoft download page](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server).
3. Run it, accept the licence, and keep the default feature set (the ODBC driver itself).
   The SDK component is optional.

Installing 18.6.x upgrades any earlier 18.x in place. Driver 17 can stay installed
alongside; they do not conflict.

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
git clone https://github.com/<org>/data-agent-poc.git C:\Projects\data-agent
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

### Create the environment file

```powershell
Copy-Item .env.example .env
```

### Generate the secrets

Run each command and copy its output into `.env`.

A JWT signing secret (must be at least 32 characters):

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

A credential encryption key (must decode to exactly 32 bytes):

```powershell
.\.venv\Scripts\python.exe -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

### Edit `backend\.env`

Set these five values:

```dotenv
DATABASE_URL=postgresql+asyncpg://dataagent:choose-a-strong-password@127.0.0.1:5432/dbassistant
JWT_SECRET=<output of the first command>
SECRET_ENCRYPTION_CURRENT_VERSION=v1
SECRET_ENCRYPTION_KEYS={"v1":"<output of the second command>"}
DATA_DIRECTORY=./runtime-data
```

Note the exact shape of `SECRET_ENCRYPTION_KEYS`: a JSON object mapping a version name to
a base64 key. `SECRET_ENCRYPTION_CURRENT_VERSION` must name a key that exists in it, or
the application refuses to start.

> **Do not change `SECRET_ENCRYPTION_KEYS` once datasources have been saved.** It encrypts
> stored database credentials. Changing it makes every saved credential unreadable.

`.env` is excluded from Git. Each machine needs its own.

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
| ODBC driver installer fails immediately | Visual C++ Redistributable missing | Complete step 1, then retry |
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
