""" 

 This is the Train Controller UI.

"""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QMainWindow, QApplication, QLabel, QSpinBox, QDoubleSpinBox,
    QVBoxLayout, QHBoxLayout, QPushButton, QLCDNumber, QGroupBox, QGridLayout,
    QSlider, QCheckBox
)

# dual import for script vs package
try:
    from .TrainControllerFrontend import TrainControllerFrontend
except Exception:  # pragma: no cover
    from TrainControllerFrontend import TrainControllerFrontend


class TrainControllerUI(QMainWindow):
    """
    Iteration #2 UI: speed/authority displays, manual/auto toggle, KP/KI,
    lights/doors/temp, service & emergency brake, and a live "speedometer".
    """

    def __init__(self, frontend: TrainControllerFrontend) -> None:
        super().__init__()
        self.frontend = frontend
        self.setWindowTitle("Train Controller")
        self._build_ui()
        self._wire_signals()
        self._start_timer()

    # -------- UI construction --------
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main = QGridLayout(root)

        # ===== Top row: Suggested speed, Train ID, Authority =====
        self.lcd_suggested = QLCDNumber()
        self.lcd_suggested.setDigitCount(3)
        self._lcd_label(main, self.lcd_suggested, "SUGGESTED SPEED (mph)", 0, 0)

        self.lbl_train_id = QLabel("T1")
        self.lbl_train_id.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_train_id.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        main.addWidget(self._boxed("TRAIN IDENTIFIER", self.lbl_train_id), 0, 1)

        self.lcd_authority = QLCDNumber()
        self.lcd_authority.setDigitCount(4)
        self._lcd_label(main, self.lcd_authority, "AUTHORITY (m)", 0, 2)

        # ===== Center: Speedometer (numeric) =====
        self.lcd_speed = QLCDNumber()
        self.lcd_speed.setDigitCount(3)
        self._lcd_label(main, self.lcd_speed, "TRAIN SPEED (mph)", 1, 0, 1, 2)

        # Manual “actual speed” knob (for demo/testing during Iteration #2)
        self.spin_actual_speed = QSpinBox()
        self.spin_actual_speed.setRange(0, 160)
        self.spin_actual_speed.setSuffix(" mph")
        main.addWidget(self._boxed("SIMULATED ACTUAL SPEED (demo)", self.spin_actual_speed), 1, 2)

        # ===== Left column: Commanded speed slider =====
        self.slider_cmd = QSlider(Qt.Orientation.Vertical)
        self.slider_cmd.setRange(0, 160)
        self.slider_cmd.setTickInterval(10)
        self.slider_cmd.setTickPosition(QSlider.TickPosition.TicksLeft)
        main.addWidget(self._boxed("COMMANDED SPEED (driver, mph)", self.slider_cmd), 0, 3, 3, 1)

        # ===== Mode & Gains =====
        mode_box = QGroupBox("MODE / GAINS")
        g = QGridLayout(mode_box)

        self.chk_auto = QCheckBox("AUTO (use CTC speed)")
        self.chk_auto.setChecked(True)
        g.addWidget(self.chk_auto, 0, 0, 1, 2)

        g.addWidget(QLabel("Speed limit (mph):"), 1, 0)
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(0, 160)
        self.spin_limit.setValue(70)
        g.addWidget(self.spin_limit, 1, 1)

        g.addWidget(QLabel("Kp:"), 2, 0)
        self.spin_kp = QDoubleSpinBox()
        self.spin_kp.setRange(0.0, 10.0)
        self.spin_kp.setSingleStep(0.1)
        self.spin_kp.setValue(0.8)
        g.addWidget(self.spin_kp, 2, 1)

        g.addWidget(QLabel("Ki:"), 3, 0)
        self.spin_ki = QDoubleSpinBox()
        self.spin_ki.setRange(0.0, 10.0)
        self.spin_ki.setSingleStep(0.1)
        self.spin_ki.setValue(0.3)
        g.addWidget(self.spin_ki, 3, 1)

        main.addWidget(mode_box, 2, 0)

        # ===== Brakes =====
        brake_box = QGroupBox("BRAKES")
        hb = QHBoxLayout(brake_box)
        self.btn_service = QPushButton("SERVICE BRAKE")
        self.btn_service.setCheckable(True)
        self.btn_eb = QPushButton("EMERGENCY BRAKE")
        self.btn_eb.setCheckable(True)
        hb.addWidget(self.btn_service)
        hb.addWidget(self.btn_eb)
        main.addWidget(brake_box, 2, 1)

        # ===== Doors / Lights / Temp =====
        misc_box = QGroupBox("DOORS / LIGHTS / TEMP")
        m = QGridLayout(misc_box)

        self.btn_door_left = QPushButton("Door Left")
        self.btn_door_left.setCheckable(True)
        self.btn_door_right = QPushButton("Door Right")
        self.btn_door_right.setCheckable(True)
        m.addWidget(self.btn_door_left, 0, 0)
        m.addWidget(self.btn_door_right, 0, 1)

        self.btn_head = QPushButton("Headlights")
        self.btn_head.setCheckable(True)
        self.btn_cabin = QPushButton("Cabin Lights")
        self.btn_cabin.setCheckable(True)
        m.addWidget(self.btn_head, 1, 0)
        m.addWidget(self.btn_cabin, 1, 1)

        m.addWidget(QLabel("Cabin Temp (°C):"), 2, 0)
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(10.0, 30.0)
        self.spin_temp.setSingleStep(0.5)
        self.spin_temp.setValue(20.0)
        m.addWidget(self.spin_temp, 2, 1)

        main.addWidget(misc_box, 2, 2)

        # ===== CTC/Track circuit demo inputs (for iteration demo) =====
        ctc_box = QGroupBox("CTC / TRACK CIRCUIT INPUTS (demo)")
        c = QGridLayout(ctc_box)
        c.addWidget(QLabel("CTC Suggested Speed (mph):"), 0, 0)
        self.spin_ctc_speed = QSpinBox()
        self.spin_ctc_speed.setRange(0, 160)
        self.spin_ctc_speed.setValue(45)
        c.addWidget(self.spin_ctc_speed, 0, 1)

        c.addWidget(QLabel("Authority (m):"), 1, 0)
        self.spin_authority = QSpinBox()
        self.spin_authority.setRange(0, 5000)
        self.spin_authority.setValue(400)
        c.addWidget(self.spin_authority, 1, 1)

        self.btn_push_ctc = QPushButton("Push CTC to Controller")
        c.addWidget(self.btn_push_ctc, 2, 0, 1, 2)

        main.addWidget(ctc_box, 0, 0, 1, 3)

    def _boxed(self, title: str, inner: QWidget) -> QGroupBox:
        g = QGroupBox(title)
        l = QVBoxLayout(g)
        l.addWidget(inner)
        return g

    def _lcd_label(self, grid: QGridLayout, lcd: QLCDNumber, title: str,
                   row: int, col: int, rowspan: int = 1, colspan: int = 1) -> None:
        box = QGroupBox(title)
        v = QVBoxLayout(box)
        v.addWidget(lcd)
        grid.addWidget(box, row, col, rowspan, colspan)

    # -------- Signal wiring --------
    def _wire_signals(self) -> None:
        self.slider_cmd.valueChanged.connect(
            lambda v: self.frontend.set_driver_speed_mph(float(v))
        )
        self.chk_auto.toggled.connect(self.frontend.set_auto_mode)
        self.spin_limit.valueChanged.connect(lambda v: self.frontend.set_speed_limit_mph(float(v)))
        self.spin_kp.valueChanged.connect(lambda v: self.frontend.set_kp(float(v)))
        self.spin_ki.valueChanged.connect(lambda v: self.frontend.set_ki(float(v)))
        self.btn_service.toggled.connect(self.frontend.set_service_brake)
        self.btn_eb.toggled.connect(self.frontend.set_emergency_brake)
        self.btn_door_left.toggled.connect(self.frontend.set_doors_left)
        self.btn_door_right.toggled.connect(self.frontend.set_doors_right)
        self.btn_head.toggled.connect(self.frontend.set_headlights)
        self.btn_cabin.toggled.connect(self.frontend.set_cabin_lights)
        self.spin_temp.valueChanged.connect(lambda v: self.frontend.set_temp_c(float(v)))
        self.spin_actual_speed.valueChanged.connect(lambda v: self.frontend.set_actual_speed_mph(float(v)))
        self.btn_push_ctc.clicked.connect(self._push_commands)

    def _push_commands(self) -> None:
        self.frontend.set_ctc_command(
            float(self.spin_ctc_speed.value()),
            float(self.spin_authority.value()),
        )

    # -------- Timer / refresh --------
    def _start_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(100)  # 100 ms
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _on_tick(self) -> None:
        # Advance controller and refresh displays
        telemetry = self.frontend.tick(0.1)

        self.lbl_train_id.setText(telemetry["train_id"])
        self.lcd_suggested.display(int(round(telemetry["cmd_speed_mph"])))
        self.lcd_authority.display(int(round(telemetry["authority_m"])))
        self.lcd_speed.display(int(round(telemetry["actual_speed_mph"])))

        # Mirror EB/SB status (controller may force these)
        self.btn_service.setChecked(telemetry["service_brake"])
        self.btn_eb.setChecked(telemetry["emergency_brake"])
