import logging
from logging import Logger

from rich.logging import RichHandler


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        force=True,
    )


def get_logger(name: str) -> Logger:
    return logging.getLogger(name)

