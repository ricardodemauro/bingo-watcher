"""CLI entrypoint."""

import logging

from bingo_watcher.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    logger.info("starting bingo-watcher")


if __name__ == "__main__":
    main()
