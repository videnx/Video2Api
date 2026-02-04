"""日志初始化"""
import logging
import os

from app.core.config import settings


def setup_logging() -> None:
    os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(settings.log_file, encoding="utf-8"),
        ],
    )
