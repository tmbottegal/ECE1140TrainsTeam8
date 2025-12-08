from __future__ import annotations
import sys,os,logging
from typing import TYPE_CHECKING, Dict
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QColor
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget, QHeaderView, QTabWidget, QTextEdit, QCheckBox, QSizePolicy)

_pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _pkg_root not in sys.path: sys.path.append(_pkg_root)
from universal.global_clock import clock as global_clock
from universal.universal import SignalState
from track_controller_backend import TrackControllerBackend

if TYPE_CHECKING: from track_controller_backend import TrackControllerBackend

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


class QTextEditLogger(logging.Handler):
    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    
    def emit(self, record):
        msg = self.format(record)
        self.text_edit.append(msg)
        self.text_edit.moveCursor(QTextCursor.MoveOperation.End)


class TrackControllerUI(QWidget):
    VIEW_ONLY_BLOCKS = {
        "Red Line": list(range(35, 46)) + list(range(67, 72)),
        "Green Line": list(range(63, 69)) + list(range(117, 122))}
    
    def __init__(self, controllers: Dict[str, "TrackControllerBackend"], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controllers = controllers
        self.backend = next(iter(self.controllers.values()))
        self.manual_mode_enabled = False
        self.current_plc_file = None
        self.bold_font = QFont()
        self.bold_font.setBold(True)
        self.big_font = QFont(self.bold_font)
        self.big_font.setPointSize(self.bold_font.pointSize() * 2)
        self.bold_font = QFont()
        self.bold_font.setBold(True)
        self.resize(1200, 800)
        try:
            for c in self.controllers.values():
                c.add_listener(self.refresh_tables)
        except Exception: logger.exception("not attached to backend dumbass")
        global_clock.register_listener(self._update_clock_display)
        self._build_ui()
        self._setup_logging()
        self.tableswitch.cellClicked.connect(self._on_switch_clicked)
        self.tablecrossing.cellClicked.connect(self._on_crossing_clicked)
        self.plc_button.clicked.connect(self._on_plc_upload)
        self._update_clock_display(global_clock.get_time())

    def _bold(self, widget):
        widget.setFont(self.bold_font)
        return widget

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        # top
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        self.dropdown_text = QLabel("Wayside SW")
        self.dropdown_text.setFont(self.big_font)
        self.dropdown_text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        top_row.addWidget(self.dropdown_text)
        top_row.addStretch()
        self.track_picker = QComboBox()
        self.track_picker.addItems(list(self.controllers.keys()))
        self.track_picker.setCurrentIndex(0)
        self.track_picker.setMinimumHeight(32)
        self.track_picker.setMinimumWidth(150)
        self.track_picker.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.track_picker.setFont(self.big_font)
        self.track_picker.currentTextChanged.connect(self.switch_line)
        top_row.addWidget(self.track_picker)
        layout.addLayout(top_row)
        self.main_tabs = QTabWidget()
        self.main_tabs.setFont(self.bold_font)
        self.main_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # tables
        self.table_widget = QWidget()
        table_layout = QVBoxLayout(self.table_widget)
        table_layout.setContentsMargins(5, 5, 5, 5)
        table_layout.setSpacing(8)
        self._add_table("Blocks", "tablemain")
        self.tablemain.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tablemain.setMinimumHeight(200)
        table_layout.addWidget(self.tablemain, stretch=5)
        self._add_table("Switches", "tableswitch")
        self.tableswitch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tableswitch.setMinimumHeight(100)
        table_layout.addWidget(self.tableswitch, stretch=2)
        self._add_table("Crossings", "tablecrossing")
        self.tablecrossing.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tablecrossing.setMinimumHeight(80)
        table_layout.addWidget(self.tablecrossing, stretch=1)
        # logs
        self.logs_widget = QWidget()
        logs_layout = QVBoxLayout(self.logs_widget)
        logs_layout.setContentsMargins(5, 5, 5, 5)
        logs_layout.setSpacing(8)
        logs_header = QHBoxLayout()
        logs_header.setSpacing(10)
        logs_title = QLabel("System Logs")
        logs_title.setFont(self.big_font)
        logs_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        logs_header.addWidget(logs_title)
        logs_header.addStretch()
        self.log_level_label = QLabel("Filter Level:")
        self.log_level_label.setFont(self.bold_font)
        self.log_level_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        logs_header.addWidget(self.log_level_label)
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level_combo.setCurrentText("INFO")
        self.log_level_combo.setFont(self.bold_font)
        self.log_level_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.log_level_combo.currentTextChanged.connect(self._on_log_level_changed)
        logs_header.addWidget(self.log_level_combo)
        self.auto_scroll_check = QCheckBox("Auto-scroll")
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.setFont(self.bold_font)
        self.auto_scroll_check.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        logs_header.addWidget(self.auto_scroll_check)
        clear_logs_btn = QPushButton("Clear Logs")
        clear_logs_btn.setFont(self.bold_font)
        clear_logs_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        clear_logs_btn.clicked.connect(self._clear_logs)
        logs_header.addWidget(clear_logs_btn)
        logs_layout.addLayout(logs_header)
        self.logs_display = QTextEdit()
        self.logs_display.setReadOnly(True)
        self.logs_display.setFont(QFont("Courier", 9))
        self.logs_display.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.logs_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        logs_layout.addWidget(self.logs_display)
        self.main_tabs.addTab(self.table_widget, "Status Tables")
        self.main_tabs.addTab(self.logs_widget, "System Logs")
        layout.addWidget(self.main_tabs, stretch=1)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        self.plc_button = QPushButton("PLC File Upload")
        self.plc_button.setFont(self.bold_font)
        self.plc_button.setMinimumHeight(50)
        self.plc_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        bottom_row.addWidget(self.plc_button)
        self.filename_box = QLineEdit("File: None")
        self.filename_box.setFont(self.big_font)
        self.filename_box.setReadOnly(True)
        self.filename_box.setMinimumWidth(200)
        self.filename_box.setMinimumHeight(50)
        self.filename_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bottom_row.addWidget(self.filename_box, stretch=1)
        self.clock_label = QLabel("Time: 2000-01-01 00:00:00")
        self.clock_label.setFont(self.big_font)
        self.clock_label.setMinimumHeight(50)
        self.clock_label.setMinimumWidth(250)
        self.clock_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet("QLabel { border: 2px solid gray; padding: 5px; background-color: #000; }")
        bottom_row.addWidget(self.clock_label)
        self.manual_button = QPushButton("Maintenance Mode")
        self.manual_button.setFont(self.bold_font)
        self.manual_button.setCheckable(True)
        self.manual_button.setMinimumHeight(50)
        self.manual_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.manual_button.toggled.connect(self.toggle_manual_mode)
        bottom_row.addWidget(self.manual_button)
        layout.addLayout(bottom_row)

    def _setup_logging(self) -> None:
        self.log_handler = QTextEditLogger(self.logs_display)
        self.log_handler.setLevel(logging.INFO)
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        logger.info("Track Controller UI initialized with logging tab")

    def _on_log_level_changed(self, level_str: str) -> None:
        level_map = {
            "ALL": logging.DEBUG,
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL}
        new_level = level_map.get(level_str, logging.INFO)
        self.log_handler.setLevel(new_level)
        logger.info(f"log level now at {level_str}")

    def _clear_logs(self) -> None:
        self.logs_display.clear()
        logger.info("the logs have been taken out back")

    def _add_table(self, label_text: str, attr_name: str) -> None:
        label = QLabel(label_text)
        label.setFont(self.bold_font)
        if hasattr(self, 'container_layout'): self.container_layout.addWidget(label)
        table = QTableWidget()
        table.setFont(self.bold_font)
        setattr(self, attr_name, table)
        if hasattr(self, 'container_layout'): self.container_layout.addWidget(table)

    def _is_view_only_block(self, block_id: int) -> bool:
        view_only = self.VIEW_ONLY_BLOCKS.get(self.backend.line_name, [])
        return block_id in view_only

    def switch_line(self, line_name: str) -> None:
        try:
            try: self.backend.remove_listener(self.refresh_tables)
            except Exception: pass
            self.backend = self.controllers[line_name]
            self.backend.add_listener(self.refresh_tables)
            self.dropdown_text.setText(f"Track: {line_name}")
            self.refresh_tables()
        except Exception: logger.exception("cant switch to line %s", line_name)

    def toggle_manual_mode(self, enabled: bool) -> None:
        self.manual_mode_enabled = enabled
        logger.info("Maintenance Mode %s", "enabled" if enabled else "disabled")
        try:
            for c in self.controllers.values(): c.set_maintenance_mode(enabled)
        except Exception: logger.exception("cant set maintenance mode")
        self.refresh_tables()

    def _on_plc_upload(self) -> None:
        if not self.manual_mode_enabled:
            QMessageBox.warning(self, "Maintenance Mode Required","PLS Enable Maintenance Mode before uploading the PLC file. Thank you for actually reading this.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self,"Open PLC File","","PLC Files (*.txt *.plc *.py)")
        if not file_path:
            logger.info("PLC upload stopped")
            return 
        try:
            self.backend.upload_plc(file_path)
            logger.info("commanded speeds: %s", self.backend._commanded_speed_mps)
            logger.info("commanded auth: %s", self.backend._commanded_auth_m)
            filename = os.path.basename(file_path)
            self.current_plc_file = file_path
            self.filename_box.setText(f"File: {filename}")
            self.refresh_tables()
            logger.info("PLC file %s uploaded for %s", file_path, self.backend.line_name)
        except PermissionError as e:
            QMessageBox.warning(self, "Permission Error", str(e))
            logger.warning("PLC upload failed - permission error: %s", e)    
        except Exception as e:
            QMessageBox.critical(self,"PLC Upload Failed",f"Failed to upload PLC:\n{str(e)}")
            logger.exception("PLC upload failed: %s", file_path)

    def refresh_tables(self) -> None:
        try:
            try: self.tablemain.itemChanged.disconnect()
            except Exception: pass
            try: self.tableswitch.itemChanged.disconnect()
            except Exception:pass
            try: self.tablecrossing.itemChanged.disconnect()
            except Exception: pass
            line_block_map = {
                "Green Line": list(range(1, 63)) + list(range(63, 69)) + list(range(117, 122)) + list(range(122, 151)),
                "Red Line": list(range(1, 34)) + list(range(35, 46)) + list(range(67, 72)),}
            block_ids = line_block_map.get(self.backend.line_name, [])
            self.tablemain.setRowCount(len(block_ids))
            self.tablemain.setColumnCount(6)
            self.tablemain.setHorizontalHeaderLabels([
                "Block", 
                "Suggested Speed (mph)", 
                "Suggested Authority (yd)", 
                "Occupancy", 
                "Commanded Speed (mph)", 
                "Commanded Authority (yd)"])
            self.tablemain.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.tablemain.verticalHeader().setVisible(False)
            blocks_data = self.backend.blocks
            for i, block in enumerate(block_ids):
                is_view_only = self._is_view_only_block(block)
                block_item = QTableWidgetItem(str(block))
                if is_view_only:
                    block_item.setBackground(QColor(200, 200, 200))
                    block_item.setForeground(QColor(100, 100, 100))
                self.tablemain.setItem(i, 0, block_item)
                data = blocks_data.get(block, {})
                self._set_table_item_with_viewonly(self.tablemain, i, 1, str(data.get("suggested_speed", "N/A")), editable=False, view_only=is_view_only)
                self._set_table_item_with_viewonly(self.tablemain, i, 2, str(data.get("suggested_auth", "N/A")), editable=False, view_only=is_view_only)
                occ_val = data.get("occupied")
                if occ_val == "N/A": occ_text = "N/A"
                else: occ_text = "Occupied" if occ_val else "Unoccupied"
                occ_item = QTableWidgetItem(occ_text)
                self._apply_editable(occ_item, editable=False)
                if occ_val == "N/A": pass
                elif occ_val:
                    occ_item.setBackground(Qt.GlobalColor.green)
                    occ_item.setForeground(Qt.GlobalColor.black)
                else:
                    occ_item.setBackground(Qt.GlobalColor.red)
                    occ_item.setForeground(Qt.GlobalColor.white)
                if is_view_only:
                    occ_item.setBackground(QColor(200, 200, 200))
                    occ_item.setForeground(QColor(100, 100, 100))
                self.tablemain.setItem(i, 3, occ_item)
                cmd_speed = data.get("commanded_speed")
                cmd_auth = data.get("commanded_auth")
                self._set_table_item_with_viewonly(self.tablemain, i, 4, str(cmd_speed), editable=False, view_only=is_view_only)
                self._set_table_item_with_viewonly(self.tablemain, i, 5, str(cmd_auth), editable=False, view_only=is_view_only)
            switches = self.backend.switches
            if switches:
                self.tableswitch.setRowCount(len(switches))
                self.tableswitch.setColumnCount(5)
                self.tableswitch.setHorizontalHeaderLabels([
                    "Block", 
                    "Position",
                    "Prev Signal",
                    "Straight Signal", 
                    "Diverging Signal"])
                self.tableswitch.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                self.tableswitch.verticalHeader().setVisible(False)
                for i, (sid, pos_int) in enumerate(switches.items()):
                    self.tableswitch.setItem(i, 0, QTableWidgetItem(str(sid)))
                    pos_text = "Straight" if pos_int == 0 else "Diverging"
                    item = QTableWidgetItem(pos_text)
                    item.setData(Qt.ItemDataRole.UserRole, pos_int)
                    self._apply_editable(item, editable=self.manual_mode_enabled)
                    self.tableswitch.setItem(i, 1, item)
                    switch_signals = getattr(self.backend, '_switch_signals', {})
                    prev_sig = switch_signals.get((sid, 0), "N/A")
                    prev_item = self._create_signal_item(prev_sig)
                    self.tableswitch.setItem(i, 2, prev_item)
                    straight_sig = switch_signals.get((sid, 1), "N/A")
                    straight_item = self._create_signal_item(straight_sig)
                    self.tableswitch.setItem(i, 3, straight_item)
                    diverging_sig = switch_signals.get((sid, 2), "N/A")
                    diverging_item = self._create_signal_item(diverging_sig)
                    self.tableswitch.setItem(i, 4, diverging_item)
            else:
                self.tableswitch.setRowCount(1)
                self.tableswitch.setColumnCount(5)
                self.tableswitch.setHorizontalHeaderLabels([
                    "Block", 
                    "Position",
                    "Prev Signal",
                    "Straight Signal", 
                    "Diverging Signal"])
                self.tableswitch.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                self.tableswitch.verticalHeader().setVisible(False)
                for col in range(5): self.tableswitch.setItem(0, col, QTableWidgetItem("No switches"))
            crossing_blocks = self.backend.crossing_blocks
            if crossing_blocks:
                self.tablecrossing.setRowCount(len(crossing_blocks))
                self.tablecrossing.setColumnCount(3)
                self.tablecrossing.setHorizontalHeaderLabels(["Crossing ID", "Block", "Status"])
                self.tablecrossing.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                self.tablecrossing.verticalHeader().setVisible(False)
                for i, (cid, block_id) in enumerate(crossing_blocks.items()):
                    gate_status = False
                    try:
                        seg = self.backend.track_model.segments.get(block_id)
                        if seg and hasattr(seg, 'gate_status'): gate_status = seg.gate_status
                    except Exception: pass
                    self.tablecrossing.setItem(i, 0, QTableWidgetItem(str(cid)))
                    self.tablecrossing.setItem(i, 1, QTableWidgetItem(str(block_id)))
                    status_text = "Active" if gate_status else "Inactive"
                    item = QTableWidgetItem(status_text)
                    item.setData(Qt.ItemDataRole.UserRole, gate_status)
                    self._apply_editable(item, editable=self.manual_mode_enabled)
                    self.tablecrossing.setItem(i, 2, item)
            else:
                self.tablecrossing.setRowCount(1)
                self.tablecrossing.setColumnCount(3)
                self.tablecrossing.setHorizontalHeaderLabels(["Crossing ID", "Block", "Status"])
                self.tablecrossing.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                self.tablecrossing.verticalHeader().setVisible(False)
                for col in range(3): self.tablecrossing.setItem(0, col, QTableWidgetItem("No crossings"))
            self.tableswitch.cellClicked.connect(self._on_switch_clicked)
            self.tablecrossing.cellClicked.connect(self._on_crossing_clicked)
        except Exception: 
            logger.exception("failed to refresh tables somehow. what did you do lol")

    def _create_signal_item(self, signal_state) -> QTableWidgetItem:
        if isinstance(signal_state, SignalState):
            sig_text = signal_state.name.title()
            item = QTableWidgetItem(sig_text)
            self._color_signal_item(item, signal_state)
        else:
            sig_text = str(signal_state) if signal_state != "N/A" else "N/A"
            item = QTableWidgetItem(sig_text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item
    
    def _set_table_item(self, table, row: int, col: int, text: str, editable: bool = False) -> None:
        item = QTableWidgetItem(text)
        self._apply_editable(item, editable=editable)
        table.setItem(row, col, item)

    def _set_table_item_with_viewonly(self, table, row: int, col: int, text: str, editable: bool = False, view_only: bool = False) -> None:
        item = QTableWidgetItem(text)
        self._apply_editable(item, editable=editable)
        if view_only:
            item.setBackground(QColor(200, 200, 200))
            item.setForeground(QColor(100, 100, 100))
        table.setItem(row, col, item)

    def _apply_editable(self, item: QTableWidgetItem, editable: bool = False) -> None:
        if editable: item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        else: item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def _color_signal_item(self, item: QTableWidgetItem, sig: SignalState) -> None:
        if sig == SignalState.RED: item.setBackground(Qt.GlobalColor.red)
        elif sig == SignalState.YELLOW: item.setBackground(Qt.GlobalColor.yellow)
        elif sig == SignalState.GREEN: 
            item.setBackground(Qt.GlobalColor.green)
            item.setForeground(Qt.GlobalColor.black)
        elif sig == SignalState.SUPERGREEN:
            item.setBackground(Qt.GlobalColor.darkGreen)
            item.setForeground(Qt.GlobalColor.black)

    def _on_switch_clicked(self, row: int, col: int) -> None:
        if not self.manual_mode_enabled: return
        try:
            if col == 1:
                sid = int(self.tableswitch.item(row, 0).text())
                current = self.backend.switches.get(sid, 0)
                next_pos = 1 if current == 0 else 0
                self.backend.safe_set_switch(sid, next_pos)
        except Exception as exc:
            QMessageBox.warning(self, "Maintenance click dont work :(", str(exc))
            self.refresh_tables()

    def _on_crossing_clicked(self, row: int, col: int) -> None:
        if not self.manual_mode_enabled: return
        try:
            if col == 2:
                cid = int(self.tablecrossing.item(row, 0).text())
                current = self.backend.crossings.get(cid, False)
                next_status = not current
                self.backend.safe_set_crossing(cid, next_status)
        except Exception as exc:
            QMessageBox.warning(self, "Maintenance click dont work :(", str(exc))
            self.refresh_tables()

    def _update_clock_display(self, current_time) -> None:
        try:
            time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
            self.clock_label.setText(f"Time: {time_str}")
            for controller in self.controllers.values():
                controller.set_time(current_time)
        except Exception: logger.exception("cant update clock display")