# Manual local startup

This guide uses PostgreSQL on Windows, Redis in Ubuntu/WSL, and separate Windows PowerShell windows for the API, worker, and frontend.

Project folder: `D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc`.

| Service | Local address |
| --- | --- |
| Frontend | http://localhost:12200 |
| API | http://127.0.0.1:12201 |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

These are the native Windows/WSL ports. The backend environment template uses Docker host ports `12202` and `12203`; change them as shown below.

## Daily startup

If the database, dependencies, and environment files are already configured, start here. Starting the application does not require deleting database or Redis data.

### 1. Check PostgreSQL

In Windows PowerShell:

```powershell
Get-Service postgresql-x64-18
```

The status should be `Running`. If it is stopped, open PowerShell as Administrator and run:

```powershell
Start-Service postgresql-x64-18
```

### 2. Start Redis

In Windows PowerShell:

```powershell
wsl -d Ubuntu
```

Inside Ubuntu:

```bash
sudo service redis-server start
redis-cli ping
```

Enter your Ubuntu password when prompted. The Redis check should return `PONG`. Keep this Ubuntu window open while using the application.

### 3. Apply database migrations

In a Windows PowerShell window:

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\backend"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Run this before starting the API and worker, including after pulling code that adds migrations. If the database is already current, no upgrade is needed.

### 4. Start the API

In the same backend PowerShell window:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 12201
```

Keep this window running.

### 5. Start the worker

Open another Windows PowerShell window:

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\backend"
.\.venv\Scripts\python.exe -m app.worker
```

Keep this window running. The worker processes analysis, connection-test, knowledge-generation, and dashboard-refresh jobs.

### 6. Start the frontend

Open another Windows PowerShell window:

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\frontend"
npm.cmd run dev
```

Keep this window running. Using `npm.cmd` avoids PowerShell restrictions on `npm.ps1`.

### 7. Verify and open the application

In a separate Windows PowerShell window:

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

Open http://localhost:12200. For a fresh database, sign up and configure a datasource and model connection/profile. Submit a question to verify the worker and provider configuration; readiness checks only PostgreSQL and Redis.

You should have four windows running: Ubuntu/Redis, API, worker, and frontend.

## First-time setup only

Skip this section if the application has already been installed and migrated on this machine.

Prerequisites: Python 3.12 or newer, Node.js with npm, PostgreSQL, and Ubuntu under WSL. The PostgreSQL service name and client path below match this machine's installation.

### Application database

Connect from Windows PowerShell and enter your PostgreSQL administrator password locally:

```powershell
& "D:\ProgramFiles\pgSQL\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

For a new installation, run the following inside `psql`. Create the database only if it does not already exist. The application password below is for local development.

```sql
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dbassistant') THEN
        CREATE ROLE dbassistant LOGIN;
    END IF;
END
$$;

ALTER ROLE dbassistant WITH LOGIN PASSWORD 'dbassistant';
CREATE DATABASE dbassistant OWNER dbassistant;
\q
```

### Redis installation

Inside Ubuntu, if Redis is not installed:

```bash
sudo apt update
sudo apt install -y redis-server redis-tools
```

### Backend installation and configuration

In Windows PowerShell:

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\backend"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
notepad .env
```

Set these values, then save and close Notepad. If you chose a different application password, update the database URL accordingly.

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://dbassistant:dbassistant@127.0.0.1:5432/dbassistant
REDIS_URL=redis://127.0.0.1:6379/0
```

The remaining template values support local development. Keep the environment file and its encryption key across restarts so saved connection credentials remain readable.

### Frontend installation and configuration

In Windows PowerShell:

```powershell
Set-Location "D:\Projects\thermo-fisher\data-agent\poc\data-agent-poc\frontend"
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
npm.cmd ci --legacy-peer-deps
```

The frontend environment file should contain:

```dotenv
VITE_API_BASE_URL=http://localhost:12201
```

Return to **Daily startup** to start services and apply migrations.

## Restart, updates, and shutdown

- After a backend code or environment change, stop the API and worker with `Ctrl+C`, then start them again.
- After changing the frontend environment file, restart the frontend development server.
- After pulling dependency changes, rerun the backend installation command and/or `npm.cmd ci --legacy-peer-deps` as appropriate. Apply migrations before restarting the API and worker.
- To stop the application, press `Ctrl+C` in the frontend, worker, and API windows. Allow the worker to finish its active jobs.
- To stop Redis, run `sudo service redis-server stop` in Ubuntu, then `exit`.
- PostgreSQL can remain running as a Windows service.

## Common startup errors

| Error | Action |
| --- | --- |
| PostgreSQL connection refused | Check the Windows service and use port `5432` in the backend environment file. |
| PostgreSQL password authentication failed | Check the application role/password and database URL; the API uses `dbassistant`, not the PostgreSQL administrator account. |
| Redis connection refused | Start Redis in Ubuntu, keep Ubuntu open, and use port `6379` in the backend environment file. From PowerShell, check `Test-NetConnection 127.0.0.1 -Port 6379`. |
| Redis service or `redis-cli` not found | Install `redis-server` and `redis-tools` inside Ubuntu using the first-time setup commands. |
| Port `12200` or `12201` already in use | Check for an API/frontend window already running before starting a second instance. |
| Backend cannot find `.env` or uses unexpected ports | Start the API, worker, and migrations from the backend folder. |
| Jobs remain queued | Check the worker window for errors and confirm it uses the same backend environment as the API. |
| Model or datasource calls fail after readiness succeeds | Check their connection settings in the application; `/ready` does not validate these connections. |
