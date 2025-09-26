"""Basic structured logging setup.

For now we keep it minimal; can be extended with structlog / loguru later.
"""
import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    root.setLevel(level.upper())
    root.addHandler(handler)


logger = logging.getLogger("legalgene")