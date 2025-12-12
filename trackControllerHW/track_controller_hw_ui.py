"""Hardware Track Controller UI.

PyQt6-based user interface for the hardware wayside controller.
"""
from __future__ import annotations

import logging
import os
import signal
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trackModel.track_model_backend import TrackNetwork

try:
    from track_controller_hw_backend import (
        HardwareTrackControllerBackend,
        TrackModelAdapter,
        SignalState,
        HW_CONTROLLED_BLOCK_MAP,
        HW_VIEW_ONLY_BLOCK_MAP,
    )
except ModuleNotFoundError:
    from trackControllerHW.track_controller_hw_backend import (
        HardwareTrackControllerBackend,
        TrackModelAdapter,
        SignalState,
        HW_CONTROLLED_BLOCK_MAP,
        HW_VIEW_ONLY_BLOCK_MAP,
    )

RED = SignalState.RED
YELLOW = SignalState.YELLOW
GREEN = SignalState.GREEN

from universal.global_clock import clock as global_clock

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QHeaderView,
    QMessageBox,
    QSplitter,
    QSizePolicy,
    QApplication,
    QAbstractItemView,
    QLineEdit,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)
if not logger.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(h)


class TrackControllerHWUI(QWidget):
    """Main UI widget for hardware track controller."""

    def __init__(
        self,
        controllers: dict[str, HardwareTrackControllerBackend],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controllers = controllers
        self.backend = next(iter(self.controllers.values()))
        self.maintenance_enabled = False
        self.current_plc_path = "None"

        self._refresh_pending = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_deferred_refresh)

        for c in self.controllers.values():
            try:
                c.add_listener(self._request_refresh)
            except Exception:
                logger.exception("Failed attaching listener to backend")

        self._apply_stylesheet()
        self._build_ui()
        self._wire_signals()

        self._hb_timer = QTimer(self)
        self._hb_timer.timeout.connect(self.refresh_all)
        self._hb_timer.start(1000)

        self.btn_plc.setEnabled(False)
        self.refresh_all()

        try:
            global_clock.register_listener(self._update_clock_display)
            self._update_clock_display(global_clock.get_time())
        except Exception:
            logger.exception("Failed to hook HW UI into global clock")

    def _request_refresh(self) -> None:
        """Request a debounced refresh."""
        if not self._refresh_pending:
            self._refresh_pending = True
            self._refresh_timer.start(50)

    def _do_deferred_refresh(self) -> None:
        """Execute the deferred refresh."""
        self._refresh_pending = False
        self.refresh_all()

    def _apply_stylesheet(self) -> None:
        """Apply the UI stylesheet."""
        self.setStyleSheet("""
            QWidget {
                background-color: #f8fafc;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                    Roboto, sans-serif;
                font-size: 13px;
                color: #1e293b;
            }
            QLabel { color: #475569; font-weight: 500; }
            QComboBox {
                padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px;
                background-color: white; min-height: 20px;
            }
            QComboBox:hover { border-color: #94a3b8; }
            QComboBox::drop-down { border: none; width: 20px; }
            QPushButton {
                padding: 8px 16px; border: 1px solid #cbd5e1; border-radius: 6px;
                background-color: white; color: #1e293b; font-weight: 500;
                min-height: 20px;
            }
            QPushButton:hover { background-color: #f1f5f9; border-color: #94a3b8; }
            QPushButton:pressed { background-color: #e2e8f0; }
            QPushButton:checked {
                background-color: #3b82f6; color: white; border-color: #2563eb;
            }
            QPushButton:checked:hover { background-color: #2563eb; }
            QLineEdit {
                padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px;
                background-color: white; color: #64748b;
            }
            QLineEdit:focus { border-color: #3b82f6; outline: none; }
            QTabWidget::pane {
                border: 1px solid #e2e8f0; border-radius: 8px;
                background-color: white; top: -1px;
            }
            QTabBar::tab {
                padding: 10px 20px; margin-right: 2px; border: 1px solid #e2e8f0;
                border-bottom: none; border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                background-color: #f1f5f9; color: #64748b;
            }
            QTabBar::tab:selected {
                background-color: white; color: #1e293b; font-weight: 500;
            }
            QTabBar::tab:hover:!selected { background-color: #e2e8f0; }
            QTableWidget {
                border: none; gridline-color: #f1f5f9;
                selection-background-color: #dbeafe; background-color: transparent;
            }
            QHeaderView::section {
                background-color: #f8fafc; padding: 10px; border: none;
                border-bottom: 2px solid #e2e8f0; font-weight: 600;
                color: #475569; text-align: left;
            }
            QSplitter::handle { background-color: #e2e8f0; width: 1px; }
        """)

    def _build_ui(self) -> None:
        """Build the UI layout."""
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QWidget()
        sidebar.setStyleSheet(
            "QWidget { background-color: white; border-right: 1px solid #e2e8f0; }"
        )
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(20, 20, 20, 20)
        side_layout.setSpacing(16)

        side_layout.addWidget(QLabel("Line:"))
        self.line_picker = QComboBox()
        self.line_picker.addItems(list(self.controllers.keys()))
        self.line_picker.setCurrentText(self.backend.line_name)
        self.line_picker.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        side_layout.addWidget(self.line_picker)
        side_layout.addSpacing(8)

        self.btn_maint = QPushButton("Maintenance Mode")
        self.btn_maint.setCheckable(True)
        side_layout.addWidget(self.btn_maint)

        self.btn_clear_faults = QPushButton("Clear Failures")
        self.btn_clear_faults.setToolTip(
            "Clear all active failure flags (maintenance mode only)"
        )
        side_layout.addWidget(self.btn_clear_faults)
        side_layout.addStretch(1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(16)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)
        self.clock_label = QLabel("Time: --")
        self.clock_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        top_bar.addStretch(1)
        top_bar.addWidget(self.clock_label)
        content_layout.addLayout(top_bar)

        plc_container = QWidget()
        plc_container.setStyleSheet(
            "QWidget { background-color: white; border: 1px solid #e2e8f0; "
            "border-radius: 8px; }"
        )
        plc_layout = QHBoxLayout(plc_container)
        plc_layout.setContentsMargins(16, 12, 16, 12)
        plc_layout.setSpacing(12)

        plc_label = QLabel("PLC File:")
        plc_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.plc_edit = QLineEdit()
        self.plc_edit.setPlaceholderText("No file selected")
        self.plc_edit.setReadOnly(True)
        self.plc_edit.setMinimumWidth(300)
        self.btn_plc = QPushButton("Browse")
        self.btn_plc.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_plc.setFixedWidth(100)

        plc_layout.addWidget(plc_label)
        plc_layout.addWidget(self.plc_edit, 1)
        plc_layout.addWidget(self.btn_plc)
        content_layout.addWidget(plc_container)

        self.tabs = QTabWidget()
        content_layout.addWidget(self.tabs)

        self.tbl_blocks = QTableWidget()
        self.tbl_blocks.setColumnCount(6)
        self.tbl_blocks.setHorizontalHeaderLabels([
            "Block",
            "Occupancy",
            "Suggested Speed (mph)",
            "Suggested Authority (yd)",
            "Commanded Speed (mph)",
            "Commanded Authority (yd)",
        ])
        self.tbl_blocks.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tbl_blocks.verticalHeader().setVisible(False)
        self.tbl_blocks.setAlternatingRowColors(False)
        self.tabs.addTab(self.tbl_blocks, "Blocks")

        self.tbl_switch = QTableWidget()
        self.tbl_switch.setColumnCount(5)
        self.tbl_switch.setHorizontalHeaderLabels([
            "Block",
            "Position",
            "Previous Signal",
            "Straight Signal",
            "Diverging Signal",
        ])
        self.tbl_switch.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tbl_switch.verticalHeader().setVisible(False)
        self.tabs.addTab(self.tbl_switch, "Switches")

        self.tbl_cross = QTableWidget()
        self.tbl_cross.setColumnCount(3)
        self.tbl_cross.setHorizontalHeaderLabels(["Crossing ID", "Block", "Status"])
        self.tbl_cross.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tbl_cross.verticalHeader().setVisible(False)
        self.tabs.addTab(self.tbl_cross, "Crossings")

        self.tbl_diag = QTableWidget()
        self.tbl_diag.setColumnCount(4)
        self.tbl_diag.setHorizontalHeaderLabels(["Type", "Block", "Time", "Details"])
        self.tbl_diag.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tbl_diag.verticalHeader().setVisible(False)
        self.diag_tab_index = self.tabs.addTab(self.tbl_diag, "Diagnostics")

        self._apply_edit_triggers()

        splitter = QSplitter()
        splitter.addWidget(sidebar)
        splitter.addWidget(content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 1350])
        root.addWidget(splitter)

    def _wire_signals(self) -> None:
        """Connect UI signals to handlers."""
        self.line_picker.currentTextChanged.connect(self._on_line_changed)
        self.btn_maint.toggled.connect(self._on_toggle_maintenance)
        self.btn_plc.clicked.connect(self._on_upload_plc)
        self.tbl_switch.cellClicked.connect(self._on_switch_click)
        self.tbl_cross.cellClicked.connect(self._on_crossing_click)
        self.tbl_blocks.cellChanged.connect(self._on_blocks_cell_changed)
        self.tbl_blocks.itemChanged.connect(self._pause_refresh_on_edit)
        self.btn_clear_faults.clicked.connect(self._on_clear_failures_clicked)

    def _pause_refresh_on_edit(self, item) -> None:
        """Pause refresh while editing."""
        if (
            self.maintenance_enabled
            and item
            and (item.flags() & Qt.ItemFlag.ItemIsEditable)
        ):
            self._hb_timer.stop()
            QTimer.singleShot(2000, lambda: self._hb_timer.start(1000))

    def _update_clock_display(self, current_time) -> None:
        """Update the clock display."""
        try:
            self.clock_label.setText(
                f"Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            for controller in self.controllers.values():
                if hasattr(controller, "set_time"):
                    try:
                        controller.set_time(current_time)
                    except Exception:
                        pass
        except Exception:
            logger.exception("Failed to update clock display (HW)")

    def _get_view_only_blocks(self) -> list[int]:
        """Get the list of view-only blocks for current line."""
        return HW_VIEW_ONLY_BLOCK_MAP.get(self.backend.line_name, [])

    def _get_controlled_blocks(self) -> list[int]:
        """Get the list of controlled blocks for current line."""
        return list(HW_CONTROLLED_BLOCK_MAP.get(self.backend.line_name, []))

    def _on_line_changed(self, name: str) -> None:
        """Handle line selection change."""
        try:
            self.backend = self.controllers[name]
        except Exception as exc:
            QMessageBox.warning(self, "Switch Line Failed", str(exc))
        finally:
            self._apply_edit_triggers()
            self.refresh_all()

    def _on_toggle_maintenance(self, enabled: bool) -> None:
        """Handle maintenance mode toggle."""
        self.maintenance_enabled = enabled
        self.btn_plc.setEnabled(enabled)
        self._apply_edit_triggers()
        for c in self.controllers.values():
            try:
                c.set_maintenance_mode(enabled)
            except Exception:
                logger.exception("Maintenance toggle failed on a controller")
        self.refresh_all()

    def _on_upload_plc(self) -> None:
        """Handle PLC upload button click."""
        try:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select PLC File",
                "",
                "PLC Files (*.txt *.plc *.py);;All Files (*)",
            )
            if not path:
                return
            self.current_plc_path = path
            self.plc_edit.setText(path)

            self._hb_timer.stop()
            QApplication.processEvents()

            self.backend.upload_plc(path)

            QTimer.singleShot(500, lambda: self._hb_timer.start(1000))
            self.refresh_all()
        except Exception as exc:
            self._hb_timer.start(1000)
            QMessageBox.warning(self, "PLC Upload Failed", str(exc))

    def _on_switch_click(self, row: int, col: int) -> None:
        """Handle switch table cell click."""
        if col != 1 or not self.maintenance_enabled:
            return
        try:
            sid_item = self.tbl_switch.item(row, 0)
            pos_item = self.tbl_switch.item(row, 1)
            if not sid_item or not pos_item:
                return
            sid = int(sid_item.text())
            current = (pos_item.text() or "Straight").strip().lower()
            next_pos = "Diverging" if current == "straight" else "Straight"
            self.backend.safe_set_switch(sid, next_pos)
        except Exception as exc:
            QMessageBox.warning(self, "Switch Change Failed", str(exc))
        finally:
            self.refresh_all()

    def _on_crossing_click(self, row: int, col: int) -> None:
        """Handle crossing table cell click."""
        if col != 2 or not self.maintenance_enabled:
            return
        try:
            cid_item = self.tbl_cross.item(row, 0)
            stat_item = self.tbl_cross.item(row, 2)
            if not cid_item or not stat_item:
                return
            cid = int(cid_item.text())
            current = (stat_item.text() or "Inactive").strip()
            next_status = "Inactive" if current == "Active" else "Active"
            self.backend.safe_set_crossing(cid, next_status)
        except Exception as exc:
            QMessageBox.warning(self, "Crossing Change Failed", str(exc))
        finally:
            self.refresh_all()

    def _on_clear_failures_clicked(self) -> None:
        """Handle clear failures button click."""
        try:
            if not self.maintenance_enabled:
                QMessageBox.information(
                    self,
                    "Maintenance Required",
                    "Enable Maintenance Mode before clearing failures.",
                )
                return
            self.backend.clear_failures()
            self.refresh_all()
        except PermissionError as exc:
            QMessageBox.warning(self, "Clear Failures Failed", str(exc))
        except Exception:
            logger.exception("Clear failures handler crashed")
            QMessageBox.warning(
                self, "Clear Failures Failed", "Unable to clear failures."
            )

    def refresh_all(self) -> None:
        """Refresh all UI elements."""
        try:
            if hasattr(self.backend, "sync_from_track_model"):
                self.backend.sync_from_track_model()

            self._refresh_blocks()
            self._refresh_switches()
            self._refresh_crossings()
            self._refresh_diagnostics()
        except KeyboardInterrupt:
            return
        except Exception:
            logger.exception("Refresh failed")

    def _refresh_blocks(self) -> None:
        """Refresh blocks table."""
        if self.tbl_blocks.state() == QAbstractItemView.State.EditingState:
            return

        ids = self.backend.get_line_block_ids()
        if not ids:
            line_defaults = {
                "Blue Line": range(1, 16),
                "Red Line": range(74, 151),
                "Green Line": range(1, 151),
            }
            ids = list(line_defaults.get(self.backend.line_name, []))

        data = self.backend.blocks
        view_only_blocks = self._get_view_only_blocks()

        self.tbl_blocks.blockSignals(True)
        try:
            self.tbl_blocks.setRowCount(len(ids))
            for r, b in enumerate(ids):
                is_view_only = b in view_only_blocks

                self._set_item(self.tbl_blocks, r, 0, str(b), editable=False)

                if is_view_only:
                    for col in range(6):
                        if item := self.tbl_blocks.item(r, col):
                            item.setBackground(QColor("#e5e7eb"))
                            item.setForeground(QColor("#6b7280"))

                occ = data.get(b, {}).get("occupied", "N/A")
                occ_text = (
                    "N/A"
                    if occ == "N/A"
                    else ("OCCUPIED" if occ else "UNOCCUPIED")
                )
                self._set_item(self.tbl_blocks, r, 1, occ_text, editable=False)
                if item := self.tbl_blocks.item(r, 1):
                    if is_view_only:
                        item.setBackground(QColor("#e5e7eb"))
                        item.setForeground(QColor("#6b7280"))
                    else:
                        color = (
                            "#22c55e"
                            if occ_text == "OCCUPIED"
                            else "#ef4444"
                            if occ_text == "UNOCCUPIED"
                            else "#ffffff"
                        )
                        item.setBackground(QColor(color))
                        item.setForeground(QColor("#000000"))

                sug_spd = data.get(b, {}).get("suggested_speed", "N/A")
                self._set_item(self.tbl_blocks, r, 2, str(sug_spd), editable=False)

                sug_auth = data.get(b, {}).get("suggested_auth", "N/A")
                self._set_item(self.tbl_blocks, r, 3, str(sug_auth), editable=False)

                cmd_spd = data.get(b, {}).get("commanded_speed", "N/A")
                can_edit = self.maintenance_enabled and not is_view_only
                self._set_item(self.tbl_blocks, r, 4, str(cmd_spd), editable=can_edit)

                cmd_auth = data.get(b, {}).get("commanded_auth", "N/A")
                self._set_item(self.tbl_blocks, r, 5, str(cmd_auth), editable=can_edit)

                if is_view_only:
                    for col in range(6):
                        if item := self.tbl_blocks.item(r, col):
                            item.setBackground(QColor("#e5e7eb"))
                            item.setForeground(QColor("#6b7280"))

            self.tbl_blocks.resizeRowsToContents()
        finally:
            self.tbl_blocks.blockSignals(False)

    def _refresh_crossings(self) -> None:
        """Refresh crossings table."""
        crosses = self.backend.crossings
        cross_blocks = self.backend.crossing_blocks

        if not crosses and not cross_blocks:
            defaults = {
                "Blue Line": (1, 9),
                "Red Line": (1, 47),
                "Green Line": (1, 108),
            }
            if default := defaults.get(self.backend.line_name):
                cross_blocks[default[0]] = default[1]
            for cid in cross_blocks:
                crosses[cid] = "N/A"

        self.tbl_cross.blockSignals(True)
        try:
            self.tbl_cross.setRowCount(max(len(crosses), 1))
            if not crosses:
                for c in range(3):
                    self._set_item(self.tbl_cross, 0, c, "", editable=False)
            else:
                for r, (cid, status) in enumerate(sorted(crosses.items())):
                    self._set_item(self.tbl_cross, r, 0, str(cid), editable=False)
                    self._set_item(
                        self.tbl_cross,
                        r,
                        1,
                        str(cross_blocks.get(cid, "-")),
                        editable=False,
                    )
                    self._set_item(
                        self.tbl_cross,
                        r,
                        2,
                        status,
                        editable=self.maintenance_enabled,
                    )
            self.tbl_cross.resizeRowsToContents()
        finally:
            self.tbl_cross.blockSignals(False)

    def _refresh_switches(self) -> None:
        """Refresh switches table."""
        switches = self.backend.switches

        if switches:
            self.tbl_switch.setRowCount(len(switches))
            self.tbl_switch.setColumnCount(5)
            self.tbl_switch.setHorizontalHeaderLabels([
                "Block",
                "Position",
                "Prev Signal",
                "Straight Signal",
                "Diverging Signal",
            ])
            self.tbl_switch.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )
            self.tbl_switch.verticalHeader().setVisible(False)

            for i, (sid, pos) in enumerate(switches.items()):
                self.tbl_switch.setItem(i, 0, QTableWidgetItem(str(sid)))

                if isinstance(pos, int):
                    pos_text = "Straight" if pos == 0 else "Diverging"
                else:
                    pos_text = (
                        "Straight"
                        if pos in ("Straight", "Normal", 0)
                        else "Diverging"
                    )
                item = QTableWidgetItem(pos_text)
                self._apply_editable(item, editable=self.maintenance_enabled)
                self.tbl_switch.setItem(i, 1, item)

                switch_signals = getattr(self.backend, "_switch_signals", {})

                prev_sig = switch_signals.get((sid, 0), "N/A")
                prev_item = self._create_signal_item(prev_sig)
                self.tbl_switch.setItem(i, 2, prev_item)

                straight_sig = switch_signals.get((sid, 1), "N/A")
                straight_item = self._create_signal_item(straight_sig)
                self.tbl_switch.setItem(i, 3, straight_item)

                diverging_sig = switch_signals.get((sid, 2), "N/A")
                diverging_item = self._create_signal_item(diverging_sig)
                self.tbl_switch.setItem(i, 4, diverging_item)
        else:
            self.tbl_switch.setRowCount(1)
            self.tbl_switch.setColumnCount(5)
            self.tbl_switch.setHorizontalHeaderLabels([
                "Block",
                "Position",
                "Prev Signal",
                "Straight Signal",
                "Diverging Signal",
            ])
            for col in range(5):
                self.tbl_switch.setItem(0, col, QTableWidgetItem("No switches"))

    def _create_signal_item(self, signal_state) -> QTableWidgetItem:
        """Create a table item for a signal state."""
        if hasattr(signal_state, "name"):
            sig_name = signal_state.name
        elif isinstance(signal_state, str) and signal_state != "N/A":
            sig_name = signal_state.split(".")[-1]
        else:
            sig_name = signal_state

        if sig_name == "N/A":
            item = QTableWidgetItem("N/A")
        else:
            text = str(sig_name).upper()
            item = QTableWidgetItem(text)
            try:
                enum_state = SignalState[text]
                self._color_signal_item_by_state(item, enum_state)
            except KeyError:
                pass

        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _color_signal_item_by_state(
        self, item: QTableWidgetItem, sig: SignalState
    ) -> None:
        """Apply color styling to a signal item."""
        if sig == RED:
            item.setBackground(QColor("#ef4444"))
            item.setForeground(QColor("#000000"))
        elif sig == YELLOW:
            item.setBackground(QColor("#eab308"))
            item.setForeground(QColor("#000000"))
        elif sig == GREEN:
            item.setBackground(QColor("#22c55e"))
            item.setForeground(QColor("#000000"))

    def _apply_editable(
        self, item: QTableWidgetItem, editable: bool = False
    ) -> QTableWidgetItem:
        """Apply editable flag to item."""
        if editable:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        else:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _get_block_signal(self, blocks_data: dict, block_id: int | None) -> str:
        """Get signal state for a block."""
        if block_id is None:
            return "Red"
        sig = blocks_data.get(block_id, {}).get("signal", SignalState.RED)
        if isinstance(sig, SignalState):
            return sig.name.title()
        elif hasattr(sig, "name"):
            return sig.name.title()
        elif isinstance(sig, str) and sig != "N/A":
            if "." in sig:
                return sig.split(".")[-1].title()
            return sig.title()
        return "Red"

    def _refresh_diagnostics(self) -> None:
        """Refresh diagnostics table."""
        if not hasattr(self.backend, "get_failure_report"):
            self.tbl_diag.setRowCount(1)
            for col, txt in enumerate(
                ["N/A", "-", "-", "Diagnostics not available"]
            ):
                self._set_item(self.tbl_diag, 0, col, txt, editable=False)
            self.tabs.setTabText(self.diag_tab_index, "Diagnostics")
            return

        report = self.backend.get_failure_report()
        active = report.get("active") or []
        pending = int(report.get("pending_commands", 0) or 0)

        self.tbl_diag.blockSignals(True)
        try:
            if not active:
                self.tbl_diag.setRowCount(1)
                for col, txt in enumerate(
                    ["None", "-", "-", "No active failures"]
                ):
                    self._set_item(self.tbl_diag, 0, col, txt, editable=False)
            else:
                self.tbl_diag.setRowCount(len(active))
                for r, rec in enumerate(active):
                    self._set_item(
                        self.tbl_diag, r, 0, str(rec.get("type", "")), editable=False
                    )
                    self._set_item(
                        self.tbl_diag,
                        r,
                        1,
                        "-" if rec.get("block") is None else str(rec["block"]),
                        editable=False,
                    )
                    self._set_item(
                        self.tbl_diag, r, 2, rec.get("time", ""), editable=False
                    )
                    self._set_item(
                        self.tbl_diag, r, 3, rec.get("details", ""), editable=False
                    )
            self.tbl_diag.resizeRowsToContents()
        finally:
            self.tbl_diag.blockSignals(False)

        self.tabs.setTabText(
            self.diag_tab_index,
            f"Diagnostics ({pending})" if pending > 0 else "Diagnostics",
        )

    def _get_switch_signal(self, switch_id: int, signal_side: int) -> str:
        """Get switch signal state from backend."""
        if hasattr(self.backend, "get_switch_signal"):
            sig = self.backend.get_switch_signal(switch_id, signal_side)
            if isinstance(sig, SignalState):
                return sig.name.title()
            elif hasattr(sig, "name"):
                return sig.name.title()
            elif isinstance(sig, str):
                if "." in sig:
                    return sig.split(".")[-1].title()
                return sig.title()
        return "Red"

    def _apply_edit_triggers(self) -> None:
        """Apply edit triggers based on maintenance mode."""
        trig = (
            (
                QAbstractItemView.EditTrigger.DoubleClicked
                | QAbstractItemView.EditTrigger.EditKeyPressed
                | QAbstractItemView.EditTrigger.SelectedClicked
            )
            if self.maintenance_enabled
            else QAbstractItemView.EditTrigger.NoEditTriggers
        )
        for tbl in (self.tbl_blocks, self.tbl_switch, self.tbl_cross):
            tbl.setEditTriggers(trig)

    def _set_item(
        self, table: QTableWidget, row: int, col: int, text: str, *, editable: bool
    ) -> None:
        """Set a table item."""
        item = QTableWidgetItem(text)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)
        table.setItem(row, col, item)

    def _color_signal_item(self, item: QTableWidgetItem, sig_text: str) -> None:
        """Color a signal item based on text."""
        colors = {"RED": "#ef4444", "YELLOW": "#eab308", "GREEN": "#22c55e"}
        clean_text = (sig_text or "RED").upper()
        if "." in clean_text:
            clean_text = clean_text.split(".")[-1]
        bg = colors.get(clean_text, "#ef4444")
        item.setBackground(QColor(bg))
        item.setForeground(QColor("#000000"))

    def _on_blocks_cell_changed(self, row: int, col: int) -> None:
        """Handle blocks table cell change."""
        if not self.maintenance_enabled:
            return

        self.tbl_blocks.blockSignals(True)
        try:
            block_item = self.tbl_blocks.item(row, 0)
            if not block_item:
                return
            b = int(block_item.text())

            if b in self._get_view_only_blocks():
                return

            if col == 4:
                if item := self.tbl_blocks.item(row, col):
                    raw = (item.text() or "").strip()
                    spd = 0 if raw in ("", "N/A") else int(raw)
                    self.backend.set_commanded_speed(b, spd)
                    logger.info("Set commanded speed for block %d to %d", b, spd)

            elif col == 5:
                if item := self.tbl_blocks.item(row, col):
                    raw = (item.text() or "").strip()
                    auth = 0 if raw in ("", "N/A") else int(raw)
                    self.backend.set_commanded_authority(b, auth)
                    logger.info("Set commanded authority for block %d to %d", b, auth)

        except Exception:
            logger.exception("Cell edit failed")
        finally:
            self.tbl_blocks.blockSignals(False)
            QTimer.singleShot(500, self.refresh_all)


