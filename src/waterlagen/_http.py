"""TLS policy for HTTPS requests made by Waterlagen downloaders."""

from threading import Lock
from typing import Any

import requests

from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(__name__)

CERTIFICATE_HELP_URL = (
    "https://d2hydro.github.io/waterlagen/produceren/https-certificaatproblemen/"
)


class DownloadCertificateError(requests.exceptions.SSLError):
    """A Waterlagen download failed certificate verification."""


def explain_certificate_error(url: str) -> DownloadCertificateError:
    """Add the source URL and recovery options to a certificate failure."""
    return DownloadCertificateError(
        f"HTTPS-certificaatcontrole mislukt voor {url}. "
        "Vraag uw IT-beheerder om een vertrouwd PEM-certificaatbestand "
        "en stel REQUESTS_CA_BUNDLE in, of zet "
        "WATERLAGEN_SSL_VERIFY=false in .env voor downloads door Waterlagen. "
        f"Uitleg: {CERTIFICATE_HELP_URL}"
    )


_warning_lock = Lock()
_warned_insecure_download = False


def _verify_certificates() -> bool:
    global _warned_insecure_download

    verify = settings.waterlagen_ssl_verify
    if verify:
        return True

    with _warning_lock:
        if not _warned_insecure_download:
            logger.warning(
                "HTTPS-certificaatcontrole voor Waterlagen-downloads is uitgeschakeld. "
                "De identiteit van de downloadserver wordt niet gecontroleerd. "
                "Gebruik bij voorkeur een vertrouwd PEM-certificaatbestand: %s",
                CERTIFICATE_HELP_URL,
            )
            _warned_insecure_download = True
    return False


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Apply the configured TLS policy and explain certificate failures."""
    verify = _verify_certificates()
    try:
        if method == "GET":
            return requests.get(url=url, verify=verify, **kwargs)
        return requests.post(url=url, verify=verify, **kwargs)
    except requests.exceptions.SSLError as exc:
        if not verify:
            raise
        raise explain_certificate_error(url) from exc


def get(url: str, **kwargs: Any) -> requests.Response:
    """Make a GET request with Waterlagen's configured TLS policy."""
    return _request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> requests.Response:
    """Make a POST request with Waterlagen's configured TLS policy."""
    return _request("POST", url, **kwargs)
