"""CLI entrypoint."""

import logging
import sys

from bingo_watcher.config import ConfigError, load_settings
from bingo_watcher.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()

    try:
        settings = load_settings()
    except ConfigError as exc:
        logger.error(str(exc))
        sys.exit(1)

    configure_logging(settings.log_level)
    logger.info("starting bingo-watcher")
    logger.info(
        "loaded config: %d ticker(s) watched, multiplier=%s",
        len(settings.watchlist),
        settings.multiplier,
    )


if __name__ == "__main__":
    main()
