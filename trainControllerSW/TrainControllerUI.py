from __future__ import annotations
""" 

 This is the Train Controller UI.

"""

""" 
Train Controller UI

This UI displays:
1. INPUTS from Train Model (commanded speed, authority, actual speed - READ ONLY)
2. Driver controls (manual speed, brakes, doors, lights, temp - WRITABLE)
3. Engineer controls (Kp, Ki, speed limit - WRITABLE)
4. OUTPUTS to Train Model (power, brakes - READ ONLY, computed by controller)

KEY ARCHITECTURAL POINT:
The Train Controller does NOT push CTC commands to the Train Model.
Instead, it RECEIVES them FROM the Train Model (via Track Circuit).
Therefore, there is NO "Push to CTC" or "Push to Train Model" button.

The UI is organized into functional panels:
- CONTROLLER PARAMETERS: Mode, gains, limits (Engineer controls)
- DRIVER CONTROLS: Manual speed, brakes, doors, lights, temp
- INPUTS FROM TRAIN MODEL: CTC commands, actual speed (READ-ONLY)
- OUTPUTS TO TRAIN MODEL: Power, brakes (READ-ONLY, computed values)
- TELEMETRY: Complete status display
"""

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
    Train Controller User Interface
    
    This UI provides controls for:
    - Driver: Manual speed, brakes, doors, lights, temperature
    - Engineer: PI gains (Kp, Ki), speed limit, auto/manual mode
    
    And displays:
    - Inputs from Train Model (commanded speed, authority, actual speed)
    - Outputs to Train Model (power, service brake, emergency brake)
    - Complete telemetry
    
    The UI updates at 10 Hz via a QTimer.
    """

    def __init__(self, frontend: TrainControllerFrontend, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the UI
        
        Args:
            frontend: TrainControllerFrontend instance that handles backend communication
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.frontend = frontend
        self.setWindowTitle("Train Controller")

        # Build the UI layout
        self._build_ui()
        
        # Wire up signal handlers (connect UI widgets to frontend methods)
        self._wire_signals()

        # Start 10 Hz update timer (100ms period)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(100)

    # ======================================================================
    # UI CONSTRUCTION HELPERS
    # ======================================================================

    def _boxed(self, title: str, inner_layout: QWidget | QVBoxLayout | QGridLayout | QHBoxLayout) -> QGroupBox:
        """
        Create a titled group box containing the given layout
        
        Args:
            title: Title for the group box
            inner_layout: Widget or layout to place inside the box
            
        Returns:
            QGroupBox with the content inside
        """
        box = QGroupBox(title)
        if isinstance(inner_layout, QWidget):
            # If given a widget, wrap it in a layout
            lay = QVBoxLayout()
            lay.addWidget(inner_layout)
            box.setLayout(lay)
        elif isinstance(inner_layout, (QVBoxLayout, QGridLayout, QHBoxLayout)):
            # If given a layout, wrap it in a widget first
            w = QWidget()
            w.setLayout(inner_layout)
            lay = QVBoxLayout()
            lay.addWidget(w)
            box.setLayout(lay)
        else:
            raise TypeError("Unsupported inner layout type")
        return box

    def _label_row(self, text: str, widget: QWidget) -> QHBoxLayout:
        """
        Create a horizontal row with a label and a widget
        
        Args:
            text: Label text
            widget: Widget to place next to the label
            
        Returns:
            QHBoxLayout containing the label and widget
        """
        row = QHBoxLayout()
        lab = QLabel(text)
        lab.setMinimumWidth(150)  # Fixed width for alignment
        row.addWidget(lab)
        row.addWidget(widget, 1)  # Widget takes remaining space
        return row

    def _build_ui(self) -> None:
        """
        Build the complete UI layout
        
        Layout structure (3 columns):
        Row 0: [Controller Parameters] [Driver Controls] [Inputs from TM]
        Row 1: [Outputs to TM] [Telemetry (spans 2 cols)]
        """
        main = QGridLayout(self)

        # ============================================================
        # COLUMN 0: CONTROLLER PARAMETERS (Engineer controls)
        # ============================================================
        
        # Auto/Manual mode checkbox
        self.chk_auto = QCheckBox("Auto Mode")
        self.chk_auto.setChecked(True)
        self.chk_auto.setToolTip("Auto: Follow CTC speed | Manual: Follow driver speed")

        # Proportional gain (Kp)
        self.spin_kp = QDoubleSpinBox()
        self.spin_kp.setRange(0.0, 10.0)
        self.spin_kp.setSingleStep(0.05)
        self.spin_kp.setValue(0.8)
        self.spin_kp.setToolTip("Proportional gain for PI controller")

        # Integral gain (Ki)
        self.spin_ki = QDoubleSpinBox()
        self.spin_ki.setRange(0.0, 10.0)
        self.spin_ki.setSingleStep(0.05)
        self.spin_ki.setValue(0.3)
        self.spin_ki.setToolTip("Integral gain for PI controller")

        # Speed limit (line speed limit)
        self.spin_speed_limit = QDoubleSpinBox()
        self.spin_speed_limit.setRange(0.0, 200.0)
        self.spin_speed_limit.setSuffix(" mph")
        self.spin_speed_limit.setSingleStep(1.0)
        self.spin_speed_limit.setValue(70.0)
        self.spin_speed_limit.setToolTip("Maximum allowed speed for this track section")

        # Assemble into vertical layout
        left_v = QVBoxLayout()
        left_v.addLayout(self._label_row("Controller Mode", self.chk_auto))
        left_v.addLayout(self._label_row("Kp (Proportional)", self.spin_kp))
        left_v.addLayout(self._label_row("Ki (Integral)", self.spin_ki))
        left_v.addLayout(self._label_row("Speed Limit", self.spin_speed_limit))
        
        main.addWidget(self._boxed("CONTROLLER PARAMETERS (Engineer)", left_v), 0, 0)

        # ============================================================
        # COLUMN 1: DRIVER CONTROLS
        # ============================================================
        
        # Manual speed setpoint (used in Manual mode)
        self.spin_driver_speed = QDoubleSpinBox()
        self.spin_driver_speed.setRange(0.0, 120.0)
        self.spin_driver_speed.setSuffix(" mph")
        self.spin_driver_speed.setSingleStep(1.0)
        self.spin_driver_speed.setToolTip("Speed setpoint in Manual mode")

        # Service brake checkbox
        self.chk_sb = QCheckBox("Service Brake")
        self.chk_sb.setToolTip("Apply service brake (moderate braking)")

        # Emergency brake checkbox
        self.chk_eb = QCheckBox("Emergency Brake")
        self.chk_eb.setToolTip("Apply emergency brake (immediate stop)")

        # Door controls
        self.chk_doors_left = QCheckBox("Left Doors Open")
        self.chk_doors_right = QCheckBox("Right Doors Open")

        # Light controls
        self.chk_headlights = QCheckBox("Headlights")
        self.chk_cabinlights = QCheckBox("Cabin Lights")

        # Temperature control
        self.spin_temp_c = QDoubleSpinBox()
        self.spin_temp_c.setRange(10.0, 30.0)
        self.spin_temp_c.setSingleStep(0.5)
        self.spin_temp_c.setValue(20.0)
        self.spin_temp_c.setSuffix(" °C")
        self.spin_temp_c.setToolTip("Cabin temperature setpoint")

        # Assemble into vertical layout
        mid_v = QVBoxLayout()
        mid_v.addLayout(self._label_row("Manual Speed", self.spin_driver_speed))
        mid_v.addLayout(self._label_row("Service Brake", self.chk_sb))
        mid_v.addLayout(self._label_row("Emergency Brake", self.chk_eb))
        mid_v.addLayout(self._label_row("Doors (Left)", self.chk_doors_left))
        mid_v.addLayout(self._label_row("Doors (Right)", self.chk_doors_right))
        mid_v.addLayout(self._label_row("Headlights", self.chk_headlights))
        mid_v.addLayout(self._label_row("Cabin Lights", self.chk_cabinlights))
        mid_v.addLayout(self._label_row("Cabin Temp", self.spin_temp_c))
        
        main.addWidget(self._boxed("DRIVER CONTROLS", mid_v), 0, 1)

        # ============================================================
        # COLUMN 2: INPUTS FROM TRAIN MODEL (Read-only displays)
        # ============================================================
        
        # These values come FROM the Train Model and are READ ONLY
        # The Train Model receives commanded speed/authority from CTC via Track Circuit
        
        # Train Model connection status
        self.lbl_tm_status = QLabel()
        if self.frontend.has_train_model():
            self.lbl_tm_status.setText("✓ Train Model CONNECTED")
            self.lbl_tm_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_tm_status.setText("⚠ DEMO MODE (no Train Model)")
            self.lbl_tm_status.setStyleSheet("color: orange; font-weight: bold;")
        
        # Read-only display of commanded speed (from CTC via TM)
        self.lbl_ctc_speed = QLabel("--")
        self.lbl_ctc_speed.setStyleSheet("background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc;")
        
        # Read-only display of authority (from CTC via TM)
        self.lbl_ctc_auth = QLabel("--")
        self.lbl_ctc_auth.setStyleSheet("background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc;")
        
        # Read-only display of actual speed (from TM tachometer)
        self.lbl_actual_speed = QLabel("--")
        self.lbl_actual_speed.setStyleSheet("background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc;")
        
        # Assemble into vertical layout
        right_v = QVBoxLayout()
        right_v.addWidget(self.lbl_tm_status)
        right_v.addWidget(QLabel("─" * 40))  # Separator
        right_v.addLayout(self._label_row("CTC Cmd Speed", self.lbl_ctc_speed))
        right_v.addWidget(QLabel("<small>(from CTC via Track Circuit)</small>"))
        right_v.addLayout(self._label_row("CTC Authority", self.lbl_ctc_auth))
        right_v.addWidget(QLabel("<small>(from CTC via Track Circuit)</small>"))
        right_v.addLayout(self._label_row("Actual Speed", self.lbl_actual_speed))
        right_v.addWidget(QLabel("<small>(from Train Model tachometer)</small>"))
        
        main.addWidget(self._boxed("INPUTS FROM TRAIN MODEL (read-only)", right_v), 0, 2)

        # ============================================================
        # ROW 1, COLUMN 0: OUTPUTS TO TRAIN MODEL (Read-only displays)
        # ============================================================
        
        # These are the controller's OUTPUT commands sent TO the Train Model
        # They are computed by the controller and are READ ONLY in the UI
        
        # Power command (computed output)
        self.lbl_power_out = QLabel("--")
        self.lbl_power_out.setStyleSheet("background-color: #e8f4f8; padding: 5px; border: 2px solid #4a90e2; font-weight: bold;")
        
        # Service brake status (computed output)
        self.lbl_sb_out = QLabel("--")
        self.lbl_sb_out.setStyleSheet("background-color: #e8f4f8; padding: 5px; border: 2px solid #4a90e2;")
        
        # Emergency brake status (computed output)
        self.lbl_eb_out = QLabel("--")
        self.lbl_eb_out.setStyleSheet("background-color: #e8f4f8; padding: 5px; border: 2px solid #4a90e2;")
        
        # Assemble into vertical layout
        output_v = QVBoxLayout()
        output_v.addLayout(self._label_row("Power Command", self.lbl_power_out))
        output_v.addWidget(QLabel("<small>(computed by controller)</small>"))
        output_v.addLayout(self._label_row("Service Brake", self.lbl_sb_out))
        output_v.addLayout(self._label_row("Emergency Brake", self.lbl_eb_out))
        
        main.addWidget(self._boxed("OUTPUTS TO TRAIN MODEL (computed)", output_v), 1, 0)

        # ============================================================
        # ROW 1, COLUMNS 1-2: TELEMETRY PANEL (Complete status)
        # ============================================================
        
        # Labels for telemetry display
        self.lbl_mode = QLabel("--")
        self.lbl_gains = QLabel("--")
        self.lbl_beacon = QLabel("--")
        self.lbl_grade = QLabel("--")

        # Assemble into vertical layout
        tele_v = QVBoxLayout()
        tele_v.addWidget(self._kv("Mode", self.lbl_mode))
        tele_v.addWidget(self._kv("PI Gains", self.lbl_gains))
        tele_v.addWidget(self._kv("Beacon", self.lbl_beacon))
        tele_v.addWidget(self._kv("Grade", self.lbl_grade))
        
        # Span across 2 columns
        main.addWidget(self._boxed("TELEMETRY", tele_v), 1, 1, 1, 2)

        # ============================================================
        # DEMO MODE CONTROLS (only shown if no Train Model)
        # ============================================================
        
        if not self.frontend.has_train_model():
            # In demo mode, allow manual control of inputs for testing
            
            self.spin_demo_actual_speed = QDoubleSpinBox()
            self.spin_demo_actual_speed.setRange(0.0, 160.0)
            self.spin_demo_actual_speed.setSuffix(" mph")
            self.spin_demo_actual_speed.setSingleStep(1.0)
            self.spin_demo_actual_speed.setValue(0.0)
            self.spin_demo_actual_speed.setToolTip("Simulate actual train speed (DEMO ONLY)")
            
            self.spin_demo_cmd_speed = QDoubleSpinBox()
            self.spin_demo_cmd_speed.setRange(0.0, 120.0)
            self.spin_demo_cmd_speed.setSuffix(" mph")
            self.spin_demo_cmd_speed.setSingleStep(1.0)
            self.spin_demo_cmd_speed.setValue(45.0)
            self.spin_demo_cmd_speed.setToolTip("Simulate CTC commanded speed (DEMO ONLY)")
            
            self.spin_demo_authority = QDoubleSpinBox()
            self.spin_demo_authority.setRange(0.0, 5000.0)
            self.spin_demo_authority.setSuffix(" m")
            self.spin_demo_authority.setSingleStep(10.0)
            self.spin_demo_authority.setValue(200.0)
            self.spin_demo_authority.setToolTip("Simulate CTC authority (DEMO ONLY)")
            
            self.btn_demo_apply = QPushButton("Apply Demo Values")
            self.btn_demo_apply.setToolTip("Apply simulated CTC commands")
            
            demo_v = QVBoxLayout()
            demo_v.addWidget(QLabel("<b>DEMO MODE CONTROLS</b>"))
            demo_v.addWidget(QLabel("<small>These simulate Train Model inputs for testing</small>"))
            demo_v.addLayout(self._label_row("Demo Actual Speed", self.spin_demo_actual_speed))
            demo_v.addLayout(self._label_row("Demo CTC Speed", self.spin_demo_cmd_speed))
            demo_v.addLayout(self._label_row("Demo Authority", self.spin_demo_authority))
            demo_v.addWidget(self.btn_demo_apply)
            
            main.addWidget(self._boxed("⚠ DEMO MODE (simulated inputs)", demo_v), 2, 0, 1, 3)

        self.setLayout(main)

    def _kv(self, key: str, value_label: QLabel, unit: str = "") -> QWidget:
        """
        Create a key-value display row
        
        Args:
            key: Label text
            value_label: QLabel widget to display the value
            unit: Optional unit suffix
            
        Returns:
            QWidget containing the key-value pair
        """
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

    # ======================================================================
    # SIGNAL WIRING - Connect UI widgets to frontend methods
    # ======================================================================

    def _wire_signals(self) -> None:
        """
        Wire up all UI widget signals to frontend methods
        
        This connects user interactions (checkbox clicks, spinbox changes, etc.)
        to the appropriate methods in the Frontend.
        """
        # Controller parameter signals
        self.chk_auto.toggled.connect(self.frontend.set_auto_mode)
        self.spin_kp.valueChanged.connect(self.frontend.set_kp)
        self.spin_ki.valueChanged.connect(self.frontend.set_ki)
        self.spin_speed_limit.valueChanged.connect(self.frontend.set_speed_limit_mph)

        # Driver control signals
        self.spin_driver_speed.valueChanged.connect(self.frontend.set_driver_speed_mph)
        self.chk_sb.toggled.connect(self.frontend.set_service_brake)
        self.chk_eb.toggled.connect(self.frontend.set_emergency_brake)
        self.chk_doors_left.toggled.connect(self.frontend.set_doors_left)
        self.chk_doors_right.toggled.connect(self.frontend.set_doors_right)
        self.chk_headlights.toggled.connect(self.frontend.set_headlights)
        self.chk_cabinlights.toggled.connect(self.frontend.set_cabin_lights)
        self.spin_temp_c.valueChanged.connect(self.frontend.set_temp_c)

        # Demo mode signals (only if no Train Model)
        if not self.frontend.has_train_model():
            self.spin_demo_actual_speed.valueChanged.connect(self.frontend.set_actual_speed_mph)
            self.btn_demo_apply.clicked.connect(self._apply_demo_ctc)

    # ======================================================================
    # EVENT HANDLERS
    # ======================================================================

    def _apply_demo_ctc(self) -> None:
        """
        DEMO MODE ONLY: Apply simulated CTC commands
        
        This simulates what the Train Model would provide to the controller
        in a real system (CTC commands via Track Circuit).
        """
        self.frontend.set_demo_ctc_command(
            speed_mph=float(self.spin_demo_cmd_speed.value()),
            authority_m=float(self.spin_demo_authority.value()),
        )

    def _on_tick(self) -> None:
        """
        Update loop - called every 100ms (10 Hz)
        
        This method:
        1. Calls frontend.tick() to run one controller cycle
        2. Updates all UI displays with the new telemetry data
        """
        # Run one tick of the controller (0.1 seconds)
        disp = self.frontend.tick(0.1)

        # Helper function to safely format numbers
        def fmt(x: Any, digits: int = 1) -> str:
            try:
                return f"{float(x):.{digits}f}"
            except Exception:
                return str(x)

        # Update INPUTS FROM TRAIN MODEL displays
        self.lbl_ctc_speed.setText(fmt(disp.get("cmd_speed_mph", 0.0)) + " mph")
        self.lbl_ctc_auth.setText(fmt(disp.get("authority_m", 0.0), 0) + " m")
        self.lbl_actual_speed.setText(fmt(disp.get("actual_speed_mph", 0.0)) + " mph")

        # Update OUTPUTS TO TRAIN MODEL displays
        self.lbl_power_out.setText(fmt(disp.get("power_kw", 0.0)) + " kW")
        
        sb_active = disp.get("service_brake", False)
        eb_active = disp.get("emergency_brake", False)
        self.lbl_sb_out.setText("ACTIVE" if sb_active else "OFF")
        self.lbl_eb_out.setText("ACTIVE" if eb_active else "OFF")
        
        # Color code the brake displays
        self.lbl_sb_out.setStyleSheet(
            "background-color: #ffcccc; padding: 5px; border: 2px solid red; font-weight: bold;" 
            if sb_active else 
            "background-color: #e8f4f8; padding: 5px; border: 2px solid #4a90e2;"
        )
        self.lbl_eb_out.setStyleSheet(
            "background-color: #ff0000; color: white; padding: 5px; border: 2px solid darkred; font-weight: bold;" 
            if eb_active else 
            "background-color: #e8f4f8; padding: 5px; border: 2px solid #4a90e2;"
        )

        # Update TELEMETRY displays
        self.lbl_mode.setText("AUTO" if disp.get("auto_mode", True) else "MANUAL")
        
        kp = disp.get("kp", 0.0)
        ki = disp.get("ki", 0.0)
        self.lbl_gains.setText(f"Kp={kp:.2f}, Ki={ki:.2f}")
        
        self.lbl_beacon.setText(disp.get("beacon_info", "None"))
        self.lbl_grade.setText(fmt(disp.get("grade_percent", 0.0)) + " %")