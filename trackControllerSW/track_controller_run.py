"""Track Controller application entry point.

This module launches the PyQt-based Track Controller user interface and
wires together the TrackNetwork backend with UI controls.

Refactored to follow the Google Python Style Guide:
- Type hints
- Proper docstrings
- Structured logging
"""

from __future__ import annotations

import logging
import sys
from typing import NoReturn
from PyQt6.QtWidgets import QApplication, QFileDialog
from track_controller_backend import TrackNetwork
from track_controller_ui import TrackControllerUI

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> NoReturn:
    """Launch the Track Controller GUI application."""
    app = QApplication(sys.argv)

    # Initialize network and user interface.
    network = TrackNetwork()
    ui = TrackControllerUI(network)

    def upload_file() -> None:
        """Handle PLC file uploads via file dialog."""
        filepath, _ = QFileDialog.getOpenFileName(
            ui,
            "Open PLC File",
            "",
            "PLC Files (*.txt *.plc *.py)"
        )

        if not filepath:
            logger.info("PLC file selection cancelled.")
            return

        ui.filename_box.setText(f"File: {filepath}")

        # Apply PLC file to the currently selected line.
        current_line_name = ui.track_picker.currentText()
        try:
            backend = ui.network.get_line(current_line_name)
            backend.upload_plc(filepath)
            ui.backend = backend
            ui.refresh_tables()
            logger.info("PLC file %s uploaded for %s", filepath, current_line_name)
        except Exception as exc:
            logger.exception("PLC upload failed for %s: %s", current_line_name, exc)

    # Connect UI actions.
    ui.plc_button.clicked.connect(upload_file)

    # Initialize UI layout.
    ui.refresh_tables()
    ui.resize(1000, 1000)
    ui.setWindowTitle("Track Controller Module")
    ui.show()

    logger.info("Track Controller UI launched successfully.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
