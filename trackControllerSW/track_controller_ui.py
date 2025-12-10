"""Track Controller UI module.

This module provides the PyQt6-based graphical user interface for the track
controller system, including status tables, system logs, and maintenance mode
controls.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_PKG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PKG_ROOT not in sys.path:
    sys.path.append(_PKG_ROOT)

from track_controller_backend import TrackControllerBackend
from universal.global_clock import clock as global_clock
from universal.universal import SignalState

if TYPE_CHECKING:
    from track_controller_backend import TrackControllerBackend

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


class QTextEditLogger(logging.Handler):
    """Custom logging handler that outputs to a QTextEdit widget."""

    def __init__(self, text_edit: QTextEdit) -> None:
        """Initialize the logger handler.

        Args:
            text_edit: The QTextEdit widget to output log messages to.
        """
        super().__init__()
        self.text_edit = text_edit
        self.setFormatter(
            logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        )

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the text edit widget.

        Args:
            record: The log record to emit.
        """
        msg = self.format(record)
        self.text_edit.append(msg)
        self.text_edit.moveCursor(QTextCursor.MoveOperation.End)


class TrackControllerUI(QWidget):
    """Main UI widget for the Track Controller system.

    This widget provides a comprehensive interface for monitoring and controlling
    track blocks, switches, and crossings across multiple railway lines.

    Attributes:
        VIEW_ONLY_BLOCKS: Dictionary mapping line names to lists of block IDs
            that should be displayed as view-only.
    """

    VIEW_ONLY_BLOCKS = {
        'Red Line': list(range(35, 46)) + list(range(67, 72)),
        'Green Line': list(range(63, 69)) + list(range(117, 122)),
    }

    def __init__(
        self,
        controllers: Dict[str, TrackControllerBackend],
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the Track Controller UI.

        Args:
            controllers: Dictionary mapping line names to their backend controllers.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.controllers = controllers
        self.backend = next(iter(self.controllers.values()))
        self.manual_mode_enabled = False
        self.current_plc_file = None

        # Initialize fonts
        self.bold_font = QFont()
        self.bold_font.setBold(True)
        self.big_font = QFont(self.bold_font)
        self.big_font.setPointSize(self.bold_font.pointSize() * 2)

        self.resize(1200, 800)

        # Register listeners
        try:
            for controller in self.controllers.values():
                controller.add_listener(self.refresh_tables)
        except Exception:
            logger.exception('Failed to attach to backend')

        global_clock.register_listener(self._update_clock_display)

        # Build UI and setup
        self._build_ui()
        self._setup_logging()

        # Connect signals
        self.tableswitch.cellClicked.connect(self._on_switch_clicked)
        self.tablecrossing.cellClicked.connect(self._on_crossing_clicked)
        self.plc_button.clicked.connect(self._on_plc_upload)

        self._update_clock_display(global_clock.get_time())

    def _build_ui(self) -> None:
        """Build the main user interface layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Top row with line selector
        self._build_top_row(layout)

        # Main tabbed interface
        self.main_tabs = QTabWidget()
        self.main_tabs.setFont(self.bold_font)
        self.main_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Build tabs
        self._build_tables_tab()
        self._build_logs_tab()

        self.main_tabs.addTab(self.table_widget, 'Status Tables')
        self.main_tabs.addTab(self.logs_widget, 'System Logs')
        layout.addWidget(self.main_tabs, stretch=1)

        # Bottom row with controls
        self._build_bottom_row(layout)

    def _build_top_row(self, parent_layout: QVBoxLayout) -> None:
        """Build the top row containing the line selector.

        Args:
            parent_layout: The parent layout to add the top row to.
        """
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.dropdown_text = QLabel('Wayside SW')
        self.dropdown_text.setFont(self.big_font)
        self.dropdown_text.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        top_row.addWidget(self.dropdown_text)
        top_row.addStretch()

        self.track_picker = QComboBox()
        self.track_picker.addItems(list(self.controllers.keys()))
        self.track_picker.setCurrentIndex(0)
        self.track_picker.setMinimumHeight(32)
        self.track_picker.setMinimumWidth(150)
        self.track_picker.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.track_picker.setFont(self.big_font)
        self.track_picker.currentTextChanged.connect(self.switch_line)
        top_row.addWidget(self.track_picker)

        parent_layout.addLayout(top_row)

    def _build_tables_tab(self) -> None:
        """Build the status tables tab."""
        self.table_widget = QWidget()
        table_layout = QVBoxLayout(self.table_widget)
        table_layout.setContentsMargins(5, 5, 5, 5)
        table_layout.setSpacing(8)

        # Blocks table
        self._add_table('Blocks', 'tablemain')
        self.tablemain.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.tablemain.setMinimumHeight(200)
        table_layout.addWidget(self.tablemain, stretch=5)

        # Switches table
        self._add_table('Switches', 'tableswitch')
        self.tableswitch.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.tableswitch.setMinimumHeight(100)
        table_layout.addWidget(self.tableswitch, stretch=2)

        # Crossings table
        self._add_table('Crossings', 'tablecrossing')
        self.tablecrossing.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.tablecrossing.setMinimumHeight(80)
        table_layout.addWidget(self.tablecrossing, stretch=1)

    def _build_logs_tab(self) -> None:
        """Build the system logs tab."""
        self.logs_widget = QWidget()
        logs_layout = QVBoxLayout(self.logs_widget)
        logs_layout.setContentsMargins(5, 5, 5, 5)
        logs_layout.setSpacing(8)

        # Logs header with controls
        logs_header = QHBoxLayout()
        logs_header.setSpacing(10)

        logs_title = QLabel('System Logs')
        logs_title.setFont(self.big_font)
        logs_title.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        logs_header.addWidget(logs_title)
        logs_header.addStretch()

        # Log level filter
        self.log_level_label = QLabel('Filter Level:')
        self.log_level_label.setFont(self.bold_font)
        self.log_level_label.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        logs_header.addWidget(self.log_level_label)

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(
            ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        )
        self.log_level_combo.setCurrentText('INFO')
        self.log_level_combo.setFont(self.bold_font)
        self.log_level_combo.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.log_level_combo.currentTextChanged.connect(self._on_log_level_changed)
        logs_header.addWidget(self.log_level_combo)

        # Auto-scroll checkbox
        self.auto_scroll_check = QCheckBox('Auto-scroll')
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.setFont(self.bold_font)
        self.auto_scroll_check.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        logs_header.addWidget(self.auto_scroll_check)

        # Clear logs button
        clear_logs_btn = QPushButton('Clear Logs')
        clear_logs_btn.setFont(self.bold_font)
        clear_logs_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        clear_logs_btn.clicked.connect(self._clear_logs)
        logs_header.addWidget(clear_logs_btn)

        logs_layout.addLayout(logs_header)

        # Logs display area
        self.logs_display = QTextEdit()
        self.logs_display.setReadOnly(True)
        self.logs_display.setFont(QFont('Courier', 9))
        self.logs_display.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.logs_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        logs_layout.addWidget(self.logs_display)

    def _build_bottom_row(self, parent_layout: QVBoxLayout) -> None:
        """Build the bottom row containing main controls.

        Args:
            parent_layout: The parent layout to add the bottom row to.
        """
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        # PLC upload button
        self.plc_button = QPushButton('PLC File Upload')
        self.plc_button.setFont(self.bold_font)
        self.plc_button.setMinimumHeight(50)
        self.plc_button.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        bottom_row.addWidget(self.plc_button)

        # Filename display
        self.filename_box = QLineEdit('File: None')
        self.filename_box.setFont(self.big_font)
        self.filename_box.setReadOnly(True)
        self.filename_box.setMinimumWidth(200)
        self.filename_box.setMinimumHeight(50)
        self.filename_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        bottom_row.addWidget(self.filename_box, stretch=1)

        # Clock display
        self.clock_label = QLabel('Time: 2000-01-01 00:00:00')
        self.clock_label.setFont(self.big_font)
        self.clock_label.setMinimumHeight(50)
        self.clock_label.setMinimumWidth(250)
        self.clock_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet(
            'QLabel { border: 2px solid gray; padding: 5px; background-color: #000; }'
        )
        bottom_row.addWidget(self.clock_label)

        # Maintenance mode button
        self.manual_button = QPushButton('Maintenance Mode')
        self.manual_button.setFont(self.bold_font)
        self.manual_button.setCheckable(True)
        self.manual_button.setMinimumHeight(50)
        self.manual_button.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.manual_button.toggled.connect(self.toggle_manual_mode)
        bottom_row.addWidget(self.manual_button)

        parent_layout.addLayout(bottom_row)

    def _setup_logging(self) -> None:
        """Configure the logging system for the UI."""
        self.log_handler = QTextEditLogger(self.logs_display)
        self.log_handler.setLevel(logging.INFO)
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        logger.info('Track Controller UI initialized with logging tab')

    def _on_log_level_changed(self, level_str: str) -> None:
        """Handle log level filter changes.

        Args:
            level_str: The selected log level string.
        """
        level_map = {
            'ALL': logging.DEBUG,
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        new_level = level_map.get(level_str, logging.INFO)
        self.log_handler.setLevel(new_level)
        logger.info('Log level changed to %s', level_str)

    def _clear_logs(self) -> None:
        """Clear all logs from the display."""
        self.logs_display.clear()
        logger.info('Logs cleared')

    def _add_table(self, label_text: str, attr_name: str) -> None:
        """Create and store a table widget.

        Args:
            label_text: The label text for the table (currently unused).
            attr_name: The attribute name to store the table under.
        """
        table = QTableWidget()
        table.setFont(self.bold_font)
        setattr(self, attr_name, table)

    def _is_view_only_block(self, block_id: int) -> bool:
        """Check if a block should be displayed as view-only.

        Args:
            block_id: The ID of the block to check.

        Returns:
            True if the block is view-only, False otherwise.
        """
        view_only = self.VIEW_ONLY_BLOCKS.get(self.backend.line_name, [])
        return block_id in view_only

    def switch_line(self, line_name: str) -> None:
        """Switch the displayed line.

        Args:
            line_name: The name of the line to switch to.
        """
        try:
            try:
                self.backend.remove_listener(self.refresh_tables)
            except Exception:
                pass

            self.backend = self.controllers[line_name]
            self.backend.add_listener(self.refresh_tables)
            self.dropdown_text.setText(f'Track: {line_name}')
            self.refresh_tables()
        except Exception:
            logger.exception('Failed to switch to line %s', line_name)

    def toggle_manual_mode(self, enabled: bool) -> None:
        """Toggle maintenance mode on or off.

        Args:
            enabled: Whether maintenance mode should be enabled.
        """
        self.manual_mode_enabled = enabled
        logger.info('Maintenance Mode %s', 'enabled' if enabled else 'disabled')
        try:
            for controller in self.controllers.values():
                controller.set_maintenance_mode(enabled)
        except Exception:
            logger.exception('Failed to set maintenance mode')
        self.refresh_tables()

    def _on_plc_upload(self) -> None:
        """Handle PLC file upload button click."""
        if not self.manual_mode_enabled:
            QMessageBox.warning(
                self,
                'Maintenance Mode Required',
                'Please enable Maintenance Mode before uploading the PLC file.',
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Open PLC File', '', 'PLC Files (*.txt *.plc *.py)'
        )
        if not file_path:
            logger.info('PLC upload cancelled')
            return

        try:
            self.backend.upload_plc(file_path)
            logger.info('Commanded speeds: %s', self.backend._commanded_speed_mps)
            logger.info('Commanded authority: %s', self.backend._commanded_auth_m)

            filename = os.path.basename(file_path)
            self.current_plc_file = file_path
            self.filename_box.setText(f'File: {filename}')
            self.refresh_tables()
            logger.info(
                'PLC file %s uploaded for %s', file_path, self.backend.line_name
            )
        except PermissionError as e:
            QMessageBox.warning(self, 'Permission Error', str(e))
            logger.warning('PLC upload failed - permission error: %s', e)
        except Exception:
            logger.exception('PLC upload failed: %s', file_path)
            QMessageBox.critical(
                self,
                'PLC Upload Failed',
                f'Failed to upload PLC file. Check logs for details.',
            )

    def refresh_tables(self) -> None:
        """Refresh all data tables with current backend state."""
        try:
            # Disconnect item changed signals to prevent loops
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

            self._refresh_blocks_table()
            self._refresh_switches_table()
            self._refresh_crossings_table()

            # Reconnect signals
            self.tableswitch.cellClicked.connect(self._on_switch_clicked)
            self.tablecrossing.cellClicked.connect(self._on_crossing_clicked)
        except Exception:
            logger.exception('Failed to refresh tables')

    def _refresh_blocks_table(self) -> None:
        """Refresh the blocks status table."""
        line_block_map = {
            'Green Line': (
                list(range(1, 63))
                + list(range(63, 69))
                + list(range(117, 122))
                + list(range(122, 151))
            ),
            'Red Line': (
                list(range(1, 34)) + list(range(35, 46)) + list(range(67, 72))
            ),
        }
        block_ids = line_block_map.get(self.backend.line_name, [])

        self.tablemain.setRowCount(len(block_ids))
        self.tablemain.setColumnCount(6)
        self.tablemain.setHorizontalHeaderLabels([
            'Block',
            'Suggested Speed (mph)',
            'Suggested Authority (yd)',
            'Occupancy',
            'Commanded Speed (mph)',
            'Commanded Authority (yd)',
        ])
        self.tablemain.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tablemain.verticalHeader().setVisible(False)

        blocks_data = self.backend.blocks

        for i, block in enumerate(block_ids):
            is_view_only = self._is_view_only_block(block)
            data = blocks_data.get(block, {})

            # Block ID
            block_item = QTableWidgetItem(str(block))
            if is_view_only:
                block_item.setBackground(QColor(200, 200, 200))
                block_item.setForeground(QColor(100, 100, 100))
            self.tablemain.setItem(i, 0, block_item)

            # Suggested speed and authority
            self._set_table_item_with_view_only(
                self.tablemain,
                i,
                1,
                str(data.get('suggested_speed', 'N/A')),
                editable=False,
                view_only=is_view_only,
            )
            self._set_table_item_with_view_only(
                self.tablemain,
                i,
                2,
                str(data.get('suggested_auth', 'N/A')),
                editable=False,
                view_only=is_view_only,
            )

            # Occupancy
            occ_val = data.get('occupied')
            if occ_val == 'N/A':
                occ_text = 'N/A'
            else:
                occ_text = 'Occupied' if occ_val else 'Unoccupied'

            occ_item = QTableWidgetItem(occ_text)
            self._apply_editable(occ_item, editable=False)

            if occ_val == 'N/A':
                pass
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

            # Commanded speed and authority
            cmd_speed = data.get('commanded_speed')
            cmd_auth = data.get('commanded_auth')
            self._set_table_item_with_view_only(
                self.tablemain,
                i,
                4,
                str(cmd_speed),
                editable=False,
                view_only=is_view_only,
            )
            self._set_table_item_with_view_only(
                self.tablemain,
                i,
                5,
                str(cmd_auth),
                editable=False,
                view_only=is_view_only,
            )

    def _refresh_switches_table(self) -> None:
        """Refresh the switches status table."""
        switches = self.backend.switches

        if switches:
            self.tableswitch.setRowCount(len(switches))
            self.tableswitch.setColumnCount(5)
            self.tableswitch.setHorizontalHeaderLabels([
                'Block',
                'Position',
                'Prev Signal',
                'Straight Signal',
                'Diverging Signal',
            ])
            self.tableswitch.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )
            self.tableswitch.verticalHeader().setVisible(False)

            for i, (sid, pos_int) in enumerate(switches.items()):
                # Switch ID
                self.tableswitch.setItem(i, 0, QTableWidgetItem(str(sid)))

                # Position
                pos_text = 'Straight' if pos_int == 0 else 'Diverging'
                item = QTableWidgetItem(pos_text)
                item.setData(Qt.ItemDataRole.UserRole, pos_int)
                self._apply_editable(item, editable=self.manual_mode_enabled)
                self.tableswitch.setItem(i, 1, item)

                # Signals
                switch_signals = getattr(self.backend, '_switch_signals', {})

                prev_sig = switch_signals.get((sid, 0), 'N/A')
                prev_item = self._create_signal_item(prev_sig)
                self.tableswitch.setItem(i, 2, prev_item)

                straight_sig = switch_signals.get((sid, 1), 'N/A')
                straight_item = self._create_signal_item(straight_sig)
                self.tableswitch.setItem(i, 3, straight_item)

                diverging_sig = switch_signals.get((sid, 2), 'N/A')
                diverging_item = self._create_signal_item(diverging_sig)
                self.tableswitch.setItem(i, 4, diverging_item)
        else:
            self._set_empty_table(
                self.tableswitch,
                ['Block', 'Position', 'Prev Signal', 'Straight Signal', 'Diverging Signal'],
                'No switches',
            )

    def _refresh_crossings_table(self) -> None:
        """Refresh the crossings status table."""
        crossing_blocks = self.backend.crossing_blocks

        if crossing_blocks:
            self.tablecrossing.setRowCount(len(crossing_blocks))
            self.tablecrossing.setColumnCount(3)
            self.tablecrossing.setHorizontalHeaderLabels(
                ['Crossing ID', 'Block', 'Status']
            )
            self.tablecrossing.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )
            self.tablecrossing.verticalHeader().setVisible(False)

            for i, (cid, block_id) in enumerate(crossing_blocks.items()):
                gate_status = False
                try:
                    seg = self.backend.track_model.segments.get(block_id)
                    if seg and hasattr(seg, 'gate_status'):
                        gate_status = seg.gate_status
                except Exception:
                    pass

                self.tablecrossing.setItem(i, 0, QTableWidgetItem(str(cid)))
                self.tablecrossing.setItem(i, 1, QTableWidgetItem(str(block_id)))

                status_text = 'Active' if gate_status else 'Inactive'
                item = QTableWidgetItem(status_text)
                item.setData(Qt.ItemDataRole.UserRole, gate_status)
                self._apply_editable(item, editable=self.manual_mode_enabled)
                self.tablecrossing.setItem(i, 2, item)
        else:
            self._set_empty_table(
                self.tablecrossing,
                ['Crossing ID', 'Block', 'Status'],
                'No crossings',
            )

    def _set_empty_table(
        self, table: QTableWidget, headers: list[str], message: str
    ) -> None:
        """Set a table to display an empty state message.

        Args:
            table: The table widget to configure.
            headers: List of header labels.
            message: The message to display in the empty table.
        """
        table.setRowCount(1)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        for col in range(len(headers)):
            table.setItem(0, col, QTableWidgetItem(message))

    def _create_signal_item(self, signal_state) -> QTableWidgetItem:
        """Create a table item for displaying signal state.

        Args:
            signal_state: The signal state to display (SignalState or string).

        Returns:
            A QTableWidgetItem configured for the signal state.
        """
        if isinstance(signal_state, SignalState):
            sig_text = signal_state.name.title()
            item = QTableWidgetItem(sig_text)
            self._color_signal_item(item, signal_state)
        else:
            sig_text = str(signal_state) if signal_state != 'N/A' else 'N/A'
            item = QTableWidgetItem(sig_text)

        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _set_table_item_with_view_only(
        self,
        table: QTableWidget,
        row: int,
        col: int,
        text: str,
        editable: bool = False,
        view_only: bool = False,
    ) -> None:
        """Set a table item with optional view-only styling.

        Args:
            table: The table widget.
            row: The row index.
            col: The column index.
            text: The text to display.
            editable: Whether the item should be editable.
            view_only: Whether to apply view-only styling.
        """
        item = QTableWidgetItem(text)
        self._apply_editable(item, editable=editable)
        if view_only:
            item.setBackground(QColor(200, 200, 200))
            item.setForeground(QColor(100, 100, 100))
        table.setItem(row, col, item)

    def _apply_editable(
        self, item: QTableWidgetItem, editable: bool = False
    ) -> None:
        """Set whether a table item is editable.

        Args:
            item: The table item to configure.
            editable: Whether the item should be editable.
        """
        if editable:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        else:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def _color_signal_item(
        self, item: QTableWidgetItem, sig: SignalState
    ) -> None:
        """Apply color styling to a signal item based on its state.

        Args:
            item: The table item to color.
            sig: The signal state to represent.
        """
        if sig == SignalState.RED:
            item.setBackground(Qt.GlobalColor.red)
        elif sig == SignalState.YELLOW:
            item.setBackground(Qt.GlobalColor.yellow)
        elif sig == SignalState.GREEN:
            item.setBackground(Qt.GlobalColor.green)
            item.setForeground(Qt.GlobalColor.black)
        elif sig == SignalState.SUPERGREEN:
            item.setBackground(Qt.GlobalColor.darkGreen)
            item.setForeground(Qt.GlobalColor.black)

    def _on_switch_clicked(self, row: int, col: int) -> None:
        """Handle switch table cell clicks in maintenance mode.

        Args:
            row: The row index of the clicked cell.
            col: The column index of the clicked cell.
        """
        if not self.manual_mode_enabled:
            return

        try:
            if col == 1:  # Position column
                switch_id = int(self.tableswitch.item(row, 0).text())
                current_position = self.backend.switches.get(switch_id, 0)
                next_position = 1 if current_position == 0 else 0
                self.backend.safe_set_switch(switch_id, next_position)
        except Exception as exc:
            QMessageBox.warning(
                self,
                'Switch Control Error',
                f'Failed to toggle switch: {exc}'
            )
            logger.exception('Failed to toggle switch in maintenance mode')
            self.refresh_tables()

    def _on_crossing_clicked(self, row: int, col: int) -> None:
        """Handle crossing table cell clicks in maintenance mode.

        Args:
            row: The row index of the clicked cell.
            col: The column index of the clicked cell.
        """
        if not self.manual_mode_enabled:
            return

        try:
            if col == 2:  # Status column
                crossing_id = int(self.tablecrossing.item(row, 0).text())
                current_status = self.backend.crossings.get(crossing_id, False)
                next_status = not current_status
                self.backend.safe_set_crossing(crossing_id, next_status)
        except Exception as exc:
            QMessageBox.warning(
                self,
                'Crossing Control Error',
                f'Failed to toggle crossing: {exc}'
            )
            logger.exception('Failed to toggle crossing in maintenance mode')
            self.refresh_tables()

    def _update_clock_display(self, current_time) -> None:
        """Update the clock display with the current simulation time.

        Args:
            current_time: The current simulation time to display.
        """
        try:
            time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
            self.clock_label.setText(f'Time: {time_str}')
            for controller in self.controllers.values():
                controller.set_time(current_time)
        except Exception:
            logger.exception('Failed to update clock display')