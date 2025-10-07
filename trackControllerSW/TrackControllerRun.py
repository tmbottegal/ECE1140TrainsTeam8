import sys
from PyQt6.QtWidgets import QApplication, QFileDialog
from TrackControllerBackend import TrackNetwork
from TrackControllerUI import TrackControllerUI


def main():
    app = QApplication(sys.argv)

    # Build network
    network = TrackNetwork()
    ui = TrackControllerUI(network)

    def upload_file():
        filepath, _ = QFileDialog.getOpenFileName(ui, "Open PLC File", "", "PLC Files (*.txt *.plc *.py)")
        if filepath:
            ui.filename_box.setText(f"File: {filepath}")

            # Apply to the currently selected line
            current_line_name = ui.track_picker.currentText()
            backend = ui.network.get_line(current_line_name)
            backend.upload_plc(filepath)

            # Update backend reference + tables
            ui.backend = backend
            ui.refresh_tables()


    ui.plc_button.clicked.connect(upload_file)

    ui.refresh_tables()
    ui.resize(1000, 1000)
    ui.setWindowTitle("Track Controller Module")
    ui.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
