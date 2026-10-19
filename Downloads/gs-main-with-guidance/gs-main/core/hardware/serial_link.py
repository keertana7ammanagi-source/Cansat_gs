"""
Hardware Abstraction Layer - Serial I/O (non-blocking).
"""
import queue
import threading
import time
import serial
import serial.tools.list_ports

from config.config_loader import Config
from utils.logger import get_logger

logger = get_logger(__name__)


def list_available_ports():
    return [(p.device, p.description) for p in serial.tools.list_ports.comports()]


class SerialLink:
    def __init__(self, port: str, baud: int = None):
        cfg = Config()
        self.port_name = port
        self.baud = baud or cfg.get('serial.baud_rate', 115200)
        self.ser = None
        self._rx_queue = queue.Queue()
        self._stop_flag = threading.Event()
        self._reader_thread = None
        self._link_broken = threading.Event()  # set only on an unexpected I/O error

    def connect(self):
        try:
            self.ser = serial.Serial(self.port_name, self.baud, timeout=0.2)
            self._stop_flag.clear()
            self._link_broken.clear()
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()
            logger.info(f"Serial connected: {self.port_name} @ {self.baud} baud")
        except Exception as e:
            logger.error(f"Serial connect error: {e}")
            raise

    def disconnect(self):
        self._stop_flag.set()
        if self._reader_thread:
            self._reader_thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                logger.info(f"Serial disconnected: {self.port_name}")
            except (serial.SerialException, OSError) as e:
                # Expected if the device was physically removed -- the
                # port is gone either way, so this isn't fatal.
                logger.warning(f"Error closing already-broken serial port: {e}")

    def is_connected(self):
        return self.ser is not None and self.ser.is_open

    def is_link_broken(self):
        """
        True only if the reader thread died from an actual I/O error (e.g.
        the USB cable/device physically disappeared) -- NOT true just
        because no telemetry has arrived recently, which is expected
        whenever the CanSat/RF link is quiet. is_connected() alone can't
        tell these apart: on some OS/driver combos self.ser.is_open stays
        True even after the underlying device is gone.
        """
        return self._link_broken.is_set()

    def _read_loop(self):
        while not self._stop_flag.is_set():
            try:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode(errors='ignore').strip()
                    if line:
                        self._rx_queue.put(line)
                else:
                    time.sleep(0.02)
            except (serial.SerialException, OSError) as e:
                logger.error(f"Serial read error: {e}")
                self._link_broken.set()
                self._stop_flag.set()
                break

    def read_available_lines(self):
        lines = []
        while not self._rx_queue.empty():
            try:
                lines.append(self._rx_queue.get_nowait())
            except queue.Empty:
                break
        return lines

    def send_command(self, cmd: str):
        if self.is_connected():
            self.ser.write((cmd.strip() + '\n').encode())
            logger.debug(f"Sent command: {cmd}")
        else:
            logger.warning("Attempted to send command while disconnected.")