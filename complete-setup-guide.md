# Complete local setup guide

Set up Data Agent from a Windows machine through the first successful SQL Server question. This guide runs PostgreSQL, the backend, and the frontend directly on Windows; Ubuntu under WSL runs Redis. Docker is not required for this setup.

For subsequent daily starts, use [manual-start.md](manual-start.md).

## 1. What you are installing

| Component | Purpose | Where it runs |
| --- | --- | --- |
| Git | Download and update the source | Windows |
| Python 3.12, 64-bit | Backend API and background worker | Windows |
| Node.js 24 LTS with npm | Frontend installation and development server | Windows |
| PostgreSQL 18 | Application accounts, conversations, jobs, settings, and artifacts | Windows |
| WSL 2 and Ubuntu | Linux environment for Redis | Windows/WSL |
| Redis server and tools | Job delivery and live event notifications | Ubuntu |
| Microsoft ODBC Driver 18 for SQL Server, x64 | Connect Python to Microsoft SQL Server | Windows |
| SQL Server Management Studio (SSMS) | Inspect SQL Server and check connectivity | Windows; recommended for setup |
| SQL Server Database Engine | Stores the business data queried by the app | Existing remote server, or optional local development instance |

Python 3.12, Node.js 24, and PostgreSQL 18 match the existing local setup. The backend declares Python 3.12 or newer, but this guide uses 3.12 as its baseline rather than assuming every newer Python version has compatible dependencies.

PostgreSQL is the application's internal database. Microsoft SQL Server is a separate business datasource. Installing SQL Server does not replace PostgreSQL.

### Commands, paths, and ports

- Run `powershell` blocks in **Windows PowerShell**. Use Administrator mode only where stated.
- Run `bash` blocks **inside Ubuntu**.
- Run PostgreSQL `sql` blocks in **psql** and SQL Server `sql` blocks in **SSMS**, as labeled.
- Replace example server names, business database names, account names, and password placeholders before using them.

Repository folder used throughout:

```text
D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc
```

| Service | Address in this setup |
| --- | --- |
| Frontend | http://localhost:12200 |
| Backend API | http://127.0.0.1:12201 |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |
| SQL Server | Your server's TCP port; commonly `1433` |

Ports `12202` and `12203` in the backend environment template are Docker host mappings. For this guide, use native ports `5432` and `6379` instead.

## 2. Install Git, Python, and Node.js

### Git

