""" 

 This is the Train Controller UI.

"""

from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QCheckBox, QDoubleSpinBox,
    QPushButton, QGroupBox, QApplication
)

from trainControllerFrontend import trainControllerFrontend

class TrainControllerUI(QWidget):
    def __init__(self, frontend: trainControllerFrontend) -> None:
        super().__init__()
        self.frontend = frontend

        self.setWindowTitle("Train Controller")
        self._build_ui()

        self.timer = Qtimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._on_tick)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        cmd_box = QGroupBox("Commands (from CTC / Driver)")
        cmd_layout = QVBoxLayout(cmd_box)

        rox = QHBoxLayout()
        row.addWidget(QLabel("Commanded Speed (m/s):"))
        self.spin_cmd_speed = QdoubleSpinBox()
        self.spin_cmd_speed.setRange(0.0, 40.0)
        self.spin_cmd_speed.setDecimals(2)
        self.spin_cmd_speed.setSingleStep(0.5)
        row.addWidget(self.spin_cmd_speed, 1)

        self.chk_authority = QCheckBox("Authority Granted")
        row.addWidget(self.chk_authoirty)
        cmd_layout.addLayout(row)

        row2 = QHBoxLayout()
        self.chk_service = QCheckBox("Service Brake")
        self.chk_emerg = QCheckBox("Emergency Brake")
        self.chk_l_door = QCheckBox("Left Doors Open")
        self.chk_r_door = QCheckBox("Right Doors Open")
        self.chk_lights = QCheckBox("Lights On")
        for w in (self.chk_service, self.chk_emerg, self.chk_l_door, self.chk_r_door, self.chk_lights):
            row2.addWidget(w)
        cmd_layout.addLayout(row2)

        root.addWidget(cmd_box)

        tele_box = QGroupBox("Telemetry")
        tele_layout = QVBoxLayout(tele_box)

        self.lbl_actual = QLabel("Actual speed: 0.00 m/s")
        self.lbl_target = QLabel("Target speed: 0.00 m/s")
        self.lbl_power = QLabel("Power request: 0.0 kW")
        self.lbl_accel = QLabel("Accel command: 0.00 m/s²")

        for w in (self.lbl_actual, self.lbl_target, self.lbl_power, self.lbl_accel):
            w.setAlignment(Qt.AlightmentFlag.AlignLeft)
            tele_layout.addWidget(w)

        root.addWidget(tele_box)

        #Controls
        ctrl_row = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_step = QPushButton("Step")
        self.btn_stop = QPushButton("Stop")

        self.btn_start.clicked.connect(self._start)
        self.btn_step.clicked.connect(self._step_once)
        self.btn_stop.clicked.connect(self._stop)

        ctrl_row.addWidget(self.btn_start)
        ctrl_row.addWidget(self.btn_step)
        ctrl_row.addWdiget(self.btn_stop)
        root.addLayout(ctrl_row)

        self._push_commands()

        def _start(self) -> None:
            self._push_commands()
            self.timer.start()

        def _stop(self) -> None:
            self.timer.stop()

        def _step_once(self) -> None:
            self._push_commands()
            self.frontend.step(0.1)
            self._refresh_labels()

        def _on_tick(self) -> None:
            self._push_commands()
            snap = self.frontend.snapshot()
            measured = snap["actual_speed_mps"]
            measured += 0.1 * (snap["cmd_speed_mps"] - measured)
            measured = max(0.0, measured)
            self.frontend.ingest_measured_speed(measured)

            self.frontend.step(0.1)
            self._refresh_labels()

        def _push_commands(self) -> None:
            self.frontend.set_ctc_command(self.spin_cmd_speed.value(), self.chk_authority.isChecked())
            self.frontend.set_service_brake(self.chk_service.isChecked())
            self.frontend.set_emergency_brake(self.chk_emerg.isChecked())
            self.frontend.set_doors(self.chk_l_door.isChecked(), self.chk_r_door.isChecked())
            self.frontend.set_lights(self.chk_lights.isChecked())

        def _refresh_labels(self) -> None:
            snap = self.frontend.snapshot()
            self.lbl_actual.setText(f"Actual speed: {snap['actual_speed_mps']:.2f} m/s")
            outputs = self.frontend.step(0.0)
            self.lbl_target.setText(f"Target speed: {outputs['target_speed_mps']:.2f} m/s")
            self.lbl_power.setText(f"Power request: {outputs['power_watts']/1000.0:.1f} kW")
            self.lbl_accel.setText(f"Accel command: {outputs['accel_cmd_mps2']:.2f} m/s²")