from PyQt6 import QtWidgets, QtCore, QtGui
from .CTC_backend import TrackState, GREEN_LINE_DATA
from universal.global_clock import clock

# Keep UI-side constants in sync with backend for display
BLOCK_LEN_M = 50.0
MPS_TO_MPH = 2.23693629

LINE_DATA = {
    "Red Line": [],
    "Green Line": [],
}


class CTCWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Centralized Traffic Controller")

        cw = QtWidgets.QWidget(self)
        self.setCentralWidget(cw)

        # === Mode toggle toolbar (Manual / Auto) ===
        self.mode = "auto"  # default

        toolbar = QtWidgets.QToolBar("Mode Toolbar")
        toolbar.setMovable(False)
        toolbar.setStyleSheet("QToolBar { spacing: 10px; }")

        self.mode_label = QtWidgets.QLabel("Mode:")
        self.mode_label.setStyleSheet("font-weight: bold; font-size: 14pt;")

        self.mode_toggle_button = QtWidgets.QPushButton("Auto Mode")
        self.mode_toggle_button.setCheckable(True)
        self.mode_toggle_button.setChecked(False)
        self.mode_toggle_button.setStyleSheet("background-color: lightblue; font-weight: bold;")
        self.mode_toggle_button.toggled.connect(self.toggle_mode)

        toolbar.addWidget(self.mode_label)
        toolbar.addWidget(self.mode_toggle_button)
        toolbar.addSeparator()
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, toolbar)

        # === Backend state ===
        self.state = TrackState("Green Line", GREEN_LINE_DATA)
        self._trainInfoPage = None
        self._manualPage = None

        # === Tabs container ===
        self.tabs = QtWidgets.QTabWidget()

        # === OCCUPANCY TAB ===
        self.occupancyTab = QtWidgets.QWidget()
        occLayout = QtWidgets.QVBoxLayout(self.occupancyTab)

        # Line selector
        selectorRow = QtWidgets.QHBoxLayout()
        selectorRow.addWidget(QtWidgets.QLabel("Select Line:"))
        self.lineSelector = QtWidgets.QComboBox()
        self.lineSelector.addItems(["Red Line", "Green Line"])
        self.lineSelector.setCurrentText("Green Line")
        self.lineSelector.currentTextChanged.connect(self._reload_line)
        selectorRow.addWidget(self.lineSelector)
        selectorRow.addStretch(1)
        occLayout.addLayout(selectorRow)

        # Track table
        self.mapTable = QtWidgets.QTableWidget(0, 9)
        self.mapTable.setHorizontalHeaderLabels([
            "Section", "Block", "Status", "Station", "Station Side",
            "Switch", "Signal Light", "Crossing", "Speed Limit"
        ])
        self.mapTable.verticalHeader().setVisible(False)
        self.mapTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.mapTable.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.mapTable.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mapTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.mapTable.setMinimumHeight(220)

        self._reload_line("Green Line")
        occLayout.addWidget(self.mapTable)

        # Buttons under the table
        self.manualBtn = QtWidgets.QPushButton("Manual Override")
        self.infoBtn = QtWidgets.QPushButton("Train Information")
        self.uploadBtn = QtWidgets.QPushButton("Upload Schedule")
        self.maintBtn = QtWidgets.QPushButton("Maintenance / Inputs")
        self.dispatchBtn = QtWidgets.QPushButton("Dispatch Train")
        for b in (self.manualBtn, self.infoBtn, self.uploadBtn, self.maintBtn, self.dispatchBtn):
            b.setMinimumHeight(40)
            b.setStyleSheet("font-size:14px; font-weight:bold;")

        btnRow = QtWidgets.QHBoxLayout()
        btnRow.addWidget(self.dispatchBtn)
        btnRow.addWidget(self.manualBtn)
        btnRow.addWidget(self.infoBtn)
        btnRow.addWidget(self.uploadBtn)
        btnRow.addWidget(self.maintBtn)
        occLayout.addLayout(btnRow)

        # Connect buttons
        self.manualBtn.clicked.connect(self._manual_override)
        self.infoBtn.clicked.connect(self._train_info)
        self.uploadBtn.clicked.connect(self._upload_schedule)
        self.maintBtn.clicked.connect(self._maintenance_inputs)
        self.dispatchBtn.clicked.connect(self._dispatch_train)

        # Action area (below buttons)
        self.actionArea = QtWidgets.QStackedWidget()
        self.blankPage = QtWidgets.QWidget()
        self.actionArea.addWidget(self.blankPage)
        self.actionArea.setCurrentWidget(self.blankPage)
        occLayout.addWidget(self.actionArea)

        # === ISSUES TAB (placeholder) ===
        self.issuesTab = QtWidgets.QWidget()
        issuesLayout = QtWidgets.QVBoxLayout(self.issuesTab)
        issuesLayout.addWidget(QtWidgets.QLabel("Issues tab — reserved for diagnostics/logs."))

        # === Assemble tabs ===
        self.tabs.addTab(self.occupancyTab, "Occupancy")
        self.tabs.addTab(self.issuesTab, "Issues")

        # === Layout ===
        layout = QtWidgets.QVBoxLayout(cw)
        self.clockLabel = QtWidgets.QLabel(f"Sim Time: {clock.get_time_string()}")
        self.clockLabel.setStyleSheet("font-weight:bold; font-size:14px;")
        layout.addWidget(self.clockLabel)
        layout.addWidget(self.tabs, stretch=2)

        # === Simulation Timer (CTC controls global clock) ===
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)  # 1s per tick

    # ---------------------------------------------------------
    # Mode Toggle
    # ---------------------------------------------------------
    def toggle_mode(self, enabled: bool):
        if enabled:
            self.mode = "manual"
            self.mode_toggle_button.setText("Manual Mode (Active)")
            self.mode_toggle_button.setStyleSheet("background-color: lightgreen; font-weight: bold;")
        else:
            self.mode = "auto"
            self.mode_toggle_button.setText("Auto Mode (Active)")
            self.mode_toggle_button.setStyleSheet("background-color: lightblue; font-weight: bold;")

        self.state.set_mode(self.mode)
        self.dispatchBtn.setEnabled(self.mode == "manual")
        print(f"[CTC UI] Switched to {self.mode.upper()} mode.")

    # ---------------------------------------------------------
    # Line + Table Reload
    # ---------------------------------------------------------
    def _reload_line(self, line_name: str):
        if line_name != self.state.line_name:
            self.state.set_line(line_name, LINE_DATA[line_name])
        blocks = self.state.get_blocks()
        self.mapTable.setRowCount(len(blocks))

        for r, b in enumerate(blocks):
            rowdata = [
                b.section, b.block_id, b.status, b.station,
                b.station_side, b.switch, b.light,
                ("Yes" if b.crossing else ""), f"{b.speed_limit:.0f} km/h"
            ]
            for c, value in enumerate(rowdata):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                if c == 2:  # status color
                    if b.status == "occupied":
                        item.setBackground(QtGui.QColor("red"))
                        item.setForeground(QtGui.QColor("white"))
                    elif b.status == "closed":
                        item.setBackground(QtGui.QColor("gray"))
                        item.setForeground(QtGui.QColor("white"))
                if c == 6:  # signal color
                    light = str(value).upper()
                    if light == "RED":
                        item.setBackground(QtGui.QColor("#b00020"))
                        item.setForeground(QtGui.QColor("white"))
                    elif light == "YELLOW":
                        item.setBackground(QtGui.QColor("#d7b600"))
                        item.setForeground(QtGui.QColor("black"))
                    elif light == "GREEN":
                        item.setBackground(QtGui.QColor("#1b5e20"))
                        item.setForeground(QtGui.QColor("white"))
                self.mapTable.setItem(r, c, item)

        # Auto-refresh subpages
        if self._trainInfoPage and self.actionArea.currentWidget() is self._trainInfoPage:
            self._populate_train_info_table()

    # ---------------------------------------------------------
    # Dispatch Train
    # ---------------------------------------------------------
    def _dispatch_train(self):
        if self.mode != "manual":
            QtWidgets.QMessageBox.warning(self, "Mode Error", "Switch to Manual Mode to dispatch a train.")
            return

        train_id, ok_id = QtWidgets.QInputDialog.getText(
            self, "Dispatch Train", "Enter Train ID (e.g., T1):"
        )
        if not ok_id or not train_id.strip():
            return
        train_id = train_id.strip().upper()

        start_block, ok_block = QtWidgets.QInputDialog.getInt(
            self, "Starting Block", "Enter starting block number:", 1, 1, 50
        )
        if not ok_block:
            return

        speed, ok_speed = QtWidgets.QInputDialog.getInt(
            self, "Suggested Speed", "Enter suggested speed (mph):", 25, 0, 80
        )
        if not ok_speed:
            return

        auth, ok_auth = QtWidgets.QInputDialog.getInt(
            self, "Suggested Authority", "Enter suggested authority (yards):", 200, 50, 2000
        )
        if not ok_auth:
            return

        self.state.dispatch_train(train_id, start_block, speed, auth)

        QtWidgets.QMessageBox.information(
            self, "Train Dispatched",
            f"{train_id} dispatched at block {start_block}\n"
            f"Speed: {speed} mph\nAuthority: {auth} yd"
        )

        # Open Train Info tab immediately
        self._train_info()
        self._reload_line(self.state.line_name)

    # ---------------------------------------------------------
    # Train Info Tab
    # ---------------------------------------------------------
    def _train_info(self):
        page = QtWidgets.QWidget()
        self._trainInfoPage = page
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Train Information (live telemetry)"))

        self.trainInfoTable = QtWidgets.QTableWidget(0, 5)
        self.trainInfoTable.setHorizontalHeaderLabels(
            ["Train ID", "Current Block", "Speed (mph)", "Authority (m)", "Line"]
        )
        self.trainInfoTable.verticalHeader().setVisible(False)
        self.trainInfoTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.trainInfoTable)

        self.actionArea.addWidget(page)
        self.actionArea.setCurrentWidget(page)
        self._populate_train_info_table()

    def _populate_train_info_table(self):
        net_status = self.state.get_network_status()
        trains = self.state.get_trains()

        self.trainInfoTable.setRowCount(len(trains))
        for r, t in enumerate(trains):
            tid = t.get("train_id", "")
            block = t.get("block", "")
            spd_mps = float(t.get("suggested_speed_mps", 0.0))
            mph = spd_mps * MPS_TO_MPH
            auth_m = float(t.get("suggested_authority_m", 0.0))
            line = t.get("line", self.state.line_name)

            self.trainInfoTable.setItem(r, 0, QtWidgets.QTableWidgetItem(str(tid)))
            self.trainInfoTable.setItem(r, 1, QtWidgets.QTableWidgetItem(str(block)))
            self.trainInfoTable.setItem(r, 2, QtWidgets.QTableWidgetItem(f"{mph:.1f}"))
            self.trainInfoTable.setItem(r, 3, QtWidgets.QTableWidgetItem(f"{auth_m:.1f}"))
            self.trainInfoTable.setItem(r, 4, QtWidgets.QTableWidgetItem(line))

    # ---------------------------------------------------------
    # Maintenance / Upload placeholders
    # ---------------------------------------------------------
    def _maintenance_inputs(self):
        row = self.mapTable.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Select a block first.")
            return
        blk_id = self.mapTable.item(row, 1).text()
        choice, ok = QtWidgets.QInputDialog.getItem(
            self, "Maintenance", f"Toggle status for block {blk_id}:",
            ["Open (free)", "Closed"], 0, False
        )
        if ok:
            closed = "Closed" in choice
            self.state.set_block_closed(int(blk_id), closed)
            self._reload_line(self.state.line_name)

    def _manual_override(self):
        QtWidgets.QMessageBox.information(self, "Manual Override", "Manual Override page coming soon.")

    def _upload_schedule(self):
        QtWidgets.QMessageBox.information(self, "Upload Schedule", "Schedule upload not yet implemented.")

    # ---------------------------------------------------------
    # Global Tick — drives entire simulation
    # ---------------------------------------------------------
    def _tick(self):
        self.state.tick_all_modules()
        self._reload_line(self.state.line_name)
        self.clockLabel.setText(f"Sim Time: {clock.get_time_string()}")


# -------------------------------------------------------------
# Main Entry Point
# -------------------------------------------------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    win = CTCWindow()
    win.resize(1100, 650)
    win.show()
    app.exec()
