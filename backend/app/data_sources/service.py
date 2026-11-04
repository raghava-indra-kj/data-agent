from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.data_sources.adapters.base import DataSourceAdapter
from app.data_sources.adapters.registry import DataSourceAdapterRegistry, registry
from app.data_sources.errors import DataSourceConfigurationError, DataSourceOperationError
from app.data_sources.models import DataSource, DataSourceFile
from app.data_sources.repository import DataSourceRepository
from app.data_sources.schemas import (
    DatabaseCredentials,
    DataSourceFileResponse,
    DataSourceResponse,
    DataSourceUpdate,
    MSSQLConfig,
    RelationalDataSourceCreate,
)
from app.data_sources.secrets import SecretService
from app.data_sources.storage import LocalDataSourceStorage
from app.data_sources.types import SchemaMetadata
from app.jobs.service import JobService
from app.knowledge.repository import KnowledgeRepository

logger = logging.getLogger(__name__)


class DataSourceService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        adapter_registry: DataSourceAdapterRegistry = registry,
    ) -> None:
        self.session = session
        self.settings = settings
        self.repo = DataSourceRepository(session)
        self.secrets = SecretService(session, settings)
        self.storage = LocalDataSourceStorage(settings)
        self.adapters = adapter_registry

    async def create_relational(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: RelationalDataSourceCreate,
    ) -> DataSource:
        name = payload.name.strip()
        await self._ensure_name_available(organization_id, name)
        config = payload.config.model_dump(mode="json")
        self.adapters.validate_config(payload.kind, config)
        secret_id = None
        if payload.credentials is not None:
            secret = await self.secrets.create(
                organization_id=organization_id,
                purpose="datasource_credentials",
                payload=self._credentials_payload(payload.credentials),
            )
            secret_id = secret.id
        data_source = DataSource(
            organization_id=organization_id,
            name=name,
            kind=payload.kind,
            display_type=payload.kind,
            status="pending",
            config=config,
            secret_id=secret_id,
            created_by=user_id,
            last_tested_at=None,
            last_error_code=None,
        )
        self.repo.add(data_source)
        await self._commit_or_duplicate()
        return data_source

    async def create_excel(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        upload: UploadFile,
    ) -> tuple[DataSource, uuid.UUID]:
        clean_name = name.strip()
        if not clean_name:
            raise AppError("DATASOURCE_NAME_REQUIRED", "Datasource name is required.", 400)
        await self._ensure_name_available(organization_id, clean_name)
        data_source = DataSource(
            id=uuid.uuid4(),
            organization_id=organization_id,
            name=clean_name,
            kind="duckdb",
            display_type="excel",
            status="preparing",
            config={},
            secret_id=None,
            created_by=user_id,
            last_tested_at=None,
            last_error_code=None,
        )
        file = DataSourceFile(id=uuid.uuid4(), data_source_id=data_source.id)
        original_filename = Path(upload.filename or "workbook.xlsx").name[:255]
        stored = await self.storage.save_excel_upload(
            upload=upload,
            organization_id=organization_id,
            data_source_id=data_source.id,
            file_id=file.id,
        )
        now = utc_now()
        file.original_filename = original_filename
        file.source_path = self.storage.to_record_path(stored.path)
        file.materialized_database_path = None
        file.sha256 = stored.sha256
        file.size_bytes = stored.size_bytes
        file.status = "uploaded"
        file.is_active = False
        file.sheet_mapping = []
        file.error_code = None
        file.created_at = now
        file.updated_at = now
        self.repo.add(data_source)
        self.repo.add_file(file)
        try:
            await self.session.flush()
            job = await JobService(self.session, self.settings).create_job(
                organization_id=organization_id,
                requested_by=user_id,
                job_type="excel_materialization",
                input_data={
                    "data_source_id": str(data_source.id),
                    "file_id": str(file.id),
                },
            )
        except IntegrityError as exc:
            await self.session.rollback()
            self.storage.remove_file(file.source_path)
            raise AppError(
                "DATASOURCE_NAME_EXISTS", "A datasource with this name already exists.", 409
            ) from exc
        except Exception:
            await self.session.rollback()
            self.storage.remove_file(file.source_path)
            raise
        return data_source, job.id

    async def replace_excel(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        data_source_id: uuid.UUID,
        upload: UploadFile,
    ) -> uuid.UUID:
        data_source = await self.require_for_org(data_source_id, organization_id)
        if data_source.kind != "duckdb" or data_source.display_type != "excel":
            raise AppError(
                "DATASOURCE_NOT_EXCEL", "Only Excel datasources accept workbook replacement.", 400
            )
        file = DataSourceFile(id=uuid.uuid4(), data_source_id=data_source.id)
        original_filename = Path(upload.filename or "workbook.xlsx").name[:255]
        stored = await self.storage.save_excel_upload(
            upload=upload,
            organization_id=organization_id,
            data_source_id=data_source.id,
            file_id=file.id,
        )
        now = utc_now()
        file.original_filename = original_filename
        file.source_path = self.storage.to_record_path(stored.path)
        file.materialized_database_path = None
        file.sha256 = stored.sha256
        file.size_bytes = stored.size_bytes
        file.status = "uploaded"
        file.is_active = False
        file.sheet_mapping = []
        file.error_code = None
        file.created_at = now
        file.updated_at = now
        self.repo.add_file(file)
        active = await self.repo.active_file(data_source.id)
        if active is None:
            data_source.status = "preparing"
        try:
            await self.session.flush()
            job = await JobService(self.session, self.settings).create_job(
                organization_id=organization_id,
                requested_by=user_id,
                job_type="excel_materialization",
                input_data={
                    "data_source_id": str(data_source.id),
                    "file_id": str(file.id),
                },
            )
        except Exception:
            await self.session.rollback()
            self.storage.remove_file(file.source_path)
            raise
        return job.id

    async def list_for_org(self, organization_id: uuid.UUID) -> list[DataSource]:
        return await self.repo.list_for_org(organization_id)

    async def require_for_org(
        self, data_source_id: uuid.UUID, organization_id: uuid.UUID
    ) -> DataSource:
        data_source = await self.repo.get_for_org(data_source_id, organization_id)
        if data_source is None:
            raise AppError("DATASOURCE_NOT_FOUND", "Datasource not found.", 404)
        return data_source

    async def to_response(self, data_source: DataSource) -> DataSourceResponse:
        active_file = await self.repo.active_file(data_source.id)
        response = DataSourceResponse.model_validate(data_source)
        if active_file is not None:
            response.active_file = DataSourceFileResponse.model_validate(active_file)
        return response

    async def update(
        self,
        *,
        data_source_id: uuid.UUID,
        organization_id: uuid.UUID,
        payload: DataSourceUpdate,
    ) -> DataSource:
        data_source = await self.require_for_org(data_source_id, organization_id)
        was_windows_auth = (
            data_source.kind == "mssql"
            and data_source.config.get("authentication_mode", "sql") == "windows"
        )
        if data_source.kind == "powerbi" and (payload.config is not None or payload.credentials is not None):
            raise AppError("POWER_BI_CONFIG_MANAGED", "Manage reports and your Microsoft connection from the Power BI settings.", 422)
        next_config_input = payload.config if payload.config is not None else data_source.config
        if data_source.kind == "mssql":
            try:
                parsed_config = self.adapters.validate_config("mssql", next_config_input)
            except DataSourceConfigurationError as exc:
                raise AppError(exc.code, exc.public_message, 400) from exc
            assert isinstance(parsed_config, MSSQLConfig)
            windows_auth = parsed_config.authentication_mode == "windows"
        else:
            windows_auth = False
        if windows_auth and payload.credentials is not None:
            raise AppError(
                "DATASOURCE_CREDENTIALS_NOT_APPLICABLE",
                "Windows authentication uses the application Windows account; omit credentials.",
                400,
            )
        if was_windows_auth and not windows_auth and payload.credentials is None:
            raise AppError(
                "DATASOURCE_CREDENTIALS_MISSING",
                "Enter username and password when switching to SQL authentication.",
                400,
            )
        if payload.name is not None:
            name = payload.name.strip()
            existing = await self.repo.find_by_name(organization_id, name)
            if existing is not None and existing.id != data_source.id:
                raise AppError("DATASOURCE_NAME_EXISTS", "A datasource with this name exists.", 409)
            data_source.name = name
        if payload.config is not None:
            if data_source.kind == "duckdb":
                if payload.config:
                    raise AppError(
                        "DATASOURCE_CONFIG_MANAGED",
                        "Excel datasource storage configuration is managed by the server.",
                        400,
                    )
            else:
                try:
                    parsed = self.adapters.validate_config(data_source.kind, payload.config)
                except DataSourceConfigurationError as exc:
                    raise AppError(exc.code, exc.public_message, 400) from exc
                next_config = parsed.model_dump(mode="json")
                location_fields = ("host", "port", "database", "schema_name")
                authentication_changed = was_windows_auth != windows_auth
                if authentication_changed or any(
                    data_source.config.get(key) != next_config.get(key) for key in location_fields
                ):
                    knowledge_repo = KnowledgeRepository(self.session)
                    base = await knowledge_repo.get_base_for_source(data_source.id, organization_id)
                    if base is not None:
                        base = await knowledge_repo.lock_base(base.id)
                        if base is not None:
                            if base.status == "generating":
                                raise AppError(
                                    "KNOWLEDGE_GENERATION_IN_PROGRESS",
                                    "Wait for knowledge generation to finish before changing "
                                    "the database connection.",
                                    409,
                                )
                            base.current_version_id = None
                            base.status = "empty"
                            base.last_error_code = None
                data_source.config = next_config
                data_source.status = "pending"
                data_source.last_error_code = None
                data_source.last_connection_diagnostics = None
                data_source.last_tested_at = None
        if windows_auth and data_source.secret_id is not None:
            secret = await self.secrets.repo.get_for_org(data_source.secret_id, organization_id)
            data_source.secret_id = None
            await self.session.flush()
            if secret is not None:
                await self.secrets.repo.delete(secret)
        if payload.credentials is not None:
            if data_source.kind == "duckdb":
                raise AppError(
                    "DATASOURCE_CREDENTIALS_NOT_APPLICABLE",
                    "Excel datasources do not use database credentials.",
                    400,
                )
            credential_payload = self._credentials_payload(payload.credentials)
            if data_source.secret_id is None:
                secret = await self.secrets.create(
                    organization_id=organization_id,
                    purpose="datasource_credentials",
                    payload=credential_payload,
                )
                data_source.secret_id = secret.id
            else:
                secret = await self.secrets.repo.get_for_org(data_source.secret_id, organization_id)
                if secret is None:
                    raise AppError("SECRET_NOT_FOUND", "Stored credentials are unavailable.", 500)
                await self.secrets.replace(secret, credential_payload)
            data_source.status = "pending"
            data_source.last_error_code = None
            data_source.last_connection_diagnostics = None
            data_source.last_tested_at = None
        if payload.status is not None:
            if payload.status == "active" and data_source.status == "disabled":
                if (
                    data_source.kind == "duckdb"
                    and await self.repo.active_file(data_source.id) is None
                ):
                    raise AppError(
                        "DATASOURCE_NOT_READY", "The Excel datasource is not materialized yet.", 409
                    )
                data_source.status = "active"
            elif payload.status == "disabled":
                data_source.status = "disabled"
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "DATASOURCE_NAME_EXISTS", "A datasource with this name already exists.", 409
            ) from exc
        # Reload the server-updated timestamp before serializing the API response.
        await self.session.refresh(data_source)
        return data_source

    async def delete(self, *, data_source_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        data_source = await self.require_for_org(data_source_id, organization_id)
        secret_id = data_source.secret_id
        await self.repo.delete_data_source(data_source)
        await self.session.flush()
        if secret_id is not None:
            secret = await self.secrets.repo.get_for_org(secret_id, organization_id)
            if secret is not None:
                await self.session.delete(secret)
        await self.session.commit()
        self.storage.remove_datasource_directory(organization_id, data_source_id)

    async def enqueue_test(
        self,
        *,
        data_source_id: uuid.UUID,
        organization_id: uuid.UUID,
        requested_by: uuid.UUID,
    ) -> uuid.UUID:
        source = await self.require_for_org(data_source_id, organization_id)
        if source.kind == "powerbi":
            raise AppError("POWER_BI_REFRESH_REQUIRED", "Use Refresh access on the Power BI source.", 422)
        job = await JobService(self.session, self.settings).create_job(
            organization_id=organization_id,
            requested_by=requested_by,
            job_type="datasource_test",
            input_data={"data_source_id": str(data_source_id)},
        )
        return job.id

    async def resolve_adapter(self, data_source: DataSource) -> DataSourceAdapter:
        if data_source.kind == "powerbi":
            raise AppError("POWER_BI_OPERATION_UNSUPPORTED", "Power BI uses Fabric IQ, not a database connection.", 422)
        credentials: dict[str, Any] | None = None
        windows_auth = (
            data_source.kind == "mssql"
            and data_source.config.get("authentication_mode", "sql") == "windows"
        )
        if data_source.secret_id is not None and not windows_auth:
            credentials = await self.secrets.read(
                secret_id=data_source.secret_id,
                organization_id=data_source.organization_id,
            )
        database_path: Path | None = None
        if data_source.kind == "duckdb":
            active_file = await self.repo.active_file(data_source.id)
            if active_file is None or not active_file.materialized_database_path:
                raise DataSourceOperationError(
                    "DATASOURCE_FILE_UNAVAILABLE",
                    "The analytical database is not ready.",
                )
            database_path = self.storage.from_record_path(active_file.materialized_database_path)
        return self.adapters.create(
            kind=data_source.kind,
            config=data_source.config,
            credentials=credentials,
            database_path=database_path,
        )

    async def test_now(self, data_source: DataSource) -> None:
        if data_source.status == "disabled":
            raise AppError("DATASOURCE_DISABLED", "The datasource is disabled.", 409)
        adapter = await self.resolve_adapter(data_source)
        try:
            async with asyncio.timeout(self.settings.datasource_operation_timeout_seconds):
                result = await adapter.test_connection()
        except TimeoutError as exc:
            raise DataSourceOperationError(
                "DATASOURCE_CONNECTION_TIMEOUT",
                "The datasource connection test timed out.",
                retryable=True,
            ) from exc
        if not result.ok:
            raise DataSourceOperationError(
                "DATASOURCE_CONNECTION_FAILED", "Unable to connect to the datasource."
            )

    async def introspect_now(self, data_source: DataSource) -> SchemaMetadata:
        if data_source.status == "disabled":
            raise AppError("DATASOURCE_DISABLED", "The datasource is disabled.", 409)
        adapter = await self.resolve_adapter(data_source)
        try:
            async with asyncio.timeout(self.settings.datasource_operation_timeout_seconds):
                return await adapter.introspect()
        except TimeoutError as exc:
            raise DataSourceOperationError(
                "DATASOURCE_INTROSPECTION_TIMEOUT",
                "Datasource inspection timed out.",
                retryable=True,
            ) from exc

    async def mark_test_succeeded(self, data_source: DataSource) -> None:
        data_source.status = "active"
        data_source.last_tested_at = utc_now()
        data_source.last_error_code = None
        data_source.last_connection_diagnostics = None
        await self.session.commit()

    async def mark_test_failed(
        self, data_source: DataSource, code: str, diagnostics: dict[str, object] | None = None
    ) -> None:
        data_source.status = "error"
        data_source.last_tested_at = utc_now()
        data_source.last_error_code = code[:100]
        data_source.last_connection_diagnostics = diagnostics
        await self.session.commit()

    async def _ensure_name_available(self, organization_id: uuid.UUID, name: str) -> None:
        if await self.repo.find_by_name(organization_id, name) is not None:
            raise AppError("DATASOURCE_NAME_EXISTS", "A datasource with this name exists.", 409)

    async def _commit_or_duplicate(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "DATASOURCE_NAME_EXISTS", "A datasource with this name already exists.", 409
            ) from exc

    @staticmethod
    def _credentials_payload(credentials: DatabaseCredentials) -> dict[str, str]:
        return {
            "username": credentials.username,
            "password": credentials.password.get_secret_value(),
        }
