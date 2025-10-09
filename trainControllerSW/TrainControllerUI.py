""" 

 This is the Train Controller UI.

"""
from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLCDNumber,
    QMainWindow,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class TrainControllerUI(QMainWindow):

    def __init__(self, frontend) -> None:
        super().__init__()
        self.frontend = frontend
        self.setWindowTitle("Train Controller")

        # widgets we need to access later
        self.lcd_suggested: Optional[QLCDNumber] = None
        self.lcd_authority: Optional[QLCDNumber] = None
        self.lcd_speed: Optional[QLCDNumber] = None

        self.lbl_train_id: Optional[QLabel] = None

        self.spin_ctc_speed: Optional[QSpinBox] = None
        self.spin_authority: Optional[QSpinBox] = None

        self.slider_cmd: Optional[QSlider] = None
        self.spin_actual_speed: Optional[QSpinBox] = None

        self.chk_auto: Optional[QCheckBox] = None
        self.spin_limit: Optional[QSpinBox] = None
        self.spin_kp: Optional[QDoubleSpinBox] = None
        self.spin_ki: Optional[QDoubleSpinBox] = None

        self.btn_service: Optional[QPushButton] = None
        self.btn_eb: Optional[QPushButton] = None

        self.btn_door_left: Optional[QPushButton] = None
        self.btn_door_right: Optional[QPushButton] = None
        self.btn_head: Optional[QPushButton] = None
        self.btn_cabin: Optional[QPushButton] = None
        self.spin_temp_f: Optional[QDoubleSpinBox] = None
        self.btn_push_ctc: Optional[QPushButton] = None

        self._build_ui()
        self._wire_signals()

        # periodic refresh
        self.timer = QTimer(self)
        self.timer.setInterval(100)  # 10 Hz
        self.timer.timeout.connect(self._on_tick)
        self.timer.start()

        self.resize(980, 700)

    # ---------- UI construction helpers ----------

    def _boxed(self, title: str, inner: QWidget) -> QGroupBox:
        """Place a single widget into a titled group box."""
        g = QGroupBox(title)
        v = QVBoxLayout(g)
        v.addWidget(inner)
        return g

    def _lcd_label(
        self,
        grid: QGridLayout,
        lcd: QLCDNumber,
        title: str,
        row: int,
        col: int,
        rowspan: int = 1,
        colspan: int = 1,
    ) -> None:
        """Add a labeled LCD group in the grid without crowding."""
        box = QGroupBox(title)
        v = QVBoxLayout(box)
        v.addWidget(lcd)
        grid.addWidget(box, row, col, rowspan, colspan)

    # ---------- Build the UI ----------

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main = QGridLayout(root)

        # Breathing room & growth rules
        main.setContentsMargins(10, 10, 10, 10)
        main.setHorizontalSpacing(12)
        main.setVerticalSpacing(12)

        # 3 columns for main content + 1 column for the vertical slider
        main.setColumnStretch(0, 3)
        main.setColumnStretch(1, 2)
        main.setColumnStretch(2, 3)
        main.setColumnStretch(3, 1)
        main.setRowStretch(0, 0)
        main.setRowStretch(1, 0)
        main.setRowStretch(2, 1)
        main.setRowStretch(3, 0)

        # ---------- Row 0: top info (no overlaps) ----------
        self.lcd_suggested = QLCDNumber()
        self.lcd_suggested.setDigitCount(3)
        self._lcd_label(main, self.lcd_suggested, "SUGGESTED SPEED (mph)", 0, 0)

        self.lbl_train_id = QLabel("Blue-01")
        self.lbl_train_id.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_train_id.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        main.addWidget(self._boxed("TRAIN IDENTIFIER", self.lbl_train_id), 0, 1)

        self.lcd_authority = QLCDNumber()
        self.lcd_authority.setDigitCount(4)
        self._lcd_label(main, self.lcd_authority, "AUTHORITY (m)", 0, 2)

        # ---------- Row 1: CTC / Track circuit demo inputs ----------
        ctc_box = QGroupBox("CTC / TRACK CIRCUIT INPUTS (demo)")
        c = QGridLayout(ctc_box)
        c.setContentsMargins(10, 8, 10, 10)

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

        main.addWidget(ctc_box, 1, 0, 1, 3)  # span three content columns

        # ---------- Right side: driver commanded speed ----------
        self.slider_cmd = QSlider(Qt.Orientation.Vertical)
        self.slider_cmd.setRange(0, 160)
        self.slider_cmd.setTickInterval(10)
        self.slider_cmd.setTickPosition(QSlider.TickPosition.TicksLeft)
        main.addWidget(
            self._boxed("COMMANDED SPEED (driver, mph)", self.slider_cmd), 0, 3, 3, 1
        )

        # ---------- Row 2: speed displays ----------
        self.lcd_speed = QLCDNumber()
        self.lcd_speed.setDigitCount(3)
        self._lcd_label(main, self.lcd_speed, "TRAIN SPEED (mph)", 2, 0, 1, 2)

        self.spin_actual_speed = QSpinBox()
        self.spin_actual_speed.setRange(0, 160)
        self.spin_actual_speed.setSuffix(" mph")
        main.addWidget(
            self._boxed("SIMULATED ACTUAL SPEED (demo)", self.spin_actual_speed), 2, 2
        )

        # ---------- Row 3: mode/gains, brakes, doors/lights/temp ----------
        # Mode / Gains
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

        main.addWidget(mode_box, 3, 0)

        # Brakes
        brake_box = QGroupBox("BRAKES")
        hb = QHBoxLayout(brake_box)
        self.btn_service = QPushButton("SERVICE BRAKE")
        self.btn_service.setCheckable(True)
        self.btn_eb = QPushButton("EMERGENCY BRAKE")
        self.btn_eb.setCheckable(True)
        hb.addWidget(self.btn_service)
        hb.addWidget(self.btn_eb)
        main.addWidget(brake_box, 3, 1)

        # Doors / Lights / Temp
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

        m.addWidget(QLabel("Cabin Temp (°F):"), 2, 0)
        self.spin_temp_f = QDoubleSpinBox()
        self.spin_temp_f.setRange(50.0, 86.0)   # ~10–30°C
        self.spin_temp_f.setSingleStep(0.5)
        self.spin_temp_f.setValue(68.0)         # 20°C ≈ 68°F
        m.addWidget(self.spin_temp_f, 2, 1)

        main.addWidget(misc_box, 3, 2)

    # ---------- Wire signals to frontend ----------

    def _wire_signals(self) -> None:
        # Push CTC inputs
        if self.btn_push_ctc:
            self.btn_push_ctc.clicked.connect(self._push_commands)

        # Driver commanded speed
        if self.slider_cmd:
            self.slider_cmd.valueChanged.connect(
                lambda v: self.frontend.set_driver_commanded_speed(int(v))
            )

        # Demo actual speed (sandbox)
        if self.spin_actual_speed:
            self.spin_actual_speed.valueChanged.connect(
                lambda v: self.frontend.set_measured_speed_mph(int(v))
            )

        # Mode / limits / gains
        if self.chk_auto:
            self.chk_auto.toggled.connect(
                lambda b: self.frontend.set_auto_mode(bool(b))
            )
        if self.spin_limit:
            self.spin_limit.valueChanged.connect(
                lambda v: self.frontend.set_limit_mph(int(v))
            )
        if self.spin_kp:
            self.spin_kp.valueChanged.connect(
                lambda x: self.frontend.set_kp(float(x))
            )
        if self.spin_ki:
            self.spin_ki.valueChanged.connect(
                lambda x: self.frontend.set_ki(float(x))
            )

        # Brakes
        if self.btn_service:
            self.btn_service.toggled.connect(
                lambda b: self.frontend.set_service_brake(bool(b))
            )
        if self.btn_eb:
            self.btn_eb.toggled.connect(
                lambda b: self.frontend.set_emergency_brake(bool(b))
            )

        # Doors / lights
        if self.btn_door_left and self.btn_door_right:
            self.btn_door_left.toggled.connect(
                lambda _: self.frontend.set_doors(
                    self.btn_door_left.isChecked(), self.btn_door_right.isChecked()
                )
            )
            self.btn_door_right.toggled.connect(
                lambda _: self.frontend.set_doors(
                    self.btn_door_left.isChecked(), self.btn_door_right.isChecked()
                )
            )
        if self.btn_head:
            self.btn_head.toggled.connect(
                lambda b: self.frontend.set_headlights(bool(b))
            )
        if self.btn_cabin:
            self.btn_cabin.toggled.connect(
                lambda b: self.frontend.set_cabin_lights(bool(b))
            )

        # Cabin temp is edited in °F; convert to °C for backend
        if self.spin_temp_f:
            self.spin_temp_f.valueChanged.connect(
                lambda f: self.frontend.set_temp_c((float(f) - 32.0) * (5.0 / 9.0))
            )

    def _push_commands(self) -> None:
        """Send CTC demo values to the controller."""
        spd = int(self.spin_ctc_speed.value())
        auth = int(self.spin_authority.value())
        self.frontend.set_ctc_command(spd, auth)

    # ---------- Timer: pull telemetry & refresh widgets ----------

    def _on_tick(self) -> None:
        telem = self.frontend.tick(0.1)  # returns a dict with telemetry

        # LCDs
        if self.lcd_suggested:
            self.lcd_suggested.display(int(telem.get("suggested_mph", 0)))
        if self.lcd_authority:
            self.lcd_authority.display(int(telem.get("authority_m", 0)))
        if self.lcd_speed:
            self.lcd_speed.display(int(telem.get("actual_speed_mph", 0)))

        # Keep slider in sync with commanded speed (if auto/manual changes)
        if self.slider_cmd:
            cmd = int(telem.get("commanded_speed_mph", 0))
            # Avoid feedback loops
            if self.slider_cmd.value() != cmd:
                self.slider_cmd.blockSignals(True)
                self.slider_cmd.setValue(cmd)
                self.slider_cmd.blockSignals(False)

        # Keep °F control synced from backend's °C
        if self.spin_temp_f:
            temp_c = float(telem.get("temp_c", 20.0))
            temp_f = temp_c * (9.0 / 5.0) + 32.0
            if abs(self.spin_temp_f.value() - temp_f) > 1e-6:
                self.spin_temp_f.blockSignals(True)
                self.spin_temp_f.setValue(temp_f)
                self.spin_temp_f.blockSignals(False)


