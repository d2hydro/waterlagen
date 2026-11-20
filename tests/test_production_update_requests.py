"""Download failures and damaged recovery records leave installations intact."""

import io
import json
from urllib.error import HTTPError

import pytest
import test_production_update as production_update
from test_production_update import NEW, OLD, release_files, updater, zip_bytes

project = production_update.project


@pytest.mark.parametrize("requested", [None, NEW, "v" + NEW])
def test_release_selection_reads_the_requested_github_release(monkeypatch, requested):
    urls = []

    def response(request, *, timeout):
        assert timeout == 60
        headers = {key.lower(): value for key, value in request.header_items()}
        assert headers["user-agent"] == "waterlagen-bijwerken"
        urls.append(request.full_url)
        return io.BytesIO(json.dumps({"tag_name": "v" + NEW}).encode())

    monkeypatch.setattr(updater, "urlopen", response)
    assert updater._release(requested) == "v" + NEW
    suffix = "latest" if requested is None else "tags/" + requested
    assert urls == [
        f"https://api.github.com/repos/d2hydro/waterlagen/releases/{suffix}"
    ]


@pytest.mark.parametrize("requested", [NEW, "v" + NEW])
def test_release_selection_tries_the_alternative_tag_after_a_404(
    monkeypatch, requested
):
    urls = []

    def response(request, *, timeout):
        urls.append(request.full_url)
        if len(urls) == 1:
            raise HTTPError(request.full_url, 404, "Not found", {}, None)
        return io.BytesIO(json.dumps({"tag_name": NEW}).encode())

    monkeypatch.setattr(updater, "urlopen", response)
    assert updater._release(requested) == NEW
    alternative = NEW if requested.startswith("v") else "v" + NEW
    assert urls[-1].endswith("/tags/" + alternative)


def test_release_http_error_is_not_retried_as_a_different_version(monkeypatch):
    requests = []

    def unavailable(request, *, timeout):
        requests.append(request)
        raise HTTPError(request.full_url, 503, "Unavailable", {}, None)

    monkeypatch.setattr(updater, "urlopen", unavailable)
    with pytest.raises(HTTPError) as failure:
        updater._release(NEW)
    assert failure.value.code == 503
    assert len(requests) == 1


def test_download_size_is_bounded_before_parsing(monkeypatch):
    monkeypatch.setattr(updater, "MAX_DOWNLOAD", 8)
    monkeypatch.setattr(
        updater, "urlopen", lambda request, timeout: io.BytesIO(b"123456789")
    )
    with pytest.raises(ValueError, match="onverwacht groot"):
        updater._get("https://example.test/package")


def test_invalid_release_version_is_rejected_before_download(monkeypatch):
    monkeypatch.setattr(updater, "_get", lambda url: pytest.fail("Unexpected download"))
    with pytest.raises(ValueError, match="Ongeldig versienummer"):
        updater._release("main")


@pytest.mark.parametrize(
    "problem",
    [
        "shape",
        "backup_type",
        "file_type",
        "directory",
        "location",
        "boolean",
        "user_path",
    ],
)
def test_invalid_recovery_metadata_does_not_change_software(project, problem):
    root, private = project
    originals = {name: (root / name).read_bytes() for name in release_files(OLD)}
    state = {"backup": ".updates/previous", "files": {"README.md": True}}
    if problem == "shape":
        state = []
    elif problem == "backup_type":
        state["backup"] = None
    elif problem == "file_type":
        state["files"] = []
    elif problem == "directory":
        state["backup"] = ".updates"
    elif problem == "location":
        state["backup"] = "other"
    elif problem == "boolean":
        state["files"]["README.md"] = "true"
    else:
        state["files"] = {".env": True}
    (root / updater.PENDING).write_text(json.dumps(state))
    with pytest.raises(ValueError):
        updater.update(root, yes=True)
    assert (root / updater.PENDING).is_file()
    for name, content in {**originals, **private}.items():
        assert (root / name).read_bytes() == content


def test_release_without_an_updater_is_rejected(monkeypatch):
    files = release_files(NEW)
    del files["tools/code_bijwerken.py"]
    files[updater.METADATA] = json.dumps(
        {"version": NEW, "files": updater._hashes(files)}
    ).encode()
    monkeypatch.setattr(updater, "_get", lambda url: zip_bytes(files))
    with pytest.raises(ValueError, match="geen volledige updater"):
        updater._bundle(NEW)
