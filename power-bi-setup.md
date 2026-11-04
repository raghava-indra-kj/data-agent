# Power BI data sources and report canvas

This release adds published Power BI reports and their semantic models to the existing data-source picker. Each application user connects their own Microsoft account. Fabric IQ supplies read-only schema, value search and DAX tools to the existing agent. Results use the existing Markdown, table, chart, execution-history and job-streaming UI.

The report is closed initially. In a Power BI conversation, select **Power BI → report name** to open it on the right. The conversation and its charts remain on the left. The panel supports drag/keyboard resizing, expand/restore and an explicit close button. Escape and outside clicks do not close it. Opening a different conversation closes the report. Narrow screens stack the report below the conversation.

## Microsoft preparation

1. Use a Microsoft Entra app registration in the tenant containing the reports. Configure a **Web** redirect URI, because this implementation exchanges the authorization code on the backend:
   `http://localhost:12201/api/v1/power-bi/connections/callback` for local development, or the corresponding HTTPS API URL in production. This replaces the old proof-of-concept SPA callback; do not register it as a SPA redirect.
2. Add delegated **Power BI Service** permissions: `Item.Read.All`, `Item.Execute.All`, and `Report.Read.All`. Grant consent according to the tenant's policy. MSAL requests the standard sign-in/offline scopes and handles authorization-code/PKCE validation and refresh.
3. Configure a client secret in the backend's secret/environment configuration. It authenticates the web OAuth client; data access still uses the connected user's delegated identity. Neither a service principal nor a shared administrator account is used to query reports.
4. Confirm each user can view the published report and access its semantic model. Verify your tenant's Fabric IQ availability and Power BI user/licensing requirements. This is **embed for your organization / user owns data**, not anonymous embedding or app-owns-data embedding.
5. Use published reports, not uploaded `.pbix` files, dashboards, paginated reports, or local Power BI Desktop files. Power BI remains responsible for refreshing the semantic model.

