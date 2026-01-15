import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union

# Module-level flag to avoid duplicate setup within a single process
_LOG_CONFIGURED = False


def _ensure_parent_dir(path: Path) -> None:
    """Ensure the parent directory for the given path exists."""
    path = path.expanduser()
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)


def _make_file_handler(
    log_file: Union[str, Path],
    level: int,
    max_bytes: int,
    backup_count: int,
    **handler_kwargs,
) -> RotatingFileHandler:
    """
    Create a rotating file handler with sane defaults.

    Parameters
    ----------
    log_file : str | Path
        Target log file.
    level : int
        Logging level for this handler (e.g., logging.INFO).
    max_bytes : int
        Max size in bytes before rotation.
    backup_count : int
        Number of rotated files to keep.
    **handler_kwargs
        Extra kwargs forwarded to RotatingFileHandler (e.g., delay=True).

    Returns
    -------
    RotatingFileHandler
    """
    log_path = Path(log_file).expanduser().resolve()
    _ensure_parent_dir(log_path)

    fh = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        **handler_kwargs,
    )
    fmt = "%(asctime)s %(levelname)s [%(process)d:%(threadName)s] %(name)s: %(message)s"
    fh.setFormatter(logging.Formatter(fmt))
    fh.setLevel(level)
    return fh


def configure_logging(
    *,
    log_file: Union[str, Path, None] = None,
    level: int = logging.INFO,
    max_bytes: int = 5_000_000,
    backup_count: int = 5,
    stdout: bool = True,
    stdout_format: Optional[str] = "%(levelname)s %(name)s: %(message)s",
    **handler_kwargs,
) -> logging.Logger:
    """
    Configure the root logger for a multi-module Dash app in an idempotent way.

    This function:
    - Adds exactly one RotatingFileHandler pointing to `log_file` (replacing any existing file handlers with other paths).
    - Optionally adds a single StreamHandler to stdout.
    - Avoids duplicate handlers on hot-reload within the same process.
    - Allows switching to a different `log_file` without handler duplication.

    Parameters
    ----------
    log_file : str | Path, optional
        Path to the log file (default: None).
    level : int, optional
        Root logger level (default: logging.INFO).
    max_bytes : int, optional
        Rotation size in bytes (default: 5_000_000).
    backup_count : int, optional
        Number of rotated files to keep (default: 5).
    also_stdout : bool, optional
        If True, add a StreamHandler to stdout (default: True).
    stdout_format : str | None, optional
        Format string for the stdout handler (default: "%(levelname)s %(name)s: %(message)s").
        If None, uses the logging default format.
    **handler_kwargs
        Extra kwargs forwarded to RotatingFileHandler (e.g., delay=True).

    Returns
    -------
    logging.Logger
        The configured root logger.
    """
    global _LOG_CONFIGURED
    root = logging.getLogger()
    root.setLevel(level)

    # Add stdout handler once (avoid stacking on hot-reload)
    if stdout and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root.handlers
    ):
        sh = logging.StreamHandler()
        sh.setLevel(level)
        if stdout_format is not None:
            sh.setFormatter(logging.Formatter(stdout_format))
        root.addHandler(sh)

    if log_file is not None:
        # Normalize the target path for comparison with existing handlers.
        log_file = Path(log_file).expanduser().resolve()

        # Remove any existing RotatingFileHandler not pointing to the same file.
        # Keep one if it already targets the same absolute file path.
        file_handler_exists_for_target = False
        for h in list(root.handlers):
            if isinstance(h, RotatingFileHandler):
                # Compare against absolute resolved paths
                existing = Path(getattr(h, "baseFilename", "")).expanduser().resolve()
                if existing == log_file:
                    file_handler_exists_for_target = True
                else:
                    root.removeHandler(h)
                    try:
                        h.close()
                    except Exception:
                        pass

        # Add file handler if none exists for the target file yet
        if not file_handler_exists_for_target:
            root.addHandler(
                _make_file_handler(
                    log_file=log_file,
                    level=level,
                    max_bytes=max_bytes,
                    backup_count=backup_count,
                    **handler_kwargs,
                )
            )

    _LOG_CONFIGURED = True
    return root


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger without adding handlers. Use this in all modules:
        logger = get_logger(__name__)

    Parameters
    ----------
    name : str | None
        Logger name (module name recommended). None returns the root logger.

    Returns
    -------
    logging.Logger
    """
    return logging.getLogger(name)


def init_logger(
    name: str, log_file: Path | None = None, debug: bool = True
) -> logging.Logger:
    """Initialise logging and return logger in app.py

    Parameters
    ----------
    log_dir : Path
        Directory to store log files.
    name : str, optional
        Logger name, by default "app"
    debug : bool, optional
        Debug-flag. Toggle between debug and info, by default True

    Returns
    -------
    logging.Logger
        logger instance to use in apps
    """

    # make dir and define log file
    # log_file.parent.mkdir(parents=True, exist_ok=True)
    if debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # configure logging with file
    configure_logging(log_file=log_file, level=log_level, delay=True)

    # return logger
    return get_logger(name)
