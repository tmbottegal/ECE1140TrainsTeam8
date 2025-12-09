from __future__ import annotations
import os
import sys
import logging
from typing import TYPE_CHECKING, Dict

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QButtonGroup, QDialog, QLineEdit,
    QMessageBox, QSizePolicy
)
from universal.global_clock import clock as global_clock
from datetime import datetime

if TYPE_CHECKING:
    from train_model_backend import TrainModelBackend

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# beacon pop-up 
class BeaconPopup(QDialog):
    def __init__(self, backend: "TrainModelBackend", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.setWindowTitle("Beacon Information")
        self.resize(380, 160)

        v = QVBoxLayout(self)
        self.cur = QLabel(f"Current Beacon:\n{self.backend.beacon_info}")
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Enter new beacon text…")
        v.addWidget(self.cur)
        v.addWidget(self.edit)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        v.addWidget(apply_btn)

    def _apply(self) -> None:
        text = self.edit.text().strip()
        if text:
            self.backend.beacon_info = text
            self.backend._notify_listeners()
            QMessageBox.information(self, "Updated", f"Beacon set to: {text}")
            self.close()

# Main UI 
class TrainModelUI(QWidget):
    """Main Train Model dashboard"""

    # unit factors
    M_TO_FT = 3.28084
    M_TO_YD = 1.09361
    KG_TO_LB = 2.20462
    MPS_TO_MPH = 2.23694
    MS2_TO_FTS2 = 3.28084

    def __init__(self, backend: "TrainModelBackend | list[TrainModelBackend]") -> None:
        super().__init__()     
        self.backend = backend
        self.backend.add_listener(self.refresh_display)

        self.setWindowTitle("Train Model")
        self.resize(1180, 680)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        # left column
        left_col = QVBoxLayout() 

        self._ui_refresh_timer = QTimer(self)
        self._ui_refresh_timer.timeout.connect(self.refresh_display)
        self._ui_refresh_timer.start(200)

        # banner (ad)
        banner_box = QGroupBox()
        banner_box.setTitle("Today's Advertisments")
        banner_box.setStyleSheet("QGroupBox {font-weight:700;}")
        banner_v = QVBoxLayout(banner_box)
        self.ad_label = QLabel()
        self.ad_label.setFixedHeight(300)
        self.ad_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ad_label.setStyleSheet("background:#1f1f1f; border:1px solid #444; padding:0;")
        banner_v.addWidget(self.ad_label)

        self._ad_paths = []
        ad_dir = os.path.dirname(os.path.abspath(__file__))
        for i in range(1, 5):  # ad1.png, ad2.png, ad3.png, ad4.png
            path = os.path.join(ad_dir, f"ad{i}.png")
            if os.path.exists(path):
                self._ad_paths.append(path)
        
        # fallback to original ad.png if numbered ads don't exist
        if not self._ad_paths:
            fallback_paths = [
                "/Users/sarakeriakes/Desktop/ECE/2025-26/1140/ECE1140TrainsTeam8/trainModel/ad.png",
                "ad.png", "./assets/ad.png", "./Assets/ad.png", "/mnt/data/ad.png",
                "C:/Users/Tim Bottegal/Desktop/ECE1140TrainsTeam8/trainModel/ad.png",
            ]
            for p in fallback_paths:
                if os.path.exists(p):
                    self._ad_paths = [p]
                    break
        
        self._current_ad_index = 0
        if self._ad_paths:
            self._set_ad_pixmap()
            # timer to rotate ads every 5 seconds
            self._ad_timer = QTimer(self)
            self._ad_timer.timeout.connect(self._rotate_ad)
            self._ad_timer.start(5000)  
        
        left_col.addWidget(banner_box)

        # three sections under ad (two-column layout)
        def make_section(title_text: str, rows: tuple[tuple[str, str], ...], *, small=False) -> tuple[QGroupBox, Dict[str, QLabel]]:
            box = QGroupBox(title_text)
            if small:
                box.setStyleSheet("QGroupBox {font-weight:800; font-size: 12px;}")
            else:
                box.setStyleSheet("QGroupBox {font-weight:800; font-size: 14px;}")
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(6)
            labels: Dict[str, QLabel] = {}
            for r, (label_text, key) in enumerate(rows):
                t = QLabel(label_text)
                t.setStyleSheet(f"font-weight:700; font-size:{11 if small else 12}px;")
                v = QLabel("—")
                v.setAlignment(Qt.AlignmentFlag.AlignCenter)
                v.setStyleSheet(
                    "background:white; color:black; padding:6px; border:1px solid #444; min-width:140px;"
                    f"font-size:{11 if small else 12}px;"
                )
                labels[key] = v
                grid.addWidget(t, r, 0)
                grid.addWidget(v, r, 1)
            return box, labels

        engine_rows = (
            ("Engine Power (kW)", "power_kw"),
            ("Acceleration (ft/s²)", "accel_fts2"),
            ("Current Velocity (mph)", "vel_mph"),
        )
        live_rows = (
            ("Commanded Speed (mph)", "cmd_speed_mph"),
            ("Commanded Authority (yd)", "auth_yd"),
            ("Track Segment", "track_segment"),
            ("Position (yd)", "pos_yd"),
            ("Grade (%)", "grade_percent"),
            ("Crew Count", "crew_count"),
            ("Passenger Count", "passenger_count"),
            ("Cabin Temperature (°F)", "temp_f"),
        )
        prop_rows = (
            ("Train Length (ft)", "len_ft"),
            ("Train Width (ft)", "wid_ft"),
            ("Train Height (ft)", "ht_ft"),
            ("Vehicle Mass (lb)", "mass_lb"),
        )

        engine_box, self.engine_labels = make_section("Engine Stats", engine_rows)
        prop_box,   self.prop_labels   = make_section("Train Properties", prop_rows, small=True)
        live_box,   self.live_labels   = make_section("Live Train Data", live_rows)

        sections_row = QHBoxLayout()
        sections_row.setSpacing(12)

        left_stack = QVBoxLayout()
        left_stack.setSpacing(10)
        left_stack.addWidget(engine_box)
        left_stack.addWidget(prop_box)

        right_stack = QVBoxLayout()
        right_stack.setSpacing(10)
        right_stack.addWidget(live_box)

        sections_row.addLayout(left_stack, 1)
        sections_row.addLayout(right_stack, 1)

        left_col.addLayout(sections_row)
        root.addLayout(left_col, 3)

        # right column
        right_col = QVBoxLayout()

        # clock (shows GLOBAL CTC time))
        self.clock_lbl = QLabel("2000-01-01 00:00:00")
        self.clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_lbl.setStyleSheet("font-size:18px; font-weight:700;")
        right_col.addWidget(self.clock_lbl)

        # subscribe to global clock updates
        global_clock.register_listener(self._update_clock_display)
        # initialize immediately with current clock time, if available
        try:
            current_time = global_clock.get_time()
            self._update_clock_display(current_time)
        except Exception:
            pass

        header_box = QGroupBox()
        header_v = QVBoxLayout(header_box)
        self.train_lbl = QLabel("Train -")
        self.train_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.train_lbl.setStyleSheet("font-size:16px; font-weight:800;")

        self.announcement_lbl = QLabel("No announcement")
        self.announcement_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.announcement_lbl.setStyleSheet(
            "font-size: 13px; padding: 8px; background: #1a1a1a; "
            "border: 1px solid #444; border-radius: 4px; color: #ddd;"
        )
        header_v.addWidget(self.train_lbl)
        header_v.addWidget(self.announcement_lbl)
        right_col.addWidget(header_box)

        # cabin/doors
        cabin_box = QGroupBox("Cabin Environment")
        cabin_v = QVBoxLayout(cabin_box)

        def make_on_off_row(title: str, attr_name: str, words=("Off", "On")):
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            off_btn = QPushButton(words[0])
            on_btn = QPushButton(words[1])
            for b in (off_btn, on_btn):
                b.setCheckable(True)
                b.setMinimumWidth(80)
            def style_on(btn: QPushButton, green: bool):
                btn.setStyleSheet(
                    "QPushButton {background:%s; color:#111; font-weight:700; padding:6px;}"
                    % ("#7ee093" if green else "#e06b6b")
                )
            def style_off(btn: QPushButton):
                btn.setStyleSheet("QPushButton {background:#2a2a2a; color:#ddd; padding:6px;}")
            grp = QButtonGroup(self)
            grp.setExclusive(True)
            grp.addButton(off_btn)
            grp.addButton(on_btn)
            def on_clicked(btn: QPushButton):
                enabled = (btn is on_btn)

                # update button styling
                style_on(on_btn, green=True) if enabled else style_off(on_btn)
                style_on(off_btn, green=False) if not enabled else style_off(off_btn)

                # propagate to backend via set_inputs
                try:
                    if attr_name in ("cabin_lights", "headlights", "left_doors",
                                     "right_doors"):
                        self.backend.set_inputs(**{attr_name: enabled})
                    else:
                        # fallback: direct attr + notify
                        setattr(self.backend, attr_name, enabled)
                        if hasattr(self.backend, "_notify_listeners"):
                            self.backend._notify_listeners()
                except Exception as e:
                    logger.exception("Failed to push cabin toggle '%s' to backend: %s", attr_name, e)

            off_btn.clicked.connect(lambda: on_clicked(off_btn))
            on_btn.clicked.connect(lambda: on_clicked(on_btn))
            off_btn.setChecked(True); style_off(on_btn); style_on(off_btn, green=False)
            row.addStretch(1)
            row.addWidget(off_btn); row.addWidget(on_btn)
            cabin_v.addLayout(row)
            return off_btn, on_btn

        self._cabin_controls = {
            "cabin_lights": make_on_off_row("Cabin Lights", "cabin_lights"),
            "headlights":   make_on_off_row("Headlights", "headlights"),
            "left_doors":   make_on_off_row("Left Doors", "left_doors", words=("Close", "Open")),
            "right_doors":  make_on_off_row("Right Doors", "right_doors", words=("Close", "Open")),
        }
        right_col.addWidget(cabin_box)

        # failure controls
        fail_box = QGroupBox("Failure Modes")
        fail_v = QVBoxLayout(fail_box)

        def make_failure_toggle(title: str, key: str):
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            disabled_btn = QPushButton("Disabled")
            enabled_btn = QPushButton("Enabled")
            for b in (disabled_btn, enabled_btn):
                b.setCheckable(True)
                b.setMinimumWidth(90)
            def style_on(btn: QPushButton, green: bool):
                btn.setStyleSheet(
                    "QPushButton {background:%s; color:#111; font-weight:700; padding:6px;}"
                    % ("#7ee093" if green else "#e06b6b")
                )
            def style_off(btn: QPushButton):
                btn.setStyleSheet("QPushButton {background:#2a2a2a; color:#ddd; padding:6px;}")
            grp = QButtonGroup(self)
            grp.setExclusive(True)
            grp.addButton(disabled_btn); grp.addButton(enabled_btn)

            self._fail_rows[key] = (disabled_btn, enabled_btn, style_on, style_off)

            def on_clicked(btn: QPushButton):
                enabled = (btn is enabled_btn)
                style_on(enabled_btn, green=False) if enabled else style_off(enabled_btn)
                style_on(disabled_btn, green=True) if not enabled else style_off(disabled_btn)
                mapping = {"engine": "engine", "brake": "brake", "signal": "signal"}
                self.backend.set_failure_state(mapping[key], enabled)

            disabled_btn.clicked.connect(lambda: on_clicked(disabled_btn))
            enabled_btn.clicked.connect(lambda: on_clicked(enabled_btn))

            disabled_btn.setChecked(True)
            style_on(disabled_btn, green=True); style_off(enabled_btn)

            row.addStretch(1)
            row.addWidget(disabled_btn); row.addWidget(enabled_btn)
            fail_v.addLayout(row)

        self._fail_rows: Dict[str, tuple] = {}
        make_failure_toggle("Engine Failure", "engine")
        make_failure_toggle("Brake Failure", "brake")
        make_failure_toggle("Signal Pickup Failure", "signal")
        right_col.addWidget(fail_box)

        # Emergency brake + beacon
        self.ebutton = QPushButton("EMERGENCY BRAKE")
        self.ebutton.setStyleSheet("background:#d33232; color:white; font-weight:1000; padding:16px;")
        self.ebutton.clicked.connect(self._activate_emergency_brake)
        right_col.addWidget(self.ebutton)

        beacon_btn = QPushButton("View/Edit Beacon Info")
        beacon_btn.clicked.connect(self._open_beacon_popup)
        right_col.addWidget(beacon_btn)

        # wrap/right panel
        right_panel = QWidget()
        right_panel.setLayout(right_col)
        right_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        right_panel.setMaximumHeight(right_panel.sizeHint().height())
        root.addWidget(right_panel, 2, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.refresh_display()

    def _rotate_ad(self) -> None:
        if not self._ad_paths:
            return
        self._current_ad_index = (self._current_ad_index + 1) % len(self._ad_paths)
        self._set_ad_pixmap()

    # helpers 
    def _update_clock_display(self, current_time: datetime) -> None:
        """
        listener for universal.global_clock
        """
        try:
            date_str = current_time.strftime("%Y-%m-%d")
            time_str = current_time.strftime("%H:%M:%S")
            self.clock_lbl.setText(f"Today's Date: {date_str}\n Current Time: {time_str}")

            # keep backend's notion of time in sync
            if hasattr(self.backend, "set_time"):
                self.backend.set_time(current_time)
        except Exception:
            logger.exception("Failed to update TrainModelUI clock display")

    def _set_ad_pixmap(self) -> None:
        if not getattr(self, "_ad_paths", None):
            return

        # pick current ad based on index
        path = self._ad_paths[self._current_ad_index]
        pm = QPixmap(path)
        if pm.isNull():
            return

        scaled = pm.scaled(
            self.ad_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.ad_label.setPixmap(scaled)


    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._set_ad_pixmap()

    #  actions
    def _activate_emergency_brake(self) -> None:
        try:
            self.backend.emergency_brake = True
            self.backend._notify_listeners()
            QMessageBox.warning(self, "Emergency Brake", "Emergency Brake Activated!")
        except Exception as exc:
            logger.exception("Emergency brake activation failed: %s", exc)

    def _open_beacon_popup(self) -> None:
        BeaconPopup(self.backend, self).exec()

    # refresh from backend
    def refresh_display(self) -> None:
        try:
            s = self.backend.report_state()
            name = str(s.get("train_id", "T1"))
            self.train_lbl.setText(f"Train {name}")


            # engine stats (imperial)
            self.engine_labels["power_kw"].setText(f"{float(s.get('power_kw', 0.0)):.2f}")
            accel_fts2 = float(s.get("acceleration", 0.0)) * self.MS2_TO_FTS2
            self.engine_labels["accel_fts2"].setText(f"{accel_fts2:.2f}")
            vel_mph = float(s.get("velocity", 0.0)) * self.MPS_TO_MPH
            self.engine_labels["vel_mph"].setText(f"{vel_mph:.2f}")

            # live train data (imperial)
            cmd_speed_mph = float(s.get("commanded_speed", 0.0)) * self.MPS_TO_MPH
            self.live_labels["cmd_speed_mph"].setText(f"{cmd_speed_mph:.2f}")
            auth_yd = float(s.get("authority", 0.0)) * self.M_TO_YD
            self.live_labels["auth_yd"].setText(f"{auth_yd:.2f}")
            self.live_labels["track_segment"].setText(str(s.get("track_segment", "—")))
            pos_yd = float(s.get("position", 0.0)) * self.M_TO_YD
            self.live_labels["pos_yd"].setText(f"{pos_yd:.2f}")
            self.live_labels["grade_percent"].setText(f"{float(s.get('grade', 0.0)):.2f}")
            self.live_labels["crew_count"].setText(str(int(s.get("crew_count", 0))))
            self.live_labels["passenger_count"].setText(str(int(s.get("passenger_count", 0))))

            # cabin temperature (F)
            temp_c = s.get("actual_temperature_c", None)
            if temp_c is not None:
                try:
                    temp_f = float(temp_c) * 9.0 / 5.0 + 32.0
                    self.live_labels["temp_f"].setText(f"{temp_f:.2f}")
                except Exception:
                    self.live_labels["temp_f"].setText(str(temp_c))
            else:
                temp_f = (
                    s.get("cabin_temp_f", None)
                    or s.get("cabin_temperature_f", None)
                    or s.get("actual_temperature", None)
                    or s.get("temperature_f", None)
                )
                self.live_labels["temp_f"].setText(f"{float(temp_f):.1f}" if temp_f is not None else "—")

            # Announcement display
            announcement = s.get("current_announcement", "")
            if announcement and announcement.strip():
                self.announcement_lbl.setText(f"{announcement}")
            else:
                self.announcement_lbl.setText("No announcement")

            # train properties (imperial)
            self.prop_labels["len_ft"].setText(f"{float(s.get('length_m', 0.0)) * self.M_TO_FT:.2f}")
            self.prop_labels["wid_ft"].setText(f"{float(s.get('width_m', 0.0)) * self.M_TO_FT:.2f}")
            self.prop_labels["ht_ft"].setText(f"{float(s.get('height_m', 0.0)) * self.M_TO_FT:.2f}")
            self.prop_labels["mass_lb"].setText(f"{float(s.get('mass_kg', 0.0)) * self.KG_TO_LB:.2f}")

            # sync failure toggles without retrigger 
            states = {
                "engine": bool(s.get("engine_failure", False)),
                "brake": bool(s.get("brake_failure", False)),
                "signal": bool(s.get("signal_pickup_failure", False)),
            }
            for key, enabled in states.items():
                disabled_btn, enabled_btn, style_on, style_off = self._fail_rows[key]
                for btn in (disabled_btn, enabled_btn):
                    btn.blockSignals(True)
                if enabled:
                    enabled_btn.setChecked(True); style_on(enabled_btn, green=False); style_off(disabled_btn)
                else:
                    disabled_btn.setChecked(True); style_on(disabled_btn, green=True); style_off(enabled_btn)
                for btn in (disabled_btn, enabled_btn):
                    btn.blockSignals(False)

            # sync cabin/door/HVAC toggles to backend state without retriggering
            cabin_states = {
                "cabin_lights": bool(s.get("cabin_lights", False)),
                "headlights":   bool(s.get("headlights", False)),
                "left_doors":   bool(s.get("left_doors", False)),
                "right_doors":  bool(s.get("right_doors", False)),
            }

            for key, (off_btn, on_btn) in self._cabin_controls.items():
                enabled = cabin_states.get(key, False)
                for btn in (off_btn, on_btn):
                    btn.blockSignals(True)
                if enabled:
                    on_btn.setChecked(True)
                else:
                    off_btn.setChecked(True)
                on_btn.setStyleSheet(
                    "QPushButton {background:%s; color:#111; font-weight:700; padding:6px;}"
                    % ("#7ee093" if enabled else "#2a2a2a")
                )
                off_btn.setStyleSheet(
                    "QPushButton {background:%s; color:%s; font-weight:%s; padding:6px;}"
                    % (("#2a2a2a", "#ddd", "400") if enabled else ("#e06b6b", "#111", "700"))
                )
                for btn in (off_btn, on_btn):
                    btn.blockSignals(False)

        except Exception as exc:
            logger.exception("refresh_display failed: %s", exc)

# standalone launcher
if __name__ == "__main__":
    from train_model_backend import TrainModelBackend
    app = QApplication(sys.argv)
    backend = TrainModelBackend()
    ui = TrainModelUI(backend)
    ui.show()
    sys.exit(app.exec())
