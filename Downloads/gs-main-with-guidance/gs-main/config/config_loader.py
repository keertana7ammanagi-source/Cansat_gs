"""
Central configuration loader – singleton pattern with YAML support.
"""
import os
import yaml
from pathlib import Path

_DEFAULT_CONFIG = {
    'serial': {'baud_rate': 115200, 'default_port': ''},
    'lora': {'frequency': 915000000, 'sync_word': 0x12},
    'logging': {'level': 'INFO', 'file': 'logs/ground_station.log'},
    'ui': {'theme': 'dark', 'graph_buffer_size': 300},
    'paths': {
        'data': 'data/',
        'images': 'data/images/',
        'flights': 'data/flights/'
    }
}


class Config:
    """
    Singleton configuration class.
    Loads settings.yaml if present, otherwise uses defaults.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        # Project root is where this file is: config/
        self.base_dir = Path(__file__).parent.parent
        self.config = _DEFAULT_CONFIG.copy()

        # Load user settings if they exist
        user_file = Path(__file__).parent / 'settings.yaml'
        if user_file.exists():
            try:
                with open(user_file, 'r') as f:
                    user = yaml.safe_load(f)
                    if user:
                        self._merge(user)
            except Exception as e:
                print(f"Warning: Failed to load settings.yaml: {e}")

    def _merge(self, user):
        """Deep merge of user config into defaults."""
        for key, value in user.items():
            if isinstance(value, dict) and key in self.config and isinstance(self.config[key], dict):
                self.config[key].update(value)
            else:
                self.config[key] = value

    def get(self, key: str, default=None):
        """
        Get a configuration value using dot notation.
        Example: config.get('serial.baud_rate') -> 115200
        """
        keys = key.split('.')
        val = self.config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
                if val is None:
                    return default
            else:
                return default
        return val if val is not None else default

    def __getitem__(self, key):
        return self.get(key)