Download and install [Git for Windows](https://git-scm.com/install/windows). Enable command-line use during installation. Open a new PowerShell window afterward:

```powershell
git --version
```

### Python

Get a 64-bit Python 3.12 runtime from the [official Windows downloads](https://www.python.org/downloads/windows/). Include pip and make the chosen interpreter available on PATH. If using Python's install manager, install/select the 3.12 runtime.

Open a new PowerShell window and check:

```powershell
python --version
python -m pip --version
python -c "import sys, struct; print(sys.executable); print(struct.calcsize('P') * 8)"
```

The version should be Python 3.12.x and the final number should be `64`. If Windows opens the Store instead, check the Python installation, PATH, and Windows App execution aliases before continuing.

### Node.js and npm

Download a Windows x64 installer for **Node.js 24 LTS** from the [official Node.js downloads](https://nodejs.org/en/download). Select that version if the page defaults to a different major release. Include npm and PATH integration.

Open a new PowerShell window:

```powershell
node --version
npm.cmd --version
```

Use `npm.cmd` in this guide so PowerShell's script policy does not block `npm.ps1`.

## 3. Get the application source

If this repository already exists, skip cloning and use its current folder. For a new checkout:

```powershell
New-Item -ItemType Directory -Force -Path "D:\Projects\thermo-fisher\data-agent\poc" | Out-Null
Set-Location "D:\Projects\thermo-fisher\data-agent\poc"
git clone https://github.com/raghavendra-jayaramu-thermofisher/data-agent-poc.git
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc"
git branch --show-current
```

Authenticate through Git's normal sign-in flow if repository access requires it. For an existing checkout, inspect local changes before updating:

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc"
git status --short --branch
```

When on `main` and ready to update:

```powershell
git pull --ff-only origin main
```

If Git reports conflicting local changes or a divergent branch, resolve that separately before continuing; do not discard local work to complete setup.

## 4. Install and prepare PostgreSQL

### Install PostgreSQL

Use the [official PostgreSQL Windows installer page](https://www.postgresql.org/download/windows/) and select PostgreSQL 18, 64-bit. Install the server and command-line tools; pgAdmin is optional. Choose port `5432`, set an administrator password, and record the installation folder.

This machine uses:

```text
Client tools: D:\ProgramFiles\pgSQL\bin
Service:     postgresql-x64-18
```

The default installer folder on another machine may be `C:\Program Files\PostgreSQL\18`; substitute its `bin\psql.exe` path in the commands below.

Check the service:

```powershell
Get-Service *postgres*
```

If stopped, run this in **Administrator PowerShell**, using the actual service name:

```powershell
Start-Service postgresql-x64-18
```

### Inspect existing databases

Connect in PowerShell and enter the PostgreSQL administrator password at the prompt:

```powershell
& "D:\ProgramFiles\pgSQL\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

Inside **psql**:

```sql
SELECT datname, pg_get_userbyid(datdba) AS owner
FROM pg_database
WHERE NOT datistemplate
ORDER BY datname;

\du
```

Keep the standard `postgres` database. Existing databases do not need to be deleted to install this application. If `dbassistant` and its role already exist, reuse the configured application credentials and skip creation.

### Create the application role and database: new installations only

The following example uses the same local-development application credentials as the environment template. Inside **psql**, run only the statements for objects that do not already exist:

```sql
CREATE ROLE dbassistant WITH LOGIN PASSWORD 'dbassistant';
CREATE DATABASE dbassistant OWNER dbassistant;
\q
```

If you choose another application password, use it in the backend database URL later. This password is separate from the PostgreSQL administrator password and your Ubuntu password.

Verify the application login from PowerShell; enter its password when prompted:

```powershell
& "D:\ProgramFiles\pgSQL\bin\psql.exe" -h 127.0.0.1 -p 5432 -U dbassistant -d dbassistant -c "SELECT current_database(), current_user;"
```

Both values should be `dbassistant`.

## 5. Install WSL 2 and Ubuntu

Check whether Ubuntu already exists:

```powershell
wsl --status
wsl --list --verbose
```

For a new installation, run **Administrator PowerShell**:

```powershell
wsl --install -d Ubuntu
```

Restart Windows if requested. Then open PowerShell:

```powershell
wsl --update
wsl --list --verbose
```

Ubuntu should show version `2`. If an existing Ubuntu distribution uses version `1`, convert it:

```powershell
wsl --set-version Ubuntu 2
```

Launch Ubuntu:

```powershell
wsl -d Ubuntu
```

On first launch, create your Linux username and password. Password characters are not displayed when typing. This is the password used by `sudo`; it is independent of Windows and PostgreSQL credentials.

If installation reports that virtualization is unavailable, follow Microsoft's prerequisites for enabling virtualization/WSL on the machine. Sources: [WSL installation](https://learn.microsoft.com/en-us/windows/wsl/install) and [Ubuntu account/password setup](https://learn.microsoft.com/en-us/windows/wsl/setup/environment).

## 6. Install and verify Redis

Inside **Ubuntu**:

```bash
sudo apt update
sudo apt install -y redis-server redis-tools
sudo service redis-server start
redis-server --version
redis-cli ping
```

The last command should return `PONG`. `redis-tools` alone provides the CLI, not the server needed by the application. These installation/start commands follow [Microsoft's Redis-on-WSL guide](https://learn.microsoft.com/en-us/windows/wsl/tutorials/wsl-database).

For a new instance, you can inspect database 0 without deleting anything:

```bash
redis-cli -n 0 DBSIZE
redis-cli -n 0 --scan --pattern 'dbassistant:*'
```

An empty instance reports `0` keys. Redis data does not need to be cleared for normal application restarts.

Keep the Ubuntu terminal open. In a separate **Windows PowerShell** window, verify Windows can reach Redis through WSL's localhost forwarding:

```powershell
Test-NetConnection 127.0.0.1 -Port 6379
```

`TcpTestSucceeded` should be `True`. If it is false, resolve WSL/Redis connectivity before starting the application. Keep Redis on its local binding rather than exposing it to the network to work around a localhost problem.

## 7. Install the SQL Server client components

Do these steps on the Windows machine that runs the API and worker, even if the business database is remote.

### Microsoft ODBC Driver 18

1. Open Microsoft's [ODBC Driver for SQL Server downloads](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server).
2. Download the **x64 Microsoft ODBC Driver 18 for SQL Server** installer.
3. Run the installer and complete installation.
4. For Driver 18.6 or earlier, install the matching [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) prerequisite if absent. Microsoft's current download documentation states that Driver 18.7 and later do not require it to be preinstalled.

The backend's `pyodbc` and `aioodbc` Python packages do not install this Windows driver. The driver name expected by the application is exactly:

```text
ODBC Driver 18 for SQL Server
```

After installing the backend dependencies in section 9, verify discovery with the application's Python interpreter:

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\backend"
.\.venv\Scripts\python.exe -c "import pyodbc; print(pyodbc.drivers())"
```

The output must include `ODBC Driver 18 for SQL Server`. This setup uses a connection string, so creating a system/user ODBC DSN is not required.

### SQL Server Management Studio

Download and install [SSMS from Microsoft](https://learn.microsoft.com/en-us/ssms/install/install). It is useful for checking the database and configuring access. SSMS is a management client; it does not install the SQL Server Database Engine.

For an existing company SQL Server, obtain its server DNS name, TCP port, database name, schema, authentication method, and read-access approval from the database owner. Install the ODBC driver locally and skip the local engine installation below.

## 8. Prepare Microsoft SQL Server

### Optional: install a local development Database Engine

Skip this subsection when connecting to an existing SQL Server.

1. Get installation media from [Microsoft SQL Server downloads](https://www.microsoft.com/en-us/sql-server/sql-server-downloads). Developer edition is intended for development/testing rather than production use.
2. Run Setup and choose a new standalone installation.
3. Include **Database Engine Services**. The application does not require Analysis Services, Reporting Services, or Integration Services.
4. Choose a default or named instance and record its name.
5. Add your current Windows account as an administrator during Database Engine Configuration.
6. Choose Windows Authentication, or Mixed Mode if you will use SQL Authentication. Store any administrator credentials locally.
7. Finish installation and verify the SQL Server service is running.

See Microsoft's [SQL Server Installation Wizard guide](https://learn.microsoft.com/en-us/sql/database-engine/install-windows/install-sql-server-from-the-installation-wizard-setup).

### Configure TCP connectivity

The application connects using a host and TCP port. A local SSMS connection using shared memory is not sufficient to prove this path works.

For a **local development instance you administer**:

1. Open SQL Server Configuration Manager.
2. Open **SQL Server Network Configuration > Protocols for your instance** and enable **TCP/IP**.
3. In TCP/IP Properties, if **Listen All = Yes**, use the **IPAll** settings: clear **TCP Dynamic Ports** and set **TCP Port** to an available fixed port, such as `1433`. If Listen All is No, configure the intended IP entry instead.
4. Restart that SQL Server instance for the change to take effect.

For a company-managed server, use the DBA-provided port instead of changing its configuration. For access from another machine, the server firewall/network must permit the client to reach that TCP port. Explicit host/port connections avoid requiring SQL Server Browser instance discovery. Source: [SQL Server fixed TCP ports](https://learn.microsoft.com/en-us/sql/database-engine/configure-windows/configure-a-server-to-listen-on-a-specific-tcp-port).

In **Windows PowerShell**, test the actual host and port:

```powershell
Test-NetConnection 127.0.0.1 -Port 1433
```

Replace `127.0.0.1` with the remote DNS name when appropriate. The result should include `TcpTestSucceeded : True`.

### Check the connection in SSMS

Connect to `tcp:127.0.0.1,1433`, or `tcp:YOUR_SERVER,YOUR_PORT`, using the intended authentication method. Run in an SSMS query window:

```sql
SELECT @@SERVERNAME AS server_name,
       DB_NAME() AS database_name,
       SUSER_SNAME() AS login_name;
```

Select the business database and confirm the expected tables/views exist. A new SQL Server installation has no business data; restore/import an authorized backup or use an existing populated datasource before expecting business answers.

### Choose authentication and read permissions

These are **SQL Server** permissions, separate from the `dbassistant` PostgreSQL role. A database administrator should apply grants to the intended business database and schemas.

**Windows Authentication:** run the API and worker directly on Windows under the same authorized account. Check the account from both PowerShell windows with:

```powershell
whoami
```

The account running these processes is used for SQL Server access; the browser user's identity and an Ubuntu account are not substituted. The adapter rejects Windows Authentication when run on Linux/WSL.

Example for a new Windows login/user, run by a SQL Server administrator in **SSMS**. Replace the account and database names; skip objects that already exist:

```sql
USE [master];
GO
CREATE LOGIN [DOMAIN\YourUser] FROM WINDOWS;
GO
USE [YourBusinessDatabase];
GO
CREATE USER [DOMAIN\YourUser] FOR LOGIN [DOMAIN\YourUser];
GRANT SELECT ON SCHEMA::[dbo] TO [DOMAIN\YourUser];
GRANT VIEW DEFINITION ON SCHEMA::[dbo] TO [DOMAIN\YourUser];
GO
```

Use your actual `whoami` identity, such as a domain or computer account recognized by that SQL Server. For a remote company server, the DBA may grant access through an existing Windows group instead.

**SQL Authentication:** use a dedicated SQL Server login and password. The server must support Mixed Mode. On a server you administer, enable **SQL Server and Windows Authentication mode** in SSMS server properties if required, then restart the instance. Source: [authentication mode configuration](https://learn.microsoft.com/en-us/sql/database-engine/configure-windows/change-server-authentication-mode).

Example for a new SQL login/user, run by an administrator in **SSMS**. Replace the password placeholder and database name first:

```sql
USE [master];
GO
CREATE LOGIN [data_agent_reader]
WITH PASSWORD = '<REPLACE_WITH_A_STRONG_PASSWORD>';
GO
USE [YourBusinessDatabase];
GO
CREATE USER [data_agent_reader] FOR LOGIN [data_agent_reader];
GRANT SELECT ON SCHEMA::[dbo] TO [data_agent_reader];
GRANT VIEW DEFINITION ON SCHEMA::[dbo] TO [data_agent_reader];
GO
```

Grant only the schemas/objects the application should query. The application login does not need server administration or database write access. See Microsoft's [login creation](https://learn.microsoft.com/en-us/sql/relational-databases/security/authentication-access/create-a-login) and [schema permission reference](https://learn.microsoft.com/en-us/sql/t-sql/statements/grant-schema-permissions-transact-sql).

### Encryption and certificates

The application's SQL Server defaults are **Encrypt = true** and **Trust server certificate = false**. Use a server certificate trusted by the client and a matching host name. For a local development instance with a self-signed certificate, you can explicitly enable Trust server certificate in the datasource form; this bypasses certificate verification while retaining encryption. See Microsoft's [ODBC encryption and certificate settings](https://learn.microsoft.com/en-us/sql/connect/odbc/dsn-connection-string-attribute).

## 9. Install and configure the backend

Run this in **Windows PowerShell**, not Ubuntu:

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\backend"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
notepad .env
```

The install command includes `pyodbc`, `aioodbc`, PostgreSQL clients, Redis support, and the agent dependencies declared by this repository. Explicitly invoking the virtual environment's Python avoids needing to change PowerShell activation policy.

Set these environment values, then save the file:

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://dbassistant:dbassistant@127.0.0.1:5432/dbassistant
REDIS_URL=redis://127.0.0.1:6379/0
CORS_ORIGINS=["http://localhost:12200","http://127.0.0.1:12200"]
PASSWORD_RESET_URL_BASE=http://localhost:12200/reset-password
EMAIL_BACKEND=console
DATA_DIRECTORY=./runtime-data
```

Use the application password you actually configured in PostgreSQL. If it contains URL-special characters, URL-encode the password portion of `DATABASE_URL`. SQL Server host/database credentials are entered in the application's datasource form later, not substituted into this PostgreSQL URL.

### Application secrets: generate once for a fresh installation

For a new environment, generate a JWT secret:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the result as `JWT_SECRET` in `.env`. Generate the encryption key:

```powershell
.\.venv\Scripts\python.exe -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Set the following in `.env`, replacing the placeholder with that output:

```dotenv
SECRET_ENCRYPTION_CURRENT_VERSION=v1
SECRET_ENCRYPTION_KEYS={"v1":"PASTE_THE_GENERATED_KEY_HERE"}
```

Preserve existing secrets when reusing an environment. In particular, changing the encryption key without retaining the old key makes existing encrypted datasource/model credentials unreadable. Keep `.env` private; the repository ignores it. Application runtime files are stored under the backend's `runtime-data` folder.

Now check that the Python ODBC client discovers Driver 18:

```powershell
.\.venv\Scripts\python.exe -c "import pyodbc; print(pyodbc.drivers())"
```

## 10. Create/update the application schema

With PostgreSQL running, execute from the **backend folder**:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
```

`current` should match `heads`. Apply migrations before starting the API and worker. They also create the checkpoint tables used to pause/resume analyses. Stop at any migration error rather than starting against a partially configured schema.

## 11. Install and configure the frontend

In another **Windows PowerShell** window:

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\frontend"
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
npm.cmd ci --legacy-peer-deps
notepad .env
```

Confirm the frontend environment file contains:

```dotenv
VITE_API_BASE_URL=http://localhost:12201
```

Keep provider API keys and database passwords out of the frontend environment. The browser calls the backend API; the backend owns those connections.

## 12. Start all application processes

Keep the Ubuntu Redis window open. PostgreSQL should already be running as a Windows service.

**API: Windows PowerShell window 1**

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 12201
```

**Worker: Windows PowerShell window 2**

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\backend"
.\.venv\Scripts\python.exe -m app.worker
```

**Frontend: Windows PowerShell window 3**

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\frontend"
npm.cmd run dev
```

The API and worker must use the same backend environment and authorized Windows identity when using SQL Server Windows Authentication. Keep all three windows running.

In a separate PowerShell window, check readiness:

```powershell
Invoke-RestMethod "http://127.0.0.1:12201/ready" | ConvertTo-Json
```

Expected response:

```json
{
  "status": "ready",
  "components": {
    "postgres": "ready",
    "redis": "ready"
  }
}
```

Open http://localhost:12200. Readiness checks the internal PostgreSQL and Redis connections. It does not verify SQL Server, the model provider, or whether a worker is processing jobs.

## 13. Configure the application and ask the first question

### Create your account/workspace

Choose Sign up and enter your email, display name, organization name, and application password. This account is separate from the database/Ubuntu accounts. The signup screen lists its password requirements.

### Add the SQL Server datasource

In **Data sources**, add a relational datasource and choose **Microsoft SQL Server**:

| Field | Value |
| --- | --- |
| Data source name | A recognizable name for the business database |
| Host | SQL Server DNS name, or `127.0.0.1` for a local instance |
| Port | Actual TCP port; `1433` only if configured that way |
| Database | Existing business database name |
| Schema | `dbo`, or the actual schema you have permission to query |
| Authentication method | Windows Authentication or SQL Authentication, as configured above |
| Username/password | Dedicated SQL login for SQL Authentication; omitted for Windows Authentication |
| ODBC driver | `ODBC Driver 18 for SQL Server` |
| Encrypt | Enabled |
| Trust server certificate | Disabled for a trusted certificate; explicitly enable for a self-signed local development instance if needed |

Use a plain server host plus the separate port field, rather than copying SSMS's `tcp:HOST,PORT` string into Host. For a named instance, obtain/configure its actual TCP port.

Save the datasource and run its connection test. Check the job/diagnostics result. Then open its knowledge/schema view and choose **Generate schema**, or **Refresh schema** if schema knowledge already exists. Wait for the background job to finish and confirm tables/views appear.

### Add a model connection and profile

In **Models**, add the provider connection using its OpenAI-compatible API base URL and API key. Use **Test connection** on its detail page to confirm access and discover available models. Then add a model profile with the exact model identifier available through that connection, enable it, and select a workspace default if desired.

Only use model settings supported by that provider/model. Pricing fields are optional cost-estimation inputs in USD per million tokens; leave them blank if unknown and consult the provider's current pricing instead of copying stale rates.

### Run an end-to-end check

1. Open **Ask** and select the SQL Server datasource and model profile.
2. Ask a small question using a table and columns you verified exist, such as a count grouped by a known category.
3. Confirm the job starts, progress appears, and an answer is returned.
4. Open execution details and inspect the SQL and datasource used.
5. Compare the query result with the same read-only SQL in SSMS against the same database and data snapshot.

This checks the browser, API, Redis, worker, model connection, SQL Server driver, authentication, permissions, and result delivery together.

## 14. Subsequent starts, updates, and stopping

Use [manual-start.md](manual-start.md) for daily startup. Database creation, package installation, and secret generation are not daily tasks.

After pulling updates, install changed dependencies as needed and apply migrations before restarting the API and worker. Restart the frontend after changing its environment file. Keep the existing application database, `.env`, encryption keys, and `runtime-data` across normal restarts.

To stop: press `Ctrl+C` in the frontend, worker, and API windows; let active worker jobs finish. Inside Ubuntu, run `sudo service redis-server stop`, then `exit`. PostgreSQL and a local SQL Server may remain running as Windows services.

## 15. Troubleshooting

| Symptom | Check/action |
| --- | --- |
| `python`/`node`/`git` not recognized | Reopen PowerShell after installation and verify PATH. |
| `npm.ps1` blocked by execution policy | Use `npm.cmd` as shown. |
| WSL virtualization error | Check the Microsoft WSL prerequisites, virtualization settings, and any requested Windows restart. |
| Forgotten Ubuntu password | In PowerShell run `wsl -d Ubuntu -u root`; inside Ubuntu run `passwd YOUR_UBUNTU_USERNAME` with your actual username, then `exit`. Reopen Ubuntu normally. Resetting a password does not require deleting the distribution. |
| Redis unit/CLI not found | Install `redis-server` and `redis-tools` inside the Ubuntu distribution you actually launch. |
| Redis works in Ubuntu but Windows cannot connect | Keep Ubuntu open, check `Test-NetConnection 127.0.0.1 -Port 6379`, and verify WSL localhost forwarding/network policy. |
| PostgreSQL connection refused | Check its Windows service and backend URL port `5432`. |
| PostgreSQL password authentication failed | Test with psql and check whether the failing login is the administrator or application role. |
| App still tries ports `12202`/`12203` | Correct backend `.env`, run from the backend folder, and restart API/worker. Check for inherited environment variables overriding the file. |
| SQL Server driver/DSN not found, such as `IM002` | Install the x64 ODBC Driver 18 and verify `pyodbc.drivers()` using the backend virtual environment. |
| SQL Server connection timeout/refused | Check host, actual TCP port, TCP/IP enablement, instance restart, VPN, firewall, and Windows `Test-NetConnection`. |
| SSMS connects but app cannot | Retest SSMS with explicit `tcp:HOST,PORT`; confirm both use the same identity, database, encryption, and trust settings. |
| SQL Server certificate chain/name error | Use a trusted certificate and matching DNS name; for self-signed local development, explicitly set Trust server certificate. |
| SQL Server login/database access denied | Check Windows process identity or SQL login credentials, Mixed Mode for SQL logins, database user mapping, and SELECT/metadata grants. |
| Windows Authentication unsupported | Run API and worker with Windows Python, not in WSL or a Linux container. |
| Schema explorer is empty | Check schema name, populated tables/views, SELECT/metadata permissions, and the schema-generation job result. |
| Jobs remain queued | Check that the worker is running with the same PostgreSQL/Redis settings as the API. |
| Worker reports unavailable checkpoint tables | Apply migrations with `alembic upgrade head`, then restart the worker. |
| Saved connections become unreadable | Restore the original encryption key configuration rather than generating another new key. |
| Application is ready but analysis fails | Check the datasource test, model connection/profile, provider access, and worker execution diagnostics. |
| Address already in use | Check existing API/frontend windows and listening processes before launching another copy. |

For SQL Server driver installation details, Microsoft's [Windows ODBC installation reference](https://learn.microsoft.com/en-us/sql/connect/odbc/windows/system-requirements-installation-and-driver-files) covers supported platforms and driver setup.
