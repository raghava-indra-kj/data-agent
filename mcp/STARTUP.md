# Start Data Agent MCP

```powershell
Set-Location "C:\Projects\data-agent\mcps\data-agent-mcp"
.\start.cmd
```

Run these commands in Windows PowerShell. For Windows authentication, use the Windows account that has access to the configured SQL Server databases.

## First time setup

Prerequisites: Python 3.12 or 3.13 and Microsoft ODBC Driver 18 for SQL Server.

```powershell
Set-Location C:\Projects\data-agent\mcps\data-agent-mcp
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

Setup installs dependencies and validates configuration without connecting to a database. Existing configuration files are preserved.

## Daily startup for ChatGPT

```powershell
Set-Location C:\Projects\data-agent\mcps\data-agent-mcp
.\start.cmd
```

The script validates source configuration and runtime limits, finds the tunnel client, runs tunnel diagnostics, and starts your existing `data-agent` profile. That profile launches the MCP server itself. Installation is separate; daily startup does not reinstall dependencies.

`start.cmd` runs `start.ps1` with a process-only execution policy override, so it works when Windows PowerShell blocks scripts. It does not change your machine or user execution policy. You can also use `start.ps1` directly if your policy permits it. Both launchers accept the same arguments.

Save these three variables in **Windows Environment Variables** before starting:

| Variable | Value |
| --- | --- |
| `DA_API_KEY` | Runtime API key with access to the intended tunnel |
| `DA_ORG_ID` | Platform organization ID, beginning with `org-` |
| `DA_TUNNEL_ID` | Tunnel ID, beginning with `tunnel_` |

The launcher reads each variable from the current process, then saved Windows User variables, then System variables. This also loads saved values into older terminals when the process value is absent. An explicit process value takes precedence; open a new terminal after changing a saved value that your current terminal already inherited.

All three variables are required in Tunnel mode. If one is missing, startup stops and names it. The launcher passes the API key through the tunnel process environment without displaying or saving it. It supplies the organization and tunnel IDs explicitly to both diagnostics and startup, overriding IDs stored in the selected profile. Older `CONTROL_PLANE_*` values and personal-account keys are overridden by your `DA_*` settings. The profile still supplies the MCP server command and other transport settings.

The launcher does not read these three settings from the plugin `.env` file. Direct mode does not require them.

The tunnel client is found through PATH or extracted `tunnel-client*windows-amd64*` folders under your Downloads directory. You can specify its path and another existing profile:

```powershell
.\start.cmd -TunnelClient "C:\path\tunnel-client.exe" -Profile data-agent
```

Alternatively, set `DATA_AGENT_TUNNEL_CLIENT` to the executable's full path. If you have not configured a tunnel profile yet, complete tunnel setup first; this script uses existing profiles.

Keep the window open and the PC awake. Press **Ctrl+C** to stop the tunnel. Avoid running direct mode at the same time against the same metadata store.

## Check configuration

Database connections are configured in `sources.json`. Runtime limits are configured in `settings.json`; optional environment overrides and password references can be configured through `.env`.

For SQL authentication, configure `authentication` with `method: "username_password"`,
`username_reference: "DATA_AGENT_USERNAME"`, and `password_reference: "DATA_AGENT_PASSWORD"`.
Set those two variables in Windows User environment variables and save the dialogs with OK.
The startup launcher loads saved user values when they are absent from its process environment.
An explicit process value takes precedence. Restart the MCP after changing credentials.
Direct CLI commands inherit their terminal environment; open a new terminal after saving variables.
Literal `username` remains supported, but it cannot be combined with `username_reference`.

```powershell
Set-Location C:\Projects\data-agent\mcps\data-agent-mcp
.\.venv\Scripts\python.exe -m data_agent_mcp check-config --sources .\sources.json
```

This check does not connect to any database.

To validate startup without launching a server:

```powershell
.\start.cmd -Mode Direct -CheckOnly
```

For tunnel diagnostics without starting the tunnel, use `.\start.cmd -CheckOnly`. This reads the same three `DA_*` environment variables and may contact the tunnel service, but does not call database tools.

## Start directly

```powershell
Set-Location C:\Projects\data-agent\mcps\data-agent-mcp
.\start.cmd -Mode Direct
```

Expected log: `Starting MCP server 'Data Agent MCP' with transport 'stdio'`.

The server waits for an MCP client; it has no browser page. Press **Ctrl+C** to stop it. Authlib deprecation warnings alone do not indicate a startup failure.

## Start for ChatGPT through the existing tunnel

Use this instead of starting the server directly. The existing `data-agent` tunnel profile launches the MCP server itself. Avoid running both against the same metadata store.

With the three `DA_*` Windows environment variables saved, run:

```powershell
Set-Location C:\Projects\data-agent\mcps\data-agent-mcp
.\start.cmd
```

The launcher runs diagnostics before starting the tunnel. Keep this window open and the PC awake. Database tools connect to the source requested by the client; scheduled refresh jobs can also connect when enabled. The ChatGPT plugin connection must select the same tunnel as `DA_TUNNEL_ID`.

Open ChatGPT and select the configured Data Agent MCP plugin. If the tool list changed, refresh the plugin's tools in ChatGPT and start a new conversation.

Press **Ctrl+C** in the tunnel window to stop the tunnel. Never share the API key, database passwords, or `.env` file.