# Standalone run (useful for quick UI checks if you import a dummy frontend)
if __name__ == "__main__":
    class _DummyFrontend:
        """Minimal stub so this file can be run by itself."""
        def __init__(self) -> None:
            self._cmd = 30
            self._meas = 0
            self._temp_c = 20.0
            self._auth = 400
            self._sugg = 45

        # setters used by UI
        def set_ctc_command(self, speed_mph, authority_m): self._sugg, self._auth = speed_mph, authority_m
        def set_limit_mph(self, v): pass
        def set_auto_mode(self, b): pass
        def set_kp(self, x): pass
        def set_ki(self, x): pass
        def set_service_brake(self, b): pass
        def set_emergency_brake(self, b): pass
        def set_doors(self, left, right): pass
        def set_headlights(self, b): pass
        def set_cabin_lights(self, b): pass
        def set_temp_c(self, c): self._temp_c = float(c)
        def set_driver_commanded_speed(self, mph): self._cmd = int(mph)
        def set_measured_speed_mph(self, mph): self._meas = int(mph)

        # telemetry pull
        def tick(self, dt):
            # simple demo: measured speed tends toward commanded
            if self._meas < self._cmd: self._meas += 1
            elif self._meas > self._cmd: self._meas -= 1
            return {
                "suggested_mph": self._sugg,
                "authority_m": self._auth,
                "actual_speed_mph": self._meas,
                "commanded_speed_mph": self._cmd,
                "temp_c": self._temp_c,
            }

    app = QApplication(sys.argv)
    ui = TrainControllerUI(_DummyFrontend())
    ui.show()
    sys.exit(app.exec())
