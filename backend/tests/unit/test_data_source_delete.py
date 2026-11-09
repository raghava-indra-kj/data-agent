from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import AppError
from app.data_sources.service import DataSourceService


@pytest.mark.asyncio
@pytest.mark.parametrize("sqlstate", ["23001", "23503"])
async def test_delete_preserves_source_when_referenced(sqlstate):
    session = AsyncMock()
    session.flush.side_effect = IntegrityError(
        "DELETE", {}, SimpleNamespace(sqlstate=sqlstate)
    )
    service = DataSourceService(session, Settings(_env_file=None))
    service.require_for_org = AsyncMock(return_value=SimpleNamespace(secret_id=uuid4()))
    service.repo.delete_data_source = AsyncMock()
    service.storage.remove_datasource_directory = Mock()

    with pytest.raises(AppError) as error:
        await service.delete(data_source_id=uuid4(), organization_id=uuid4())

    assert error.value.code == "DATASOURCE_IN_USE"
    assert error.value.status_code == 409
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    service.storage.remove_datasource_directory.assert_not_called()


@pytest.mark.asyncio
async def test_delete_does_not_mask_other_integrity_errors():
    session = AsyncMock()
    session.flush.side_effect = IntegrityError(
        "DELETE", {}, SimpleNamespace(sqlstate="23505")
    )
    service = DataSourceService(session, Settings(_env_file=None))
    service.require_for_org = AsyncMock(return_value=SimpleNamespace(secret_id=None))
    service.repo.delete_data_source = AsyncMock()

    with pytest.raises(IntegrityError):
        await service.delete(data_source_id=uuid4(), organization_id=uuid4())
    session.rollback.assert_awaited_once()
