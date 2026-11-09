import argparse
import getpass
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from data_agent_mcp.bootstrap import build_test_connection, sources_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Database knowledge MCP server and owner configuration utilities."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser(
        "serve", help="Run the MCP server over stdio; makes no startup database connection."
    )
    serve.add_argument(
        "--sources",
        type=Path,
        help="JSON configuration path; otherwise DATA_AGENT_SOURCES_FILE or ./sources.json",
    )
    serve.add_argument(
        "--settings",
        type=Path,
        help="Runtime limits JSON; otherwise DATA_AGENT_SETTINGS_FILE or settings.json next to sources",
    )
    serve.add_argument(
        "--state",
        type=Path,
        help="SQLite metadata path; otherwise DATA_AGENT_STATE_FILE or state/metadata.sqlite3 next to sources",
    )
    test = commands.add_parser(
        "test-connection",
        help="Explicitly connect to one configured source and print JSON diagnostics.",
    )
    test.add_argument("--sources", type=Path)
    test.add_argument("--source-id", required=True, help="Source UUID from the JSON file")
    test.add_argument(
        "--output", type=Path, help="Also save the sanitized JSON result to this file"
    )
    test.add_argument(
        "--prompt-password",
        action="store_true",
        help="Securely prompt for the selected SQL login password for this test only; no password is saved",
    )
    validate = commands.add_parser(
        "check-config", help="Validate configuration offline and list source IDs; never connect."
    )
    validate.add_argument("--sources", type=Path)
    settings_check = commands.add_parser(
        "check-settings",
        help="Show effective non-secret runtime limits without connecting to a database.",
    )
    settings_check.add_argument("--settings", type=Path)
    settings_check.add_argument("--sources", type=Path)
    args = parser.parse_args(argv)
    if args.command == "serve":
        from data_agent_mcp.bootstrap import build_product
        from data_agent_mcp.presentation.mcp.server import create_server

        services = build_product(args.sources, args.settings, args.state)
        create_server(build_test_connection(args.sources), services).run(
            transport="stdio", show_banner=False
        )
        return 0
    if args.command == "check-settings":
        from dotenv import load_dotenv

        from data_agent_mcp.domain.queries import OperationError
        from data_agent_mcp.infrastructure.configuration.settings import load_settings

        owner_root = sources_path(args.sources).parent
        load_dotenv(
            Path(os.environ.get("DATA_AGENT_ENV_FILE", str(owner_root / ".env"))), override=False
        )
        settings_path = args.settings or Path(
            os.environ.get("DATA_AGENT_SETTINGS_FILE", "settings.json")
        )
        if not settings_path.is_absolute():
            settings_path = owner_root / settings_path
        try:
            print(
                json.dumps(
                    {"valid": True, "settings": asdict(load_settings(settings_path))}, indent=2
                )
            )
            return 0
        except OperationError as exc:
            print(json.dumps({"valid": False, "code": exc.code, "message": str(exc)}))
            return 1
    if args.command == "check-config":
        from data_agent_mcp.application.ports.data_sources import ConfigurationError
        from data_agent_mcp.infrastructure.configuration.file_data_sources import (
            FileDataSourceRepository,
        )

        try:
            configured = FileDataSourceRepository(sources_path(args.sources)).list_all()
        except ConfigurationError as exc:
            print(json.dumps({"valid": False, "message": str(exc)}))
            return 1
        print(
            json.dumps(
                {
                    "valid": True,
                    "sources": [
                        {
                            "id": str(source.id),
                            "name": source.name,
                            "engine": source.engine.value,
                            "enabled": source.enabled,
                            "authentication_method": source.authentication.method.value,
                        }
                        for source in configured
                    ],
                },
                indent=2,
            )
        )
        return 0
    use_case = build_test_connection(args.sources)
    if args.prompt_password:
        from data_agent_mcp.application.ports.data_sources import ConfigurationError
        from data_agent_mcp.application.use_cases.test_connection import TestConnection
        from data_agent_mcp.domain.data_sources.models import (
            DatabaseEngine,
            UsernamePasswordAuthentication,
        )
        from data_agent_mcp.infrastructure.configuration.file_data_sources import (
            FileDataSourceRepository,
        )
        from data_agent_mcp.infrastructure.credentials.environment import (
            EnvironmentCredentialResolver,
        )
        from data_agent_mcp.infrastructure.databases.mssql.connection_tester import (
            MssqlConnectionTester,
        )

        repository = FileDataSourceRepository(sources_path(args.sources))
        try:
            source = repository.get(UUID(args.source_id))
        except (ValueError, ConfigurationError):
            source = None
        if (
            source
            and source.enabled
            and source.engine == DatabaseEngine.MSSQL
            and isinstance(source.authentication, UsernamePasswordAuthentication)
        ):
            if not sys.stdin.isatty():
                print(
                    "Password prompting requires an interactive terminal. Use an environment reference for automation.",
                    file=sys.stderr,
                )
                return 2
            environment = dict(os.environ)
            try:
                environment[source.authentication.password_reference.key] = getpass.getpass(
                    "SQL password (not saved): "
                )
            except (EOFError, KeyboardInterrupt):
                print("Password prompt cancelled.", file=sys.stderr)
                return 2
            use_case = TestConnection(
                repository,
                EnvironmentCredentialResolver(environment),
                {DatabaseEngine.MSSQL: MssqlConnectionTester()},
            )
    result = use_case.execute(args.source_id)
    rendered = json.dumps(asdict(result), indent=2)
    if args.output:
        try:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        except OSError:
            print(rendered)
            print("Could not write the diagnostics output file.", file=sys.stderr)
            return 2
    print(rendered)
    return 0 if result.success else 1
