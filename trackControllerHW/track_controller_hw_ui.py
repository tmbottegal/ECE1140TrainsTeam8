from __future__ import annotations
import sys, os, logging
from typing import Dict

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QFileDialog,
    QHeaderView, QMessageBox, QSplitter, QSizePolicy, QApplication, QAbstractItemView,
    QLineEdit,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # set to WARNING to reduce log output
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

        # Let backends notify us when state changes
        for c in self.controllers.values():
            try:
                c.add_listener(self.refresh_all)
            except Exception:
                logger.exception("Failed attaching listener to backend")

        self._apply_stylesheet()
        self._build_ui()
        self._wire_signals()

        # Heartbeat refresh
        self._hb_timer = QTimer(self)
        self._hb_timer.timeout.connect(self.refresh_all)
        self._hb_timer.start(1000)

        # Disable Browse until Maintenance
        try:
            self.btn_plc.setEnabled(False)
        except Exception:
            pass

        self.refresh_all()

    def _apply_stylesheet(self) -> None:
        """Apply modern, clean styling to the entire UI"""
        self.setStyleSheet("""
            QWidget {
                background-color: #f8fafc;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 13px;
                color: #1e293b;
            }
            
            QLabel {
                color: #475569;
                font-weight: 500;
            }
            
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: white;
                min-height: 20px;
            }
            
            QComboBox:hover {
                border-color: #94a3b8;
            }
            
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            
            QPushButton {
                padding: 8px 16px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: white;
                color: #1e293b;
                font-weight: 500;
                min-height: 20px;
            }
            
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
            
            QPushButton:pressed {
                background-color: #e2e8f0;
            }
            
            QPushButton:checked {
                background-color: #3b82f6;
                color: white;
                border-color: #2563eb;
            }
            
            QPushButton:checked:hover {
                background-color: #2563eb;
            }
            
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: white;
                color: #64748b;
            }
            
            QLineEdit:focus {
                border-color: #3b82f6;
                outline: none;
            }
            
            QTabWidget::pane {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: white;
                top: -1px;
            }
            
            QTabBar::tab {
                padding: 10px 20px;
                margin-right: 2px;
                border: 1px solid #e2e8f0;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                background-color: #f1f5f9;
                color: #64748b;
            }
            
            QTabBar::tab:selected {
                background-color: white;
                color: #1e293b;
                font-weight: 500;
            }
            
            QTabBar::tab:hover:!selected {
                background-color: #e2e8f0;
            }
            
            QTableWidget {
                border: none;
                gridline-color: #f1f5f9;
                selection-background-color: #dbeafe;
                background-color: transparent;
            }
            
            QHeaderView::section {
                background-color: #f8fafc;
                padding: 10px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
                font-weight: 600;
                color: #475569;
                text-align: left;
            }
            
            QSplitter::handle {
                background-color: #e2e8f0;
                width: 1px;
            }
        """)

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar ----
        sidebar = QWidget()
        sidebar.setStyleSheet("""
            QWidget {
                background-color: white;
                border-right: 1px solid #e2e8f0;
            }
        """)
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

        side_layout.addStretch(1)

        # ---- Main content ----
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(16)

        # --- PLC upload section ---
        plc_container = QWidget()
        plc_container.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
        """)
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

        # -------- Blocks table --------
        self.tbl_blocks = QTableWidget()
        self.tbl_blocks.setColumnCount(7)
        self.tbl_blocks.setHorizontalHeaderLabels([
            "Block",
            "Occupied",
            "Suggested Speed (mph)",
            "Suggested Authority (yd)",
            "Commanded Speed (mph)",
            "Commanded Authority (yd)",
            "Signal",
        ])
        self.tbl_blocks.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_blocks.verticalHeader().setVisible(False)
        self.tbl_blocks.setAlternatingRowColors(False)
        self.tabs.addTab(self.tbl_blocks, "Blocks")

        # Switches
        self.tbl_switch = QTableWidget()
        self.tbl_switch.setColumnCount(3)
        self.tbl_switch.setHorizontalHeaderLabels(["Switch ID", "Blocks", "Position"])
        self.tbl_switch.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_switch.verticalHeader().setVisible(False)
        self.tabs.addTab(self.tbl_switch, "Switches")

        # Crossings
        self.tbl_cross = QTableWidget()
        self.tbl_cross.setColumnCount(3)
        self.tbl_cross.setHorizontalHeaderLabels(["Crossing ID", "Block", "Status"])
        self.tbl_cross.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_cross.verticalHeader().setVisible(False)
        self.tabs.addTab(self.tbl_cross, "Crossings")

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
        
        # Pause refresh when editing
        self.tbl_blocks.itemChanged.connect(self._pause_refresh_on_edit)
        
    def _pause_refresh_on_edit(self, item) -> None:
        """Pause the refresh timer briefly when user is editing"""
        if self.maintenance_enabled and item and (item.flags() & Qt.ItemFlag.ItemIsEditable):
            self._hb_timer.stop()
            QTimer.singleShot(2000, lambda: self._hb_timer.start(1000))

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
        try:
            self.btn_plc.setEnabled(enabled)
        except Exception:
            pass
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
                self,
                "Select PLC File",
                "",
                "PLC Files (*.txt *.plc *.py);;All Files (*)",
            )
            if not path:
                return
            self.current_plc_path = path
            self.plc_edit.setText(path)
            self.backend.upload_plc(path)
            self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "PLC Upload Failed", str(exc))

    def _on_switch_click(self, row: int, col: int) -> None:
        if col != 2 or not self.maintenance_enabled:
            return
        try:
            sid_item = self.tbl_switch.item(row, 0)
            pos_item = self.tbl_switch.item(row, 2)
            if not sid_item or not pos_item:
                return
            sid = int(sid_item.text())
            current = (pos_item.text() or "Normal").strip()
            next_pos = "Alternate" if current == "Normal" else "Normal"
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

    # -------------- Refresh --------------
    def refresh_all(self) -> None:
        try:
            self._refresh_blocks()
            self._refresh_switches()
            self._refresh_crossings()
        except KeyboardInterrupt:
            return
        except Exception:
            logger.exception("Refresh failed")

    def _refresh_blocks(self) -> None:
        # Don't refresh if user is actively editing a cell
        if self.tbl_blocks.state() == QAbstractItemView.State.EditingState:
            return
            
        ids = self.backend.get_line_block_ids()
        logger.debug(f"Refreshing blocks for {self.backend.line_name}; ids={len(ids)}")
        if not ids:
            if self.backend.line_name == "Blue Line":
                ids = list(range(1, 16))
            elif self.backend.line_name == "Red Line":
                ids = list(range(74, 151))
            elif self.backend.line_name == "Green Line":
                ids = list(range(1, 151))

        data = self.backend.blocks

        self.tbl_blocks.blockSignals(True)
        try:
            self.tbl_blocks.setRowCount(len(ids))
            for r, b in enumerate(ids):
                # Block #
                self._set_item(self.tbl_blocks, r, 0, str(b), editable=False)

                # Occupied
                occ = data.get(b, {}).get("occupied", "N/A")
                occ_text = "N/A" if occ == "N/A" else ("Yes" if occ else "No")
                self._set_item(self.tbl_blocks, r, 1, occ_text, editable=False)

                # Suggested
                sug_spd = data.get(b, {}).get("suggested_speed", "N/A")
                sug_auth = data.get(b, {}).get("suggested_auth", "N/A")
                self._set_item(self.tbl_blocks, r, 2, str(sug_spd), editable=False)
                self._set_item(self.tbl_blocks, r, 3, str(sug_auth), editable=False)

                # Commanded
                cmd_spd = data.get(b, {}).get("commanded_speed", "N/A")
                cmd_auth = data.get(b, {}).get("commanded_auth", "N/A")
                self._set_item(self.tbl_blocks, r, 4, str(cmd_spd), editable=self.maintenance_enabled)
                self._set_item(self.tbl_blocks, r, 5, str(cmd_auth), editable=self.maintenance_enabled)

                # Signal with color
                sig = data.get(b, {}).get("signal", "N/A")
                sig_text = sig.name.title() if isinstance(sig, SignalState) else (sig if isinstance(sig, str) else "N/A")
                self._set_item(self.tbl_blocks, r, 6, sig_text, editable=self.maintenance_enabled)
                item_sig = self.tbl_blocks.item(r, 6)
                if item_sig:
                    self._color_signal_item(item_sig, sig_text)

            self.tbl_blocks.resizeRowsToContents()
        finally:
            self.tbl_blocks.blockSignals(False)

    def _refresh_switches(self) -> None:
        switches = self.backend.switches
        switch_map = self.backend.switch_map
        if not switches and not switch_map:
            if self.backend.line_name == "Blue Line":
                switch_map[1] = (5, 6, 11)
            elif self.backend.line_name == "Red Line":
                switch_map[1] = (90, 91, 92)
                switch_map[2] = (120, 121, 122)
            elif self.backend.line_name == "Green Line":
                switch_map[1] = (12, 13, 14)
                switch_map[2] = (28, 29, 30)
            for sid in switch_map:
                switches[sid] = "N/A"
        rows = max(len(switches), 1)

        self.tbl_switch.blockSignals(True)
        try:
            self.tbl_switch.setRowCount(rows)
            if not switches:
                for c in range(3):
                    self._set_item(self.tbl_switch, 0, c, "", editable=False)
            else:
                for r, (sid, pos) in enumerate(switches.items()):
                    self._set_item(self.tbl_switch, r, 0, str(sid), editable=False)
                    self._set_item(self.tbl_switch, r, 1, str(switch_map.get(sid, ())), editable=False)
                    self._set_item(self.tbl_switch, r, 2, pos, editable=self.maintenance_enabled)
            self.tbl_switch.resizeRowsToContents()
        finally:
            self.tbl_switch.blockSignals(False)

    def _refresh_crossings(self) -> None:
        crosses = self.backend.crossings
        cross_blocks = self.backend.crossing_blocks
        if not crosses and not cross_blocks:
            if self.backend.line_name == "Blue Line":
                cross_blocks[1] = 9
            elif self.backend.line_name == "Red Line":
                cross_blocks[1] = 100
            elif self.backend.line_name == "Green Line":
                cross_blocks[1] = 19
            for cid in cross_blocks:
                crosses[cid] = "N/A"
        rows = max(len(crosses), 1)

        self.tbl_cross.blockSignals(True)
        try:
            self.tbl_cross.setRowCount(rows)
            if not crosses:
                for c in range(3):
                    self._set_item(self.tbl_cross, 0, c, "", editable=False)
            else:
                for r, (cid, status) in enumerate(crosses.items()):
                    self._set_item(self.tbl_cross, r, 0, str(cid), editable=False)
                    self._set_item(self.tbl_cross, r, 1, str(cross_blocks.get(cid, "-")), editable=False)
                    self._set_item(self.tbl_cross, r, 2, status, editable=self.maintenance_enabled)
            self.tbl_cross.resizeRowsToContents()
        finally:
            self.tbl_cross.blockSignals(False)

    # -------------- Helpers --------------
    def _apply_edit_triggers(self) -> None:
        if self.maintenance_enabled:
            trig = (QAbstractItemView.EditTrigger.DoubleClicked
                    | QAbstractItemView.EditTrigger.EditKeyPressed
                    | QAbstractItemView.EditTrigger.SelectedClicked)
        else:
            trig = QAbstractItemView.EditTrigger.NoEditTriggers
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
        s = (sig_text or "").upper()
        if s == "RED":
            item.setBackground(QColor("#ef4444"))
            item.setForeground(QColor("#000000"))
        elif s == "YELLOW":
            item.setBackground(QColor("#eab308"))
            item.setForeground(QColor("#000000"))
        elif s == "GREEN":
            item.setBackground(QColor("#22c55e"))
            item.setForeground(QColor("#000000"))
        else:
            item.setBackground(QColor("#ffffff"))
            item.setForeground(QColor("#000000"))

    def _on_blocks_cell_changed(self, row: int, col: int) -> None:
        if not self.maintenance_enabled:
            return
        
        # Block signals during this update to prevent recursive calls
        self.tbl_blocks.blockSignals(True)
        try:
            block_item = self.tbl_blocks.item(row, 0)
            if not block_item:
                return
            b = int(block_item.text())

            if col == 4:  # Commanded Speed
                item = self.tbl_blocks.item(row, col)
                if not item:
                    return
                raw = (item.text() or "").strip()
                spd = 0 if raw in ("", "N/A") else int(raw)
                self.backend.set_commanded_speed(b, spd)
                logger.info(f"Set commanded speed for block {b} to {spd}")

            elif col == 5:  # Commanded Authority
                item = self.tbl_blocks.item(row, col)
                if not item:
                    return
                raw = (item.text() or "").strip()
                auth = 0 if raw in ("", "N/A") else int(raw)
                self.backend.set_commanded_authority(b, auth)
                logger.info(f"Set commanded authority for block {b} to {auth}")

            elif col == 6:  # Signal
                item = self.tbl_blocks.item(row, col)
                if not item:
                    return
                sig_text = (item.text() or "N/A").strip().upper()
                if sig_text in ("RED", "YELLOW", "GREEN"):
                    # Set the text to uppercase
                    item.setText(sig_text)
                    # Update backend
                    self.backend.set_signal(b, sig_text)
                    logger.info(f"Set signal for block {b} to {sig_text}")
                    # Update the color immediately
                    self._color_signal_item(item, sig_text)
                else:
                    logger.warning(f"Invalid signal value: {sig_text}. Must be RED, YELLOW, or GREEN")
                    # Revert to previous value
                    old_sig = self.backend.blocks.get(b, {}).get("signal", "N/A")
                    old_text = old_sig.name.title() if isinstance(old_sig, SignalState) else (old_sig if isinstance(old_sig, str) else "N/A")
                    item.setText(old_text)
                    self._color_signal_item(item, old_text)
        except Exception:
            logger.exception("Cell edit failed")
        finally:
            self.tbl_blocks.blockSignals(False)
            # Refresh after a short delay
            QTimer.singleShot(500, self.refresh_all)


# -------------------- app boot --------------------
def _build_networks() -> Dict[str, TrackModelAdapter]:
    tm_blue = TrackModelAdapter()
    tm_red = TrackModelAdapter()
    tm_green = TrackModelAdapter()

    tm_blue.ensure_blocks(list(range(1, 16)))
    tm_red.ensure_blocks(list(range(74, 151)))
    tm_green.ensure_blocks(list(range(1, 151)))

    return {"Blue Line": tm_blue, "Red Line": tm_red, "Green Line": tm_green}


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
    tm_blue, tm_red, tm_green = nets["Blue Line"], nets["Red Line"], nets["Green Line"]

    controllers = {
        "Blue Line": HardwareTrackControllerBackend(tm_blue, line_name="Blue Line"),
        "Red Line": HardwareTrackControllerBackend(tm_red, line_name="Red Line"),
        "Green Line": HardwareTrackControllerBackend(tm_green, line_name="Green Line"),
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