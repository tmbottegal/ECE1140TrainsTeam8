from __future__ import annotations
import sys, logging
from typing import Dict

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QFileDialog,
    QHeaderView, QMessageBox, QSplitter, QSizePolicy, QApplication, QAbstractItemView,
    QLineEdit,
)

from trackControllerHW.track_controller_hw_backend import (
    HardwareTrackControllerBackend,
    TrackModelAdapter,
    SignalState,
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

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ---- Sidebar ----
        sidebar = QWidget()
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(8, 8, 8, 8)
        side_layout.setSpacing(8)

        # (Removed the left-panel title per your request)

        side_layout.addWidget(QLabel("Line:"))
        self.line_picker = QComboBox()
        self.line_picker.addItems(list(self.controllers.keys()))
        self.line_picker.setCurrentText(self.backend.line_name)
        self.line_picker.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        side_layout.addWidget(self.line_picker)

        # Space between Line dropdown and Maintenance button (tweak this value if desired)
        side_layout.addSpacing(14)

        self.btn_maint = QPushButton("Maintenance Mode")
        self.btn_maint.setCheckable(True)
        side_layout.addWidget(self.btn_maint)

        # (Removed the Status label since it's redundant)
        side_layout.addStretch(1)

        # ---- Main content ----
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        # --- Clean PLC "search bar + Browse" row ---
        plc_row = QHBoxLayout()

        plc_label = QLabel("Upload PLC File:")
        plc_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.plc_edit = QLineEdit()
        self.plc_edit.setPlaceholderText("No file selected")
        self.plc_edit.setReadOnly(True)
        self.plc_edit.setMinimumWidth(420)
        self.plc_edit.setStyleSheet(
            "QLineEdit { padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 6px; }"
        )

        self.btn_plc = QPushButton("Browse")
        self.btn_plc.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_plc.setFixedWidth(90)

        plc_row.addWidget(plc_label)
        plc_row.addWidget(self.plc_edit, 1)
        plc_row.addWidget(self.btn_plc)

        content_layout.addLayout(plc_row)

        # Tabs
        self.tabs = QTabWidget()
        content_layout.addWidget(self.tabs)

        # -------- Blocks table (separate suggested/commanded columns; removed "—" col) --------
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
        root.addWidget(splitter)

    def _wire_signals(self) -> None:
        self.line_picker.currentTextChanged.connect(self._on_line_changed)
        self.btn_maint.toggled.connect(self._on_toggle_maintenance)
        self.btn_plc.clicked.connect(self._on_upload_plc)
        self.tbl_switch.cellClicked.connect(self._on_switch_click)
        self.tbl_cross.cellClicked.connect(self._on_crossing_click)
        self.tbl_blocks.cellChanged.connect(self._on_blocks_cell_changed)

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
            self.plc_edit.setText(path)     # show in the search bar
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
            # Ctrl+C landed mid-slot; swallow so we can quit cleanly.
            return
        except Exception:
            logger.exception("Refresh failed")

    def _refresh_blocks(self) -> None:
        ids = self.backend.get_line_block_ids()
        logger.debug(f"Refreshing blocks for {self.backend.line_name}; ids={len(ids)}")
        if not ids:
            # Fallback ranges so you still see a table if something is off
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

                # Suggested (separate columns)
                sug_spd = data.get(b, {}).get("suggested_speed", "N/A")
                sug_auth = data.get(b, {}).get("suggested_auth", "N/A")
                self._set_item(self.tbl_blocks, r, 2, str(sug_spd), editable=False)
                self._set_item(self.tbl_blocks, r, 3, str(sug_auth), editable=False)

                # Commanded (separate columns) – editable in maintenance
                cmd_spd = data.get(b, {}).get("commanded_speed", "N/A")
                cmd_auth = data.get(b, {}).get("commanded_auth", "N/A")
                self._set_item(self.tbl_blocks, r, 4, str(cmd_spd), editable=self.maintenance_enabled)
                self._set_item(self.tbl_blocks, r, 5, str(cmd_auth), editable=self.maintenance_enabled)

                # Signal – editable in maintenance, colored cells
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
            item.setBackground(Qt.GlobalColor.red)
        elif s == "YELLOW":
            item.setBackground(Qt.GlobalColor.yellow)
        elif s == "GREEN":
            item.setBackground(Qt.GlobalColor.green)
        else:
            item.setBackground(Qt.GlobalColor.transparent)

    def _on_blocks_cell_changed(self, row: int, col: int) -> None:
        if not self.maintenance_enabled:
            return
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

            elif col == 5:  # Commanded Authority
                item = self.tbl_blocks.item(row, col)
                if not item:
                    return
                raw = (item.text() or "").strip()
                auth = 0 if raw in ("", "N/A") else int(raw)
                self.backend.set_commanded_authority(b, auth)

            elif col == 6:  # Signal
                item = self.tbl_blocks.item(row, col)
                if not item:
                    return
                sig_text = (item.text() or "N/A").strip().upper()
                if sig_text in ("RED", "YELLOW", "GREEN"):
                    self.backend.set_signal(b, sig_text)
        except Exception:
            logger.exception("Cell edit failed")
        finally:
            self.refresh_all()


# -------------------- app boot --------------------
def _build_networks() -> Dict[str, TrackModelAdapter]:
    tm_blue = TrackModelAdapter()
    tm_red = TrackModelAdapter()
    tm_green = TrackModelAdapter()

    tm_blue.ensure_blocks(list(range(1, 16)))      # Blue: 1..15
    tm_red.ensure_blocks(list(range(74, 151)))     # Red: 74..150
    tm_green.ensure_blocks(list(range(1, 151)))    # Green: 1..150

    return {"Blue Line": tm_blue, "Red Line": tm_red, "Green Line": tm_green}


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, lambda *args: QApplication.quit())

    app = QApplication(sys.argv)

    # Quiet excepthook for Ctrl+C so no traceback prints
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

    # Clean shutdown on window close or Ctrl+C
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