def _build_networks() -> dict[str, TrackNetwork]:
    """Build track networks for standalone mode."""
    tm = TrackNetwork()
    return {"Blue Line": tm, "Red Line": tm, "Green Line": tm}


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *args: QApplication.quit())

    app = QApplication(sys.argv)

    def _quiet_excepthook(exctype, value, tb):
        if exctype is KeyboardInterrupt:
            try:
                QApplication.quit()
            except Exception:
                pass
            return
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = _quiet_excepthook

    nets = _build_networks()
    controllers = {
        name: HardwareTrackControllerBackend(nets[name], line_name=name)
        for name in ["Blue Line", "Red Line", "Green Line"]
    }
    for b in controllers.values():
        b.start_live_link(1.0)

    ui = TrackControllerHWUI(controllers)
    ui.resize(1600, 1000)
    ui.setWindowTitle("Wayside Controller - Hardware UI")
    ui.show()

    app.aboutToQuit.connect(ui._hb_timer.stop)
    app.aboutToQuit.connect(lambda: [b.stop_live_link() for b in controllers.values()])

    try:
        rc = app.exec()
    except KeyboardInterrupt:
        rc = 0
    finally:
        for b in controllers.values():
            try:
                b.stop_live_link()
            except Exception:
                pass
    sys.exit(rc)