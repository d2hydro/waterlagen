import logging
from logging.handlers import RotatingFileHandler

import pytest

import waterlagen.logger as logger_mod


@pytest.fixture
def clean_root_logger(monkeypatch):
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level

    for handler in list(root.handlers):
        root.removeHandler(handler)
    monkeypatch.setattr(logger_mod, "_LOG_CONFIGURED", False)

    yield root

    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    for handler in original_handlers:
        root.addHandler(handler)
    root.setLevel(original_level)


def test_ensure_parent_dir_creates_missing_parent(tmp_path):
    target = tmp_path / "logs" / "app.log"
    logger_mod._ensure_parent_dir(target)
    assert target.parent.exists()


def test_make_file_handler_sets_level_and_path(tmp_path):
    log_file = tmp_path / "run.log"
    handler = logger_mod._make_file_handler(
        log_file=log_file,
        level=logging.WARNING,
        max_bytes=1024,
        backup_count=2,
        delay=True,
    )

    assert isinstance(handler, RotatingFileHandler)
    assert handler.level == logging.WARNING
    assert handler.baseFilename == str(log_file.resolve())
    assert handler.formatter is not None
    handler.close()


def test_configure_logging_is_idempotent_for_same_file(tmp_path, clean_root_logger):
    log_file = tmp_path / "app.log"
    initial_stream_non_file = len(
        [
            h
            for h in clean_root_logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, RotatingFileHandler)
        ]
    )

    root_1 = logger_mod.configure_logging(log_file=log_file, stdout=True)
    root_2 = logger_mod.configure_logging(log_file=log_file, stdout=True)

    file_handlers = [h for h in root_2.handlers if isinstance(h, RotatingFileHandler)]
    stream_handlers = [
        h
        for h in root_2.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, RotatingFileHandler)
    ]

    assert root_1 is root_2
    assert len(file_handlers) == 1
    assert len(stream_handlers) == initial_stream_non_file
    assert logger_mod._LOG_CONFIGURED is True


def test_configure_logging_switches_file_handler(tmp_path, clean_root_logger):
    log_a = tmp_path / "a.log"
    log_b = tmp_path / "b.log"

    logger_mod.configure_logging(log_file=log_a, stdout=False)
    root = logger_mod.configure_logging(log_file=log_b, stdout=False)

    file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(log_b.resolve())


@pytest.mark.parametrize(
    "debug, expected_level",
    [(True, logging.DEBUG), (False, logging.INFO)],
)
def test_init_logger_configures_level(monkeypatch, tmp_path, debug, expected_level):
    captured = {}
    log_file = tmp_path / "app.log"

    def _fake_configure_logging(**kwargs):
        captured.update(kwargs)
        return logging.getLogger()

    monkeypatch.setattr(logger_mod, "configure_logging", _fake_configure_logging)

    logger = logger_mod.init_logger(name="waterlagen.test", log_file=log_file, debug=debug)

    assert logger.name == "waterlagen.test"
    assert captured["log_file"] == log_file
    assert captured["level"] == expected_level
    assert captured["delay"] is True
