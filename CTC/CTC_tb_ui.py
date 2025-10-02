from PyQt6 import QtWidgets, QtCore


class CTCWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CTC Testbench")
        cw = QtWidgets.QWidget(self)
        self.setCentralWidget(cw)

        # === Tabs ===
        self.tabs = QtWidgets.QTabWidget()

        # Occupancy tab
        self.occupancyTab = QtWidgets.QWidget()
        occLayout = QtWidgets.QVBoxLayout(self.occupancyTab)

        # Track Table (map)
        self.mapTable = QtWidgets.QTableWidget(0, 9)
        self.mapTable.setHorizontalHeaderLabels([
            "Section", "Block", "Occupancy", "Station",
            "Status", "Switch", "Traffic Light",
            "Crossing Road", "Beacon"
        ])
        self.mapTable.verticalHeader().setVisible(False)
        self.mapTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.mapTable.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.mapTable.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mapTable.setMinimumHeight(220)

        header = self.mapTable.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)

        self._seed_demo_map()

   
        occLayout.addWidget(self.mapTable)

        # 4 Buttons only for Occupancy tab
        self.manualBtn = QtWidgets.QPushButton("Manual Override")
        self.infoBtn   = QtWidgets.QPushButton("Train Information")
        self.uploadBtn = QtWidgets.QPushButton("Upload Schedule")
        self.maintBtn  = QtWidgets.QPushButton("Maintenance")

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
        self.maintBtn.clicked.connect(self._maintenance)

        # Placeholder area below buttons
        self.actionArea = QtWidgets.QStackedWidget()
        occLayout.addWidget(self.actionArea)

        self.blankPage = QtWidgets.QWidget()
        self.actionArea.addWidget(self.blankPage)
        self.actionArea.setCurrentWidget(self.blankPage)

        # Temperature tab
        tempTab = QtWidgets.QWidget()
        tempLayout = QtWidgets.QVBoxLayout(tempTab)
        tempLayout.addWidget(QtWidgets.QLabel("Will implement later"))
        tempLayout.addWidget(self.mapTable)

        # Issues tab
        issuesTab = QtWidgets.QWidget()
        issuesLayout = QtWidgets.QVBoxLayout(issuesTab)
        issuesLayout.addWidget(QtWidgets.QLabel("Will implement later"))
        issuesLayout.addWidget(self.mapTable)

        # Add tabs
        self.tabs.addTab(self.occupancyTab, "Occupancy")
        self.tabs.addTab(tempTab, "Temperature")
        self.tabs.addTab(issuesTab, "Issues")

        # Final layout
        layout = QtWidgets.QVBoxLayout(cw)
        layout.addWidget(QtWidgets.QLabel("MAP"))
        layout.addWidget(self.mapTable, stretch=3)
        layout.addWidget(self.tabs, stretch=2)

    # === Demo Data for Map ===
    def _seed_demo_map(self):
        demo_rows = [
            ("A", 1,  "free", "YARD", "Open", "", "GREEN", "", ""),
            ("A", 2,  "occ",  "", "Closed", "", "RED", "True", ""),
            ("A", 3,  "free", "", "Open", "", "GREEN", "", ""),
            ("A", 5,  "free", "", "Open", "SW1", "GREEN", "", ""),
            ("B", 6,  "free", "", "Open", "SW1", "GREEN", "", ""),
            ("B", 7,  "occ",  "", "Closed", "", "RED", "True", ""),
            ("B", 9,  "free", "B", "Open", "", "YELLOW", "", ""),
            ("C", 11, "free", "", "Open", "SW1", "GREEN", "", ""),
            ("C", 12, "occ",  "", "Closed", "", "RED", "True", ""),
            ("C", 15, "free", "C", "Open", "", "GREEN", "", ""),
        ]

        self.mapTable.setRowCount(len(demo_rows))
        for r, row in enumerate(demo_rows):
            for c, value in enumerate(row):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.mapTable.setItem(r, c, item)

    def _get_selected_block(self):
        row = self.mapTable.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a block first.")
            return None, None
        sec = self.mapTable.item(row, 0).text()
        blk = self.mapTable.item(row, 1).text()
        return row, f"{sec}{blk}"

    # === Button Actions ===
    def _manual_override(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)

        label = QtWidgets.QLabel("Manual Override - Dispatch Trains")
        layout.addWidget(label)

        trainTable = QtWidgets.QTableWidget(0, 6)
        trainTable.setHorizontalHeaderLabels([
            "Train ID", "Current Block", "Origin", "Destination", "Speed", "Authority"
        ])
        trainTable.verticalHeader().setVisible(False)
        trainTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        trainTable.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

        trains = [
            ("T1", "A2", "YARD", "C", 0, 0),
            ("T2", "A5", "YARD", "C", 0, 0),
            ("T3", "B8", "B", "YARD", 0, 0),
        ]
        trainTable.setRowCount(len(trains))
        for r, row in enumerate(trains):
            for c, value in enumerate(row):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                trainTable.setItem(r, c, item)

        layout.addWidget(trainTable)

        # Input fields
        form = QtWidgets.QFormLayout()
        speedSpin = QtWidgets.QSpinBox()
        speedSpin.setRange(0, 120)
        speedSpin.setSuffix(" mph")
        authSpin = QtWidgets.QSpinBox()
        authSpin.setRange(0, 100)
        authSpin.setSuffix(" blocks")
        destCombo = QtWidgets.QComboBox()
        destCombo.addItems(["YARD", "B", "C"])
        form.addRow("Suggested Speed:", speedSpin)
        form.addRow("Suggested Authority:", authSpin)
        form.addRow("Destination:", destCombo)
        layout.addLayout(form)

        dispatchBtn = QtWidgets.QPushButton("Dispatch")
        layout.addWidget(dispatchBtn)

        def on_dispatch():
            row = trainTable.currentRow()
            if row < 0:
                QtWidgets.QMessageBox.warning(self, "No Train Selected", "Please select a train first.")
                return
            train_id = trainTable.item(row, 0).text()
            trainTable.setItem(row, 4, QtWidgets.QTableWidgetItem(str(speedSpin.value())))
            trainTable.setItem(row, 5, QtWidgets.QTableWidgetItem(str(authSpin.value())))
            trainTable.setItem(row, 3, QtWidgets.QTableWidgetItem(destCombo.currentText()))
            QtWidgets.QMessageBox.information(self, "Train Dispatched",
                f"{train_id} dispatched to {destCombo.currentText()} "
                f"at {speedSpin.value()} mph, authority {authSpin.value()} blocks.")

        dispatchBtn.clicked.connect(on_dispatch)

        self.actionArea.addWidget(page)
        self.actionArea.setCurrentWidget(page)

    def _train_info(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)

        label = QtWidgets.QLabel("Train Information")
        layout.addWidget(label)

        trainTable = QtWidgets.QTableWidget(0, 6)
        trainTable.setHorizontalHeaderLabels([
            "Train ID", "Current Block", "Origin", "Destination", "Speed", "Authority"
        ])
        trainTable.verticalHeader().setVisible(False)

        trains = [
            ("T1", "A2", "YARD", "C", 30, 5),
            ("T2", "A5", "YARD", "B", 40, 8),
            ("T3", "B8", "B", "YARD", 25, 6),
        ]
        trainTable.setRowCount(len(trains))
        for r, row in enumerate(trains):
            for c, value in enumerate(row):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                trainTable.setItem(r, c, item)

        header = trainTable.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)

        layout.addWidget(trainTable)

        self.actionArea.addWidget(page)
        self.actionArea.setCurrentWidget(page)

    def _upload_schedule(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Upload Schedule", "", "CSV/Excel Files (*.csv *.xlsx)"
        )
        if fname:
            QtWidgets.QMessageBox.information(self, "Schedule Uploaded", f"Loaded file: {fname}")

    def _maintenance(self):
        row, block_id = self._get_selected_block()
        if row is None:
            return
        choice, ok = QtWidgets.QInputDialog.getItem(
            self, "Maintenance", f"Set status for Block {block_id}:",
            ["Open", "Closed"], 0, False
        )
        if ok:
            self.mapTable.setItem(row, 4, QtWidgets.QTableWidgetItem(choice))


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    win = CTCWindow()
    win.resize(900, 600)
    win.show()
    app.exec()
