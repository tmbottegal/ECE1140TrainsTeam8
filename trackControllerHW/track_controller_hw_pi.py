"""Raspberry Pi entry point for Hardware Track Controller."""
from __future__ import annotations

import logging
import os
import sys

from PyQt6.QtWidgets import QApplication

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trackControllerHW.track_controller_hw_backend import HardwareTrackControllerBackend
from trackControllerHW.track_controller_hw_ui import TrackControllerHWUI

try:
    from trackControllerHW.network_ctc_proxy import NetworkCTCProxy
except ImportError:
    from network_ctc_proxy import NetworkCTCProxy

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class DummyTrackModel:
    """Minimal stand-in for TrackNetwork on the Pi."""

    def __init__(self, line_name: str) -> None:
        self.line_name = line_name
        self.segments: dict = {}


def main() -> None:
    """Initialize and run the hardware track controller on Pi."""
    green_model = DummyTrackModel("Green Line")

    hw_controllers = {
        "Green Line": HardwareTrackControllerBackend(green_model, "Green Line"),
    }

    # Change this IP to match your laptop
    LAPTOP_IP = "10.6.18.59"
    proxy = NetworkCTCProxy(host=LAPTOP_IP, port=6000)
    for backend in hw_controllers.values():
        backend.set_ctc_backend(proxy)

    app = QApplication(sys.argv)
    hw_ui = TrackControllerHWUI(hw_controllers)
    hw_ui.setWindowTitle("Wayside Controller - Hardware UI (Pi)")
    hw_ui.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()