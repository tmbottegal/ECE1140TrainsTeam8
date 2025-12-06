from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QButtonGroup,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from train_model_backend import TrainModelBackend

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class TrainModelTestUI(QWidget):
    MPS_TO_MPH = 2.23694
    M_TO_YD = 1.09361

    def __init__(self, backend: "TrainModelBackend") -> None:
        super().__init__()
        self.backend = backend
        self.backend.add_listener(self._sync_from_backend)

        self._toggle_meta = {}
        self._is_syncing = False

        self.setWindowTitle("Train Controller Testbench")
        self.resize(720, 680)

        main_layout = QVBoxLayout(self)
        
        s = self.backend.report_state()
        name = str(s.get("train_id", "T1"))
        header = QLabel(f"Train {name}")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 1px;")
        main_layout.addWidget(header)
        self.header_label = header

        # top section with two columns
        top_section = QHBoxLayout()
        
        # left column: Engine Commands
        control_group = QGroupBox("Engine Commands")
        control_layout = QGridLayout(control_group)
        control_layout.setHorizontalSpacing(10)
        control_layout.setVerticalSpacing(20)
        control_group.setMinimumHeight(260)

        row = 0

        # power
        lbl = QLabel("Power:")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        control_layout.addWidget(lbl, row, 0)

        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(0.0, 2000.0)
        self.power_spin.setValue(0.0)
        self.power_spin.setSuffix(" kW")
        self.power_spin.setSingleStep(10.0)
        self.power_spin.setReadOnly(True)
        self.power_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        control_layout.addWidget(self.power_spin, row, 1, 1, 2)
        row += 1

        # commanded speed
        lbl = QLabel("Commanded Speed:")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        control_layout.addWidget(lbl, row, 0)

        self.cmd_speed_spin = QDoubleSpinBox()
        self.cmd_speed_spin.setRange(0.0, 80.0)
        self.cmd_speed_spin.setValue(0.0)
        self.cmd_speed_spin.setSuffix(" mph")
        self.cmd_speed_spin.setSingleStep(5.0)
        control_layout.addWidget(self.cmd_speed_spin, row, 1, 1, 2)
        row += 1

        # authority
        lbl = QLabel("Commanded Authority:")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        control_layout.addWidget(lbl, row, 0)

        self.authority_spin = QDoubleSpinBox()
        self.authority_spin.setRange(0.0, 10000.0)
        self.authority_spin.setValue(0.0)
        self.authority_spin.setSuffix(" yds")
        self.authority_spin.setSingleStep(100.0)
        self.authority_spin.setReadOnly(True)
        self.authority_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        control_layout.addWidget(self.authority_spin, row, 1, 1, 2)
        row += 1

        # gain
        lbl = QLabel("Gain (K):")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        control_layout.addWidget(lbl, row, 0)

        self.k_label = QLabel("10.0")
        control_layout.addWidget(self.k_label, row, 1, 1, 2)
        row += 1

        # service brake 
        lbl = QLabel("Service Brake:")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        control_layout.addWidget(lbl, row, 0)

        self.service_brake_btns = self._create_toggle_buttons(
            "Disabled", "Enabled", "service_brake", green=True, red=True
        )
        control_layout.addWidget(self.service_brake_btns[0], row, 1)
        control_layout.addWidget(self.service_brake_btns[1], row, 2)
        row += 1

        # emergency brake 
        lbl = QLabel("Emergency Brake:")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        control_layout.addWidget(lbl, row, 0)

        self.emergency_brake_btns = self._create_toggle_buttons(
            "Disabled", "Enabled", "emergency_brake", green=True, red=True
        )
        control_layout.addWidget(self.emergency_brake_btns[0], row, 1)
        control_layout.addWidget(self.emergency_brake_btns[1], row, 2)

        control_layout.setColumnStretch(1, 1)
        control_layout.setColumnStretch(2, 1)

        top_section.addWidget(control_group, 1)

        
        # right column: Failure Modes
        failure_group = QGroupBox("Failure Modes")
        failure_layout = QGridLayout(failure_group)
        failure_layout.setHorizontalSpacing(10)
        failure_layout.setVerticalSpacing(16)
        failure_group.setMinimumHeight(200)

        row = 0

        # engine failure
        lbl = QLabel("Engine Failure:")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        failure_layout.addWidget(lbl, row, 0)

        self.engine_fail_btns = self._create_toggle_buttons(
            "Disabled", "Enabled", "engine_failure", green=True, red=True
        )
        failure_layout.addWidget(self.engine_fail_btns[0], row, 1)
        failure_layout.addWidget(self.engine_fail_btns[1], row, 2)
        row += 1

        # brake failure
        lbl = QLabel("Brake Failure:")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        failure_layout.addWidget(lbl, row, 0)

        self.brake_fail_btns = self._create_toggle_buttons(
            "Disabled", "Enabled", "brake_failure", green=True, red=True
        )
        failure_layout.addWidget(self.brake_fail_btns[0], row, 1)
        failure_layout.addWidget(self.brake_fail_btns[1], row, 2)
        row += 1

        # signal pickup failure
        lbl = QLabel("Signal Pickup Failure:")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        failure_layout.addWidget(lbl, row, 0)

        self.signal_fail_btns = self._create_toggle_buttons(
            "Disabled", "Enabled", "signal_pickup_failure", green=True, red=True
        )
        failure_layout.addWidget(self.signal_fail_btns[0], row, 1)
        failure_layout.addWidget(self.signal_fail_btns[1], row, 2)

        failure_layout.setColumnStretch(1, 1)
        failure_layout.setColumnStretch(2, 1)

        top_section.addWidget(failure_group, 1)

        main_layout.addLayout(top_section)
        
        # communications section
        track_group = QGroupBox("Communications")
        track_layout = QGridLayout(track_group)
        
        track_layout.addWidget(QLabel("Announcement:"), 0, 0)
        self.announcement_edit = QLineEdit()
        self.announcement_edit.setPlaceholderText("No Announcements")
        track_layout.addWidget(self.announcement_edit, 0, 1)
        announce_btn = QPushButton("Play")
        announce_btn.setMaximumWidth(80)
        announce_btn.clicked.connect(self._play_announcement)
        track_layout.addWidget(announce_btn, 0, 2)
        
        track_layout.addWidget(QLabel("Beacon Info:"), 1, 0)
        self.beacon_edit = QLineEdit()
        self.beacon_edit.setPlaceholderText("No Beacon Info")
        track_layout.addWidget(self.beacon_edit, 1, 1)
        
        main_layout.addWidget(track_group)

        # train environment with column layout
        amenities_group = QGroupBox("Train Environment")
        amenities_layout = QVBoxLayout(amenities_group)
        amenities_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        amenities_layout.setContentsMargins(15, 15, 15, 15)
        amenities_group.setMinimumHeight(200) 

        # temperature row
        temp_row = QHBoxLayout()
        temp_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        temp_row.addWidget(QLabel("Current Temperature:"))
        self.current_temp_label = QDoubleSpinBox()
        self.current_temp_label.setRange(0.0, 200.0)
        self.current_temp_label.setValue(72.0)
        self.current_temp_label.setSuffix(" °F")
        self.current_temp_label.setReadOnly(True)
        self.current_temp_label.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        temp_row.addWidget(self.current_temp_label)

        temp_row.addSpacing(16)

        temp_row.addWidget(QLabel("Temperature Setpoint:"))
        self.temp_setpoint_spin = QDoubleSpinBox()
        self.temp_setpoint_spin.setRange(60.0, 80.0)
        self.temp_setpoint_spin.setValue(72.0)
        self.temp_setpoint_spin.setSuffix(" °F")
        self.temp_setpoint_spin.setSingleStep(1.0)
        self.temp_setpoint_spin.valueChanged.connect(self._on_temp_changed)
        temp_row.addWidget(self.temp_setpoint_spin)

        amenities_layout.addLayout(temp_row)

        # lights/doors grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(25)

        # bold section headers
        lights_header = QLabel("Lights")
        lights_header.setStyleSheet("font-weight: bold;")
        doors_header = QLabel("Doors")
        doors_header.setStyleSheet("font-weight: bold;")

        grid.addWidget(lights_header, 0, 0, 1, 3, alignment=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(doors_header, 0, 4, 1, 3, alignment=Qt.AlignmentFlag.AlignCenter)

        # lights: cabin
        cabin_label = QLabel("Cabin:")
        cabin_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(cabin_label, 1, 0)

        self.cabin_lights_btns = self._create_toggle_buttons("Off", "On", "cabin_lights")
        grid.addWidget(self.cabin_lights_btns[0], 1, 1)
        grid.addWidget(self.cabin_lights_btns[1], 1, 2)

        # lights: headlights
        head_label = QLabel("Headlights:")
        head_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(head_label, 2, 0)

        self.headlights_btns = self._create_toggle_buttons("Off", "On", "headlights")
        grid.addWidget(self.headlights_btns[0], 2, 1)
        grid.addWidget(self.headlights_btns[1], 2, 2)

        # doors: left
        left_label = QLabel("Left:")
        left_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(left_label, 1, 4)

        self.left_doors_btns = self._create_toggle_buttons("Closed", "Open", "left_doors")
        grid.addWidget(self.left_doors_btns[0], 1, 5)
        grid.addWidget(self.left_doors_btns[1], 1, 6)

        # doors: right
        right_label = QLabel("Right:")
        right_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(right_label, 2, 4)

        self.right_doors_btns = self._create_toggle_buttons("Closed", "Open", "right_doors")
        grid.addWidget(self.right_doors_btns[0], 2, 5)
        grid.addWidget(self.right_doors_btns[1], 2, 6)

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 0)  # spacer column
        grid.setColumnStretch(4, 0)
        grid.setColumnStretch(5, 0)
        grid.setColumnStretch(6, 0)

        amenities_layout.addLayout(grid)

        main_layout.addWidget(amenities_group, alignment=Qt.AlignmentFlag.AlignHCenter)

    

        # timers
        self._ctrl_timer = QTimer(self)
        self._ctrl_timer.timeout.connect(self._controller_step)
        self._ctrl_timer.start(200)
        
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_display)
        self._refresh_timer.start(100)

    def _on_temp_changed(self, value: float) -> None:
        if self._is_syncing:
            return
        try:
            self.backend.set_inputs(temperature_setpoint_f=float(value))
        except Exception as e:
            logger.exception("Failed to push temperature setpoint: %s", e)

    def _generate_announcement_from_beacon(self, beacon: str) -> None:
        if not beacon or beacon == "None":
            return
        next_station = beacon.strip()
        announcement = f"{next_station}"
        self.backend.set_inputs(announcement=announcement)

    def _sync_from_backend(self) -> None:
        if self._is_syncing:
            return
        try:
            self._is_syncing = True
            s = self.backend.report_state()

            train_id = str(s.get("train_id", "T99"))
            self.header_label.setText(f"Train {train_id}")

            cmd_speed_mps = float(s.get("commanded_speed", 0.0))
            auth_m = float(s.get("authority", 0.0))
            beacon = str(s.get("beacon", "None"))

            cmd_speed_mph = cmd_speed_mps * self.MPS_TO_MPH
            auth_yd = auth_m * self.M_TO_YD

            self.cmd_speed_spin.blockSignals(True)
            self.cmd_speed_spin.setValue(cmd_speed_mph)
            self.cmd_speed_spin.blockSignals(False)

            self.authority_spin.blockSignals(True)
            self.authority_spin.setValue(auth_yd)
            self.authority_spin.blockSignals(False)

            self.beacon_edit.blockSignals(True)
            self.beacon_edit.setText("" if beacon == "None" else beacon)
            self.beacon_edit.blockSignals(False)

            self._generate_announcement_from_beacon(beacon)

        except Exception as e:
            logger.exception("Failed to sync testbench from backend: %s", e)
        finally:
            self._is_syncing = False

    def _refresh_display(self) -> None:
        if self._is_syncing:
            return
        try:
            self._is_syncing = True
            s = self.backend.report_state()

            temp_c = s.get("actual_temperature_c", None)
            if temp_c is not None:
                temp_f = float(temp_c) * 9.0 / 5.0 + 32.0
                self.current_temp_label.setValue(temp_f)
                
            temp_setpoint_c = s.get("temperature_setpoint_c", None)
            if temp_setpoint_c is not None:
                temp_setpoint_f = float(temp_setpoint_c) * 9.0 / 5.0 + 32.0
                self.temp_setpoint_spin.blockSignals(True)
                self.temp_setpoint_spin.setValue(temp_setpoint_f)
                self.temp_setpoint_spin.blockSignals(False)

            self._set_toggle_state("service_brake", bool(s.get("service_brake", False)))
            self._set_toggle_state("emergency_brake", bool(s.get("emergency_brake", False)))
            self._set_toggle_state("cabin_lights", bool(s.get("cabin_lights", False)))
            self._set_toggle_state("headlights", bool(s.get("headlights", False)))
            self._set_toggle_state("left_doors", bool(s.get("left_doors", False)))
            self._set_toggle_state("right_doors", bool(s.get("right_doors", False)))
            self._set_toggle_state("engine_failure", bool(s.get("engine_failure", False)))
            self._set_toggle_state("brake_failure", bool(s.get("brake_failure", False)))
            self._set_toggle_state("signal_pickup_failure", bool(s.get("signal_pickup_failure", False)))

        except Exception as e:
            logger.exception("Testbench _refresh_display failed: %s", e)
        finally:
            self._is_syncing = False

    def _controller_step(self) -> None:
        if self._is_syncing:
            return
        try:
            v_cmd_backend = float(getattr(self.backend, "commanded_speed", 0.0))
            v_act = float(getattr(self.backend, "velocity", 0.0))
            v_cmd_driver_mps = float(self.cmd_speed_spin.value()) / self.MPS_TO_MPH
            v_cmd = v_cmd_driver_mps if v_cmd_driver_mps > 0.0 else v_cmd_backend

            self.backend.set_inputs(commanded_speed_mph=v_cmd * self.MPS_TO_MPH)

            K = 10.0
            error = max(0.0, v_cmd - v_act)
            power_cmd_kw = K * error

            if self.service_brake_btns[1].isChecked() or self.emergency_brake_btns[1].isChecked():
                power_cmd_kw = 0.0

            power_cmd_kw = max(0.0, min(power_cmd_kw, 2000.0))

            self.backend.set_inputs(
                power_kw=power_cmd_kw,
                service_brake=self.service_brake_btns[1].isChecked(),
                emergency_brake=self.emergency_brake_btns[1].isChecked(),
                beacon_info=str(getattr(self.backend, "beacon_info", "None")),
                temperature_setpoint_f=float(self.temp_setpoint_spin.value()),
            )

            self.power_spin.blockSignals(True)
            self.power_spin.setValue(power_cmd_kw)
            self.power_spin.blockSignals(False)

        except Exception as e:
            logger.exception("Controller step failed: %s", e)

    def _create_toggle_buttons(self, off_text: str, on_text: str, attr_name: str,
                               red: bool = False, green: bool = False) -> tuple:
        off_btn = QPushButton(off_text)
        on_btn = QPushButton(on_text)

        for btn in (off_btn, on_btn):
            btn.setCheckable(True)
            btn.setMinimumWidth(80)

        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(off_btn)
        group.addButton(on_btn)

        self._toggle_meta[attr_name] = (off_btn, on_btn, red, green)

        def _apply_to_backend(enabled: bool) -> None:
            if self._is_syncing:
                return
            try:
                if attr_name in ("engine_failure", "brake_failure", "signal_pickup_failure"):
                    mapping = {"engine_failure": "engine", "brake_failure": "brake", "signal_pickup_failure": "signal"}
                    self.backend.set_failure_state(mapping[attr_name], enabled)
                    return
                if attr_name in ("service_brake", "emergency_brake", "cabin_lights", "headlights", "left_doors", "right_doors"):
                    self.backend.set_inputs(**{attr_name: enabled})
                else:
                    if hasattr(self.backend, attr_name):
                        setattr(self.backend, attr_name, enabled)
                        if hasattr(self.backend, "_notify_listeners"):
                            self.backend._notify_listeners()
            except Exception as e:
                logger.exception("Failed to push toggle '%s' to backend: %s", attr_name, e)

        def update_style_and_push() -> None:
            if self._is_syncing:
                return
            enabled = on_btn.isChecked()

            if off_btn.isChecked():
                off_color = "#7ee093" if green else "#e06b6b"
                off_btn.setStyleSheet(f"background:{off_color}; color:#111; font-weight:bold; padding:6px;")
                on_btn.setStyleSheet("background:#2a2a2a; color:#888; padding:6px;")
            else:
                off_btn.setStyleSheet("background:#2a2a2a; color:#888; padding:6px;")
                on_color = "#e06b6b" if red else "#7ee093"
                on_btn.setStyleSheet(f"background:{on_color}; color:#111; font-weight:bold; padding:6px;")

            _apply_to_backend(enabled)

        off_btn.clicked.connect(update_style_and_push)
        on_btn.clicked.connect(update_style_and_push)

        off_btn.setChecked(True)
        update_style_and_push()

        return off_btn, on_btn

    def _set_toggle_state(self, attr_name: str, enabled: bool) -> None:
        if attr_name not in self._toggle_meta:
            return

        off_btn, on_btn, red, green = self._toggle_meta[attr_name]

        for b in (off_btn, on_btn):
            b.blockSignals(True)

        if enabled:
            on_btn.setChecked(True)
            off_btn.setChecked(False)
        else:
            off_btn.setChecked(True)
            on_btn.setChecked(False)

        if off_btn.isChecked():
            off_color = "#7ee093" if green else "#e06b6b"
            off_btn.setStyleSheet(f"background:{off_color}; color:#111; font-weight:bold; padding:6px;")
            on_btn.setStyleSheet("background:#2a2a2a; color:#888; padding:6px;")
        else:
            off_btn.setStyleSheet("background:#2a2a2a; color:#888; padding:6px;")
            on_color = "#e06b6b" if red else "#7ee093"
            on_btn.setStyleSheet(f"background:{on_color}; color:#111; font-weight:bold; padding:6px;")

        for b in (off_btn, on_btn):
            b.blockSignals(False)

    def _play_announcement(self) -> None:
        announcement_text = self.announcement_edit.text().strip()
        if announcement_text:
            try:
                self.backend.set_inputs(announcement=announcement_text)
            except Exception as e:
                logger.exception("Failed to push announcement: %s", e)
            QMessageBox.information(self, "Announcement Playing", f"Now announcing:\n\n\"{announcement_text}\"")
        else:
            QMessageBox.warning(self, "No Announcement", "Please enter an announcement first.")


if __name__ == "__main__":
    from train_model_backend import TrainModelBackend
    
    app = QApplication(sys.argv)
    backend = TrainModelBackend()
    test_ui = TrainModelTestUI(backend)
    test_ui.show()
    sys.exit(app.exec())
