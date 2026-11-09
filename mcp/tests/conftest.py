import httpx
import pyodbc
import pytest


@pytest.fixture(autouse=True)
def forbid_real_database_connections(monkeypatch):
    """The entire offline suite fails if it attempts an actual ODBC connection."""

    def forbidden(*args, **kwargs):
        pytest.fail("Real database connections are prohibited in this test suite")

    monkeypatch.setattr(pyodbc, "connect", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
