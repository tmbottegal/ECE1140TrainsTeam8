"""
train_model_test_ui.py
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from train_model_backend import TrainModelBackend

# Configure logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class TrainModelTestUI(QWidget):
    """Test interface for applying manual inputs to the Train Model backend"""

    def __init__(self, backend: "TrainModelBackend") -> None:
        super().__init__()
        self.backend = backend
        self.main_ui = None  # will hold TrainModelUI once opened

        self.setWindowTitle("Train Model - Testbench")
        self.resize(640, 620)

        main_layout = QVBoxLayout()

        # power
        power_group = QGroupBox("Train Power Command")
        power_layout = QHBoxLayout()
        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(0.0, 2000.0)
        self.power_spin.setValue(0.0)
        self.power_spin.setSuffix(" kW")
        self.power_spin.setSingleStep(10.0)
        power_layout.addWidget(QLabel("Power:"))
        power_layout.addWidget(self.power_spin)
        power_group.setLayout(power_layout)
        main_layout.addWidget(power_group)

        # commanded speed (mph)
        spd_group = QGroupBox("Commanded Speed")
        spd_layout = QHBoxLayout()
        self.cmd_speed_spin = QDoubleSpinBox()
        self.cmd_speed_spin.setRange(0.0, 80.0)
        self.cmd_speed_spin.setValue(0.0)
        self.cmd_speed_spin.setSingleStep(1.0)
        self.cmd_speed_spin.setSuffix(" mph")
        spd_layout.addWidget(QLabel("Cmd Speed:"))
        spd_layout.addWidget(self.cmd_speed_spin)
        spd_group.setLayout(spd_layout)
        main_layout.addWidget(spd_group)

        # brakes
        brake_group = QGroupBox("Brake Commands")
        brake_layout = QHBoxLayout()
        self.service_brake_check = QCheckBox("Service Brake")
        self.emergency_brake_check = QCheckBox("Emergency Brake")
        brake_layout.addWidget(self.service_brake_check)
        brake_layout.addWidget(self.emergency_brake_check)
        brake_group.setLayout(brake_layout)
        main_layout.addWidget(brake_group)

        # grade 
        grade_group = QGroupBox("Track Grade")
        grade_layout = QHBoxLayout()
        self.grade_spin = QDoubleSpinBox()
        self.grade_spin.setRange(-10.0, 10.0)
        self.grade_spin.setValue(0.0)
        self.grade_spin.setSingleStep(0.5)
        self.grade_spin.setSuffix(" %")
        grade_layout.addWidget(QLabel("Grade:"))
        grade_layout.addWidget(self.grade_spin)
        grade_group.setLayout(grade_layout)
        main_layout.addWidget(grade_group)

        # beacon 
        beacon_group = QGroupBox("Beacon Information")
        beacon_layout = QHBoxLayout()
        self.beacon_edit = QLineEdit()
        self.beacon_edit.setPlaceholderText("Enter beacon info (e.g. Station A -> Station B)")
        beacon_layout.addWidget(self.beacon_edit)
        beacon_group.setLayout(beacon_layout)
        main_layout.addWidget(beacon_group)

        # passenger count 
        pax_group = QGroupBox("Passenger Count")
        pax_layout = QHBoxLayout()
        self.passenger_spin = QSpinBox()
        self.passenger_spin.setRange(0, 1000)
        self.passenger_spin.setValue(200)
        pax_layout.addWidget(QLabel("Passengers:"))
        pax_layout.addWidget(self.passenger_spin)
        pax_group.setLayout(pax_layout)
        main_layout.addWidget(pax_group)

        # device toggles
        dev_group = QGroupBox("Devices & Doors")
        dev_layout = QHBoxLayout()
        self.cabin_lights = QCheckBox("Cabin Lights")
        self.headlights = QCheckBox("Headlights")
        self.left_doors = QCheckBox("Left Doors")
        self.right_doors = QCheckBox("Right Doors")
        self.heating = QCheckBox("Heating")
        self.air_conditioning = QCheckBox("A/C")
        for w in (
            self.cabin_lights,
            self.headlights,
            self.left_doors,
            self.right_doors,
            self.heating,
            self.air_conditioning,
        ):
            dev_layout.addWidget(w)
        dev_group.setLayout(dev_layout)
        main_layout.addWidget(dev_group)

        # failure states
        fail_group = QGroupBox("Failure States")
        fail_layout = QHBoxLayout()
        self.engine_fail = QCheckBox("Engine Failure")
        self.brake_fail = QCheckBox("Brake Failure")
        self.signal_fail = QCheckBox("Signal Pickup Failure")
        fail_layout.addWidget(self.engine_fail)
        fail_layout.addWidget(self.brake_fail)
        fail_layout.addWidget(self.signal_fail)
        fail_group.setLayout(fail_layout)
        main_layout.addWidget(fail_group)

        # apply button 
        apply_button = QPushButton("Apply Inputs to Train Model")
        apply_button.setStyleSheet(
            "font-weight: bold; background-color: steelblue; color: white; padding: 8px; font-size: 14px;"
        )
        apply_button.clicked.connect(self._apply_inputs)
        main_layout.addWidget(apply_button)

        # open dashboard button (launches the UI) 
        open_btn = QPushButton("Open Train Dashboard")
        open_btn.setStyleSheet("font-weight: bold; padding: 8px; font-size: 14px;")
        open_btn.clicked.connect(self._open_dashboard)
        main_layout.addWidget(open_btn)

        # footer
        footer = QLabel("Iteration #2 Testbench – set inputs, then open the main dashboard")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color: gray; font-size: 12px;")
        main_layout.addWidget(footer)

        self.setLayout(main_layout)

    # ------------------------------------------------------------------
    def _apply_inputs(self) -> None:
        """Collect input values and send them to backend for processing."""
        try:
            power_kw = float(self.power_spin.value())
            service_brake = self.service_brake_check.isChecked()
            emergency_brake = self.emergency_brake_check.isChecked()
            grade_percent = float(self.grade_spin.value())
            beacon_text = self.beacon_edit.text().strip() or "None"
            cmd_speed_mph = float(self.cmd_speed_spin.value())

            # Update failures first (so step uses current state)
            self.backend.set_failure_state("engine", self.engine_fail.isChecked())
            self.backend.set_failure_state("brake", self.brake_fail.isChecked())
            self.backend.set_failure_state("signal", self.signal_fail.isChecked())

            # Apply control inputs (includes device toggles + commanded speed in mph)
            self.backend.set_inputs(
                power_kw=power_kw,
                service_brake=service_brake,
                emergency_brake=emergency_brake,
                grade_percent=grade_percent,
                beacon_info=beacon_text,
                cabin_lights=self.cabin_lights.isChecked(),
                headlights=self.headlights.isChecked(),
                left_doors=self.left_doors.isChecked(),
                right_doors=self.right_doors.isChecked(),
                heating=self.heating.isChecked(),
                air_conditioning=self.air_conditioning.isChecked(),
                commanded_speed_mph=cmd_speed_mph,
            )

            # Adjust mass with passengers (~70 kg each)
            passengers = int(self.passenger_spin.value())
            base_mass = 40900.0
            self.backend.passenger_count = passengers
            self.backend.mass_kg = base_mass + passengers * 70.0
            self.backend._notify_listeners()

            QMessageBox.information(self, "Inputs Applied", "Train model updated successfully!")
        except Exception as e:
            logger.exception("Failed to apply inputs: %s", e)
            QMessageBox.critical(self, "Error", str(e))

    # ------------------------------------------------------------------
    def _open_dashboard(self) -> None:
        """Opens the TrainModelUI (if not already open)."""
        if self.main_ui is not None:
            self.main_ui.activateWindow()
            return
        try:
            from train_model_ui import TrainModelUI

            self.main_ui = TrainModelUI(self.backend)
            self.main_ui.show()
        except Exception as e:
            logger.exception("Failed to open dashboard: %s", e)
            QMessageBox.critical(self, "Error", str(e))


# Launch testbench first (user opens dashboard from there)
if __name__ == "__main__":
    from train_model_backend import TrainModelBackend

    app = QApplication(sys.argv)
    backend = TrainModelBackend()
    test_ui = TrainModelTestUI(backend)
    test_ui.show()
    sys.exit(app.exec())
