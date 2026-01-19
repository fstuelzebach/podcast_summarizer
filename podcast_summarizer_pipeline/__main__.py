import logging

from .logging_config import setup_logging
from .pipeline import run_pipeline


def main() -> None:
    setup_logging(logging.INFO)
    run_pipeline()


if __name__ == "__main__":
    main()
