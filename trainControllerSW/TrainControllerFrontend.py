"""
TrainControllerFrontend.py
PyQt6 UI for Train Controller matching the provided screenshot

Creates a UI with:
- Driver and Engineer tabs
- All controls and displays
- Dark gray/beige theme matching screenshot
- Real-time updates
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QLineEdit, QGroupBox, QTextEdit,
                             QTabWidget, QDoubleSpinBox, QCheckBox, QSlider, QSpinBox)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont

# Import backend - this will handle its own universal/clock imports
from TrainControllerBackend import TrainControllerBackend

# Import ConversionFunctions (for any additional UI needs)
try:
    from universal import ConversionFunctions
except (ImportError, ModuleNotFoundError):
    # Use the one from Backend
    from TrainControllerBackend import ConversionFunctions

# Import global clock
try:
    from global_clock import clock
except (ImportError, ModuleNotFoundError):
    # Use the one from Backend
    from TrainControllerBackend import clock


class TrainControllerUI(QMainWindow):
    """Main Train Controller UI window."""
    
    def __init__(self):
        super().__init__()
        self.backend = TrainControllerBackend()
        self.init_ui()
        
        # Update timer (50ms = 20Hz)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.timeout.connect(self.tick_clock)
        self.timer.start(50)
        
    def init_ui(self):
        """Initialize the UI."""
        self.setWindowTitle(f"Train Controller - Train {self.backend.train_id}")
        self.setGeometry(100, 100, 1250, 850)
        
        # Set color scheme matching screenshot
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #4a4a4a;
                color: #ffffff;
                font-family: Arial;
            }
            QGroupBox {
                border: 2px solid #d4af37;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                padding: 15px;
                background-color: #5a5a5a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                padding: 0 5px;
                color: #d4af37;
            }
            QPushButton {
                background-color: #6a6a6a;
                border: 1px solid #888;
                border-radius: 3px;
                padding: 8px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7a7a7a;
            }
            QPushButton:pressed {
                background-color: #5a5a5a;
            }
            QPushButton#greenButton {
                background-color: #4CAF50;
            }
            QPushButton#redButton {
                background-color: #d32f2f;
                font-size: 14pt;
            }
            QLineEdit {
                background-color: #6a6a6a;
                border: 1px solid #888;
                border-radius: 3px;
                padding: 5px;
                color: white;
            }
            QLineEdit[readOnly="true"] {
                background-color: #5a5a5a;
            }
            QTextEdit {
                background-color: #5a5a5a;
                border: 1px solid #888;
                color: white;
            }
            QTabWidget::pane {
                border: 1px solid #888;
            }
            QTabBar::tab {
                background-color: #6a6a6a;
                color: white;
                padding: 10px 20px;
                border: 1px solid #888;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #d4af37;
                color: black;
            }
        """)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Header with date/time and train ID
        header = QHBoxLayout()
        self.date_label = QLabel()
        self.date_label.setStyleSheet("font-size: 12pt; font-weight: bold; color: white;")
        self.time_label = QLabel()
        self.time_label.setStyleSheet("font-size: 12pt; font-weight: bold; color: white;")
        header.addWidget(self.date_label)
        header.addStretch()
        header.addWidget(self.time_label)
        main_layout.addLayout(header)
        
        # Train ID
        train_label = QLabel(f"Train {self.backend.train_id}")
        train_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #d4af37;")
        main_layout.addWidget(train_label)
        
        # Tabs
        self.tabs = QTabWidget()
        self.driver_tab = QWidget()
        self.engineer_tab = QWidget()
        self.tabs.addTab(self.driver_tab, "Driver")
        self.tabs.addTab(self.engineer_tab, "Engineer")
        main_layout.addWidget(self.tabs)
        
        self.setup_driver_tab()
        self.setup_engineer_tab()
        
    def setup_driver_tab(self):
        """Setup driver tab matching screenshot."""
        layout = QVBoxLayout(self.driver_tab)
        
        # Top row: Control Parameters + Train Speed + Right buttons
        top = QHBoxLayout()
        
        # Control Parameters
        ctrl_group = QGroupBox("Control Parameters")
        ctrl_layout = QVBoxLayout()
        
        speed_lim = QHBoxLayout()
        speed_lim.addWidget(QLabel("Speed Limit:"))
        self.speed_limit_disp = QLineEdit("44 MPH")
        self.speed_limit_disp.setReadOnly(True)
        speed_lim.addWidget(self.speed_limit_disp)
        ctrl_layout.addLayout(speed_lim)
        
        cmd_spd = QHBoxLayout()
        cmd_spd.addWidget(QLabel("Commanded Speed:"))
        self.cmd_speed_disp = QLineEdit("0.0 MPH")
        self.cmd_speed_disp.setReadOnly(True)
        cmd_spd.addWidget(self.cmd_speed_disp)
        ctrl_layout.addLayout(cmd_spd)
        
        auth = QHBoxLayout()
        auth.addWidget(QLabel("Authority:"))
        self.authority_disp = QLineEdit("0 ft")
        self.authority_disp.setReadOnly(True)
        auth.addWidget(self.authority_disp)
        ctrl_layout.addLayout(auth)
        
        ctrl_group.setLayout(ctrl_layout)
        top.addWidget(ctrl_group)
        
        # Train Speed
        speed_group = QGroupBox("Train Speed")
        speed_layout = QVBoxLayout()
        
        cur_spd = QHBoxLayout()
        cur_spd.addWidget(QLabel("Current Measured Speed:"))
        self.current_speed_disp = QLineEdit("0")
        self.current_speed_disp.setReadOnly(True)
        self.current_speed_disp.setStyleSheet("font-size: 20pt; font-weight: bold;")
        cur_spd.addWidget(self.current_speed_disp)
        cur_spd.addWidget(QLabel("MPH"))
        speed_layout.addLayout(cur_spd)
        
        set_spd = QHBoxLayout()
        set_spd.addWidget(QLabel("Set Speed:"))
        self.set_speed_input = QDoubleSpinBox()
        self.set_speed_input.setRange(0, 100)
        self.set_speed_input.setSuffix(" MPH")
        set_spd.addWidget(self.set_speed_input)
        self.set_speed_btn = QPushButton("Set Speed")
        self.set_speed_btn.clicked.connect(self.on_set_speed)
        set_spd.addWidget(self.set_speed_btn)
        speed_layout.addLayout(set_spd)
        
        spd_btns = QHBoxLayout()
        self.spd_minus = QPushButton("-")
        self.spd_minus.clicked.connect(lambda: self.backend.decrease_speed(1))
        spd_btns.addWidget(self.spd_minus)
        self.spd_plus = QPushButton("+")
        self.spd_plus.clicked.connect(lambda: self.backend.increase_speed(1))
        spd_btns.addWidget(self.spd_plus)
        speed_layout.addLayout(spd_btns)
        
        self.mode_btn = QPushButton("Toggle Manual and Automatic")
        self.mode_btn.clicked.connect(self.toggle_mode)
        speed_layout.addWidget(self.mode_btn)
        
        speed_group.setLayout(speed_layout)
        top.addWidget(speed_group)
        
        # Right side buttons
        right_btns = QVBoxLayout()
        
        self.right_doors_btn = QPushButton("Right Doors\nClosed")
        self.right_doors_btn.setObjectName("greenButton")
        self.right_doors_btn.clicked.connect(self.backend.toggle_right_doors)
        self.right_doors_btn.setMinimumHeight(60)
        right_btns.addWidget(self.right_doors_btn)
        
        self.left_doors_btn = QPushButton("Left Doors\nClosed")
        self.left_doors_btn.setObjectName("greenButton")
        self.left_doors_btn.clicked.connect(self.backend.toggle_left_doors)
        self.left_doors_btn.setMinimumHeight(60)
        right_btns.addWidget(self.left_doors_btn)
        
        self.interior_lights_btn = QPushButton("Indoor Lights\nOff")
        self.interior_lights_btn.clicked.connect(self.backend.toggle_interior_lights)
        right_btns.addWidget(self.interior_lights_btn)
        
        self.headlights_btn = QPushButton("Headlights\nOn")
        self.headlights_btn.clicked.connect(self.backend.toggle_headlights)
        right_btns.addWidget(self.headlights_btn)
        
        self.ac_btn = QPushButton("A/C\nOn")
        self.ac_btn.setObjectName("greenButton")
        self.ac_btn.clicked.connect(self.backend.toggle_ac)
        right_btns.addWidget(self.ac_btn)
        
        top.addLayout(right_btns)
        layout.addLayout(top)
        
        # Middle row: Engine Commands + Route Info + Emergency/Temp
        middle = QHBoxLayout()
        
        # Engine Commands
        engine_group = QGroupBox("Engine Commands")
        engine_layout = QVBoxLayout()
        
        set_spd_e = QHBoxLayout()
        set_spd_e.addWidget(QLabel("Set Speed:"))
        self.engine_speed_disp = QLineEdit("0 MPH")
        self.engine_speed_disp.setReadOnly(True)
        set_spd_e.addWidget(self.engine_speed_disp)
        engine_layout.addLayout(set_spd_e)
        
        pwr = QHBoxLayout()
        pwr.addWidget(QLabel("Output Power:"))
        self.power_disp = QLineEdit("0 kW")
        self.power_disp.setReadOnly(True)
        pwr.addWidget(self.power_disp)
        engine_layout.addLayout(pwr)
        
        engine_group.setLayout(engine_layout)
        middle.addWidget(engine_group)
        
        # Route Info
        route_group = QGroupBox("Route Information")
        route_layout = QVBoxLayout()
        
        nxt_stn = QHBoxLayout()
        nxt_stn.addWidget(QLabel("Next Station:"))
        self.station_disp = QLineEdit("")
        self.station_disp.setReadOnly(True)
        nxt_stn.addWidget(self.station_disp)
        route_layout.addLayout(nxt_stn)
        
        line = QHBoxLayout()
        line.addWidget(QLabel("Current Train Line:"))
        self.line_disp = QLineEdit("Green")
        self.line_disp.setReadOnly(True)
        line.addWidget(self.line_disp)
        route_layout.addLayout(line)
        
        route_group.setLayout(route_layout)
        middle.addWidget(route_group)
        
        # Emergency brake + temp
        right_ctrl = QVBoxLayout()
        
        # Emergency brake
        self.ebrake_enable = QCheckBox("Enable Emergency Brake")
        self.ebrake_enable.stateChanged.connect(lambda: self.backend.toggle_emergency_enable())
        right_ctrl.addWidget(self.ebrake_enable)
        
        self.ebrake_btn = QPushButton("Emergency Brake")
        self.ebrake_btn.setObjectName("redButton")
        self.ebrake_btn.setMinimumHeight(80)
        self.ebrake_btn.clicked.connect(lambda: self.backend.set_emergency_brake(True))
        right_ctrl.addWidget(self.ebrake_btn)
        
        # Service brake label
        sbrake_lbl = QLabel("Service Brake")
        sbrake_lbl.setStyleSheet("font-weight: bold; color: #d4af37;")
        sbrake_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_ctrl.addWidget(sbrake_lbl)
        
        self.sbrake_slider = QSlider(Qt.Orientation.Vertical)
        self.sbrake_slider.setRange(0, 100)
        self.sbrake_slider.setValue(0)
        self.sbrake_slider.valueChanged.connect(self.on_sbrake_change)
        self.sbrake_slider.setMinimumHeight(100)
        right_ctrl.addWidget(self.sbrake_slider, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.sbrake_label = QLabel("0% Brake")
        self.sbrake_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_ctrl.addWidget(self.sbrake_label)
        
        # Temperature
        temp_btns = QHBoxLayout()
        self.temp_minus = QPushButton("-")
        self.temp_minus.clicked.connect(lambda: self.backend.set_cabin_temp(self.backend.cabin_temp_f - 1))
        temp_btns.addWidget(self.temp_minus)
        
        self.temp_disp = QLabel("68°F")
        self.temp_disp.setStyleSheet("font-size: 16pt; font-weight: bold;")
        self.temp_disp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        temp_btns.addWidget(self.temp_disp)
        
        self.temp_plus = QPushButton("+")
        self.temp_plus.clicked.connect(lambda: self.backend.set_cabin_temp(self.backend.cabin_temp_f + 1))
        temp_btns.addWidget(self.temp_plus)
        right_ctrl.addLayout(temp_btns)
        
        self.curr_temp_lbl = QLabel("Current Car Temp: 68°F")
        self.curr_temp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_ctrl.addWidget(self.curr_temp_lbl)
        
        middle.addLayout(right_ctrl)
        layout.addLayout(middle)
        
        # Bottom row: Status Log + Failures
        bottom = QHBoxLayout()
        
        # Status Log
        log_group = QGroupBox("Status Log")
        log_layout = QVBoxLayout()
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setMaximumHeight(150)
        log_layout.addWidget(self.status_log)
        log_group.setLayout(log_layout)
        bottom.addWidget(log_group)
        
        # Failures
        fail_group = QGroupBox("Failures")
        fail_layout = QVBoxLayout()
        
        eng_fail = QHBoxLayout()
        eng_fail.addWidget(QLabel("Engine Failure:"))
        self.engine_fail_disp = QLineEdit("NONE")
        self.engine_fail_disp.setReadOnly(True)
        eng_fail.addWidget(self.engine_fail_disp)
        fail_layout.addLayout(eng_fail)
        
        brk_fail = QHBoxLayout()
        brk_fail.addWidget(QLabel("Brake Failure:"))
        self.brake_fail_disp = QLineEdit("NONE")
        self.brake_fail_disp.setReadOnly(True)
        brk_fail.addWidget(self.brake_fail_disp)
        fail_layout.addLayout(brk_fail)
        
        sig_fail = QHBoxLayout()
        sig_fail.addWidget(QLabel("Signal Failure:"))
        self.signal_fail_disp = QLineEdit("NONE")
        self.signal_fail_disp.setReadOnly(True)
        sig_fail.addWidget(self.signal_fail_disp)
        fail_layout.addLayout(sig_fail)
        
        fail_group.setLayout(fail_layout)
        bottom.addWidget(fail_group)
        
        layout.addLayout(bottom)
        
    def setup_engineer_tab(self):
        """Setup engineer tab."""
        layout = QVBoxLayout(self.engineer_tab)
        
        # PI Gains
        gains_group = QGroupBox("PI Controller Gains")
        gains_layout = QVBoxLayout()
        
        kp_row = QHBoxLayout()
        kp_row.addWidget(QLabel("Kp (Proportional):"))
        self.kp_input = QDoubleSpinBox()
        self.kp_input.setRange(0, 100000)
        self.kp_input.setValue(10000)
        self.kp_input.setSingleStep(100)
        kp_row.addWidget(self.kp_input)
        gains_layout.addLayout(kp_row)
        
        ki_row = QHBoxLayout()
        ki_row.addWidget(QLabel("Ki (Integral):"))
        self.ki_input = QDoubleSpinBox()
        self.ki_input.setRange(0, 100000)
        self.ki_input.setValue(1000)
        self.ki_input.setSingleStep(100)
        ki_row.addWidget(self.ki_input)
        gains_layout.addLayout(ki_row)
        
        set_gains_btn = QPushButton("Set Gains")
        set_gains_btn.clicked.connect(self.on_set_gains)
        gains_layout.addWidget(set_gains_btn)
        
        gains_group.setLayout(gains_layout)
        layout.addWidget(gains_group)
        
        # Test inputs
        test_group = QGroupBox("Test Inputs (for testing without Train Model)")
        test_layout = QVBoxLayout()
        
        test_spd = QHBoxLayout()
        test_spd.addWidget(QLabel("Simulate Current Speed (MPH):"))
        self.test_speed = QDoubleSpinBox()
        self.test_speed.setRange(0, 100)
        test_spd.addWidget(self.test_speed)
        test_spd_btn = QPushButton("Set")
        test_spd_btn.clicked.connect(self.on_test_speed)
        test_spd.addWidget(test_spd_btn)
        test_layout.addLayout(test_spd)
        
        test_cmd = QHBoxLayout()
        test_cmd.addWidget(QLabel("Simulate Commanded Speed (MPH):"))
        self.test_cmd = QDoubleSpinBox()
        self.test_cmd.setRange(0, 100)
        test_cmd.addWidget(self.test_cmd)
        test_cmd_btn = QPushButton("Set")
        test_cmd_btn.clicked.connect(self.on_test_cmd)
        test_cmd.addWidget(test_cmd_btn)
        test_layout.addLayout(test_cmd)
        
        test_auth = QHBoxLayout()
        test_auth.addWidget(QLabel("Simulate Authority (ft):"))
        self.test_auth = QDoubleSpinBox()
        self.test_auth.setRange(0, 10000)
        self.test_auth.setValue(1000)
        test_auth.addWidget(self.test_auth)
        test_auth_btn = QPushButton("Set")
        test_auth_btn.clicked.connect(self.on_test_auth)
        test_auth.addWidget(test_auth_btn)
        test_layout.addLayout(test_auth)
        
        self.test_station = QCheckBox("Simulate at Station")
        self.test_station.stateChanged.connect(self.on_test_station)
        test_layout.addWidget(self.test_station)
        
        fail_row = QHBoxLayout()
        self.test_eng_fail = QCheckBox("Engine Failure")
        self.test_eng_fail.stateChanged.connect(self.on_test_failures)
        fail_row.addWidget(self.test_eng_fail)
        
        self.test_brk_fail = QCheckBox("Brake Failure")
        self.test_brk_fail.stateChanged.connect(self.on_test_failures)
        fail_row.addWidget(self.test_brk_fail)
        test_layout.addLayout(fail_row)
        
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        
        layout.addStretch()
        
    def tick_clock(self):
        """Advance the global clock."""
        clock.tick()
        
    def update_display(self):
        """Update all displays."""
        state = self.backend.get_state()
        
        # Date/time
        dt = clock.get_time()
        self.date_label.setText(f"Date: {dt.strftime('%m/%d/%Y')}")
        self.time_label.setText(f"Time: {dt.strftime('%I:%M:%S %p')}")
        
        # Control params
        self.speed_limit_disp.setText(f"{state['speed_limit_mph']:.0f} MPH")
        
        if state['automatic_mode']:
            self.cmd_speed_disp.setText(f"{state['commanded_speed_mph']:.1f} MPH")
        else:
            self.cmd_speed_disp.setText(f"{state['setpoint_speed_mph']:.1f} MPH")
            
        self.authority_disp.setText(f"{state['authority_ft']:.0f} ft")
        
        # Speed
        self.current_speed_disp.setText(f"{state['current_speed_mph']:.0f}")
        self.engine_speed_disp.setText(f"{state['setpoint_speed_mph']:.0f} MPH")
        
        # Power
        self.power_disp.setText(f"{state['power_kw']:.0f} kW")
        
        # Doors
        self.right_doors_btn.setText(f"Right Doors\n{'Open' if state['right_doors_open'] else 'Closed'}")
        self.left_doors_btn.setText(f"Left Doors\n{'Open' if state['left_doors_open'] else 'Closed'}")
        
        # Lights
        self.interior_lights_btn.setText(f"Indoor Lights\n{'On' if state['interior_lights_on'] else 'Off'}")
        self.headlights_btn.setText(f"Headlights\n{'On' if state['headlights_on'] else 'Off'}")
        
        # A/C
        self.ac_btn.setText(f"A/C\n{'On' if state['ac_on'] else 'Off'}")
        
        # Temp
        self.temp_disp.setText(f"{state['cabin_temp_f']:.0f}°F")
        self.curr_temp_lbl.setText(f"Current Car Temp: {state['cabin_temp_f']:.0f}°F")
        
        # Route
        self.station_disp.setText(state['station_name'])
        self.line_disp.setText(state['current_line'])
        
        # Failures
        self.engine_fail_disp.setText("FAILURE" if state['engine_failure'] else "NONE")
        self.engine_fail_disp.setStyleSheet(
            f"background-color: {'#cc0000' if state['engine_failure'] else '#5a5a5a'};"
        )
        
        self.brake_fail_disp.setText("FAILURE" if state['brake_failure'] else "NONE")
        self.brake_fail_disp.setStyleSheet(
            f"background-color: {'#cc0000' if state['brake_failure'] else '#5a5a5a'};"
        )
        
        self.signal_fail_disp.setText("FAILURE" if state['signal_failure'] else "NONE")
        self.signal_fail_disp.setStyleSheet(
            f"background-color: {'#cc0000' if state['signal_failure'] else '#5a5a5a'};"
        )
        
        # Status log
        log_text = "\n".join(state['status_log'])
        if log_text != self.status_log.toPlainText():
            self.status_log.setText(log_text)
            self.status_log.verticalScrollBar().setValue(
                self.status_log.verticalScrollBar().maximum()
            )
        
        # Mode button
        self.mode_btn.setText(f"Mode: {'AUTOMATIC' if state['automatic_mode'] else 'MANUAL'}")
        
        # Service brake slider
        if state['service_brake']:
            self.sbrake_slider.setValue(100)
        else:
            self.sbrake_slider.setValue(0)
            
    def on_set_speed(self):
        """Handle set speed button."""
        self.backend.set_setpoint_speed_mph(self.set_speed_input.value())
        
    def toggle_mode(self):
        """Toggle automatic/manual mode."""
        self.backend.set_automatic_mode(not self.backend.automatic_mode)
        
    def on_sbrake_change(self, value):
        """Handle service brake slider."""
        self.backend.set_service_brake(value > 50)
        self.sbrake_label.setText(f"{value}% Brake")
        
    def on_set_gains(self):
        """Handle set gains button."""
        self.backend.set_kp(self.kp_input.value())
        self.backend.set_ki(self.ki_input.value())
        
    def on_test_speed(self):
        """Handle test speed input."""
        self.backend.update_from_train_model(self.test_speed.value())
        
    def on_test_cmd(self):
        """Handle test commanded speed."""
        self.backend.update_from_track_controller(
            self.test_cmd.value(),
            self.backend.authority_ft,
            self.backend.speed_limit_mph
        )
        
    def on_test_auth(self):
        """Handle test authority."""
        self.backend.update_from_track_controller(
            self.backend.commanded_speed_mph,
            self.test_auth.value(),
            self.backend.speed_limit_mph
        )
        
    def on_test_station(self):
        """Handle test station checkbox."""
        self.backend.at_station = self.test_station.isChecked()
        if self.backend.at_station:
            self.backend.station_name = "Test Station"
        else:
            self.backend.station_name = ""
            
    def on_test_failures(self):
        """Handle test failure checkboxes."""
        self.backend.update_from_train_model(
            self.backend.current_speed_mph,
            self.test_eng_fail.isChecked(),
            self.test_brk_fail.isChecked(),
            False
        )


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = TrainControllerUI()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()