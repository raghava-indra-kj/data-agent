[CmdletBinding()]
param(
    [ValidateSet("Tunnel", "Direct")]
    [string]$Mode = "Tunnel",
    [string]$Profile = "data-agent",
    [string]$TunnelClient = $env:DATA_AGENT_TUNNEL_CLIENT,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$pluginDirectory = $PSScriptRoot
$pythonExecutable = Join-Path $pluginDirectory ".venv\Scripts\python.exe"
$sourcesFile = Join-Path $pluginDirectory "sources.json"
$tunnelEnvironmentOriginals = @{}
$locationPushed = $false

try {
    if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
        throw "Python environment is missing. Run .\setup.ps1 in the plugin folder first."
    }
    if (-not (Test-Path -LiteralPath $sourcesFile -PathType Leaf)) {
        throw "sources.json is missing. Run .\setup.ps1, then configure your data sources."
    }

    Push-Location -LiteralPath $pluginDirectory
    $locationPushed = $true
    # Existing terminals may predate variables saved through Windows Settings.
    # Preserve explicit process overrides; otherwise inherit the saved user values.
    foreach ($credentialVariable in @("DATA_AGENT_USERNAME", "DATA_AGENT_PASSWORD")) {
        if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($credentialVariable, "Process"))) {
            $userValue = [Environment]::GetEnvironmentVariable($credentialVariable, "User")
            if (-not [string]::IsNullOrEmpty($userValue)) {
                [Environment]::SetEnvironmentVariable($credentialVariable, $userValue, "Process")
            }
        }
    }
    $userValue = $null
    Write-Host "Checking data source configuration (no database connection)..."
    & $pythonExecutable -m data_agent_mcp check-config --sources $sourcesFile
    if ($LASTEXITCODE -ne 0) { throw "Source configuration check failed. Fix sources.json before starting." }
    & $pythonExecutable -m data_agent_mcp check-settings --sources $sourcesFile
    if ($LASTEXITCODE -ne 0) { throw "Runtime settings check failed. Fix settings.json or DATA_AGENT_* overrides." }

    if ($Mode -eq "Direct") {
        if ($CheckOnly) {
            Write-Host "Direct startup checks passed. No server was started."
            exit 0
        }
        Write-Host "Starting MCP over stdio. Keep this window open; Ctrl+C stops the server."
        & $pythonExecutable -m data_agent_mcp serve --sources $sourcesFile
        if ($LASTEXITCODE -ne 0) { throw "MCP server exited with code $LASTEXITCODE. See the server output above." }
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($TunnelClient)) {
        $tunnelCommand = Get-Command tunnel-client.exe -CommandType Application -ErrorAction SilentlyContinue
        if ($tunnelCommand) {
            $TunnelClient = $tunnelCommand.Source
        } else {
            $downloads = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads"
            $candidates = @(Get-ChildItem -LiteralPath $downloads -Directory -Filter "tunnel-client*windows-amd64*" -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending)
            foreach ($candidate in $candidates) {
                $candidateExecutable = Join-Path $candidate.FullName "tunnel-client.exe"
                if (Test-Path -LiteralPath $candidateExecutable -PathType Leaf) {
                    $TunnelClient = $candidateExecutable
                    break
                }
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($TunnelClient) -or -not (Test-Path -LiteralPath $TunnelClient -PathType Leaf)) {
        throw "Tunnel client was not found. Pass -TunnelClient 'C:\path\tunnel-client.exe' or set DATA_AGENT_TUNNEL_CLIENT to its full path."
    }

    $tunnelEnvironment = @{}
    foreach ($variableName in @("DA_API_KEY", "DA_ORG_ID", "DA_TUNNEL_ID")) {
        foreach ($scopeName in @("Process", "User", "Machine")) {
            $variableValue = [Environment]::GetEnvironmentVariable($variableName, $scopeName)
            if (-not [string]::IsNullOrWhiteSpace($variableValue)) {
                $tunnelEnvironment[$variableName] = $variableValue.Trim()
                break
            }
        }
    }
    $variableValue = $null
    $missingVariables = @("DA_API_KEY", "DA_ORG_ID", "DA_TUNNEL_ID") |
        Where-Object { -not $tunnelEnvironment.ContainsKey($_) }
    if ($missingVariables) {
        throw "Missing tunnel environment variables: $($missingVariables -join ', '). Save them in Windows Environment Variables, then run .\start.cmd again."
    }
    if ($tunnelEnvironment["DA_ORG_ID"] -notmatch '^org-[A-Za-z0-9]+$') {
        throw "DA_ORG_ID must contain a Platform organization ID beginning with org-."
    }
    if ($tunnelEnvironment["DA_TUNNEL_ID"] -notmatch '^tunnel_[0-9a-f]{32}$') {
        throw "DA_TUNNEL_ID must contain a tunnel ID beginning with tunnel_ followed by 32 hexadecimal characters."
    }

    $environmentMapping = @{
        "CONTROL_PLANE_API_KEY" = "DA_API_KEY"
        "CONTROL_PLANE_ORGANIZATION_ID" = "DA_ORG_ID"
        "CONTROL_PLANE_TUNNEL_ID" = "DA_TUNNEL_ID"
    }
    foreach ($targetVariable in $environmentMapping.Keys) {
        $tunnelEnvironmentOriginals[$targetVariable] = [Environment]::GetEnvironmentVariable($targetVariable, "Process")
        [Environment]::SetEnvironmentVariable($targetVariable, $tunnelEnvironment[$environmentMapping[$targetVariable]], "Process")
    }
    # Explicit ID arguments override stale IDs in an existing tunnel profile.
    $tunnelArguments = @(
        "--profile", $Profile,
        "--control-plane.organization-id", $tunnelEnvironment["DA_ORG_ID"],
        "--control-plane.tunnel-id", $tunnelEnvironment["DA_TUNNEL_ID"]
    )
    Write-Host "Using tunnel settings from DA_API_KEY, DA_ORG_ID, and DA_TUNNEL_ID."
    Write-Host "Organization: $($tunnelEnvironment['DA_ORG_ID'])"
    Write-Host "Tunnel ID: $($tunnelEnvironment['DA_TUNNEL_ID'])"

    Write-Host "Checking tunnel profile '$Profile'..."
    & $TunnelClient doctor @tunnelArguments --explain
    if ($LASTEXITCODE -ne 0) {
        throw "Tunnel diagnostics failed. Follow the doctor output above; the tunnel was not started."
    }
    if ($CheckOnly) {
        Write-Host "Tunnel startup checks passed. No server or tunnel was started."
        exit 0
    }
    Write-Host "Starting the ChatGPT tunnel. Its profile launches MCP; do not start another MCP instance."
    Write-Host "Keep this window open and the PC awake. Ctrl+C stops the tunnel."
    & $TunnelClient run @tunnelArguments
    if ($LASTEXITCODE -ne 0) { throw "Tunnel exited with code $LASTEXITCODE. See the output above." }
} catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    exit 1
} finally {
    foreach ($targetVariable in $tunnelEnvironmentOriginals.Keys) {
        [Environment]::SetEnvironmentVariable($targetVariable, $tunnelEnvironmentOriginals[$targetVariable], "Process")
    }
    if ($locationPushed) { Pop-Location }
}
