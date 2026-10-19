"""
Image Archive – saves frames from cameras.
"""
import os
import time
from datetime import datetime
from pathlib import Path

from config.config_loader import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class ImageArchive:
    def __init__(self, base_dir: str = None):
        cfg = Config()
        if base_dir is None:
            base_dir = cfg.get('paths.images', 'data/images/')

        self.base_dir = Path(base_dir)
        self.atmospheric_dir = self.base_dir / 'atmospheric_cam'
        self.ground_dir = self.base_dir / 'ground_cam'
        self.atmospheric_dir.mkdir(parents=True, exist_ok=True)
        self.ground_dir.mkdir(parents=True, exist_ok=True)

    def _target_dir(self, camera: str) -> Path:
        if camera == 'atmospheric':
            return self.atmospheric_dir
        elif camera == 'ground':
            return self.ground_dir
        else:
            raise ValueError("camera must be 'atmospheric' or 'ground'")

    def save_frame(self, camera: str, image_bytes: bytes, mission_time: str = None) -> str:
        from config import TEAM_ID  # keep old import for now, or import from constants
        # We'll move TEAM_ID to core/telemetry/constants later.
        target = self._target_dir(camera)
        stamp = mission_time.replace(':', '-') if mission_time else datetime.now().strftime('%H-%M-%S')
        filename = f"{TEAM_ID}_{camera}_{stamp}_{int(time.time()*1000)}.jpg"
        filepath = target / filename
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        logger.debug(f"Saved frame: {filepath}")
        return str(filepath)

    def latest_frame(self, camera: str) -> str:
        target = self._target_dir(camera)
        files = list(target.glob('*.jpg'))
        if not files:
            return None
        latest = max(files, key=os.path.getmtime)
        return str(latest)

    def frame_count(self, camera: str) -> int:
        target = self._target_dir(camera)
        return len(list(target.glob('*.jpg')))