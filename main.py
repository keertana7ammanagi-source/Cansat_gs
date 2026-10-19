#!/usr/bin/env python3
"""
ANTRS-GroundStation – Main entry point.
"""
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5 import QtWidgets
from ui.main_window import MainWindow
from utils.logger import setup_logging
from utils.path_helpers import ensure_directories
from config.config_loader import Config


def main():
    # 1. Load config
    cfg = Config()

    # 2. Setup logging
    setup_logging()

    # 3. Ensure all required directories exist
    ensure_directories()

    # 4. Launch the application
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()