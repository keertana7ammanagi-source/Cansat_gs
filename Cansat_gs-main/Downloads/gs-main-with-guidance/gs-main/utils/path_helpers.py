"""
Path management utilities.
"""
import os
import logging
from pathlib import Path

from config.config_loader import Config


def ensure_directories():
    """
    Create all required directories: logs, data, flights, images.
    """
    cfg = Config()
    base = Path(cfg.base_dir)

    dirs = [
        cfg.get('logging.file', 'logs/ground_station.log'),
        cfg.get('paths.data', 'data/'),
        cfg.get('paths.flights', 'data/flights/'),
        cfg.get('paths.images', 'data/images/'),
    ]

    for d in dirs:
        p = Path(d)
        if p.suffix:  # It's a file path
            p.parent.mkdir(parents=True, exist_ok=True)
        else:         # It's a directory
            p.mkdir(parents=True, exist_ok=True)

    logging.info("Directories verified/created.")


def resolve_path(path: str) -> Path:
    """
    Resolve a path relative to the project root.
    """
    cfg = Config()
    return Path(cfg.base_dir) / path