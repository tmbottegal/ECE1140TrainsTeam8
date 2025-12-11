from __future__ import annotations
import sys, os, logging
from typing import Dict

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
    )
except ModuleNotFoundError:
    from trackControllerHW.track_controller_hw_backend import (
        HardwareTrackControllerBackend,
        TrackModelAdapter,
        SignalState,
    )

from universal.global_clock import clock as global_clock

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QFileDialog,
    QHeaderView, QMessageBox, QSplitter, QSizePolicy, QApplication, QAbstractItemView,
    QLineEdit,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Changed from DEBUG to WARNING to reduce spam
if not logger.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(h)


class TrackControllerHWUI(QWidget):
    def __init__(self, controllers: Dict[str, HardwareTrackControllerBackend], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controllers = controllers
        self.backend = next(iter(self.controllers.values()))
        self.maintenance_enabled = False
        self.current_plc_path = "None"

        # Debounce refresh requests from backend listeners
        self._refresh_pending = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_deferred_refresh)

        # Let backends notify us when state changes (debounced)
        for c in self.controllers.values():
            try:
                c.add_listener(self._request_refresh)
            except Exception:
                logger.exception("Failed attaching listener to backend")

        self._apply_stylesheet()
        self._build_ui()
        self._wire_signals()

        # Heartbeat refresh (every 1 second)
        self._hb_timer = QTimer(self)
        self._hb_timer.timeout.connect(self.refresh_all)
        self._hb_timer.start(1000)

        # Disable Browse until Maintenance
        self.btn_plc.setEnabled(False)

        self.refresh_all()

        # Global clock hookup
        try:
            global_clock.register_listener(self._update_clock_display)
            self._update_clock_display(global_clock.get_time())
        except Exception:
            logger.exception("Failed to hook HW UI into global clock")

    def _request_refresh(self) -> None:
        """Debounced refresh request - coalesces multiple rapid calls into one refresh."""
        if not self._refresh_pending:
            self._refresh_pending = True
            self._refresh_timer.start(50)  # 50ms debounce

    def _do_deferred_refresh(self) -> None:
        """Execute the deferred refresh."""
        self._refresh_pending = False
        self.refresh_all()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background-color: #f8fafc;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
                background-color: white; color: #1e293b; font-weight: 500; min-height: 20px;
            }
            QPushButton:hover { background-color: #f1f5f9; border-color: #94a3b8; }
            QPushButton:pressed { background-color: #e2e8f0; }
            QPushButton:checked { background-color: #3b82f6; color: white; border-color: #2563eb; }
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
                border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;
                background-color: #f1f5f9; color: #64748b;
            }
            QTabBar::tab:selected { background-color: white; color: #1e293b; font-weight: 500; }
            QTabBar::tab:hover:!selected { background-color: #e2e8f0; }
            QTableWidget {
                border: none; gridline-color: #f1f5f9;
                selection-background-color: #dbeafe; background-color: transparent;
            }
            QHeaderView::section {
                background-color: #f8fafc; padding: 10px; border: none;
                border-bottom: 2px solid #e2e8f0; font-weight: 600; color: #475569; text-align: left;
            }
            QSplitter::handle { background-color: #e2e8f0; width: 1px; }
        """)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setStyleSheet("QWidget { background-color: white; border-right: 1px solid #e2e8f0; }")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(20, 20, 20, 20)
        side_layout.setSpacing(16)

        side_layout.addWidget(QLabel("Line:"))
        self.line_picker = QComboBox()
        self.line_picker.addItems(list(self.controllers.keys()))
        self.line_picker.setCurrentText(self.backend.line_name)
        self.line_picker.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        side_layout.addWidget(self.line_picker)
        side_layout.addSpacing(8)

        self.btn_maint = QPushButton("Maintenance Mode")
        self.btn_maint.setCheckable(True)
        side_layout.addWidget(self.btn_maint)

        self.btn_clear_faults = QPushButton("Clear Failures")
        self.btn_clear_faults.setToolTip("Clear all active failure flags (maintenance mode only)")
        side_layout.addWidget(self.btn_clear_faults)
        side_layout.addStretch(1)

        # Main content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(16)

        # Top bar: clock
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)
        self.clock_label = QLabel("Time: --")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_bar.addStretch(1)
        top_bar.addWidget(self.clock_label)
        content_layout.addLayout(top_bar)

        # PLC upload section
        plc_container = QWidget()
        plc_container.setStyleSheet(
            "QWidget { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; }"
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

        # Tabs
        self.tabs = QTabWidget()
        content_layout.addWidget(self.tabs)

        # Blocks table
        self.tbl_blocks = QTableWidget()
        self.tbl_blocks.setColumnCount(7)
        self.tbl_blocks.setHorizontalHeaderLabels([
            "Block", "Occupancy", "Suggested Speed (mph)", "Suggested Authority (yd)",
            "Commanded Speed (mph)", "Commanded Authority (yd)", "Signal",
        ])
        self.tbl_blocks.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_blocks.verticalHeader().setVisible(False)
        self.tbl_blocks.setAlternatingRowColors(False)
        self.tabs.addTab(self.tbl_blocks, "Blocks")

        # Switches table
        self.tbl_switch = QTableWidget()
        self.tbl_switch.setColumnCount(5)
        self.tbl_switch.setHorizontalHeaderLabels([
            "Block", "Position", "Entry Signal", "Straight Signal", "Diverging Signal",
        ])
        self.tbl_switch.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_switch.verticalHeader().setVisible(False)
        self.tabs.addTab(self.tbl_switch, "Switches")

        # Crossings table
        self.tbl_cross = QTableWidget()
        self.tbl_cross.setColumnCount(3)
        self.tbl_cross.setHorizontalHeaderLabels(["Crossing ID", "Block", "Status"])
        self.tbl_cross.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_cross.verticalHeader().setVisible(False)
        self.tabs.addTab(self.tbl_cross, "Crossings")

        # Diagnostics table
        self.tbl_diag = QTableWidget()
        self.tbl_diag.setColumnCount(4)
        self.tbl_diag.setHorizontalHeaderLabels(["Type", "Block", "Time", "Details"])
        self.tbl_diag.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
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
        self.line_picker.currentTextChanged.connect(self._on_line_changed)
        self.btn_maint.toggled.connect(self._on_toggle_maintenance)
        self.btn_plc.clicked.connect(self._on_upload_plc)
        self.tbl_switch.cellClicked.connect(self._on_switch_click)
        self.tbl_cross.cellClicked.connect(self._on_crossing_click)
        self.tbl_blocks.cellChanged.connect(self._on_blocks_cell_changed)
        self.tbl_blocks.itemChanged.connect(self._pause_refresh_on_edit)
        self.btn_clear_faults.clicked.connect(self._on_clear_failures_clicked)

    def _pause_refresh_on_edit(self, item) -> None:
        if self.maintenance_enabled and item and (item.flags() & Qt.ItemFlag.ItemIsEditable):
            self._hb_timer.stop()
            QTimer.singleShot(2000, lambda: self._hb_timer.start(1000))

    def _update_clock_display(self, current_time) -> None:
        try:
            self.clock_label.setText(f"Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            for controller in self.controllers.values():
                if hasattr(controller, 'set_time'):
                    try:
                        controller.set_time(current_time)
                    except Exception:
                        pass  # Silently ignore - clock sync is non-critical
        except Exception:
            logger.exception("Failed to update clock display (HW)")

    # -------------- Actions --------------
    def _on_line_changed(self, name: str) -> None:
        try:
            self.backend = self.controllers[name]
        except Exception as exc:
            QMessageBox.warning(self, "Switch Line Failed", str(exc))
        finally:
            self._apply_edit_triggers()
            self.refresh_all()

    def _on_toggle_maintenance(self, enabled: bool) -> None:
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
        try:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select PLC File", "", "PLC Files (*.txt *.plc *.py);;All Files (*)"
            )
            if not path:
                return
            self.current_plc_path = path
            self.plc_edit.setText(path)
            
            # Pause heartbeat during PLC upload to prevent UI thrashing
            self._hb_timer.stop()
            QApplication.processEvents()  # Let UI breathe
            
            self.backend.upload_plc(path)
            
            # Resume heartbeat after a short delay
            QTimer.singleShot(500, lambda: self._hb_timer.start(1000))
            self.refresh_all()
        except Exception as exc:
            self._hb_timer.start(1000)  # Ensure timer restarts on error
            QMessageBox.warning(self, "PLC Upload Failed", str(exc))

    def _on_switch_click(self, row: int, col: int) -> None:
        if col != 1 or not self.maintenance_enabled:
            return
        try:
            sid_item = self.tbl_switch.item(row, 0)
            pos_item = self.tbl_switch.item(row, 1)
            if not sid_item or not pos_item:
                return
            sid = int(sid_item.text())
            current = (pos_item.text() or "Straight").strip().lower()
            next_pos = "Diverging" if current in ("straight", "normal") else "Straight"
            self.backend.safe_set_switch(sid, next_pos)
        except Exception as exc:
            QMessageBox.warning(self, "Switch Change Failed", str(exc))
        finally:
            self.refresh_all()

    def _on_crossing_click(self, row: int, col: int) -> None:
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
        try:
            if not self.maintenance_enabled:
                QMessageBox.information(self, "Maintenance Required",
                                        "Enable Maintenance Mode before clearing failures.")
                return
            self.backend.clear_failures()
            self.refresh_all()
        except PermissionError as exc:
            QMessageBox.warning(self, "Clear Failures Failed", str(exc))
        except Exception:
            logger.exception("Clear failures handler crashed")
            QMessageBox.warning(self, "Clear Failures Failed", "Unable to clear failures.")

    # -------------- Refresh --------------
    def refresh_all(self) -> None:
        try:
            self._refresh_blocks()
            self._refresh_switches()
            self._refresh_crossings()
            self._refresh_diagnostics()
        except KeyboardInterrupt:
            return
        except Exception:
            logger.exception("Refresh failed")

    def _refresh_blocks(self) -> None:
        if self.tbl_blocks.state() == QAbstractItemView.State.EditingState:
            return

        ids = self.backend.get_line_block_ids()
        if not ids:
            line_defaults = {"Blue Line": range(1, 16), "Red Line": range(74, 151), "Green Line": range(1, 151)}
            ids = list(line_defaults.get(self.backend.line_name, []))

        data = self.backend.blocks
        self.tbl_blocks.blockSignals(True)
        try:
            self.tbl_blocks.setRowCount(len(ids))
            for r, b in enumerate(ids):
                self._set_item(self.tbl_blocks, r, 0, str(b), editable=False)

                # Occupancy
                occ = data.get(b, {}).get("occupied", "N/A")
                occ_text = "N/A" if occ == "N/A" else ("OCCUPIED" if occ else "UNOCCUPIED")
                self._set_item(self.tbl_blocks, r, 1, occ_text, editable=False)
                if item := self.tbl_blocks.item(r, 1):
                    color = "#22c55e" if occ_text == "OCCUPIED" else "#ef4444" if occ_text == "UNOCCUPIED" else "#ffffff"
                    item.setBackground(QColor(color))
                    item.setForeground(QColor("#000000"))

                # Suggested
                self._set_item(self.tbl_blocks, r, 2, str(data.get(b, {}).get("suggested_speed", "N/A")), editable=False)
                self._set_item(self.tbl_blocks, r, 3, str(data.get(b, {}).get("suggested_auth", "N/A")), editable=False)

                # Commanded
                self._set_item(self.tbl_blocks, r, 4, str(data.get(b, {}).get("commanded_speed", "N/A")), editable=self.maintenance_enabled)
                self._set_item(self.tbl_blocks, r, 5, str(data.get(b, {}).get("commanded_auth", "N/A")), editable=self.maintenance_enabled)

                # Signal
                sig = data.get(b, {}).get("signal", "N/A")
                sig_text = sig.name.title() if isinstance(sig, SignalState) else (sig if isinstance(sig, str) else "N/A")
                self._set_item(self.tbl_blocks, r, 6, sig_text, editable=self.maintenance_enabled)
                if item := self.tbl_blocks.item(r, 6):
                    self._color_signal_item(item, sig_text)

            self.tbl_blocks.resizeRowsToContents()
        finally:
            self.tbl_blocks.blockSignals(False)

    def _refresh_crossings(self) -> None:
        crosses = self.backend.crossings
        cross_blocks = self.backend.crossing_blocks

        if not crosses and not cross_blocks:
            defaults = {"Blue Line": (1, 9), "Red Line": (1, 47), "Green Line": (1, 108)}
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
                    self._set_item(self.tbl_cross, r, 1, str(cross_blocks.get(cid, "-")), editable=False)
                    self._set_item(self.tbl_cross, r, 2, status, editable=self.maintenance_enabled)
            self.tbl_cross.resizeRowsToContents()
        finally:
            self.tbl_cross.blockSignals(False)

    def _refresh_switches(self) -> None:
        switches = self.backend.switches
        switch_map = self.backend.switch_map
        blocks_data = self.backend.blocks

        if not switch_map and not switches and self.backend.line_name == "Blue Line":
            switch_map[5] = (5, 6, 11)
            switches.setdefault(5, "N/A")

        switch_ids = sorted(switch_map.keys())
        self.tbl_switch.blockSignals(True)
        try:
            self.tbl_switch.setRowCount(max(len(switch_ids), 1))
            if not switch_ids:
                for c in range(5):
                    self._set_item(self.tbl_switch, 0, c, "", editable=False)
            else:
                for r, sid in enumerate(switch_ids):
                    blocks_tuple = switch_map.get(sid, ())
                    entry = blocks_tuple[0] if len(blocks_tuple) >= 1 else None
                    straight = blocks_tuple[1] if len(blocks_tuple) >= 2 else None
                    diverging = blocks_tuple[2] if len(blocks_tuple) >= 3 else None

                    self._set_item(self.tbl_switch, r, 0, str(sid), editable=False)
                    self._set_item(self.tbl_switch, r, 1, str(switches.get(sid, "N/A")), editable=self.maintenance_enabled)

                    def get_signal(block_id):
                        if block_id is None:
                            return "N/A"
                        sig = blocks_data.get(block_id, {}).get("signal", "N/A")
                        return sig.name.title() if isinstance(sig, SignalState) else (sig if isinstance(sig, str) else "N/A")

                    for col, blk in [(2, entry), (3, straight), (4, diverging)]:
                        txt = get_signal(blk)
                        self._set_item(self.tbl_switch, r, col, txt, editable=False)
                        if item := self.tbl_switch.item(r, col):
                            self._color_signal_item(item, txt)

            self.tbl_switch.resizeRowsToContents()
        finally:
            self.tbl_switch.blockSignals(False)

    def _refresh_diagnostics(self) -> None:
        if not hasattr(self.backend, "get_failure_report"):
            self.tbl_diag.setRowCount(1)
            for col, txt in enumerate(["N/A", "-", "-", "Diagnostics not available"]):
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
                for col, txt in enumerate(["None", "-", "-", "No active failures"]):
                    self._set_item(self.tbl_diag, 0, col, txt, editable=False)
            else:
                self.tbl_diag.setRowCount(len(active))
                for r, rec in enumerate(active):
                    self._set_item(self.tbl_diag, r, 0, str(rec.get("type", "")), editable=False)
                    self._set_item(self.tbl_diag, r, 1, "-" if rec.get("block") is None else str(rec["block"]), editable=False)
                    self._set_item(self.tbl_diag, r, 2, rec.get("time", ""), editable=False)
                    self._set_item(self.tbl_diag, r, 3, rec.get("details", ""), editable=False)
            self.tbl_diag.resizeRowsToContents()
        finally:
            self.tbl_diag.blockSignals(False)

        self.tabs.setTabText(self.diag_tab_index, f"Diagnostics ({pending})" if pending > 0 else "Diagnostics")

    # -------------- Helpers --------------
    def _apply_edit_triggers(self) -> None:
        trig = (QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | 
                QAbstractItemView.EditTrigger.SelectedClicked) if self.maintenance_enabled else QAbstractItemView.EditTrigger.NoEditTriggers
        for tbl in (self.tbl_blocks, self.tbl_switch, self.tbl_cross):
            tbl.setEditTriggers(trig)

    def _set_item(self, table: QTableWidget, row: int, col: int, text: str, *, editable: bool) -> None:
        item = QTableWidgetItem(text)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)
        table.setItem(row, col, item)

    def _color_signal_item(self, item: QTableWidgetItem, sig_text: str) -> None:
        colors = {"RED": "#ef4444", "YELLOW": "#eab308", "GREEN": "#22c55e"}
        bg = colors.get((sig_text or "").upper(), "#ffffff")
        item.setBackground(QColor(bg))
        item.setForeground(QColor("#000000"))

    def _on_blocks_cell_changed(self, row: int, col: int) -> None:
        if not self.maintenance_enabled:
            return

        self.tbl_blocks.blockSignals(True)
        try:
            block_item = self.tbl_blocks.item(row, 0)
            if not block_item:
                return
            b = int(block_item.text())

            if col == 4:  # Commanded Speed
                if item := self.tbl_blocks.item(row, col):
                    raw = (item.text() or "").strip()
                    spd = 0 if raw in ("", "N/A") else int(raw)
                    self.backend.set_commanded_speed(b, spd)
                    logger.info(f"Set commanded speed for block {b} to {spd}")

            elif col == 5:  # Commanded Authority
                if item := self.tbl_blocks.item(row, col):
                    raw = (item.text() or "").strip()
                    auth = 0 if raw in ("", "N/A") else int(raw)
                    self.backend.set_commanded_authority(b, auth)
                    logger.info(f"Set commanded authority for block {b} to {auth}")

            elif col == 6:  # Signal
                if item := self.tbl_blocks.item(row, col):
                    sig_text = (item.text() or "N/A").strip().upper()
                    if sig_text in ("RED", "YELLOW", "GREEN"):
                        item.setText(sig_text)
                        self.backend.set_signal(b, sig_text)
                        logger.info(f"Set signal for block {b} to {sig_text}")
                    else:
                        logger.warning(f"Invalid signal value: {sig_text}. Must be RED, YELLOW, or GREEN")
                        old_sig = self.backend.blocks.get(b, {}).get("signal", "N/A")
                        old_text = old_sig.name.upper() if isinstance(old_sig, SignalState) else (old_sig.upper() if isinstance(old_sig, str) else "N/A")
                        item.setText(old_text)
        except Exception:
            logger.exception("Cell edit failed")
        finally:
            self.tbl_blocks.blockSignals(False)
            QTimer.singleShot(500, self.refresh_all)


# -------------------- app boot --------------------
def _build_networks() -> Dict[str, TrackNetwork]:
    tm = TrackNetwork()
    return {"Blue Line": tm, "Red Line": tm, "Green Line": tm}


if __name__ == "__main__":
    import signal
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
    ui.setWindowTitle("Wayside Controller – Hardware UI")
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