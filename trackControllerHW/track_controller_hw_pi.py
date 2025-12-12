# trackControllerHW/track_controller_hw_pi.py
from __future__ import annotations
import os
import sys
import logging

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
    """
    Minimal stand-in for TrackNetwork on the Pi if you don't want to
    run the full Track Model there. It just gives the backend a
    .segments dict so it doesn't crash when checking adjacency, etc.
    """
    def __init__(self, line_name: str) -> None:
        self.line_name = line_name
        self.segments = {}  # if backend accesses this, it just sees empty


def main() -> None:
    # 1) Build dummy track models for each line the Pi HW controls
    #    If your HW controller only handles Green Line, you can just keep one.
    green_model = DummyTrackModel("Green Line")
    # red_model = DummyTrackModel("Red Line")  # uncomment if Pi also controls Red

    # 2) Create the HW controllers (using the same class as in main.py)
    hw_controllers = {
        "Green Line": HardwareTrackControllerBackend(green_model, "Green Line"),
        # "Red Line": HardwareTrackControllerBackend(red_model, "Red Line"),
    }

    # 3) Attach NetworkCTCProxy so HW controller sends status to laptop
    LAPTOP_IP = "10.4.6.21"  # CHANGE THIS to your friend's laptop IP
    proxy = NetworkCTCProxy(host=LAPTOP_IP, port=6000)
    for backend in hw_controllers.values():
        backend.set_ctc_backend(proxy)

    # (Optional) If you still want the HW backend to poll a local track model,
    # you can call backend.start_live_link(...). Since we are using DummyTrackModel,
    # you probably don't need live link on the Pi.

    # 4) Start HW UI on the Pi
    app = QApplication(sys.argv)
    hw_ui = TrackControllerHWUI(hw_controllers)
    hw_ui.setWindowTitle("Wayside Controller – Hardware UI (Pi)")
    hw_ui.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