Microsoft references: [Fabric IQ MCP and permissions](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp), [embed for your organization](https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-sample-for-your-organization), [renew embedded access tokens](https://learn.microsoft.com/en-us/javascript/api/overview/powerbi/refresh-token).

## Configuration and installation

Set these values in `backend/.env` for native processes, or in the backend environment for Docker deployment. Use the same configuration and encryption keys for the API and worker.

```dotenv
POWER_BI_ENABLED=true
POWER_BI_EMBEDDING_ENABLED=true
POWER_BI_TENANT_ID=<tenant GUID>
POWER_BI_CLIENT_ID=<app registration GUID>
POWER_BI_CLIENT_SECRET=<secret value from your secret manager>
POWER_BI_REDIRECT_URI=http://localhost:12201/api/v1/power-bi/connections/callback
POWER_BI_FRONTEND_URL=http://localhost:12200
POWER_BI_MCP_URL=https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq
POWER_BI_TOOL_VARIANT=Fabric.Routing.FabricIQ.V1
```

Use `localhost` consistently for the local frontend and callback so the OAuth browser-binding cookie returns correctly. In production, use HTTPS and serve the frontend and API on the same site (preferably one origin behind a reverse proxy). The API callback path must be routed to FastAPI, not to the SPA. Configure the existing `CORS_ORIGINS` with the exact frontend origin and credentials enabled. Never use wildcard origins for the authenticated API.

From the repository root in PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\alembic.exe upgrade head
cd ..\frontend
npm.cmd ci
npm.cmd run build
```

Use the existing application start/deployment workflow after installation. Native development commands, in separate terminals, are:

```powershell
# API: working directory backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 12201
# Worker: working directory backend
.\.venv\Scripts\python.exe -m app.worker
# Frontend: working directory frontend
npm.cmd run dev -- --host localhost --port 12200
```

The existing PostgreSQL database and model-provider configuration are still required. Migration `0024_power_bi` is additive. Apply migrations before starting the updated API and worker. Existing SQL/Excel source records, SQL tools and SQL execution contracts remain in place. The default feature flags are false, so an installation without Microsoft configuration continues to start normally. The Power BI SDK is loaded only when a report is opened.

## User workflow

1. An owner/admin opens **Data sources → Add data source → Power BI**.
2. Select **Connect Microsoft**, complete sign-in and return to the application.
3. Search for a report or paste its browser URL, verify access, name the data source, and add it.
4. Adding another report backed by the same semantic model links that report to the existing source. Different semantic models produce separate sources. Duplicate names are rejected safely.
5. Every user connects their own account before asking. On **Ask**, select the Power BI source and submit a question. Existing SQL/Excel sources may also be selected; queries remain separate per source.
6. Open a conversation's **Power BI** menu to choose a report. No embed token or iframe is created until that selection.
7. **Entire model** is the default question scope. **Page filters & slicers** captures supported report/page filters and slicer state when Send is clicked. Closing the canvas removes the live view from subsequent submissions. Historical question scope stays with its job/DAX evidence.

The first release supports basic categorical inclusion/exclusion and simple advanced comparison filters. Relative dates, Top N, hierarchy filters, unreadable/custom slicers and other unsupported filters block a filtered submission with an actionable message. Chart-specific filters/cross-highlights are not represented as a complete view; the UI states that limit. After a chart selection event, reload the report or choose Entire model. Model-defined measures can intentionally modify filter context; the agent must explain scope and use the model's metric definitions.

## Data and security boundaries

- A source identifies a tenant and semantic model. Reports are separate bindings with their own report/workspace IDs. Each embed request rechecks current report access and its model binding. A report rebound to a different model produces an error requiring review; it never silently queries the old model under a new report.
- Microsoft token caches and temporary OAuth flows are encrypted through the existing secret service. Token refresh is serialized per user/tenant connection with a database lock. Callback state is single-use, expires after ten minutes, and is bound to the initiating browser and application user.
- The short-lived delegated token required by the embed SDK is returned only by an authenticated, `no-store` endpoint and retained in browser memory. It is renewed without recreating the report. Refresh tokens and client secrets never reach the frontend. Disconnect stops the current report frame.
- Fabric IQ requests use Microsoft-host allowlisted endpoints, a pinned `X-Variants` header, runtime tool-schema validation, timeouts, cancellation and bounded result sizes. Redirects are not followed with bearer credentials. Results support structured JSON and embedded CSV resources, including inline previews.
- Power BI conversations and jobs are private to their creator, including lists, message routes, traces, artifact rows/exports and SSE. Other workspace members, including admins, cannot read them. Existing SQL-only conversations retain their existing workspace visibility. An identity pin prevents continuing a Power BI conversation under a different Microsoft account.
- Historical answers are retained for their application-user owner under the existing conversation retention policy. Disconnect/revocation prevents new access but does not erase previously retrieved answers. Deleting the conversation follows the existing deletion workflow. Organizations that require immediate revocation of historical exports need an additional retention policy before rollout.
- DAX executions are stored separately from SQL with source/model identity, timing, truncation and captured context. Tables/charts reference these records. No synthetic SQL is written for Power BI. In mixed conversations, shared knowledge/skill writes and public HTML output tools are disabled. Private jobs cannot be published to shared dashboards.
- Metadata snapshots are scoped to the Microsoft connection. The agent retrieves live metadata under the current user; an admin's schema is never served as another user's OLS-filtered schema.

Configure production secret encryption/rotation and database encryption/backups using existing deployment controls. Do not log access tokens, authorization codes, callback query strings or complete model/query data in infrastructure logs. Redact the OAuth callback query at the reverse proxy, and use appropriate access-log configuration.

## Rollout and acceptance

Deploy backend/migration first, then frontend, initially with flags disabled. Enable for a test tenant after consent and licensing checks. Before wider rollout, exercise two users with different RLS/OLS access, two reports sharing a model, two models, expired/revoked sign-in, changed report bindings, a long-lived open report, throttling, and unsupported slicers. Confirm both users receive their own expected model results.

Automated tests use mocked Microsoft/Fabric responses and a separate PostgreSQL test database. They cover registration/deduplication, OAuth state/browser binding, privacy routes, audited DAX/chart evidence, result normalization, filtering, and the canvas lifecycle. They do not certify a live tenant's permissions, report-specific DAX semantics, or Microsoft service availability.

Disable `POWER_BI_ENABLED` and `POWER_BI_EMBEDDING_ENABLED` to stop new Power BI operations while keeping existing SQL/Excel features available. Keep the additive migration in place when rolling the application back. Do not downgrade the migration on a database containing Power BI history without an explicit export/deletion decision.

Workspace restructuring, workspace/table/column knowledge inheritance, joins across semantic models, shared Power BI dashboards, scheduled unattended queries, matrix creation from DAX and app-owns-data embedding are outside this release.
