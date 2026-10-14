"""Opt-in production logging with one writer for parent and worker processes."""

import logging
import multiprocessing
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path

_context: ContextVar[str] = ContextVar(
    "production_log_context", default="voorbereiding"
)
_queue = None
_writer = None


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.production = _context.get()
        return True


class _RunWriter(logging.Handler):
    """Keep all file I/O in the listener, including nested-production messages."""

    def __init__(self, level: int) -> None:
        super().__init__(level)
        self.file: logging.FileHandler | None = None
        self.terminal = logging.StreamHandler(sys.stderr)
        self.terminal.setFormatter(
            logging.Formatter("%(levelname)s [%(production)s] %(message)s")
        )
        self.pending: list[logging.LogRecord] = []
        self.parent_pid = os.getpid()

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.WARNING or (
            record.levelno >= logging.INFO and record.process == self.parent_pid
        ):
            self.terminal.handle(record)
        if self.file is None:
            self.pending.append(record)
        else:
            self.file.handle(record)

    def attach(self, path: Path) -> None:
        with self.lock:
            if self.file is not None:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            self.file = logging.FileHandler(path, encoding="utf-8")
            self.file.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s [%(production)s] %(name)s: %(message)s"
                )
            )
            for record in self.pending:
                self.file.handle(record)
            self.pending.clear()

    def close(self) -> None:
        if self.file is not None:
            self.file.close()
        self.terminal.close()
        super().close()


def _queue_handler(queue, level: int) -> QueueHandler:
    handler = QueueHandler(queue)
    handler.setLevel(level)
    handler.addFilter(_ContextFilter())
    return handler


@contextmanager
def production_logging(*, debug: bool = False) -> Iterator[None]:
    """Collect production logs without permanently changing caller handlers.

    Parameters
    ----------
    debug : bool, optional
        Include diagnostic messages in the run file, default False.

    Yields
    ------
    None
        Active logging session. The first production owns ``productie.log``;
        nested productions and worker processes share its queue and writer.
        The root logger is left untouched and package handlers are restored.
    """
    global _queue, _writer
    if _queue is not None:
        yield
        return
    logger = logging.getLogger("waterlagen")
    previous = logger.handlers[:], logger.level, logger.propagate
    level = logging.DEBUG if debug else logging.INFO
    queue = multiprocessing.get_context("spawn").Queue()
    writer = _RunWriter(level)
    listener = QueueListener(queue, writer, respect_handler_level=True)
    _queue, _writer = queue, writer
    handler = _queue_handler(queue, level)
    logger.handlers, logger.level, logger.propagate = [handler], level, False
    listener.start()
    try:
        yield
    finally:
        listener.stop()
        logger.handlers, logger.level, logger.propagate = previous
        handler.close()
        writer.close()
        queue.close()
        queue.join_thread()
        _queue, _writer = None, None


@contextmanager
def run_log(path: Path) -> Iterator[None]:
    """Attach the top-level run file; nested runs retain the same writer."""
    if _writer is not None:
        _writer.attach(path / "productie.log")
    with log_context(str(path)):
        yield


@contextmanager
def log_context(description: str) -> Iterator[None]:
    """Add product, run or tile context without changing handler ownership."""
    token = _context.set(description)
    try:
        yield
    finally:
        _context.reset(token)


def initialize_worker(queue, context: str, level: int) -> None:
    """Route spawned-worker records to the parent writer."""
    global _queue
    _queue = queue
    _context.set(context)
    logger = logging.getLogger("waterlagen")
    logger.handlers = [_queue_handler(queue, level)]
    logger.setLevel(level)
    logger.propagate = False


def executor_logging() -> dict:
    """ProcessPoolExecutor arguments; leave caller-owned logging untouched by default."""
    if _queue is None:
        return {}
    return {
        "initializer": initialize_worker,
        "initargs": (_queue, _context.get(), logging.getLogger("waterlagen").level),
    }


def central_logging_active() -> bool:
    """Whether this process participates in an explicitly enabled logging session."""
    return _queue is not None
