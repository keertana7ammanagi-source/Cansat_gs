"""
Camera Dashboard – atmospheric and ground camera feeds with live streaming support.
"""
import os
import threading
import cv2
from PyQt5 import QtWidgets, QtCore, QtGui

from .base_dashboard import BaseDashboard
from utils.logger import get_logger

logger = get_logger(__name__)


class CameraDashboard(BaseDashboard):
    frame_ready = QtCore.pyqtSignal(str, QtGui.QPixmap)

    def __init__(self, parent=None, image_archive=None):
        super().__init__(parent)
        self.image_archive = image_archive
        self.streaming = False
        self.cap_atmo = None
        self.cap_ground = None
        self.stream_thread = None
        self._build_ui()
        self.frame_ready.connect(self._update_camera_label)

    def _build_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(12)

        # Atmospheric
        atmo_box = QtWidgets.QGroupBox("Atmospheric Camera | Side-mounted | 30° downward")
        atmo_layout = QtWidgets.QVBoxLayout()
        self.atmo_img = QtWidgets.QLabel("No image")
        self.atmo_img.setAlignment(QtCore.Qt.AlignCenter)
        self.atmo_img.setMinimumSize(480, 360)
        self.atmo_img.setStyleSheet("border: 1px solid #2a3a4a; background: #0a1016;")
        atmo_layout.addWidget(self.atmo_img)
        self.atmo_status = QtWidgets.QLabel(
            "Resolution: 800x600 @ 30 fps\nFrames captured: --\nLast frame: --\nStorage: -- / 32 GB (SD card)"
        )
        self.atmo_status.setStyleSheet("color: #8ac0d0; font-size: 14px;")
        atmo_layout.addWidget(self.atmo_status)
        atmo_box.setLayout(atmo_layout)
        layout.addWidget(atmo_box)

        # Ground
        ground_box = QtWidgets.QGroupBox("Ground Camera | Bottom-facing | 90° downward")
        ground_layout = QtWidgets.QVBoxLayout()
        self.ground_img = QtWidgets.QLabel("No image")
        self.ground_img.setAlignment(QtCore.Qt.AlignCenter)
        self.ground_img.setMinimumSize(480, 360)
        self.ground_img.setStyleSheet("border: 1px solid #2a3a4a; background: #0a1016;")
        ground_layout.addWidget(self.ground_img)
        self.ground_status = QtWidgets.QLabel(
            "Resolution: 800x600 @ 30 fps\nFrames captured: --\nLast frame: --\nStorage: -- / 32 GB (SD card)"
        )
        self.ground_status.setStyleSheet("color: #8ac0d0; font-size: 14px;")
        ground_layout.addWidget(self.ground_status)
        ground_box.setLayout(ground_layout)
        layout.addWidget(ground_box)

        # Info panel
        info = QtWidgets.QVBoxLayout()
        info.addWidget(QtWidgets.QLabel("Libraries: OpenCV, PyQt5, Pillow"))
        info.addWidget(QtWidgets.QLabel("Stream: ESP32-CAM HTTP / RTSP"))
        info.addWidget(QtWidgets.QLabel("Capture interval: 5 seconds (archive)"))
        info.addWidget(QtWidgets.QLabel("Storage: Local archive + SD card"))
        info.addWidget(QtWidgets.QLabel("Inference: Post-flight AI analysis"))
        info.addStretch()
        layout.addLayout(info)

    def start_stream(self, camera: str, url: str):
        if camera == 'atmospheric':
            self.atmo_url = url
            if self.cap_atmo is not None:
                self.cap_atmo.release()
            self.cap_atmo = cv2.VideoCapture(url)
            if not self.cap_atmo.isOpened():
                logger.error(f"Could not open atmospheric stream: {url}")
                return
        elif camera == 'ground':
            self.ground_url = url
            if self.cap_ground is not None:
                self.cap_ground.release()
            self.cap_ground = cv2.VideoCapture(url)
            if not self.cap_ground.isOpened():
                logger.error(f"Could not open ground stream: {url}")
                return
        else:
            return

        if not self.streaming:
            self.streaming = True
            self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
            self.stream_thread.start()

    def _stream_loop(self):
        while self.streaming:
            if self.cap_atmo is not None and self.cap_atmo.isOpened():
                ret, frame = self.cap_atmo.read()
                if ret:
                    self.frame_ready.emit("atmospheric", self._cv_to_pixmap(frame))
                else:
                    logger.warning("Atmospheric stream lost.")
                    self.cap_atmo.release()
                    self.cap_atmo = None

            if self.cap_ground is not None and self.cap_ground.isOpened():
                ret, frame = self.cap_ground.read()
                if ret:
                    self.frame_ready.emit("ground", self._cv_to_pixmap(frame))
                else:
                    logger.warning("Ground stream lost.")
                    self.cap_ground.release()
                    self.cap_ground = None

            QtCore.QThread.msleep(33)

    def _cv_to_pixmap(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_img = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        return QtGui.QPixmap.fromImage(qt_img)

    def _update_camera_label(self, camera: str, pixmap: QtGui.QPixmap):
        if camera == 'atmospheric':
            self.atmo_img.setPixmap(pixmap.scaled(480, 360, QtCore.Qt.KeepAspectRatio))
        elif camera == 'ground':
            self.ground_img.setPixmap(pixmap.scaled(480, 360, QtCore.Qt.KeepAspectRatio))

    def stop_stream(self):
        self.streaming = False
        if self.stream_thread is not None:
            self.stream_thread.join(timeout=2.0)
            self.stream_thread = None
        if self.cap_atmo:
            self.cap_atmo.release()
            self.cap_atmo = None
        if self.cap_ground:
            self.cap_ground.release()
            self.cap_ground = None

    def refresh_images(self, image_archive):
        if self.streaming:
            return
        if not image_archive:
            return
        for cam, img_label, status_label in [
            ("atmospheric", self.atmo_img, self.atmo_status),
            ("ground", self.ground_img, self.ground_status)
        ]:
            latest = image_archive.latest_frame(cam)
            if latest and os.path.exists(latest):
                pixmap = QtGui.QPixmap(latest)
                if not pixmap.isNull():
                    img_label.setPixmap(pixmap.scaled(480, 360, QtCore.Qt.KeepAspectRatio))
                    count = image_archive.frame_count(cam)
                    status_label.setText(
                        f"Resolution: 800x600 @ 30 fps\n"
                        f"Frames captured: {count}\n"
                        f"Last frame: {os.path.basename(latest)}\n"
                        f"Storage: {count*0.2:.1f} MB / 32 GB (SD card)"
                    )
                    continue
            dummy = QtGui.QPixmap(480, 360)
            dummy.fill(QtGui.QColor(10, 16, 22))
            painter = QtGui.QPainter(dummy)
            painter.setPen(QtGui.QColor(60, 90, 120))
            painter.drawText(dummy.rect(), QtCore.Qt.AlignCenter, f"[ No {cam} feed ]\n(Simulated)")
            painter.end()
            img_label.setPixmap(dummy)
            status_label.setText(
                f"Resolution: 800x600 @ 30 fps\n"
                f"Frames captured: 0\n"
                f"Last frame: --\n"
                f"Storage: 0 / 32 GB (SD card)"
            )

    def update(self, packet):
        pass

    def reset(self):
        self.stop_stream()