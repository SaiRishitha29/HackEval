import pytest
from backend.app.services.ssrf_defense import SSRFDefender, SSRFValidationError


def test_ssrf_rejects_disallowed_schemes():
    defender = SSRFDefender()
    with pytest.raises(SSRFValidationError):
        defender.validate_url("ftp://example.com/api")

    with pytest.raises(SSRFValidationError):
        defender.validate_url("file:///etc/passwd")

    with pytest.raises(SSRFValidationError):
        defender.validate_url("gopher://example.com")


def test_ssrf_rejects_blacklisted_hostnames():
    defender = SSRFDefender()
    with pytest.raises(SSRFValidationError):
        defender.validate_url("https://metadata.google.internal/computeMetadata/v1")

    with pytest.raises(SSRFValidationError):
        defender.validate_url("https://instance-data/latest/meta-data/")


def test_ssrf_rejects_private_and_metadata_ips(monkeypatch):
    defender = SSRFDefender()

    # Test IP resolution blocking for cloud metadata
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(None, None, None, None, ("169.254.169.254", port))])
    with pytest.raises(SSRFValidationError) as exc:
        defender.resolve_and_verify_ip("attacker-cloud-metadata.com")
    assert "prohibited IP address" in str(exc.value)

    # Test IP resolution blocking for RFC 1918 10.0.0.1
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(None, None, None, None, ("10.50.1.1", port))])
    with pytest.raises(SSRFValidationError) as exc:
        defender.resolve_and_verify_ip("internal-corp-service.com")
    assert "prohibited IP address" in str(exc.value)

    # Test IP resolution blocking for 192.168.1.1
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(None, None, None, None, ("192.168.1.1", port))])
    with pytest.raises(SSRFValidationError) as exc:
        defender.resolve_and_verify_ip("router.home")
    assert "prohibited IP address" in str(exc.value)


def test_ssrf_rejects_redirects(monkeypatch):
    defender = SSRFDefender()

    class MockRedirectResponse:
        status_code = 302
        is_redirect = True
        headers = {"Location": "http://169.254.169.254/secret"}
        content = b""

    class MockClient:
        def post(self, url, json):
            return MockRedirectResponse()

    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(None, None, None, None, ("93.184.216.34", port))])
    with pytest.raises(SSRFValidationError) as exc:
        defender.execute_safe_post(MockClient(), "https://example.com/api", {"test": 1})
    assert "Redirect blocked" in str(exc.value)


def test_ssrf_rejects_oversized_payloads(monkeypatch):
    defender = SSRFDefender()

    class MockOversizedResponse:
        status_code = 200
        is_redirect = False
        headers = {"Content-Length": "2097152"}  # 2MB
        content = b"A" * 2097152

    class MockClient:
        def post(self, url, json):
            return MockOversizedResponse()

    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(None, None, None, None, ("93.184.216.34", port))])
    with pytest.raises(SSRFValidationError) as exc:
        defender.execute_safe_post(MockClient(), "https://example.com/api", {"test": 1})
    assert "exceeds maximum limit" in str(exc.value)
