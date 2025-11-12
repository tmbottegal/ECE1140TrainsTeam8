from __future__ import annotations
import sys,os,logging
from typing import TYPE_CHECKING, Dict, NoReturn
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

_pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)

from universal.universal import SignalState
from track_controller_backend import TrackControllerBackend
from trackModel.track_model_backend import TrackNetwork as TrackModelNetwork

if TYPE_CHECKING:
    from track_controller_backend import TrackControllerBackend

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

class TrackControllerUI(QWidget):
    """Main application window for the Track Controller module."""
    def __init__(self, controllers: Dict[str, "TrackControllerBackend"], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controllers = controllers
        self.backend = next(iter(self.controllers.values()))
        self.manual_mode_enabled = False
        self.current_plc_file = None
        try:
            for c in self.controllers.values():
                c.add_listener(self.refresh_tables)
        except Exception:
            logger.exception("Failed to attach refresh listener to backend(s).")

        self._build_ui()
        self.tablemain.cellClicked.connect(self._on_block_clicked)
        self.tableswitch.cellClicked.connect(self._on_switch_clicked)
        self.tablecrossing.cellClicked.connect(self._on_crossing_clicked)
        self.plc_button.clicked.connect(self._on_plc_upload)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        top_row = QHBoxLayout()
        self.dropdown_text = QLabel("Track Controller")
        font_title = QFont()
        font_title.setPointSize(16)
        font_title.setBold(True)
        self.dropdown_text.setFont(font_title)
        top_row.addWidget(self.dropdown_text)
        top_row.addStretch()
        self.track_picker = QComboBox()
        line_names = list(self.controllers.keys())
        self.track_picker.addItems(line_names)
        self.track_picker.setCurrentIndex(0)
        self.track_picker.setFixedHeight(32)
        self.track_picker.setFixedWidth(220)
        font_drop = QFont()
        font_drop.setPointSize(14)
        font_drop.setBold(True)
        self.track_picker.setFont(font_drop)
        self.track_picker.currentTextChanged.connect(self.switch_line)
        top_row.addWidget(self.track_picker)
        layout.addLayout(top_row)
        #scroll area for tables
        self.table_hud = QScrollArea()
        self.table_hud.setWidgetResizable(True)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self._add_table("Blocks", "tablemain")
        self._add_table("Switches", "tableswitch")
        self._add_table("Crossings", "tablecrossing")
        self.table_hud.setWidget(self.container)
        layout.addWidget(self.table_hud)
        #bottom controls
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
        #clock
        self.clock_label = QLabel("Time: 2000-01-01 00:00:00")
        font_clock = QFont()
        font_clock.setPointSize(14)
        font_clock.setBold(True)
        self.clock_label.setFont(font_clock)
        self.clock_label.setFixedHeight(bigboi.height() * 2)
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet("QLabel { border: 2px solid gray; padding: 5px; background-color: #000000; }")
        bottom_row.addWidget(self.clock_label)
        #maintenace button
        self.manual_button = QPushButton("Maintenance Mode")
        self.manual_button.setCheckable(True)
        self.manual_button.setFixedHeight(bigboi.height() * 2)
        self.manual_button.toggled.connect(self.toggle_manual_mode)
        bottom_row.addWidget(self.manual_button)
        layout.addLayout(bottom_row)

    def _add_table(self, label_text: str, attr_name: str) -> None:
        self.container_layout.addWidget(QLabel(label_text))
        table = QTableWidget()
        setattr(self, attr_name, table)
        self.container_layout.addWidget(table)

    def switch_line(self, line_name: str) -> None:
        try:
            try:
                self.backend.remove_listener(self.refresh_tables)
            except Exception:
                pass
            self.backend = self.controllers[line_name]
            self.backend.add_listener(self.refresh_tables)
            self.dropdown_text.setText(f"Track: {line_name}")
            self.refresh_tables()
        except Exception:
            logger.exception("Failed to switch to line %s", line_name)

    def toggle_manual_mode(self, enabled: bool) -> None:
        self.manual_mode_enabled = enabled
        logger.info("Maintenance Mode %s", "enabled" if enabled else "disabled")
        try:
            for c in self.controllers.values():
                c.set_maintenance_mode(enabled)
        except Exception:
            logger.exception("Failed to set maintenance mode on controllers")
        self.refresh_tables()

    def _on_plc_upload(self) -> None:
        """Handle PLC file upload button click."""
        if not self.manual_mode_enabled:
            QMessageBox.warning(
                self, 
                "Maintenance Mode Required",
                "You must enable Maintenance Mode before uploading a PLC file."
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PLC File",
            "",
            "PLC Files (*.txt *.plc *.py)"
        )
        if not file_path:
            logger.info("PLC file selection cancelled.")
            return 
        
        try:
            self.backend.upload_plc(file_path)
            logger.info("After PLC upload - commanded speeds: %s", self.backend._commanded_speed_mps)
            logger.info("After PLC upload - commanded auth: %s", self.backend._commanded_auth_m)
            filename = os.path.basename(file_path)
            self.current_plc_file = file_path
            self.filename_box.setText(f"File: {filename}")
            self.refresh_tables()
            logger.info("PLC file %s uploaded for %s", file_path, self.backend.line_name)

        except PermissionError as e:
            QMessageBox.warning(
                self,
                "Permission Error",
                str(e)
            )
            logger.warning("PLC upload failed - permission error: %s", e)
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "PLC Upload Failed",
                f"Failed to upload PLC file:\n{str(e)}"
            )
            logger.exception("PLC upload failed: %s", file_path)

    def refresh_tables(self) -> None:
        try:
            try:
                self.tablemain.itemChanged.disconnect()
            except Exception:
                pass
            try:
                self.tableswitch.itemChanged.disconnect()
            except Exception:
                pass
            try:
                self.tablecrossing.itemChanged.disconnect()
            except Exception:
                pass

            line_block_map = {
                "Blue Line": range(1, 16),
                "Green Line": list(range(1, 63)) + list(range(122, 151)),
                "Red Line": range(1, 34),
            }
            block_ids = line_block_map.get(self.backend.line_name, [])
            self.tablemain.setRowCount(len(block_ids))
            self.tablemain.setColumnCount(7)
            self.tablemain.setHorizontalHeaderLabels([
                "Block", "Suggested Speed (mph)", "Suggested Authority (yd)",
                "Occupancy", "Commanded Speed (mph)", "Commanded Authority (yd)",
                "Signal State"
            ])
            self.tablemain.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.tablemain.verticalHeader().setVisible(False)
            blocks_data = self.backend.blocks
            for i, block in enumerate(block_ids):
                self.tablemain.setItem(i, 0, QTableWidgetItem(str(block)))
                data = blocks_data.get(block, {})

                self._set_table_item(self.tablemain, i, 1, str(data.get("suggested_speed", "N/A")), editable=False)
                self._set_table_item(self.tablemain, i, 2, str(data.get("suggested_auth", "N/A")), editable=False)

                occ_val = data.get("occupied")
                if occ_val == "N/A":
                    occ_text = "N/A"
                else:
                    occ_text = "Yes" if occ_val else "No"
                self._set_table_item(self.tablemain, i, 3, occ_text, editable=False)

                cmd_speed = data.get("commanded_speed")
                cmd_auth = data.get("commanded_auth")
                self._set_table_item(self.tablemain, i, 4, str(cmd_speed), editable=False)
                self._set_table_item(self.tablemain, i, 5, str(cmd_auth), editable=False)

                sig = data.get("signal")
                if isinstance(sig, SignalState):
                    sig_text = sig.name.title()
                else:
                    sig_text = "N/A"
                item = QTableWidgetItem(sig_text)
                if isinstance(sig, SignalState):
                    self._color_signal_item(item, sig)
                else:
                    item.setBackground(Qt.GlobalColor.blue)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tablemain.setItem(i, 6, item)

            switches = self.backend.switches
            
            self.tableswitch.setRowCount(max(len(switches), 1))
            self.tableswitch.setColumnCount(2)
            self.tableswitch.setHorizontalHeaderLabels(["Switch ID", "Blocks"])
            self.tableswitch.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            
            for i, (sid, pos_int) in enumerate(switches.items()):
                self.tableswitch.setItem(i, 0, QTableWidgetItem(str(sid)))
                
                pos_text = "Normal" if pos_int == 0 else "Alternate"
                item = QTableWidgetItem(pos_text)

                item.setData(Qt.ItemDataRole.UserRole, pos_int)
                self._apply_editable(item, editable=self.manual_mode_enabled)
                self.tableswitch.setItem(i, 2, item)
            
            if not switches:
                for col in range(2):
                    self.tableswitch.setItem(0, col, QTableWidgetItem(""))

            crossings = self.backend.crossings
            crossing_blocks = self.backend.crossing_blocks
            if not crossings:
                if self.backend.line_name == "Blue Line":
                    crossing_blocks[1] = 3
                elif self.backend.line_name == "Red Line":
                    crossing_blocks[1] = 11
                elif self.backend.line_name == "Green Line":
                    crossing_blocks[1] = 19
                for cid in crossing_blocks:
                    crossings[cid] = False 
            
            self.tablecrossing.setRowCount(max(len(crossings), 1))
            self.tablecrossing.setColumnCount(3)
            self.tablecrossing.setHorizontalHeaderLabels(["Crossing ID", "Block", "Status"])
            self.tablecrossing.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            
            for i, (cid, status_bool) in enumerate(crossings.items()):
                block = crossing_blocks.get(cid, "-")
                self.tablecrossing.setItem(i, 0, QTableWidgetItem(str(cid)))
                self.tablecrossing.setItem(i, 1, QTableWidgetItem(str(block)))
                
                status_text = "Active" if status_bool else "Inactive"
                item = QTableWidgetItem(status_text)

                item.setData(Qt.ItemDataRole.UserRole, status_bool)
                self._apply_editable(item, editable=self.manual_mode_enabled)
                self.tablecrossing.setItem(i, 2, item)
            
            if not crossings:
                for col in range(3):
                    self.tablecrossing.setItem(0, col, QTableWidgetItem(""))

            self.tablemain.cellClicked.connect(self._on_block_clicked)
            self.tableswitch.cellClicked.connect(self._on_switch_clicked)
            self.tablecrossing.cellClicked.connect(self._on_crossing_clicked)

        except Exception:
            logger.exception("Failed to refresh tables.")

    def _set_table_item(self, table, row: int, col: int, text: str, editable: bool = False) -> None:
        item = QTableWidgetItem(text)
        self._apply_editable(item, editable=editable)
        table.setItem(row, col, item)

    def _apply_editable(self, item: QTableWidgetItem, editable: bool = False) -> None:
        if editable:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        else:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def _color_signal_item(self, item: QTableWidgetItem, sig: SignalState) -> None:
        if sig == SignalState.RED:
            item.setBackground(Qt.GlobalColor.red)
        elif sig == SignalState.YELLOW:
            item.setBackground(Qt.GlobalColor.yellow)
        elif sig == SignalState.GREEN:
            item.setBackground(Qt.GlobalColor.green)
        elif sig == SignalState.SUPERGREEN:
            item.setBackground(Qt.GlobalColor.darkGreen)

    def _on_block_clicked(self, row: int, col: int) -> None:
        if not self.manual_mode_enabled:
            return
        if col in (3, 6):
            QMessageBox.information(self, "Maintenance Mode", 
                "Occupancy and signal state cannot be edited from UI in maintenance mode. "
                "Use PLC upload for signal/command changes.")
            return

    def _on_switch_clicked(self, row: int, col: int) -> None:
        if not self.manual_mode_enabled:
            return
        try:
            if col == 2:
                sid = int(self.tableswitch.item(row, 0).text())
                current = self.backend.switches.get(sid, 0)  # Get int value
                # Toggle: 0 -> 1, 1 -> 0
                next_pos = 1 if current == 0 else 0
                self.backend.safe_set_switch(sid, next_pos)
        except Exception as exc:
            QMessageBox.warning(self, "Maintenance Click Failed", str(exc))
            self.refresh_tables()

    def _on_crossing_clicked(self, row: int, col: int) -> None:
        if not self.manual_mode_enabled:
            return
        try:
            if col == 2:
                cid = int(self.tablecrossing.item(row, 0).text())
                current = self.backend.crossings.get(cid, False)
                next_status = not current
                self.backend.safe_set_crossing(cid, next_status)
        except Exception as exc:
            QMessageBox.warning(self, "Maintenance Click Failed", str(exc))
            self.refresh_tables()
