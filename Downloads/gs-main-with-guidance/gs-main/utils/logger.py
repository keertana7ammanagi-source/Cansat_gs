"""
Logging configuration for the ground station.
"""
import os
import sys
import logging
from pathlib import Path

from config.config_loader import Config


def setup_logging():
    """
    Configure Python logging: file + console.
    Creates the log directory if it doesn't exist.
    """
    cfg = Config()
    log_file = cfg.get('logging.file', 'logs/ground_station.log')
    log_level_name = cfg.get('logging.level', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Silence noisy third-party logs (optional)
    logging.getLogger('PyQt5').setLevel(logging.WARNING)

    logging.info("Logging initialized. Log file: %s", log_file)


def get_logger(name: str):
    """
    Get a logger instance for a module.
    """
    return logging.getLogger(name)