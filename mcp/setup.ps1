param([string]$PythonCommand = "py")

$ErrorActionPreference = "Stop"
$pluginDirectory = $PSScriptRoot
$pythonExecutable = Join-Path $pluginDirectory ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    if ($PythonCommand -eq "py") {
        & $PythonCommand -3.12 -m venv (Join-Path $pluginDirectory ".venv")
    } else {
        & $PythonCommand -m venv (Join-Path $pluginDirectory ".venv")
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment. Use Python 3.12 or 3.13." }
}

& $pythonExecutable -m pip install $pluginDirectory
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

$sourcesFile = Join-Path $pluginDirectory "sources.json"
if (-not (Test-Path -LiteralPath $sourcesFile)) {
    [System.IO.File]::WriteAllText($sourcesFile, '{"version":1,"sources":[]}', [System.Text.UTF8Encoding]::new($false))
}
$settingsFile = Join-Path $pluginDirectory "settings.json"
if (-not (Test-Path -LiteralPath $settingsFile)) {
    Copy-Item -LiteralPath (Join-Path $pluginDirectory "settings.example.json") -Destination $settingsFile
}

& $pythonExecutable -m data_agent_mcp check-config --sources $sourcesFile
if ($LASTEXITCODE -ne 0) { throw "Source configuration is invalid." }
& $pythonExecutable -m data_agent_mcp check-settings --sources $sourcesFile --settings $settingsFile
if ($LASTEXITCODE -ne 0) { throw "Runtime configuration is invalid." }

Write-Host "Setup complete. No database connection was attempted."
Write-Host "Run: & '$pythonExecutable' -m data_agent_mcp serve --sources '$sourcesFile'"
