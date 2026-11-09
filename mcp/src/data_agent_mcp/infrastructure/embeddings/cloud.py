"""Optional OpenAI-compatible cloud embeddings; never downloads/runs a local model."""

import ipaddress
import math
import os
from urllib.parse import urlparse

import httpx

from data_agent_mcp.domain.queries import OperationError


class CloudEmbeddingProvider:
    def __init__(self, settings, environment=None, client=None):
        self.settings = settings
        self.environment = environment if environment is not None else os.environ
        self.base_url = self.environment.get(
            "DATA_AGENT_EMBEDDING_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = self.environment.get("DATA_AGENT_EMBEDDING_MODEL", "text-embedding-3-small")
        self.key_reference = self.environment.get(
            "DATA_AGENT_EMBEDDING_KEY_REFERENCE", "DATA_AGENT_EMBEDDING_API_KEY"
        )
        self.client = client

    @property
    def configured(self):
        return bool(self.environment.get(self.key_reference))

    @property
    def model_key(self):
        return self.base_url + "/" + self.model

    def embed(self, texts):
        if not self.configured:
            raise OperationError(
                "EMBEDDINGS_NOT_CONFIGURED",
                "Configure a cloud embedding API key locally. Keyword search remains available.",
            )
        url = urlparse(self.base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise OperationError(
                "CLOUD_ENDPOINT_REQUIRED",
                "Embedding endpoints must use HTTPS without credentials, query strings or fragments in the URL.",
            )
        host = url.hostname.lower()
        if host == "localhost" or host.endswith((".localhost", ".local")):
            raise OperationError(
                "CLOUD_ENDPOINT_REQUIRED", "Local embedding endpoints are not supported."
            )
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and not address.is_global:
            raise OperationError(
                "CLOUD_ENDPOINT_REQUIRED", "Private/local embedding endpoints are not supported."
            )
        inputs = [t[: self.settings.embedding_max_characters] for t in texts]
        try:
            with httpx.Client(
                timeout=self.settings.embedding_timeout_seconds,
                follow_redirects=False,
                transport=self.client,
            ) as client:
                response = client.post(
                    self.base_url + "/embeddings",
                    headers={"Authorization": "Bearer " + self.environment[self.key_reference]},
                    json={"model": self.model, "input": inputs},
                )
                response.raise_for_status()
                data = response.json()["data"]
            ordered = sorted(data, key=lambda item: item["index"])
            if len(ordered) != len(inputs) or [row["index"] for row in ordered] != list(
                range(len(inputs))
            ):
                raise ValueError("Invalid embedding response")
            vectors = [row["embedding"] for row in ordered]
            for vector in vectors:
                if (
                    not vector
                    or len(vector) > self.settings.embedding_max_dimensions
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
                ):
                    raise ValueError("Invalid vector")
            if len({len(v) for v in vectors}) > 1:
                raise ValueError("Inconsistent vector dimensions")
            return vectors
        except httpx.HTTPStatusError as exc:
            request_id = exc.response.headers.get("x-request-id", "")[:200]
            raise OperationError(
                "EMBEDDING_PROVIDER_FAILED",
                "The cloud embedding provider rejected the request.",
                {
                    "http_status": exc.response.status_code,
                    "request_id": request_id,
                    "provider_host": host,
                },
            ) from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise OperationError(
                "EMBEDDING_PROVIDER_FAILED",
                "The cloud embedding request failed or returned an invalid vector. Provider payloads and credentials were withheld.",
            ) from None
