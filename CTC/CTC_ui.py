# CTC_ui.py — Integration-ready Centralized Traffic Control UI
# ------------------------------------------------------------
# Supports:
#   • Live map view (blocks, occupancy, switches, lights)
#   • Active train tracking
#   • Manual dispatch & override
#   • Maintenance controls
#   • Schedule upload
#   • Global simulation clock display
# ------------------------------------------------------------

from PyQt6 import QtWidgets, QtCore, QtGui
from .CTC_backend import TrackState
from universal.global_clock import clock

BLOCK_LEN_M = 50.0
MPS_TO_MPH = 2.23693629

# Placeholder until real Green Line data provided
#LINE_DATA = {"Green Line": []}


class CTCWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Centralized Traffic Control")
        self.backend = TrackState("Green", None)
        print(f"[UI] Loaded {len(self.backend.get_blocks())} blocks from Green Line CSV.")

        self.resize(1100, 650)

        cw = QtWidgets.QWidget(self)
        self.setCentralWidget(cw)
        layout = QtWidgets.QVBoxLayout(cw)

        # =======================================================
        # --- Top bar ---
        # =======================================================
        topBar = QtWidgets.QHBoxLayout()

        self.activeTrainLabel = QtWidgets.QLabel("Active Trains:")
        self.activeTrainCount = QtWidgets.QLabel("0")
        self.activeTrainCount.setFixedWidth(30)
        self.activeTrainCount.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.activeTrainCount.setStyleSheet("font-weight:bold; border:1px solid gray;")

        self.greenRadio = QtWidgets.QRadioButton("Green Line")
        self.redRadio = QtWidgets.QRadioButton("Red Line")
        self._ui_ready = False 
        self.greenRadio.setChecked(True)
        

        
         # temporary lock to prevent early refresh

        self.maintRadio = QtWidgets.QRadioButton("Maintenance Mode")

        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                             QtWidgets.QSizePolicy.Policy.Preferred)

        self.clockLabel = QtWidgets.QLabel(clock.current_time.strftime("%I:%M %p"))
        self.clockLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.clockLabel.setFixedWidth(80)
        self.clockLabel.setStyleSheet("border:1px solid gray; padding:2px;")

        for w in [self.activeTrainLabel, self.activeTrainCount,
                  self.greenRadio, self.redRadio, self.maintRadio,
                  spacer, self.clockLabel]:
            topBar.addWidget(w)
        layout.addLayout(topBar)

        # =======================================================
        # --- Main Split Layout (Left: Map | Right: Control) ---
        # =======================================================
        mainSplit = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(mainSplit, 1)

                # =======================================================
        # LEFT PANEL — MAP / TRACK VIEW
        # =======================================================
        leftWidget = QtWidgets.QWidget()
        leftLayout = QtWidgets.QVBoxLayout(leftWidget)

        mapGroup = QtWidgets.QGroupBox("Map")
        mapLayout = QtWidgets.QVBoxLayout(mapGroup)

        # 7-column detailed map table
        self.mapTable = QtWidgets.QTableWidget(0, 6)
        self.mapTable = QtWidgets.QTableWidget(0, 5)
        self.mapTable.setHorizontalHeaderLabels([
             "Block", "Occupancy", "Station",
            "Traffic Light", "Crossing"
        ])

        self.mapTable.verticalHeader().setVisible(False)
        self.mapTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.mapTable.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        mapLayout.addWidget(self.mapTable)
        leftLayout.addWidget(mapGroup)


        # Throughput and Block Info
        statsGroup = QtWidgets.QGroupBox()
        statsLayout = QtWidgets.QGridLayout(statsGroup)
        statsLayout.addWidget(QtWidgets.QLabel("Throughput:"), 0, 0)
        self.throughputVal = QtWidgets.QLabel("0")
        statsLayout.addWidget(self.throughputVal, 0, 1)

        statsLayout.addWidget(QtWidgets.QLabel("Block ID:"), 1, 0)
        self.blockIDVal = QtWidgets.QLabel("")
        statsLayout.addWidget(self.blockIDVal, 1, 1)

        statsLayout.addWidget(QtWidgets.QLabel("Block Length (yd):"), 2, 0)
        self.blockLenVal = QtWidgets.QLabel("")
        statsLayout.addWidget(self.blockLenVal, 2, 1)

        statsLayout.addWidget(QtWidgets.QLabel("Speed Limit (mph):"), 3, 0)
        self.speedVal = QtWidgets.QLabel("")
        statsLayout.addWidget(self.speedVal, 3, 1)
        leftLayout.addWidget(statsGroup)

        mainSplit.addWidget(leftWidget)

        # =======================================================
        # RIGHT PANEL — TRAIN CONTROL / SUBSECTIONS
        # =======================================================
        rightWidget = QtWidgets.QWidget()
        rightLayout = QtWidgets.QVBoxLayout(rightWidget)

        # Active Trains header
        rightLayout.addWidget(QtWidgets.QLabel("Active Trains"))

        self.trainTable = QtWidgets.QTableWidget(0, 4)
        self.trainTable.setHorizontalHeaderLabels(
            ["Train ID", "Current Block", "Next Stop", "Mode"]
        )
        self.trainTable.verticalHeader().setVisible(False)
        self.trainTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        rightLayout.addWidget(self.trainTable)

        # Button row
        btnLayout = QtWidgets.QGridLayout()
        self.dispatchBtn = QtWidgets.QPushButton("Dispatch Train")
        self.selectBtn = QtWidgets.QPushButton("Select Train")
        self.maintBtn = QtWidgets.QPushButton("Maintenance")
        self.uploadBtn = QtWidgets.QPushButton("Upload Schedule File")
        for r, b in enumerate([self.dispatchBtn, self.selectBtn, self.maintBtn, self.uploadBtn]):
            b.setMinimumHeight(40)
            b.setStyleSheet("font-size:14px; font-weight:bold;")
            btnLayout.addWidget(b, r // 2, r % 2)
        rightLayout.addLayout(btnLayout)

        # Subsection container
        self.subStack = QtWidgets.QStackedWidget()
        self.subStack.addWidget(QtWidgets.QWidget())  # blank default
        rightLayout.addWidget(self.subStack, 1)

        mainSplit.addWidget(rightWidget)
        mainSplit.setStretchFactor(0, 3)
        mainSplit.setStretchFactor(1, 2)

        # =======================================================
        # Backend + Timer setup
        # =======================================================
        #self.state = TrackState("Green Line", LINE_DATA["Green Line"])
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

        # Wire buttons to section loaders
        self.dispatchBtn.clicked.connect(self._show_dispatch)
        self.selectBtn.clicked.connect(self._show_select)
        self.maintBtn.clicked.connect(self._show_maintenance)
        self.uploadBtn.clicked.connect(self._show_upload)

        self.greenRadio.toggled.connect(self._switch_line)
        self.redRadio.toggled.connect(self._switch_line)
        self._ui_ready = True
        # initial refresh
        self._refresh_map()
        self._refresh_trains()


    def _switch_line(self):
        if not getattr(self, "_ui_ready", False):
            return  # skip if UI still being constructed
        if self.greenRadio.isChecked():
            print("[UI] Switched to Green Line")
            # only reload if not already green
            if self.backend.line_name.lower() != "green":
                self.backend.set_line("Green", self.backend._lines.get("Green", []))
        elif self.redRadio.isChecked():
            print("[UI] Switched to Red Line")
            # Red not yet implemented — clear table for now
            self.backend.set_line("Red", [])
        self._refresh_map()
        self._refresh_trains()


    # =======================================================
    # --- Periodic Tick: update clock, trains, and map ---
    # =======================================================
    def _tick(self):
        self.backend.simulation_tick()
        self.clockLabel.setText(clock.current_time.strftime("%I:%M %p"))
        self._refresh_map()
        self._refresh_trains()

    # =======================================================
    # --- Refresh Map and Train Table ---
    # =======================================================
    def _refresh_map(self):
        blocks = self.backend.get_blocks()
        self.mapTable.setRowCount(len(blocks))

        for r, b in enumerate(blocks):
            # 1️⃣ Block number
            block_id = getattr(b, "block_id", "")

            # 2️⃣ Occupancy (default free)
            status = getattr(b, "status", "free")

            # 3️⃣ Station
            station = getattr(b, "station", "")
            if str(station).lower() == "nan" or station == "":
                station = ""
            # Always mark Yard as a station at block 0
            if int(block_id) == 0:
                station = "Yard"

            # 4️⃣ Traffic light
            light = getattr(b, "light", "")
            if str(light).lower() == "nan":
                light = ""

            # 5️⃣ Crossing
            crossing = "Yes" if getattr(b, "has_crossing", False) else ""


            # Assemble row
            row = [block_id, status, station, light, crossing]

            for c, val in enumerate(row):
                item = QtWidgets.QTableWidgetItem(str(val))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

                # --- Occupancy coloring ---
                if c == 1:
                    if status == "occupied":
                        item.setBackground(QtGui.QColor("green"))
                        item.setForeground(QtGui.QColor("white"))
                    elif status == "closed":
                        item.setBackground(QtGui.QColor("gray"))
                        item.setForeground(QtGui.QColor("white"))

                # --- Light coloring ---
                if c == 3:
                    l = str(val).upper()
                    if l == "RED":
                        item.setBackground(QtGui.QColor("#b00020"))
                        item.setForeground(QtGui.QColor("white"))
                    elif l == "YELLOW":
                        item.setBackground(QtGui.QColor("#d7b600"))
                        item.setForeground(QtGui.QColor("black"))
                    elif l == "GREEN":
                        item.setBackground(QtGui.QColor("#1b5e20"))
                        item.setForeground(QtGui.QColor("white"))

                self.mapTable.setItem(r, c, item)





    def _refresh_trains(self):
        trains = self.backend.get_trains()
        self.trainTable.setRowCount(len(trains))
        self.activeTrainCount.setText(str(len(trains)))
        for r, t in enumerate(trains):
            tid = str(t.get("train_id", ""))
            blk = str(t.get("block", ""))
            nxt = str(t.get("desired_branch", ""))
            mode = "Manual" if t.get("manual", False) else "Auto"
            for c, val in enumerate([tid, blk, nxt, mode]):
                item = QtWidgets.QTableWidgetItem(val)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.trainTable.setItem(r, c, item)

    # =======================================================
    # --- Subpages ---
    # =======================================================
        # =======================================================
    # --- Dispatch Train Subpage ---
    # =======================================================
    def _show_dispatch(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(page)
        layout.addRow(QtWidgets.QLabel("<b>Dispatch New Train</b>"))

        # --- Train ID Entry ---
        self.trainIDEntry = QtWidgets.QLineEdit("Train_1")
        layout.addRow("Train ID:", self.trainIDEntry)

        # --- Destination Dropdown ---
        self.destCombo = QtWidgets.QComboBox()
        # Preload known stations (you can add more later)
        self.destCombo.addItems([
            "Edgebrook", "Whited", "Central", "Inglewood", "Overbrook"
        ])
        layout.addRow("Destination:", self.destCombo)

        # --- Arrival Time Picker ---
        self.arrivalTime = QtWidgets.QTimeEdit(QtCore.QTime.currentTime())
        self.arrivalTime.setDisplayFormat("hh:mm AP")
        layout.addRow("Planned Arrival Time:", self.arrivalTime)

        # --- Dispatch Button ---
        dispatchBtn = QtWidgets.QPushButton("Dispatch Train")
        dispatchBtn.setStyleSheet("font-weight:bold; font-size:14px;")
        layout.addRow(dispatchBtn)

        dispatchBtn.clicked.connect(self._dispatch_train)

        self.subStack.addWidget(page)
        self.subStack.setCurrentWidget(page)


    # =======================================================
    # --- Dispatch Handler ---
    # =======================================================
    def _dispatch_train(self):
        """Spawn a new train from Yard (block 0) toward selected destination."""
        tid = self.trainIDEntry.text().strip()
        dest = self.destCombo.currentText().strip()
        arrival_time = self.arrivalTime.time().toString("hh:mm AP")

        if not tid:
            QtWidgets.QMessageBox.warning(self, "Dispatch Error", "Train ID cannot be empty.")
            return

        try:
            # Always start at Yard (block 0)
            self.backend.add_train(tid, "0")

            QtWidgets.QMessageBox.information(
                self, "Train Dispatched",
                f"Train {tid} dispatched from Yard to {dest}\n"
                f"Planned arrival: {arrival_time}"
            )

            self._refresh_trains()
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Dispatch Error", f"Failed to dispatch train:\n{e}"
            )


    def _show_select(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(page)
        layout.addRow(QtWidgets.QLabel("Manual Override"))
        self.speedSpin = QtWidgets.QDoubleSpinBox()
        self.speedSpin.setRange(0, 120)
        self.speedSpin.setSuffix(" mph")
        self.authSpin = QtWidgets.QDoubleSpinBox()
        self.authSpin.setRange(0, 2000)
        self.authSpin.setSuffix(" m")
        layout.addRow("Suggested Speed:", self.speedSpin)
        layout.addRow("Suggested Authority:", self.authSpin)
        applyBtn = QtWidgets.QPushButton("Apply to Selected Train")
        layout.addRow(applyBtn)
        applyBtn.clicked.connect(self._apply_manual)
        self.subStack.addWidget(page)
        self.subStack.setCurrentWidget(page)

    def _show_maintenance(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Maintenance Mode"))
        self.blockEntry = QtWidgets.QLineEdit()
        self.blockEntry.setPlaceholderText("Enter Block ID (e.g., A3)")
        layout.addWidget(self.blockEntry)
        startBtn = QtWidgets.QPushButton("Start Maintenance")
        endBtn = QtWidgets.QPushButton("End Maintenance")
        layout.addWidget(startBtn)
        layout.addWidget(endBtn)
        startBtn.clicked.connect(lambda: self.backend.set_status(self.blockEntry.text(), "closed"))
        endBtn.clicked.connect(lambda: self.backend.set_status(self.blockEntry.text(), "free"))
        self.subStack.addWidget(page)
        self.subStack.setCurrentWidget(page)

    def _show_upload(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Upload Schedule File"))
        uploadBtn = QtWidgets.QPushButton("Select CSV File")
        layout.addWidget(uploadBtn)
        uploadBtn.clicked.connect(self._upload_schedule)
        self.subStack.addWidget(page)
        self.subStack.setCurrentWidget(page)

    # =======================================================
    # --- Manual Override handler ---
    # =======================================================
    def _apply_manual(self):
        row = self.trainTable.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Manual Override", "Select a train first.")
            return
        tid = self.trainTable.item(row, 0).text()
        mph = self.speedSpin.value()
        mps = mph / MPS_TO_MPH
        meters = self.authSpin.value()
        self.backend.set_train_override(tid, True, speed_mps=mps, authority_m=meters)
        QtWidgets.QMessageBox.information(self, "Manual Override",
                                          f"Applied {mph:.1f} mph, {int(meters)} m to {tid}.")

    # =======================================================
    # --- Upload schedule handler ---
    # =======================================================
    def _upload_schedule(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Schedule CSV", "", "CSV Files (*.csv)")
        if not fname:
            return
        try:
            rows = []
            with open(fname, "r") as f:
                header = [h.strip().lower() for h in f.readline().split(",")]
                for line in f:
                    if not line.strip():
                        continue
                    vals = [v.strip() for v in line.split(",")]
                    tid, t_s, orig, dest = vals[:4]
                    rows.append((tid, int(t_s), orig, dest))
            self.backend.load_route_schedule(rows)
            QtWidgets.QMessageBox.information(self, "Schedule", f"Loaded {len(rows)} route rows.")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Schedule", f"Error loading CSV:\n{e}")


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    win = CTCWindow()
    win.show()
    app.exec()
