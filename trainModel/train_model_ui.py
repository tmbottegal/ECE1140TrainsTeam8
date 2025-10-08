# train_model_ui.py
from __future__ import annotations
import os
import sys
import logging
from typing import TYPE_CHECKING, Dict

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QButtonGroup, QDialog, QLineEdit,
    QMessageBox
)

if TYPE_CHECKING:
    from train_model_backend import TrainModelBackend

# logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# beacon pop-up 
class BeaconPopup(QDialog):
    """pop-up window to view/edit beacon text"""
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


# main UI
class TrainModelUI(QWidget):
    """main Train Model dashboard"""

    def __init__(self, backend: "TrainModelBackend") -> None:
        super().__init__()
        self.backend = backend
        self.backend.add_listener(self.refresh_display)

        self.setWindowTitle("Train Model")
        self.resize(1100, 620)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)

        # left column
        left_col = QVBoxLayout()
        title = QLabel("Train Model Dashboard")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:18px; font-weight:800;")
        left_col.addWidget(title)

        # banner area with advertisement image
        banner_box = QGroupBox()
        banner_box.setTitle("Train Stats")
        banner_box.setStyleSheet("QGroupBox {font-weight:700;}")
        banner_v = QVBoxLayout(banner_box)
        self.ad_label = QLabel()
        self.ad_label.setMinimumHeight(230)
        self.ad_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ad_label.setStyleSheet("background:#1f1f1f; border:1px solid #444;")
        banner_v.addWidget(self.ad_label)

        # load ad.png
        self._ad_path = next(
            (p for p in (
                "/Users/sarakeriakes/Desktop/ECE/2025-26/1140/ECE1140TrainsTeam8/trainModel/ad.png",
                "ad.png", "./assets/ad.png", "./Assets/ad.png", "/mnt/data/ad.png"
            ) if os.path.exists(p)),
             None
        )
        if self._ad_path:
            self._set_ad_pixmap()
        left_col.addWidget(banner_box)

        # two-column grid of stat labels
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(18)
        stats_grid.setVerticalSpacing(10)
        self.stat_labels: Dict[str, QLabel] = {}

        # left column stats
        left_stats = [
            ("Engine Power (kW)", "power_kw"),
            ("Acceleration (m/s²)", "acceleration"),
            ("Velocity (m/s)", "velocity"),
            ("Passenger Count", "passenger_count"),
            ("Crew Count", "crew_count"),
            ("Vehicle Mass (kg)", "mass_kg"),
        ]
        # right column stats
        right_stats = [
            ("Train Length (m)", "length_m"),
            ("Train Width (m)", "width_m"),
            ("Commanded Speed (m/s)", "commanded_speed"),
            ("Commanded Authority (m)", "authority"),
            ("Track Segment", "track_segment"),
            ("Grade (%)", "grade"),
        ]

        def add_row(r: int, label: str, key: str, col: int) -> None:
            t = QLabel(label)
            t.setStyleSheet("font-weight:700;")
            v = QLabel("—")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.setStyleSheet("background:white; color:black; padding:6px; border:1px solid #444;")
            self.stat_labels[key] = v
            # label in col*2, value in col*2+1
            stats_grid.addWidget(t, r, col * 2)
            stats_grid.addWidget(v, r, col * 2 + 1)

        # populate grid
        for r, (label, key) in enumerate(left_stats):
            add_row(r, label, key, 0)
        for r, (label, key) in enumerate(right_stats):
            add_row(r, label, key, 1)

        left_col.addLayout(stats_grid)
        root.addLayout(left_col, 2)

        # right column
        right_col = QVBoxLayout()

        # card header: train + next stop (simple placeholders)
        header_box = QGroupBox()
        header_v = QVBoxLayout(header_box)
        self.train_lbl = QLabel("Train 1")
        self.train_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.train_lbl.setStyleSheet("font-size:16px; font-weight:800;")
        self.next_lbl = QLabel("Next Stop: Station C")
        self.next_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_lbl.setStyleSheet("font-size:14px;")
        header_v.addWidget(self.train_lbl)
        header_v.addWidget(self.next_lbl)
        right_col.addWidget(header_box)

        # failure controls
        fail_box = QGroupBox("Failure Modes")
        fail_v = QVBoxLayout(fail_box)

        def make_toggle_row(title: str, key: str):
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            disabled_btn = QPushButton("Disabled")
            enabled_btn = QPushButton("Enabled")
            for b in (disabled_btn, enabled_btn):
                b.setCheckable(True)
                b.setMinimumWidth(90)
            # style helpers
            def style_on(btn: QPushButton, green: bool):
                btn.setStyleSheet(
                    "QPushButton {background:%s; color:#111; font-weight:700; padding:6px;}"
                    % ("#7ee093" if green else "#e06b6b")
                )
            def style_off(btn: QPushButton):
                btn.setStyleSheet("QPushButton {background:#2a2a2a; color:#ddd; padding:6px;}")

            group = QButtonGroup(self)
            group.setExclusive(True)
            group.addButton(disabled_btn)
            group.addButton(enabled_btn)

            # keep references so we can sync from backend later
            self._fail_rows[key] = (disabled_btn, enabled_btn, style_on, style_off)

            # connect -> backend
            def on_clicked(btn: QPushButton):
                enabled = (btn is enabled_btn)
                # set styles
                style_on(enabled_btn, green=False) if enabled else style_off(enabled_btn)
                style_on(disabled_btn, green=True) if not enabled else style_off(disabled_btn)
                # write to backend
                mapping = {"brake": "brake", "engine": "engine", "signal": "signal"}
                self.backend.set_failure_state(mapping[key], enabled)

            disabled_btn.clicked.connect(lambda: on_clicked(disabled_btn))
            enabled_btn.clicked.connect(lambda: on_clicked(enabled_btn))

            # default UI state = disabled
            disabled_btn.setChecked(True)
            style_on(disabled_btn, green=True)
            style_off(enabled_btn)

            row.addStretch(1)
            row.addWidget(disabled_btn)
            row.addWidget(enabled_btn)
            fail_v.addLayout(row)

        self._fail_rows: Dict[str, tuple] = {}
        make_toggle_row("Brake Failure", "brake")
        make_toggle_row("Engine Failure", "engine")
        make_toggle_row("Signal Pickup Failure", "signal")
        right_col.addWidget(fail_box)

        # emergency brake
        self.ebutton = QPushButton("EMERGENCY BRAKE")
        self.ebutton.setStyleSheet("background:#d33232; color:white; font-weight:900; padding:12px;")
        self.ebutton.clicked.connect(self._activate_emergency_brake)
        right_col.addWidget(self.ebutton)

        # beacon pop-up
        beacon_btn = QPushButton("View/Edit Beacon Info")
        beacon_btn.clicked.connect(self._open_beacon_popup)
        right_col.addWidget(beacon_btn)

        right_col.addStretch(1)
        root.addLayout(right_col, 1)

        # initial paint
        self.refresh_display()

    # helpers
    def _set_ad_pixmap(self) -> None:
        if not self._ad_path:
            return
        pm = QPixmap(self._ad_path)
        if pm.isNull():
            return
        # scale to label size, keep aspect
        scaled = pm.scaled(self.ad_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self.ad_label.setPixmap(scaled)

    def resizeEvent(self, e) -> None:  # keep ad responsive
        super().resizeEvent(e)
        self._set_ad_pixmap()

    # actions
    def _activate_emergency_brake(self) -> None:
        try:
            self.backend.emergency_brake = True
            self.backend._simulate_step()
            self.backend._notify_listeners()
            QMessageBox.warning(self, "Emergency Brake", "Emergency Brake Activated!")
        except Exception as exc:
            logger.exception("Emergency brake activation failed: %s", exc)

    def _open_beacon_popup(self) -> None:
        BeaconPopup(self.backend, self).exec()

    # UI sync from backend 
    def refresh_display(self) -> None:
        """Pull a snapshot from the backend and refresh labels + toggle states."""
        try:
            s = self.backend.report_state()

            # Numbers / text
            def setv(key: str):
                val = s.get(key, "—")
                if isinstance(val, float):
                    self.stat_labels[key].setText(f"{val:.2f}")
                else:
                    self.stat_labels[key].setText(str(val))

            for k in (
                "power_kw", "acceleration", "velocity",
                "passenger_count", "crew_count", "mass_kg",
                "length_m", "width_m", "commanded_speed",
                "authority", "track_segment", "grade"
            ):
                if k in self.stat_labels:  # guard if you trimmed fields
                    setv(k)

            # sync failures without re-triggering clicks
            states = {
                "brake": bool(s.get("brake_failure", False)),
                "engine": bool(s.get("engine_failure", False)),
                "signal": bool(s.get("signal_pickup_failure", False)),
            }
            for key, enabled in states.items():
                disabled_btn, enabled_btn, style_on, style_off = self._fail_rows[key]
                # block signals so we don't send set_failure_state again
                for btn in (disabled_btn, enabled_btn):
                    btn.blockSignals(True)
                if enabled:
                    enabled_btn.setChecked(True)
                    style_on(enabled_btn, green=False)
                    style_off(disabled_btn)
                else:
                    disabled_btn.setChecked(True)
                    style_on(disabled_btn, green=True)
                    style_off(enabled_btn)
                for btn in (disabled_btn, enabled_btn):
                    btn.blockSignals(False)

        except Exception as exc:
            logger.exception("refresh_display failed: %s", exc)


# standalone test launcher
if __name__ == "__main__":
    from train_model_backend import TrainModelBackend
    app = QApplication(sys.argv)
    backend = TrainModelBackend()
    ui = TrainModelUI(backend)
    ui.show()
    sys.exit(app.exec())
