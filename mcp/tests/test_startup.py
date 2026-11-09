"""Check Windows startup orchestration without starting MCP or touching databases."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(
    not POWERSHELL or not (ROOT / ".venv/Scripts/python.exe").exists(),
    reason="Requires Windows PowerShell and the installed plugin environment",
)


def invoke(script: Path, *arguments: str, env: dict[str, str]):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


@pytest.fixture
def startup_env(tmp_path):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DATA_AGENT_", "DA_", "CONTROL_PLANE_", "OPENAI_"))
    }
    env["DA_API_KEY"] = "  fake-key-for-mocked-tunnel-only  "
    env["DA_ORG_ID"] = "  org-StartupTest  "
    env["DA_TUNNEL_ID"] = "  tunnel_0123456789abcdef0123456789abcdef  "
    env["CONTROL_PLANE_API_KEY"] = "legacy-key-must-be-overridden"
    env["CONTROL_PLANE_ORGANIZATION_ID"] = "org-Legacy"
    env["CONTROL_PLANE_TUNNEL_ID"] = "tunnel_00000000000000000000000000000000"
    env["OPENAI_PERSONAL_ACCOUNT_API_KEY"] = "legacy-personal-key-must-not-be-used"
    env["DATA_AGENT_USERNAME"] = "startup-test-user-no-database-connection"
    env["DATA_AGENT_PASSWORD"] = "startup-test-password-no-database-connection"
    env["DATA_AGENT_ENV_FILE"] = str(tmp_path / "absent.env")
    env["STARTUP_TEST_TRACE"] = str(tmp_path / "calls.txt")
    return env


@pytest.fixture
def mock_tunnel(tmp_path):
    script = tmp_path / "mock-tunnel.ps1"
    script.write_text(
        "Add-Content -LiteralPath $env:STARTUP_TEST_TRACE -Value $args[0]\n"
        "if ($env:CONTROL_PLANE_API_KEY -cne $env:DA_API_KEY.Trim()) { throw 'Wrong API key source.' }\n"
        "foreach ($setting in @(@('ORGANIZATION_ID', 'DA_ORG_ID', '--control-plane.organization-id'), "
        "@('TUNNEL_ID', 'DA_TUNNEL_ID', '--control-plane.tunnel-id'))) {\n"
        "  $expected = [Environment]::GetEnvironmentVariable($setting[1]).Trim()\n"
        "  $actual = [Environment]::GetEnvironmentVariable('CONTROL_PLANE_' + $setting[0])\n"
        "  if ($actual -cne $expected) { throw 'Wrong environment setting.' }\n"
        "  $flagIndex = [Array]::IndexOf($args, $setting[2])\n"
        "  if ($flagIndex -lt 0 -or $args[$flagIndex + 1] -cne $expected) { throw 'Missing ID override.' }\n"
        "}\n"
        "if ($args -contains $env:CONTROL_PLANE_API_KEY) { throw 'API key must not be passed as an argument.' }\n"
        "if ($args[0] -eq 'doctor') {\n"
        "  $global:LASTEXITCODE = [int]$env:STARTUP_TEST_DOCTOR_EXIT\n"
        "} else {\n"
        "  $global:LASTEXITCODE = [int]$env:STARTUP_TEST_RUN_EXIT\n"
        "}\n",
        encoding="utf-8",
    )
    return script


@pytest.mark.parametrize(
    ("doctor_exit", "run_exit", "check_only", "expected_exit", "calls"),
    [
        (2, 0, False, 1, ["doctor"]),
        (0, 0, True, 0, ["doctor"]),
        (0, 0, False, 0, ["doctor", "run"]),
        (0, 7, False, 1, ["doctor", "run"]),
    ],
)
def test_tunnel_orchestration(
    startup_env, mock_tunnel, doctor_exit, run_exit, check_only, expected_exit, calls
):
    startup_env["STARTUP_TEST_DOCTOR_EXIT"] = str(doctor_exit)
    startup_env["STARTUP_TEST_RUN_EXIT"] = str(run_exit)
    arguments = ["-TunnelClient", str(mock_tunnel)]
    if check_only:
        arguments.append("-CheckOnly")
    result = invoke(ROOT / "start.ps1", *arguments, env=startup_env)
    assert result.returncode == expected_exit, result.stderr
    assert Path(startup_env["STARTUP_TEST_TRACE"]).read_text().splitlines() == calls
    for variable in ("DA_API_KEY", "CONTROL_PLANE_API_KEY", "OPENAI_PERSONAL_ACCOUNT_API_KEY"):
        assert startup_env[variable].strip() not in result.stdout + result.stderr


@pytest.mark.parametrize("missing_name", ["DA_API_KEY", "DA_ORG_ID", "DA_TUNNEL_ID"])
def test_check_only_reports_missing_variable(startup_env, mock_tunnel, missing_name):
    # Do not modify the user's saved environment just to simulate an absent value.
    import winreg

    for root, path in (
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(root, path) as registry_key:
                value, _ = winreg.QueryValueEx(registry_key, missing_name)
        except FileNotFoundError:
            continue
        if isinstance(value, str) and value.strip():
            pytest.skip(f"{missing_name} has a saved Windows fallback on this machine")
    startup_env.pop(missing_name)
    result = invoke(
        ROOT / "start.ps1", "-TunnelClient", str(mock_tunnel), "-CheckOnly", env=startup_env
    )
    assert result.returncode == 1
    assert f"Missing tunnel environment variables: {missing_name}" in result.stderr
    assert not Path(startup_env["STARTUP_TEST_TRACE"]).exists()


@pytest.mark.parametrize(
    ("variable", "value"),
    [("DA_ORG_ID", "not-an-org-id"), ("DA_TUNNEL_ID", "not-a-tunnel-id")],
)
def test_invalid_tunnel_environment_stops_before_tunnel(
    startup_env, mock_tunnel, variable, value
):
    startup_env[variable] = value
    result = invoke(
        ROOT / "start.ps1", "-TunnelClient", str(mock_tunnel), "-CheckOnly", env=startup_env
    )
    assert result.returncode == 1
    assert variable in result.stderr
    assert not Path(startup_env["STARTUP_TEST_TRACE"]).exists()


def test_direct_mode_does_not_require_tunnel_environment(startup_env):
    startup_env["DA_ORG_ID"] = "invalid"
    startup_env["DA_TUNNEL_ID"] = "invalid"
    result = invoke(ROOT / "start.ps1", "-Mode", "Direct", "-CheckOnly", env=startup_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Direct startup checks passed" in result.stdout


def test_invalid_settings_stop_before_tunnel(startup_env, mock_tunnel):
    startup_env["DATA_AGENT_QUERY_MAX_ROWS"] = "invalid"
    result = invoke(ROOT / "start.ps1", "-TunnelClient", str(mock_tunnel), env=startup_env)
    assert result.returncode == 1
    assert "Runtime settings check failed" in result.stderr
    assert not Path(startup_env["STARTUP_TEST_TRACE"]).exists()


def test_missing_environment_has_actionable_error(tmp_path, startup_env):
    script = tmp_path / "start.ps1"
    shutil.copyfile(ROOT / "start.ps1", script)
    result = invoke(script, "-Mode", "Direct", "-CheckOnly", env=startup_env)
    assert result.returncode == 1
    assert "setup.ps1" in result.stderr
