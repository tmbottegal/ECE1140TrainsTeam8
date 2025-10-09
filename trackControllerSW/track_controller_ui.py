"""Track Controller user interface.

Provides the PyQt-based front-end for monitoring and controlling
the Track Controller system. Supports:
- Viewing block, switch, crossing, and signal states
- Uploading PLC files
- Manual override testing interface

Refactored per Google Python Style Guide:
- Docstrings and type hints
- Logging instead of print statements
- Consistent formatting
"""

from __future__ import annotations

import logging
import copy
from typing import TYPE_CHECKING
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

if TYPE_CHECKING:
    from track_controller_backend import TrackNetwork, TrackControllerBackend

# Configure module-level logger.
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ManualOverrideDialog(QDialog):
    """Modeless dialog for manual backend control during testing."""

    applied = pyqtSignal()

    def __init__(self, parent_ui: TrackControllerUI) -> None:
        """Initialize the manual override dialog."""
        super().__init__(parent=parent_ui)
        self.ui = parent_ui
        self.setWindowTitle("Test UI")
        self.setModal(False)
        self.resize(420, 380)

        self._build_ui()
        self._connect_signals()

        # 🆕 Save original backend state for cancel restore
        self.original_state = copy.deepcopy(self.ui.backend.report_state())

    def _build_ui(self) -> None:
        """Construct dialog layout."""
        form = QFormLayout(self)

        # Block controls
        self.block_spin = QSpinBox()
        self.block_spin.setMinimum(1)
        self.block_spin.setMaximum(self.ui.backend.num_blocks)
        form.addRow("Block #", self.block_spin)

        self.occ_combo = QComboBox()
        self.occ_combo.addItems(["No", "Yes"])
        form.addRow("Occupancy", self.occ_combo)

        # Broken rail control
        self.broken_combo = QComboBox()
        self.broken_combo.addItems(["No", "Yes"])
        form.addRow("Broken Rail", self.broken_combo)

        # Switch controls
        self.switch_combo = QComboBox()
        switch_ids = sorted(self.ui.backend.switches.keys())
        if not switch_ids:
            self.switch_combo.addItem("None")
            self.switch_combo.setEnabled(False)
        else:
            for sid in switch_ids:
                self.switch_combo.addItem(str(sid))
        form.addRow("Switch ID", self.switch_combo)

        self.switch_pos_combo = QComboBox()
        self.switch_pos_combo.addItems(["Normal", "Alternate"])
        form.addRow("Switch Position", self.switch_pos_combo)

        # Crossing controls
        self.crossing_combo = QComboBox()
        crossing_ids = sorted(self.ui.backend.crossings.keys())
        if not crossing_ids:
            self.crossing_combo.addItem("None")
            self.crossing_combo.setEnabled(False)
        else:
            for cid in crossing_ids:
                self.crossing_combo.addItem(str(cid))
        form.addRow("Crossing ID", self.crossing_combo)

        self.crossing_status_combo = QComboBox()
        self.crossing_status_combo.addItems(["Inactive", "Active"])
        form.addRow("Crossing Status", self.crossing_status_combo)

        # Signal controls
        self.signal_combo = QComboBox()
        self.signal_combo.addItems(["Red", "Yellow", "Green", "Super Green"])
        form.addRow("Signal Color", self.signal_combo)

        # Commanded speed
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(0, 120)  # adjust max speed if needed
        form.addRow("Commanded Speed", self.speed_spin)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Apply")
        apply_btn = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_btn.clicked.connect(self._apply)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _connect_signals(self) -> None:
        """Connect dialog widgets to backend updates."""
        try:
            self.block_spin.valueChanged.connect(self.refresh_from_backend)
            self.occ_combo.currentTextChanged.connect(self._on_occupancy_changed)
            self.broken_combo.currentTextChanged.connect(self._on_broken_changed)
            self.switch_combo.currentTextChanged.connect(
                self._on_switch_selection_changed
            )
            self.switch_pos_combo.currentTextChanged.connect(
                self._on_switch_position_changed
            )
            self.crossing_combo.currentTextChanged.connect(
                self._on_crossing_selection_changed
            )
            self.crossing_status_combo.currentTextChanged.connect(
                self._on_crossing_status_changed
            )
            self.signal_combo.currentTextChanged.connect(self._on_signal_changed)
            self.speed_spin.valueChanged.connect(self._on_speed_changed)
        except Exception:
            logger.exception("Failed to connect manual override handlers.")

    def refresh_from_backend(self) -> None:
        """Update dialog fields from backend state."""
        try:
            b = self.block_spin.value()
            self.occ_combo.setCurrentText(
                "Yes" if self.ui.backend.blocks[b]["occupied"] else "No"
            )
            self.broken_combo.setCurrentText(
                "Yes" if self.ui.backend.blocks[b]["broken"] else "No"
            )
            self.signal_combo.setCurrentText(
                self.ui.backend.blocks[b].get("signal", "Green")
            )
            self.speed_spin.setValue(self.ui.backend.blocks[b]["commanded_speed"])
        except Exception:
            logger.debug("Failed to refresh block or signal state.")

    def reject(self) -> None:
        """Revert backend to its original state when closing without applying."""
        try:
            # Restore block states
            for b, data in self.original_state["blocks"].items():
                block = self.ui.backend.blocks[b]
                block.update({
                    "occupied": data["occupied"],
                    "broken": data["broken"],
                    "suggested_speed": data["suggested_speed"],
                    "commanded_speed": data["commanded_speed"],
                    "suggested_auth": data["suggested_auth"],
                    "commanded_auth": data["commanded_auth"],
                    "signal": data["signal"],
                })

            # Restore switches
            self.ui.backend.switches = self.original_state["switches"].copy()
            self.ui.backend.switch_map = self.original_state["switch_map"].copy()

            # Restore crossings
            self.ui.backend.crossings = {
                cid: info["status"]
                for cid, info in self.original_state["crossings"].items()
            }
            self.ui.backend.crossing_blocks = {
                cid: info["block"]
                for cid, info in self.original_state["crossings"].items()
            }

            # Notify listeners and refresh UI
            self.ui.backend._notify_listeners()
            self.ui.refresh_tables()
            logger.info("Manual Override cancelled — backend reverted.")
        except Exception:
            logger.exception("Failed to revert backend on cancel.")

        super().reject()

    # Handlers for live changes
    def _on_occupancy_changed(self, text: str) -> None:
        try:
            block = self.block_spin.value()
            occ = text == "Yes"
            self.ui.backend.set_block_occupancy(block, occ)
            self.applied.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Occupancy Failed", str(exc))

    def _on_broken_changed(self, text: str) -> None:
        try:
            block = self.block_spin.value()
            if text == "Yes":
                self.ui.backend.break_rail(block)
            else:
                self.ui.backend.repair_rail(block)
            self.applied.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Broken Rail Failed", str(exc))
            self.refresh_from_backend()

    def _on_switch_selection_changed(self, sid_text: str) -> None:
        try:
            sid = int(sid_text)
            pos = self.ui.backend.switches.get(sid, "Normal")
            self.switch_pos_combo.blockSignals(True)
            self.switch_pos_combo.setCurrentText(pos)
            self.switch_pos_combo.blockSignals(False)
        except Exception:
            logger.debug("Switch selection change ignored.")

    def _on_switch_position_changed(self, pos_text: str) -> None:
        if not self.switch_combo.isEnabled():
            return
        try:
            sid = int(self.switch_combo.currentText())
            self.ui.backend.safe_set_switch(sid, pos_text)
            self.applied.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Switch Failed", str(exc))
            self.refresh_from_backend()

    def _on_crossing_selection_changed(self, cid_text: str) -> None:
        try:
            cid = int(cid_text)
            status = self.ui.backend.crossings.get(cid, "Inactive")
            self.crossing_status_combo.blockSignals(True)
            self.crossing_status_combo.setCurrentText(status)
            self.crossing_status_combo.blockSignals(False)
        except Exception:
            logger.debug("Crossing selection change ignored.")

    def _on_crossing_status_changed(self, status_text: str) -> None:
        if not self.crossing_combo.isEnabled():
            return
        try:
            cid = int(self.crossing_combo.currentText())
            self.ui.backend.safe_set_crossing(cid, status_text)
            self.applied.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Crossing Failed", str(exc))
            self.refresh_from_backend()

    def _on_signal_changed(self, color_text: str) -> None:
        try:
            block = self.block_spin.value()
            self.ui.backend.set_signal(block, color_text)
            self.applied.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Signal Failed", str(exc))
            self.refresh_from_backend()

    def _on_speed_changed(self, val: int) -> None:
        try:
            block = self.block_spin.value()
            self.ui.backend.set_commanded_speed(block, val)
            self.applied.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Speed Failed", str(exc))
            self.refresh_from_backend()

    def _apply(self) -> None:
        """Apply changes to backend and close if successful."""
        errors: list[str] = []
        block = self.block_spin.value()

        try:
            # Apply values from UI to backend
            self.ui.backend.set_signal(block, self.signal_combo.currentText())
            self.ui.backend.set_commanded_speed(block, self.speed_spin.value())

        except Exception as e:
            errors.append(str(e))

        QApplication.processEvents()
        self.applied.emit()

        if errors:
            QMessageBox.warning(self, "Test UI: Error", "\n".join(errors))
        else:
            QMessageBox.information(self, "Test UI", "Changes applied.")
            self.accept()


