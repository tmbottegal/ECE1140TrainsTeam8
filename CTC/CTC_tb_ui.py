from PyQt6 import QtWidgets, QtCore, QtGui
from .CTC_backend import TrackState   # make sure ctc_backend.py is in same folder

LINE_DATA = {
    "Blue Line": [
        ("A", 1,  "free", "YARD",      "Open", "","",      "",      ""),
        ("A", 2,  "free", "",          "Open", "","",      "",      ""),
        ("A", 3,  "free", "",          "Open", "","",      "True",  ""),  # crossing
        ("A", 4,  "free", "",          "Open", "","",      "",      ""),
        ("A", 5,  "free", "",          "Open", "SW1","",   "",      ""),  # switch to 6 or 11
        ("B", 6,  "free", "",          "Open", "SW1","GREEN","",     ""),
        ("B", 7,  "free", "",          "Open", "","",      "",      ""),
        ("B", 8,  "free", "",          "Open", "","",      "",      ""),
        ("B", 9,  "free", "",          "Open", "","",      "",      "Beacon"),
        ("B", 10, "free", "Station B", "Open", "","",      "",      ""),
        ("C", 11, "free", "",          "Open", "SW1","GREEN","",     ""),
        ("C", 12, "free", "",          "Open", "","",      "",      ""),
        ("C", 13, "free", "",          "Open", "","",      "",      ""),
        ("C", 14, "free", "",          "Open", "","",      "",      "Beacon"),
        ("C", 15, "free", "Station C", "Open", "","",      "",      ""),
    ],
    "Red Line":   [],
    "Green Line": [],
}


class CTCWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CTC Testbench")
        cw = QtWidgets.QWidget(self)
        self.setCentralWidget(cw)

        # === Backend state ===
        self.state = TrackState("Blue Line", LINE_DATA["Blue Line"])

        # === Tabs ===
        self.tabs = QtWidgets.QTabWidget()

        # === Occupancy tab ===
        self.occupancyTab = QtWidgets.QWidget()
        occLayout = QtWidgets.QVBoxLayout(self.occupancyTab)

        # Line selector
        selectorRow = QtWidgets.QHBoxLayout()
        selectorRow.addWidget(QtWidgets.QLabel("Select Line:"))
        self.lineSelector = QtWidgets.QComboBox()
        self.lineSelector.addItems(["Blue Line", "Red Line", "Green Line"])
        self.lineSelector.setCurrentText("Blue Line")
        self.lineSelector.currentTextChanged.connect(self._reload_line)
        selectorRow.addWidget(self.lineSelector)
        selectorRow.addStretch(1)
        occLayout.addLayout(selectorRow)

        # Track table
        self.mapTable = QtWidgets.QTableWidget(0, 9)
        self.mapTable.setHorizontalHeaderLabels([
            "Section", "Block", "Occupancy", "Station",
            "Status", "Switch", "Traffic Light",
            "Crossing", "Beacon"
        ])
        self.mapTable.verticalHeader().setVisible(False)
        self.mapTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.mapTable.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.mapTable.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mapTable.setMinimumHeight(220)
        self.mapTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)

        self._reload_line("Blue Line")
        occLayout.addWidget(self.mapTable)

        # Buttons
        self.manualBtn = QtWidgets.QPushButton("Manual Override")
        self.infoBtn   = QtWidgets.QPushButton("Train Information")
        self.uploadBtn = QtWidgets.QPushButton("Upload Schedule")
        self.maintBtn  = QtWidgets.QPushButton("Maintenance / Inputs")
        for b in (self.manualBtn, self.infoBtn, self.uploadBtn, self.maintBtn):
            b.setMinimumHeight(40)
            b.setStyleSheet("font-size:14px; font-weight:bold;")
        btnRow = QtWidgets.QHBoxLayout()
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

        # Action area
        self.actionArea = QtWidgets.QStackedWidget()
        occLayout.addWidget(self.actionArea)
        self.blankPage = QtWidgets.QWidget()
        self.actionArea.addWidget(self.blankPage)
        self.actionArea.setCurrentWidget(self.blankPage)

        # === Extra Tabs ===
        tempTab = QtWidgets.QWidget()
        tempLayout = QtWidgets.QVBoxLayout(tempTab)
        tempLayout.addWidget(QtWidgets.QLabel("Will implement later"))
        issuesTab = QtWidgets.QWidget()
        issuesLayout = QtWidgets.QVBoxLayout(issuesTab)
        issuesLayout.addWidget(QtWidgets.QLabel("Will implement later"))
        self.tabs.addTab(self.occupancyTab, "Occupancy")
        self.tabs.addTab(tempTab, "Temperature")
        self.tabs.addTab(issuesTab, "Issues")

        layout = QtWidgets.QVBoxLayout(cw)
        layout.addWidget(QtWidgets.QLabel("MAP"))
        layout.addWidget(self.tabs, stretch=2)

        # === Simulation Timer ===
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)   # 1s per tick

    # ---------- helpers ----------
    def _reload_line(self, line_name: str):
        if line_name != self.state.line_name:
            self.state.set_line(line_name, LINE_DATA[line_name])
        blocks = self.state.get_blocks()
        self.mapTable.setRowCount(len(blocks))
        for r, b in enumerate(blocks):
            rowdata = [
                b.line, b.block_id, b.status, b.station,
                b.signal, b.switch, b.light,
                b.crossing, b.maintenance
            ]
            for c, value in enumerate(rowdata):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                if c == 2:  # Occupancy col
                    if b.status == "occupied":
                        item.setBackground(QtGui.QColor("red"))
                        item.setForeground(QtGui.QColor("white"))
                    elif b.status == "closed":
                        item.setBackground(QtGui.QColor("gray"))
                        item.setForeground(QtGui.QColor("white"))
                self.mapTable.setItem(r, c, item)

    def _get_selected_block(self):
        row = self.mapTable.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a block first.")
            return None, None
        sec = self.mapTable.item(row, 0).text()
        blk = self.mapTable.item(row, 1).text()
        return row, f"{sec}{blk}"

    # ---------- actions ----------
    def _maintenance_inputs(self):
        row, block_id = self._get_selected_block()
        if row is None:
            return
        choice, ok = QtWidgets.QInputDialog.getItem(
            self, "Inputs", f"Toggle status for Block {block_id}:",
            ["free", "occupied", "closed"], 0, False
        )
        if ok:
            self.state.set_status(block_id, choice)
            self._reload_line(self.state.line_name)

    def _manual_override(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Manual Override - Dispatch Trains"))

        self.trainTable = QtWidgets.QTableWidget(0, 6)
        self.trainTable.setHorizontalHeaderLabels(
            ["Train ID", "Current Block", "Origin", "Destination", "Speed", "Authority"]
        )
        self.trainTable.verticalHeader().setVisible(False)

        trains = [
            ("T1", "A2", "YARD", "C", 0, 0),
            ("T2", "A5", "YARD", "C", 0, 0),
        ]
        self.trainTable.setRowCount(len(trains))
        for r, row in enumerate(trains):
            for c, value in enumerate(row):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.trainTable.setItem(r, c, item)
        layout.addWidget(self.trainTable)

        form = QtWidgets.QFormLayout()
        speedSpin = QtWidgets.QSpinBox(); speedSpin.setRange(0, 120); speedSpin.setSuffix(" mph")
        authSpin  = QtWidgets.QSpinBox(); authSpin.setRange(0, 20);  authSpin.setSuffix(" blocks")
        destCombo = QtWidgets.QComboBox(); destCombo.addItems(["YARD", "B", "C"])
        form.addRow("Suggested Speed:", speedSpin)
        form.addRow("Suggested Authority:", authSpin)
        form.addRow("Destination:", destCombo)
        layout.addLayout(form)

        dispatchBtn = QtWidgets.QPushButton("Dispatch")
        layout.addWidget(dispatchBtn)

        def on_dispatch():
            row = self.trainTable.currentRow()
            if row < 0:
                QtWidgets.QMessageBox.warning(self, "No Train Selected", "Please select a train first.")
                return
            self.trainTable.setItem(row, 4, QtWidgets.QTableWidgetItem(str(speedSpin.value())))
            self.trainTable.setItem(row, 5, QtWidgets.QTableWidgetItem(str(authSpin.value())))
            self.trainTable.setItem(row, 3, QtWidgets.QTableWidgetItem(destCombo.currentText()))
            QtWidgets.QMessageBox.information(
                self, "Train Dispatched",
                f"Train dispatched to {destCombo.currentText()} at {speedSpin.value()} mph, "
                f"authority {authSpin.value()} blocks."
            )

        dispatchBtn.clicked.connect(on_dispatch)
        self.actionArea.addWidget(page)
        self.actionArea.setCurrentWidget(page)

    def _train_info(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Train Information"))

        trainTable = QtWidgets.QTableWidget(0, 6)
        trainTable.setHorizontalHeaderLabels(
            ["Train ID", "Current Block", "Origin", "Destination", "Speed", "Authority"]
        )
        trainTable.verticalHeader().setVisible(False)

        trains = [
            ("T1", "A2", "YARD", "C", 30, 5),
            ("T2", "A5", "YARD", "B", 40, 8),
        ]
        trainTable.setRowCount(len(trains))
        for r, row in enumerate(trains):
            for c, value in enumerate(row):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                trainTable.setItem(r, c, item)
        trainTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(trainTable)

        self.actionArea.addWidget(page)
        self.actionArea.setCurrentWidget(page)

    def _upload_schedule(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Upload Schedule", "", "CSV/Excel Files (*.csv *.xlsx)"
        )
        if fname:
            QtWidgets.QMessageBox.information(self, "Schedule Uploaded", f"Loaded file: {fname}")

    # ---------- simulation tick ----------
    def _tick(self):
        self.state._advance_one_step()
        self._reload_line(self.state.line_name)


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    win = CTCWindow()
    win.resize(1000, 600)
    win.show()
    app.exec()
