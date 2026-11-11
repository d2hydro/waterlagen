"""Certificate policy for Waterlagen's own HTTPS requests."""

import logging

import pytest
import requests
from pydantic import ValidationError

from waterlagen import _http
from waterlagen.bgt.download import poll_downloadstatus, request_download
from waterlagen.settings import Settings


def test_ssl_verify_defaults_to_true(monkeypatch):
    monkeypatch.delenv("WATERLAGEN_SSL_VERIFY", raising=False)
    assert Settings(_env_file=None).waterlagen_ssl_verify is True


def test_ssl_verify_env_overrides_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("WATERLAGEN_SSL_VERIFY=false\n", encoding="utf-8")
    monkeypatch.delenv("WATERLAGEN_SSL_VERIFY", raising=False)
    assert Settings().waterlagen_ssl_verify is False

    monkeypatch.setenv("WATERLAGEN_SSL_VERIFY", "true")
    assert Settings().waterlagen_ssl_verify is True


def test_ssl_verify_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("WATERLAGEN_SSL_VERIFY", "not-a-boolean")
    with pytest.raises(ValidationError, match="waterlagen_ssl_verify"):
        Settings(_env_file=None)


@pytest.mark.parametrize("bundle_variable", ["REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"])
def test_ssl_verify_true_respects_requests_ca_bundle(monkeypatch, bundle_variable):
    captured_verify = []

    def fake_send(self, request, **kwargs):
        captured_verify.append(kwargs["verify"])
        response = requests.Response()
        response.status_code = 200
        response.request = request
        return response

    monkeypatch.setattr(_http.settings, "waterlagen_ssl_verify", True)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    monkeypatch.setenv(bundle_variable, "C:/certificates/trusted.pem")
    monkeypatch.setattr(requests.sessions.Session, "send", fake_send)

    _http.get("https://example.test/data", timeout=7)

    assert captured_verify == ["C:/certificates/trusted.pem"]


def test_ssl_verify_false_overrides_ca_bundle_and_warns_once(monkeypatch, caplog):
    captured = []

    def fake_send(self, request, **kwargs):
        captured.append((request.method, kwargs["verify"]))
        response = requests.Response()
        response.status_code = 200
        response.request = request
        return response

    monkeypatch.setattr(_http.settings, "waterlagen_ssl_verify", False)
    monkeypatch.setattr(_http, "_warned_insecure_download", False)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "C:/certificates/trusted.pem")
    monkeypatch.setattr(requests.sessions.Session, "send", fake_send)
    caplog.set_level(logging.WARNING, logger="waterlagen._http")

    _http.get("https://example.test/data", timeout=7)
    _http.post("https://example.test/job", json={"key": "value"})

    assert captured == [("GET", False), ("POST", False)]
    warnings = [
        record.message for record in caplog.records if record.name == _http.__name__
    ]
    assert len(warnings) == 1
    assert "identiteit van de downloadserver" in warnings[0]
    assert _http.CERTIFICATE_HELP_URL in warnings[0]


def test_redirect_keeps_certificate_policy(monkeypatch):
    captured = []

    def fake_send(self, request, **kwargs):
        captured.append((request.url, kwargs["verify"]))
        response = requests.Response()
        response.request = request
        response.url = request.url
        response._content = b""
        if request.url.endswith("/start"):
            response.status_code = 302
            response.headers["Location"] = "https://example.test/file"
        else:
            response.status_code = 200
        return response

    monkeypatch.setattr(_http.settings, "waterlagen_ssl_verify", False)
    monkeypatch.setattr(_http, "_warned_insecure_download", False)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "C:/certificates/trusted.pem")
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake_send)

    response = _http.get("https://example.test/start", timeout=7)

    assert response.url == "https://example.test/file"
    assert captured == [
        ("https://example.test/start", False),
        ("https://example.test/file", False),
    ]


def test_ssl_error_explains_both_routes_without_retry(monkeypatch):
    calls = []
    original_error = requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED")

    def fail_get(*, url, verify, timeout):
        calls.append((url, verify, timeout))
        raise original_error

    monkeypatch.setattr(_http.settings, "waterlagen_ssl_verify", True)
    monkeypatch.setattr(_http.requests, "get", fail_get)

    with pytest.raises(requests.exceptions.SSLError) as error:
        _http.get("https://example.test/source.gpkg", timeout=11)

    assert calls == [("https://example.test/source.gpkg", True, 11)]
    assert error.value.__cause__ is original_error
    assert "https://example.test/source.gpkg" in str(error.value)
    assert "REQUESTS_CA_BUNDLE" in str(error.value)
    assert "WATERLAGEN_SSL_VERIFY=false" in str(error.value)
    assert _http.CERTIFICATE_HELP_URL in str(error.value)


def test_ssl_error_with_verification_off_is_not_misreported(monkeypatch):
    original_error = requests.exceptions.SSLError("TLS handshake failed")

    def fail_get(*, url, verify, timeout):
        assert verify is False
        raise original_error

    monkeypatch.setattr(_http.settings, "waterlagen_ssl_verify", False)
    monkeypatch.setattr(_http, "_warned_insecure_download", False)
    monkeypatch.setattr(_http.requests, "get", fail_get)

    with pytest.raises(requests.exceptions.SSLError) as error:
        _http.get("https://example.test/source.gpkg", timeout=11)

    assert error.value is original_error


def test_bgt_request_and_poll_use_same_certificate_policy(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_post(*, url, verify, json):
        calls.append(("POST", url, verify))
        return FakeResponse({"downloadRequestId": "job-1"})

    def fake_get(*, url, verify, timeout):
        calls.append(("GET", url, verify))
        return FakeResponse(
            {"status": "COMPLETED", "_links": {"download": {"href": "/file.zip"}}}
        )

    monkeypatch.setattr(_http.settings, "waterlagen_ssl_verify", False)
    monkeypatch.setattr(_http, "_warned_insecure_download", False)
    monkeypatch.setattr(_http.requests, "post", fake_post)
    monkeypatch.setattr(_http.requests, "get", fake_get)

    request_id = request_download(["waterdeel"], None)
    download_url = poll_downloadstatus(request_id, poll_interval_s=0)

    assert request_id == "job-1"
    assert download_url.endswith("/file.zip")
    assert [method for method, _, _ in calls] == ["POST", "GET"]
    assert all(verify is False for _, _, verify in calls)