class TrackControllerUI(QWidget):
    """Main application window for the Track Controller module."""

    def __init__(self, network: TrackNetwork, parent: QWidget | None = None) -> None:
        """Initialize the Track Controller UI."""
        super().__init__(parent)
        self.network = network
        self.backend = network.get_line("Blue Line")

        try:
            self.backend.add_listener(self.refresh_tables)
        except Exception:
            logger.exception("Failed to attach refresh listener to backend.")

        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the main layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Track selector row
        top_row = QHBoxLayout()
        self.dropdown_text = QLabel("Track: Blue Line")
        font_title = QFont()
        font_title.setPointSize(16)
        font_title.setBold(True)
        self.dropdown_text.setFont(font_title)
        top_row.addWidget(self.dropdown_text)
        top_row.addStretch()

        self.track_picker = QComboBox()
        self.track_picker.addItems(["Blue Line", "Red Line", "Green Line"])
        self.track_picker.setCurrentIndex(0)
        self.track_picker.setFixedHeight(32)
        self.track_picker.setFixedWidth(160)
        font_drop = QFont()
        font_drop.setPointSize(14)
        self.track_picker.setFont(font_drop)
        self.track_picker.currentTextChanged.connect(self.switch_line)
        top_row.addWidget(self.track_picker)
        layout.addLayout(top_row)

        # Scroll area for tables
        self.table_hud = QScrollArea()
        self.table_hud.setWidgetResizable(True)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)

        # Add data tables
        self._add_table("Blocks", "tablemain")
        self._add_table("Switches", "tableswitch")
        self._add_table("Crossings", "tablecrossing")
        self._add_table("Broken Rails", "tablebroken")
        self._add_table("Signals", "tablesignal")

        self.table_hud.setWidget(self.container)
        layout.addWidget(self.table_hud)

        # Bottom control row
        bottom_row = QHBoxLayout()
        self.plc_button = QPushButton("PLC File Upload")
        bigboi = self.plc_button.sizeHint()
        self.plc_button.setFixedSize(bigboi.width() * 2, bigboi.height() * 2)
        bottom_row.addWidget(self.plc_button)

        self.filename_box = QLineEdit("File: None")
        self.filename_box.setReadOnly(True)
        self.filename_box.setFixedWidth(800)
        font_text = QFont()
        font_text.setPointSize(14)
        self.filename_box.setFont(font_text)
        self.filename_box.setFixedHeight(bigboi.height() * 2)
        bottom_row.addWidget(self.filename_box)
        bottom_row.addStretch()

        self.manual_button = QPushButton("Test UI")
        self.manual_button.clicked.connect(self.open_manual_override)
        self.manual_button.setFixedHeight(bigboi.height() * 2)
        bottom_row.addWidget(self.manual_button)
        layout.addLayout(bottom_row)

    def _add_table(self, label_text: str, attr_name: str) -> None:
        """Add a labeled QTableWidget to the container layout."""
        self.container_layout.addWidget(QLabel(label_text))
        table = QTableWidget()
        setattr(self, attr_name, table)
        self.container_layout.addWidget(table)

    def switch_line(self, line_name: str) -> None:
        """Switch the UI to a different track line."""
        self.dropdown_text.setText(f"Track: {line_name}")
        try:
            self.backend.remove_listener(self.refresh_tables)
        except Exception:
            logger.debug("No previous listener to remove.")

        self.backend = self.network.get_line(line_name)
        try:
            self.backend.add_listener(self.refresh_tables)
        except Exception:
            logger.exception("Failed to add listener for new line.")
        self.refresh_tables()

    def open_manual_override(self) -> None:
        """Open the manual override dialog."""
        dlg = ManualOverrideDialog(self)
        dlg.refresh_from_backend()
        dlg.applied.connect(self.refresh_tables)
        dlg.show()

    def refresh_tables(self) -> None:
        """Refresh all table data from backend."""
        try:
            # Blocks table
            self.tablemain.setRowCount(self.backend.num_blocks)
            self.tablemain.setColumnCount(6)
            self.tablemain.setHorizontalHeaderLabels([
                "Block", "Suggested Speed (mph)", "Commanded Speed (mph)", "Occupancy",
                "Suggested Authority (miles)", "Commanded Authority (miles)"
            ])
            self.tablemain.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch)
            self.tablemain.verticalHeader().setVisible(False)

            for i, (block, data) in enumerate(self.backend.blocks.items()):
                self.tablemain.setItem(i, 0, QTableWidgetItem(str(block)))
                self.tablemain.setItem(i, 1, QTableWidgetItem(
                    str(data["suggested_speed"])))
                self.tablemain.setItem(i, 2, QTableWidgetItem(
                    str(data["commanded_speed"])))
                self.tablemain.setItem(i, 3, QTableWidgetItem(
                    "Yes" if data["occupied"] else "No"))
                self.tablemain.setItem(i, 4, QTableWidgetItem(
                    str(data["suggested_auth"])))
                self.tablemain.setItem(i, 5, QTableWidgetItem(
                    str(data["commanded_auth"])))

            # Switches
            self.tableswitch.setRowCount(len(self.backend.switches))
            self.tableswitch.setColumnCount(3)
            self.tableswitch.setHorizontalHeaderLabels(
                ["Switch ID", "Blocks", "Position"])
            self.tableswitch.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch)
            for i, (sid, pos) in enumerate(self.backend.switches.items()):
                self.tableswitch.setItem(i, 0, QTableWidgetItem(str(sid)))
                blocks = self.backend.switch_map.get(sid, ())
                self.tableswitch.setItem(i, 1, QTableWidgetItem(str(blocks)))
                self.tableswitch.setItem(i, 2, QTableWidgetItem(pos))

            # Crossings
            self.tablecrossing.setRowCount(len(self.backend.crossings))
            self.tablecrossing.setColumnCount(3)
            self.tablecrossing.setHorizontalHeaderLabels(
                ["Crossing ID", "Block", "Status"])
            self.tablecrossing.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch)
            for i, (cid, status) in enumerate(self.backend.crossings.items()):
                block = self.backend.crossing_blocks.get(cid, "-")
                self.tablecrossing.setItem(i, 0, QTableWidgetItem(str(cid)))
                self.tablecrossing.setItem(i, 1, QTableWidgetItem(str(block)))
                self.tablecrossing.setItem(i, 2, QTableWidgetItem(status))

            # Broken rails
            broken_blocks = [
                b for b, d in self.backend.blocks.items() if d["broken"]
            ]
            self.tablebroken.setRowCount(len(broken_blocks))
            self.tablebroken.setColumnCount(2)
            self.tablebroken.setHorizontalHeaderLabels(["Block", "Status"])
            self.tablebroken.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch)
            for i, b in enumerate(broken_blocks):
                self.tablebroken.setItem(i, 0, QTableWidgetItem(str(b)))
                self.tablebroken.setItem(i, 1, QTableWidgetItem("Broken"))

            # Signals
            self.tablesignal.setRowCount(self.backend.num_blocks)
            self.tablesignal.setColumnCount(2)
            self.tablesignal.setHorizontalHeaderLabels(["Block", "Signal"])
            self.tablesignal.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch)
            for i, (block, data) in enumerate(self.backend.blocks.items()):
                self.tablesignal.setItem(i, 0, QTableWidgetItem(str(block)))
                sig = data.get("signal", "Green")
                item = QTableWidgetItem(sig)

                # Apply background color
                if sig == "Red":
                    item.setBackground(Qt.GlobalColor.red)
                    item.setForeground(Qt.GlobalColor.black)
                elif sig == "Yellow":
                    item.setBackground(Qt.GlobalColor.yellow)
                    item.setForeground(Qt.GlobalColor.black)
                elif sig == "Green":
                    item.setBackground(Qt.GlobalColor.green)
                    item.setForeground(Qt.GlobalColor.black)
                elif sig == "Super Green":
                    item.setBackground(Qt.GlobalColor.cyan)
                    item.setForeground(Qt.GlobalColor.black)

                self.tablesignal.setItem(i, 1, item)
        except Exception:
            logger.exception("Failed to refresh tables.")

