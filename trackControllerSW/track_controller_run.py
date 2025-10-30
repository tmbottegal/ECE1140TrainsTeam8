from __future__ import annotations
import sys,os,logging

_pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..")) # it makes shit work
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)

from typing import NoReturn
from PyQt6.QtWidgets import QApplication, QFileDialog
from track_controller_backend import TrackControllerBackend
from track_controller_ui import TrackControllerUI
from trackModel.track_model_backend import TrackNetwork as TrackModelNetwork

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

def main() -> NoReturn:
    app = QApplication(sys.argv)
    track_model_network = TrackModelNetwork()
    controllers = {
        "Blue Line": TrackControllerBackend(track_model_network, line_name="Blue Line"),
        "Red Line": TrackControllerBackend(track_model_network, line_name="Red Line"),
        "Green Line": TrackControllerBackend(track_model_network, line_name="Green Line"),
    }

    # Start live update link for all controllers
    for backend in controllers.values():
        backend.start_live_link(poll_interval=1.0)

    ui = TrackControllerUI(controllers)
    def upload_file() -> None:
        filepath, _ = QFileDialog.getOpenFileName(ui, "Open PLC File", "", "PLC Files (*.txt *.plc *.py)")
        if not filepath:
            logger.info("PLC file selection cancelled.")
            return
        ui.filename_box.setText(f"File: {filepath}")
        try:
            current_line_name = ui.track_picker.currentText()
            backend = controllers[current_line_name]
            backend.upload_plc(filepath)
            ui.refresh_tables()
            logger.info("PLC file %s uploaded for %s", filepath, current_line_name)
        except Exception as exc:
            logger.exception("PLC upload failed: %s", exc)
    ui.plc_button.clicked.connect(upload_file)
    ui.refresh_tables()
    ui.resize(1800, 1100)
    ui.setWindowTitle("Track Controller Module")
    ui.show()
    logger.info("Track Controller UI launched successfully.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
