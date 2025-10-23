""" 

 This is the Train Controller UI.

"""

from __future__ import annotations

from typing import Optional, Dict, Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QGroupBox, QDoubleSpinBox, QApplication, QSpinBox
)

# Frontend is the single dependency here
try:
    from .TrainControllerFrontend import TrainControllerFrontend
except Exception:
    from TrainControllerFrontend import TrainControllerFrontend  # type: ignore


class TrainControllerUI(QWidget):
    """
    Minimal, reliable UI for the Train Controller module.
    - If a Train Model is attached to the Frontend, the UI becomes read-only
      for "Actual Speed" and the "Push CTC" button writes *into the Train Model*
      (matching prof's loop: TM -> TC -> TM).
    - If no Train Model is present, the UI runs a demo physics loop.
    """

    def __init__(self, frontend: TrainControllerFrontend, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.frontend = frontend
        self.setWindowTitle("Train Controller")

        self._build_ui()
        self._wire_signals()

        # 10 Hz update
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(100)

    # ----------------- UI construction helpers -----------------

    def _boxed(self, title: str, inner_layout: QWidget | QVBoxLayout | QGridLayout | QHBoxLayout) -> QGroupBox:
        box = QGroupBox(title)
        if isinstance(inner_layout, QWidget):
            lay = QVBoxLayout()
            lay.addWidget(inner_layout)
            box.setLayout(lay)
        elif isinstance(inner_layout, (QVBoxLayout, QGridLayout, QHBoxLayout)):
            w = QWidget()
            w.setLayout(inner_layout)
            lay = QVBoxLayout()
            lay.addWidget(w)
            box.setLayout(lay)
        else:
            raise TypeError("Unsupported inner layout")
        return box

    def _label_row(self, text: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        lab = QLabel(text)
        lab.setMinimumWidth(150)
        row.addWidget(lab)
        row.addWidget(widget, 1)
        return row

    def _build_ui(self) -> None:
        main = QGridLayout(self)

        # ----- Left column: modes, gains, limits -----
        self.chk_auto = QCheckBox("Auto Mode")
        self.chk_auto.setChecked(True)

        self.spin_kp = QDoubleSpinBox()
        self.spin_kp.setRange(0.0, 10.0)
        self.spin_kp.setSingleStep(0.05)
        self.spin_kp.setValue(0.8)

        self.spin_ki = QDoubleSpinBox()
        self.spin_ki.setRange(0.0, 10.0)
        self.spin_ki.setSingleStep(0.05)
        self.spin_ki.setValue(0.3)

        self.spin_speed_limit = QDoubleSpinBox()
        self.spin_speed_limit.setRange(0.0, 200.0)
        self.spin_speed_limit.setSuffix(" mph")
        self.spin_speed_limit.setSingleStep(1.0)
        self.spin_speed_limit.setValue(70.0)

        left_v = QVBoxLayout()
        left_v.addLayout(self._label_row("Controller Mode", self.chk_auto))
        left_v.addLayout(self._label_row("Kp", self.spin_kp))
        left_v.addLayout(self._label_row("Ki", self.spin_ki))
        left_v.addLayout(self._label_row("Speed Limit", self.spin_speed_limit))
        main.addWidget(self._boxed("CONTROL", left_v), 0, 0)

        # ----- Middle column: driver & brakes & lights/doors -----
        self.spin_driver_speed = QDoubleSpinBox()
        self.spin_driver_speed.setRange(0.0, 120.0)
        self.spin_driver_speed.setSuffix(" mph")
        self.spin_driver_speed.setSingleStep(1.0)

        self.chk_sb = QCheckBox("Service Brake")
        self.chk_eb = QCheckBox("Emergency Brake")

        self.chk_doors_left = QCheckBox("Doors Left Open")
        self.chk_doors_right = QCheckBox("Doors Right Open")
        self.chk_headlights = QCheckBox("Headlights")
        self.chk_cabinlights = QCheckBox("Cabin Lights")

        self.spin_temp_c = QDoubleSpinBox()
        self.spin_temp_c.setRange(10.0, 30.0)
        self.spin_temp_c.setSingleStep(0.5)
        self.spin_temp_c.setValue(20.0)
        self.spin_temp_c.setSuffix(" °C")

        mid_v = QVBoxLayout()
        mid_v.addLayout(self._label_row("Driver Manual Speed", self.spin_driver_speed))
        mid_v.addLayout(self._label_row("Service Brake", self.chk_sb))
        mid_v.addLayout(self._label_row("Emergency Brake", self.chk_eb))
        mid_v.addLayout(self._label_row("Doors (Left)", self.chk_doors_left))
        mid_v.addLayout(self._label_row("Doors (Right)", self.chk_doors_right))
        mid_v.addLayout(self._label_row("Headlights", self.chk_headlights))
        mid_v.addLayout(self._label_row("Cabin Lights", self.chk_cabinlights))
        mid_v.addLayout(self._label_row("Cabin Temp", self.spin_temp_c))
        main.addWidget(self._boxed("DRIVER I/O", mid_v), 0, 1)

        # ----- Right column: CTC push + Actual speed (demo) -----
        self.spin_ctc_speed = QDoubleSpinBox()
        self.spin_ctc_speed.setRange(0.0, 120.0)
        self.spin_ctc_speed.setSuffix(" mph")
        self.spin_ctc_speed.setSingleStep(1.0)
        self.spin_ctc_speed.setValue(45.0)

        self.spin_ctc_auth = QDoubleSpinBox()
        self.spin_ctc_auth.setRange(0.0, 5000.0)
        self.spin_ctc_auth.setSuffix(" m")
        self.spin_ctc_auth.setSingleStep(10.0)
        self.spin_ctc_auth.setValue(200.0)

        self.btn_push_ctc = QPushButton("Push to Train Model")

        right_v = QVBoxLayout()
        right_v.addLayout(self._label_row("CTC Speed", self.spin_ctc_speed))
        right_v.addLayout(self._label_row("CTC Authority", self.spin_ctc_auth))
        right_v.addWidget(self.btn_push_ctc)
        main.addWidget(self._boxed("CTC → (via Train Model)", right_v), 0, 2)

        # Demo-only: simulated actual speed control (disabled if TM attached)
        self.spin_actual_speed = QDoubleSpinBox()
        self.spin_actual_speed.setRange(0.0, 160.0)
        self.spin_actual_speed.setSuffix(" mph")
        self.spin_actual_speed.setSingleStep(1.0)
        self.spin_actual_speed.setValue(0.0)
        demo_v = QVBoxLayout()
        demo_v.addLayout(self._label_row("Demo Actual Speed", self.spin_actual_speed))
        main.addWidget(self._boxed("SIMULATED INPUT (demo mode only)", demo_v), 1, 2)

        # ----- Telemetry panel -----
        self.lbl_tm = QLabel("Train Model: (detecting...)")
        self.lbl_cmd_speed = QLabel("--")
        self.lbl_auth = QLabel("--")
        self.lbl_act_speed = QLabel("--")
        self.lbl_power = QLabel("--")
        self.lbl_mode = QLabel("--")
        self.lbl_brakes = QLabel("--")
        self.lbl_gains = QLabel("--")

        tele_v = QVBoxLayout()
        tele_v.addWidget(self.lbl_tm)
        tele_v.addWidget(self._kv("Cmd Speed", self.lbl_cmd_speed, "mph"))
        tele_v.addWidget(self._kv("Authority", self.lbl_auth, "m"))
        tele_v.addWidget(self._kv("Actual Speed", self.lbl_act_speed, "mph"))
        tele_v.addWidget(self._kv("Power", self.lbl_power, "kW"))
        tele_v.addWidget(self._kv("Mode", self.lbl_mode))
        tele_v.addWidget(self._kv("Brakes", self.lbl_brakes))
        tele_v.addWidget(self._kv("Gains", self.lbl_gains))
        main.addWidget(self._boxed("TELEMETRY (read-only)", tele_v), 1, 0, 1, 2)

        # disable demo knob if TM attached
        if self.frontend.has_train_model():
            self.spin_actual_speed.setEnabled(False)
            self.lbl_tm.setText("Train Model: ATTACHED")
        else:
            self.lbl_tm.setText("Train Model: (none — demo mode)")

        self.setLayout(main)

    def _kv(self, key: str, value_label: QLabel, unit: str = "") -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        k = QLabel(f"{key}:")
        k.setMinimumWidth(120)
        lay.addWidget(k)
        lay.addWidget(value_label, 1)
        if unit:
            lay.addWidget(QLabel(unit))
        return row

    # ----------------- signal wiring -----------------

    def _wire_signals(self) -> None:
        self.chk_auto.toggled.connect(self.frontend.set_auto_mode)
        self.spin_kp.valueChanged.connect(self.frontend.set_kp)
        self.spin_ki.valueChanged.connect(self.frontend.set_ki)
        self.spin_speed_limit.valueChanged.connect(self.frontend.set_speed_limit_mph)

        self.spin_driver_speed.valueChanged.connect(self.frontend.set_driver_speed_mph)
        self.chk_sb.toggled.connect(self.frontend.set_service_brake)
        self.chk_eb.toggled.connect(self.frontend.set_emergency_brake)

        self.chk_doors_left.toggled.connect(self.frontend.set_doors_left)
        self.chk_doors_right.toggled.connect(self.frontend.set_doors_right)
        self.chk_headlights.toggled.connect(self.frontend.set_headlights)
        self.chk_cabinlights.toggled.connect(self.frontend.set_cabin_lights)
        self.spin_temp_c.valueChanged.connect(self.frontend.set_temp_c)

        # demo-only: only works without Train Model
        self.spin_actual_speed.valueChanged.connect(self.frontend.set_actual_speed_mph)

        self.btn_push_ctc.clicked.connect(self._push_ctc)

    # ----------------- event handlers -----------------

    def _push_ctc(self) -> None:
        self.frontend.set_ctc_command(
            speed_mph=float(self.spin_ctc_speed.value()),
            authority_m=float(self.spin_ctc_auth.value()),
        )

    def _on_tick(self) -> None:
        disp = self.frontend.tick(0.1)  # 10 Hz

        # update telemetry labels safely
        def fmt(x: Any, digits: int = 1) -> str:
            try:
                return f"{float(x):.{digits}f}"
            except Exception:
                return str(x)

        self.lbl_cmd_speed.setText(fmt(disp.get("cmd_speed_mph", 0.0)))
        self.lbl_auth.setText(fmt(disp.get("authority_m", 0.0), 0))
        self.lbl_act_speed.setText(fmt(disp.get("actual_speed_mph", 0.0)))
        self.lbl_power.setText(fmt(disp.get("power_kw", 0.0)))
        self.lbl_mode.setText("AUTO" if disp.get("auto_mode", True) else "MANUAL")

        sb = "SB" if disp.get("service_brake", False) else "--"
        eb = "EB" if disp.get("emergency_brake", False) else "--"
        self.lbl_brakes.setText(f"{sb}  {eb}")

        kp = disp.get("kp", 0.0)
        ki = disp.get("ki", 0.0)
        self.lbl_gains.setText(f"Kp={kp:.2f}  Ki={ki:.2f}")

