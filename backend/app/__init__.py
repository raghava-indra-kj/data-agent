# Trust the OS certificate store so TLS-inspecting corporate proxies work (requests, httpx, msal).
# Lives here so every entry point (API, worker, scripts) gets it, not just the API.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass
