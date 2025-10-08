"""
train_model_test_ui.py
"""

from __future__ import annotations
import sys
import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QLineEdit,
    QGroupBox,
    QMessageBox,
)

if TYPE_CHECKING:
    from train_model_backend import TrainModelBackend

# Configure logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class TrainModelTestUI(QWidget):
    """test interface for applying manual inputs to the Train Model backend"""

    def __init__(self, backend: "TrainModelBackend") -> None:
        super().__init__()
        self.backend = backend

        self.setWindowTitle("Train Model Test Interface")
        self.resize(600, 500)

        main_layout = QVBoxLayout()

        # power
        power_group = QGroupBox("Train Power Command")
        power_layout = QHBoxLayout()
        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(0, 2000)
        self.power_spin.setValue(0)
        self.power_spin.setSuffix(" kW")
        self.power_spin.setSingleStep(10)
        power_layout.addWidget(QLabel("Power:"))
        power_layout.addWidget(self.power_spin)
        power_group.setLayout(power_layout)
        main_layout.addWidget(power_group)

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

        # failure states
        fail_group = QGroupBox("Failure States (toggle on/off)")
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

        # footer
        footer = QLabel("Iteration #2 Test UI – Manual input to backend for demo")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color: gray; font-size: 12px;")
        main_layout.addWidget(footer)

        self.setLayout(main_layout)

    # ------------------------------------------------------------------
    def _apply_inputs(self) -> None:
        """collect input values and send them to backend for processing."""
        try:
            power_kw = self.power_spin.value()
            service_brake = self.service_brake_check.isChecked()
            emergency_brake = self.emergency_brake_check.isChecked()
            grade_percent = self.grade_spin.value()
            beacon_text = self.beacon_edit.text().strip() or "None"

            # update failures
            self.backend.set_failure_state("engine", self.engine_fail.isChecked())
            self.backend.set_failure_state("brake", self.brake_fail.isChecked())
            self.backend.set_failure_state("signal", self.signal_fail.isChecked())

            # apply control inputs
            self.backend.set_inputs(
                power_kw=power_kw,
                service_brake=service_brake,
                emergency_brake=emergency_brake,
                grade_percent=grade_percent,
                beacon_info=beacon_text,
            )

            # adjust train mass slightly with passenger count
            passengers = self.passenger_spin.value()
            base_mass = 40900.0
            self.backend.mass_kg = base_mass + passengers * 70  # each passenger adds ~70 kg
            self.backend._notify_listeners()

            QMessageBox.information(self, "Inputs Applied", "Train model updated successfully!")
        except Exception as e:
            logger.exception("Failed to apply inputs: %s", e)
            QMessageBox.critical(self, "Error", str(e))

# combined launcher 
if __name__ == "__main__":
    from train_model_backend import TrainModelBackend
    from train_model_ui import TrainModelUI

    app = QApplication(sys.argv)
    backend = TrainModelBackend()

    # launch both the UI and Test UI side-by-side for demonstration
    main_ui = TrainModelUI(backend)
    test_ui = TrainModelTestUI(backend)

    main_ui.show()
    test_ui.show()

    sys.exit(app.exec())
