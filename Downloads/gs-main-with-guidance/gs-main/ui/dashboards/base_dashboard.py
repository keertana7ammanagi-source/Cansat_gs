"""
Base class for all dashboards.
"""
from PyQt5 import QtWidgets


class BaseDashboard(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def update(self, packet):
        raise NotImplementedError("Subclasses must implement update()")

    def reset(self):
        pass