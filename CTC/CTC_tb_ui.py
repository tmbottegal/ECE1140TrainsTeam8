# CTC_tb_ui.py
from PyQt6 import QtWidgets, QtCore, QtGui
from .CTC_backend import TrackState

# Keep UI-side constants in sync with backend policy for display/convert
BLOCK_LEN_M = 50.0          # meters per block (demo line)
MPS_TO_MPH  = 2.23693629
SCENARIOS = ["Manual Sandbox", "Meet-and-Branch", "Maintenance Detour", "Broken Rail", "Crossing Gate Demo"]

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
        self._trainInfoPage = None
        self._manualPage = None

        # === Tabs container ===
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
        self.mapTable = QtWidgets.QTableWidget(0, 10)
        self.mapTable.setHorizontalHeaderLabels([
            "Section", "Block", "Occupancy", "Station",
            "Status", "Switch", "Traffic Light",
            "Crossing", "Broken Rail", "Beacon"
        ])
        self.mapTable.verticalHeader().setVisible(False)
        self.mapTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.mapTable.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.mapTable.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mapTable.setMinimumHeight(220)
        self.mapTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)

        # seed initial table rows from LINE_DATA + latest snapshot merge
        self._reload_line("Blue Line")
        occLayout.addWidget(self.mapTable)

        # Buttons under the table
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

        # Action area (below buttons)
        self.actionArea = QtWidgets.QStackedWidget()
        occLayout.addWidget(self.actionArea)
        self.blankPage = QtWidgets.QWidget()
        self.actionArea.addWidget(self.blankPage)
        self.actionArea.setCurrentWidget(self.blankPage)

        # === Test Bench (Stub) tab — separate test UI ===
        self.testTab = QtWidgets.QWidget()
        testLayout = QtWidgets.QVBoxLayout(self.testTab)

        # === Scenario selector row (Blue Line) ===
        scenRow = QtWidgets.QHBoxLayout()
        scenRow.addWidget(QtWidgets.QLabel("Scenario:"))

        # 1) the actual dropdown
        self.scenarioCombo = QtWidgets.QComboBox(self.testTab)
        self.scenarioCombo.addItems(SCENARIOS)
        self.scenarioCombo.setCurrentIndex(0)
        self.scenarioCombo.setMinimumWidth(220)  # prevents collapsing
        self.scenarioCombo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)

        scenRow.addWidget(self.scenarioCombo)

        # 2) buttons
        self.btnLoad  = QtWidgets.QPushButton("Load")
        self.btnRun   = QtWidgets.QPushButton("Run")
        self.btnPause = QtWidgets.QPushButton("Pause")
        self.btnStep  = QtWidgets.QPushButton("Step")
        self.btnReset = QtWidgets.QPushButton("Reset")
        for b in (self.btnLoad, self.btnRun, self.btnPause, self.btnStep, self.btnReset):
            scenRow.addWidget(b)

        scenRow.addStretch(1)
        testLayout.addLayout(scenRow)

        # short description under the row
        self.scenarioDesc = QtWidgets.QLabel("Manual Sandbox: no trains spawn; nothing moves until Run/Step.")
        self.scenarioDesc.setStyleSheet("color:#888;")
        testLayout.addWidget(self.scenarioDesc)

        # wire the buttons
        self.btnLoad.clicked.connect(self._scenario_load)
        self.btnRun.clicked.connect(self._scenario_run)
        self.btnPause.clicked.connect(self._scenario_pause)
        self.btnStep.clicked.connect(self._scenario_step)
        self.btnReset.clicked.connect(self._scenario_reset)


       
        hint = QtWidgets.QLabel(
            "Test-only controls.\n"
            "• TC → CTC: Switch position & Broken rail simulated here by the stub."
        )
        hint.setStyleSheet("color: #bbb;")
        testLayout.addWidget(hint)

        # ---- Block tools ----
        blockGroup = QtWidgets.QGroupBox("Block tools (TC → CTC telemetry, set here via stub)")
        bl = QtWidgets.QGridLayout(blockGroup)
        self.blockCombo = QtWidgets.QComboBox()
        self._refresh_block_combo()
        self.blockStatus = QtWidgets.QComboBox()
        self.blockStatus.addItems(["Open (free)", "Closed"])  # removed "occupied" — telemetry driven
        self.brokenCheck = QtWidgets.QCheckBox("Broken rail")
        applyBlockBtn = QtWidgets.QPushButton("Apply to Block")

        bl.addWidget(QtWidgets.QLabel("Block:"), 0, 0); bl.addWidget(self.blockCombo, 0, 1)
        bl.addWidget(QtWidgets.QLabel("Status:"), 1, 0); bl.addWidget(self.blockStatus, 1, 1)
        bl.addWidget(self.brokenCheck, 2, 1)
        bl.addWidget(applyBlockBtn, 3, 0, 1, 2)

        applyBlockBtn.clicked.connect(self._apply_block_tools)
        testLayout.addWidget(blockGroup)

        # ---- Switch tools ----
        switchGroup = QtWidgets.QGroupBox("Switch tools (TC → CTC position, set here via stub)")
        sl = QtWidgets.QGridLayout(switchGroup)
        self.switchCombo = QtWidgets.QComboBox()
        self._refresh_switch_combo()
        self.switchPos = QtWidgets.QComboBox(); self.switchPos.addItems(["STRAIGHT", "DIVERGE"])
        applySwitchBtn = QtWidgets.QPushButton("Set Switch Position")

        self.autoLineCheck = QtWidgets.QCheckBox("Auto-line SW1 when trains approach")
        self.autoLineCheck.setChecked(True)
        self.autoLineCheck.toggled.connect(lambda v: self.state.set_auto_line(v))

        sl.addWidget(QtWidgets.QLabel("Switch ID:"), 0, 0); sl.addWidget(self.switchCombo, 0, 1)
        sl.addWidget(QtWidgets.QLabel("Position:"), 1, 0); sl.addWidget(self.switchPos, 1, 1)
        sl.addWidget(applySwitchBtn, 2, 0, 1, 2)

        sl.addWidget(self.autoLineCheck, 3, 0, 1, 2)

        applySwitchBtn.clicked.connect(self._apply_switch_tools)
        testLayout.addWidget(switchGroup)

        # ---- Train tools (direct CTC→TC send) ----
       # trainGroup = QtWidgets.QGroupBox("Train tools (CTC → TC: send suggested speed/authority)")
        #tl = QtWidgets.QGridLayout(trainGroup)
       # self.trainCombo = QtWidgets.QComboBox(); self.trainCombo.addItems(["T1", "T2"])
        #self.speedSpinTB = QtWidgets.QSpinBox(); self.speedSpinTB.setRange(0, 120); self.speedSpinTB.setSuffix(" mph")
        #self.authSpinTB  = QtWidgets.QSpinBox(); self.authSpinTB.setRange(0, 1000); self.authSpinTB.setSuffix(" m")
        #applyTrainBtn = QtWidgets.QPushButton("Apply to Train")

       # tl.addWidget(QtWidgets.QLabel("Train:"), 0, 0); tl.addWidget(self.trainCombo, 0, 1)
       # tl.addWidget(QtWidgets.QLabel("Suggested Speed:"), 1, 0); tl.addWidget(self.speedSpinTB, 1, 1)
       # tl.addWidget(QtWidgets.QLabel("Suggested Authority:"), 2, 0); tl.addWidget(self.authSpinTB, 2, 1)
       # tl.addWidget(applyTrainBtn, 3, 0, 1, 2)

       # applyTrainBtn.clicked.connect(self._apply_train_tools)
        #testLayout.addWidget(trainGroup)

                # ---- Crossing tools (TC → CTC telemetry) ----
        xGroup = QtWidgets.QGroupBox("Crossing tools (TC → CTC telemetry)")
        xl = QtWidgets.QGridLayout(xGroup)

        self.crossingBlockCombo = QtWidgets.QComboBox()
        # Only include blocks that actually have a crossing; on Blue it's A3
        self.crossingBlockCombo.addItems([b for b in [f"{blk.line}{blk.block_id}" for blk in self.state.get_blocks()] if b == "A3"])

        self.crossingMode = QtWidgets.QComboBox()
        self.crossingMode.addItems(["Auto (derived)", "Force Down", "Force Up"])

        applyXBtn = QtWidgets.QPushButton("Apply Crossing State")

        xl.addWidget(QtWidgets.QLabel("Crossing block:"), 0, 0); xl.addWidget(self.crossingBlockCombo, 0, 1)
        xl.addWidget(QtWidgets.QLabel("State:"),           1, 0); xl.addWidget(self.crossingMode,      1, 1)
        xl.addWidget(applyXBtn,                            2, 0, 1, 2)

        applyXBtn.clicked.connect(self._apply_crossing_tools)
        testLayout.addWidget(xGroup)


        testLayout.addStretch(1)
        # ---- Reset / Control tools ----
        ctrlGroup = QtWidgets.QGroupBox("Reset / Control")
        cl = QtWidgets.QGridLayout(ctrlGroup)

        self.pauseBtn = QtWidgets.QPushButton("Pause")
        self.stepBtn  = QtWidgets.QPushButton("Step 1 tick")
        self.stepBtn.setEnabled(False)

        resetTrainsBtn = QtWidgets.QPushButton("Reset Trains")
        resetInfraBtn  = QtWidgets.QPushButton("Reset Infrastructure")
        resetAllBtn    = QtWidgets.QPushButton("Reset ALL")

        cl.addWidget(self.pauseBtn,     0, 0)
        cl.addWidget(self.stepBtn,      0, 1)
        cl.addWidget(resetTrainsBtn,    1, 0)
        cl.addWidget(resetInfraBtn,     1, 1)
        cl.addWidget(resetAllBtn,       2, 0, 1, 2)

        testLayout.addWidget(ctrlGroup)

        # Wire up controls
        self.pauseBtn.clicked.connect(self._toggle_pause)
        self.stepBtn.clicked.connect(self._step_once)
        resetTrainsBtn.clicked.connect(lambda: (self.state.reset_trains(), self._reload_line(self.state.line_name)))
        resetInfraBtn.clicked.connect(lambda: (self.state.reset_infrastructure(), self._reload_line(self.state.line_name)))
        resetAllBtn.clicked.connect(lambda: (self.state.reset_all(), self._reload_line(self.state.line_name)))


        # === Extra Tabs (placeholders) ===
        tempTab = QtWidgets.QWidget()
        tempLayout = QtWidgets.QVBoxLayout(tempTab)
        tempLayout.addWidget(QtWidgets.QLabel("Will implement later"))
        issuesTab = QtWidgets.QWidget()
        issuesLayout = QtWidgets.QVBoxLayout(issuesTab)
        issuesLayout.addWidget(QtWidgets.QLabel("Will implement later"))

        self.tabs.addTab(self.occupancyTab, "Occupancy")
        self.tabs.addTab(self.testTab, "Test Bench (Stub)")
        self.tabs.addTab(tempTab, "Temperature")
        self.tabs.addTab(issuesTab, "Issues")

        layout = QtWidgets.QVBoxLayout(cw)
        layout.addWidget(QtWidgets.QLabel("MAP"))
        layout.addWidget(self.tabs, stretch=2)

        # === Simulation Timer ===
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)   # 1s per tick

        # Hold references to dynamic pages for live refresh
        self._trainInfoPage = None
        self._manualPage = None

    # ---------- helpers ----------
    def _scenario_load(self):
        name = self.scenarioCombo.currentText()
        msg = self.state.scenario_load(name)  # backend wrapper calls stub.seed_*
        # refresh table; pause timer so nothing moves yet
        if self.timer.isActive():
            self.timer.stop()
        self.stepBtn.setEnabled(True)
        self.pauseBtn.setText("Resume Timer")
        self._reload_line(self.state.line_name)
        # description
        desc = {
            "Manual Sandbox": "No trains. Add trains or use tools. Nothing moves until Run/Step.",
            "Meet-and-Branch": "T1→B, T2→C. SW1 AUTO lines by approach.",
            "Maintenance Detour": "B7 closed initially; reopen to proceed.",
            "Broken Rail": "When near C11, inject broken rail on C12; train must stop before fault.",
            "Crossing Gate Demo": "T1 starts at A1 with A3 crossing DOWN. Open the gate here to let it proceed.",

        }.get(name, "")
        if desc:
            self.scenarioDesc.setText(desc)

    def _scenario_run(self):
        if not self.timer.isActive():
            self.timer.start(1000)
        self.stepBtn.setEnabled(False)
        self.pauseBtn.setText("Pause Timer")

    def _scenario_pause(self):
        if self.timer.isActive():
            self.timer.stop()
            self.stepBtn.setEnabled(True)
            self.pauseBtn.setText("Resume Timer")

    def _scenario_step(self):
        if not self.timer.isActive():
            self.state.stub_tick()
            self._reload_line(self.state.line_name)

    def _scenario_reset(self):
        self.state.reset_all()
        self._reload_line(self.state.line_name)
        self.scenarioCombo.setCurrentText("Manual Sandbox")
        self.scenarioDesc.setText("Manual Sandbox: no trains spawn; nothing moves until Run/Step.")

    def _refresh_block_combo(self, preserve: bool = False):
        if not hasattr(self, "blockCombo"):
            return
        prev = self.blockCombo.currentText() if preserve else None

        self.blockCombo.blockSignals(True)
        self.blockCombo.clear()
        for b in self.state.get_blocks():
            self.blockCombo.addItem(f"{b.line}{b.block_id}")
        self.blockCombo.blockSignals(False)

        if preserve and prev:
            idx = self.blockCombo.findText(prev)
            if idx >= 0:
                self.blockCombo.setCurrentIndex(idx)

    def _refresh_switch_combo(self, preserve: bool = False):
        if not hasattr(self, "switchCombo"):
            return
        prev = self.switchCombo.currentText() if preserve else None

        switches = sorted({b.switch for b in self.state.get_blocks() if b.switch})
        self.switchCombo.blockSignals(True)
        self.switchCombo.clear()
        if switches:
            self.switchCombo.addItems(switches)
        self.switchCombo.blockSignals(False)

        if preserve and prev:
            idx = self.switchCombo.findText(prev)
            if idx >= 0:
                self.switchCombo.setCurrentIndex(idx)

    def _reload_line(self, line_name: str):
        # Only rebuild models/combos when the line actually changes
        line_changed = (line_name != self.state.line_name)
        if line_changed:
            self.state.set_line(line_name, LINE_DATA[line_name])

        blocks = self.state.get_blocks()
        self.mapTable.setRowCount(len(blocks))
        for r, b in enumerate(blocks):
            rowdata = [
                b.line, b.block_id, b.status, b.station,
                b.signal, b.switch, b.light,
                (str(b.crossing_open) if getattr(b, "has_crossing", False) else ""), str(getattr(b, "broken_rail", False)), b.beacon
            ]
            for c, value in enumerate(rowdata):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

                # Occupancy coloring
                if c == 2:
                    if b.status == "occupied":
                        item.setBackground(QtGui.QColor("red"))
                        item.setForeground(QtGui.QColor("white"))
                    elif b.status == "closed":
                        item.setBackground(QtGui.QColor("gray"))
                        item.setForeground(QtGui.QColor("white"))

                # Traffic light coloring
                if c == 6:
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

        if line_changed:
            self._refresh_block_combo(preserve=True)
            self._refresh_switch_combo(preserve=True)

        # If Train Info / Manual pages are open, refresh them too
        if self._trainInfoPage and self.actionArea.currentWidget() is self._trainInfoPage:
            self._populate_train_info_table()
        if self._manualPage and self.actionArea.currentWidget() is self._manualPage:
            self._populate_manual_table()

    def _get_selected_block(self):
        row = self.mapTable.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a block first.")
            return None, None
        sec = self.mapTable.item(row, 0).text()
        blk = self.mapTable.item(row, 1).text()
        return row, f"{sec}{blk}"

    # ---------- actions (Occupancy tab) ----------
    def _maintenance_inputs(self):
        row, block_id = self._get_selected_block()
        if row is None:
            return
        choice, ok = QtWidgets.QInputDialog.getItem(
            self, "Inputs", f"Toggle status for Block {block_id}:",
            ["Open (free)", "Closed"], 0, False
        )
        if ok:
            status = "closed" if "Closed" in choice else "free"
            self.state.set_status(block_id, status)
            self._reload_line(self.state.line_name)

    # ---------- Manual Override ---------- MUST REV 
    def _manual_override(self):
        page = QtWidgets.QWidget()
        page.setObjectName("ManualPage")
        self._manualPage = page

        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Manual Override — per-train override of CTC policy"))

        # Table shows live trains
        self.manualTable = QtWidgets.QTableWidget(0, 6)
        self.manualTable.setHorizontalHeaderLabels(
            ["Train ID", "Current Block", "Override?", "Speed (mph)", "Authority (m)", "Destination"]
        )
        self.manualTable.verticalHeader().setVisible(False)
        self.manualTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.manualTable)

        # Controls
        form = QtWidgets.QFormLayout()
        self.overrideCheck = QtWidgets.QCheckBox("Enable override for selected train")
        self.speedSpinMO = QtWidgets.QDoubleSpinBox(); self.speedSpinMO.setRange(0, 120); self.speedSpinMO.setDecimals(1); self.speedSpinMO.setSuffix(" mph")
        self.authSpinMO  = QtWidgets.QDoubleSpinBox(); self.authSpinMO.setRange(0, 2000); self.authSpinMO.setDecimals(0); self.authSpinMO.setSuffix(" m")
        destCombo = QtWidgets.QComboBox(); destCombo.addItems(["YARD", "B", "C"])  # display only (not wired in stub)

        form.addRow(self.overrideCheck)
        form.addRow("Suggested Speed:", self.speedSpinMO)
        form.addRow("Suggested Authority:", self.authSpinMO)
        form.addRow("Destination:", destCombo)
        layout.addLayout(form)

        applyBtn = QtWidgets.QPushButton("Apply")
        layout.addWidget(applyBtn)

        applyBtn.clicked.connect(self._apply_manual_override)

        self.actionArea.addWidget(page)
        self.actionArea.setCurrentWidget(page)
        self._populate_manual_table()

    def _populate_manual_table(self):
        trains = self.state.get_trains()
        self.manualTable.setRowCount(len(trains))
        for r, t in enumerate(trains):
            tid   = str(t.get("train_id", ""))
            block = str(t.get("block", ""))

            # Pull any remembered override values for display hints
            # (No direct read API; we'll just leave cells empty until user sets)
            chk = QtWidgets.QTableWidgetItem("No")
            chk.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.manualTable.setItem(r, 0, QtWidgets.QTableWidgetItem(tid))
            self.manualTable.setItem(r, 1, QtWidgets.QTableWidgetItem(block))
            self.manualTable.setItem(r, 2, chk)
            self.manualTable.setItem(r, 3, QtWidgets.QTableWidgetItem(""))  # speed mph (user-entered)
            self.manualTable.setItem(r, 4, QtWidgets.QTableWidgetItem(""))  # authority m (user-entered)
            self.manualTable.setItem(r, 5, QtWidgets.QTableWidgetItem(""))

     # Fill the manual override table from live trains
    def _apply_manual_override(self):
        row = self.manualTable.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "No Train Selected", "Please select a train first.")
            return

        tid = self.manualTable.item(row, 0).text()
        enabled = self.overrideCheck.isChecked()
        mph = float(self.speedSpinMO.value())
        meters = float(self.authSpinMO.value())
        mps = mph / MPS_TO_MPH  # mph → m/s

        # Send to backend; backend converts meters→blocks for the stub
        self.state.set_train_override(tid, enabled, speed_mps=mps, authority_m=meters)

        # Update table indicator
        self.manualTable.setItem(row, 2, QtWidgets.QTableWidgetItem("Yes" if enabled else "No"))
        self.manualTable.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{mph:.1f}"))
        self.manualTable.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{int(meters)}"))

        QtWidgets.QMessageBox.information(self, "Override",
            f"{'Enabled' if enabled else 'Disabled'} override for {tid}.\n"
            f"Speed={mph:.1f} mph, Authority={int(meters)} m.")
        self._reload_line(self.state.line_name)
    # ---------- Train Information ----------
    def _train_info(self):
        page = QtWidgets.QWidget()
        page.setObjectName("TrainInfoPage")
        self._trainInfoPage = page

        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Train Information (live telemetry)"))

        self.trainInfoTable = QtWidgets.QTableWidget(0, 6)
        self.trainInfoTable.setHorizontalHeaderLabels(
            ["Train ID", "Current Block", "Speed (mph)", "Authority (m)", "Destination", "Raw Blocks"]
        )
        self.trainInfoTable.verticalHeader().setVisible(False)
        self.trainInfoTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.trainInfoTable)

        self.actionArea.addWidget(page)
        self.actionArea.setCurrentWidget(page)
        self._populate_train_info_table()

    def _populate_train_info_table(self):
        trains = self.state.get_trains()
        self.trainInfoTable.setRowCount(len(trains))
        for r, t in enumerate(trains):
            tid   = str(t.get("train_id", ""))
            block = str(t.get("block", ""))
            spd_mps = float(t.get("suggested_speed_mps", 0.0))
            mph = spd_mps * MPS_TO_MPH
            auth_blocks = int(t.get("authority_blocks", 0))
            auth_m = int(auth_blocks * BLOCK_LEN_M)
            branch = str(t.get("desired_branch", ""))

            self.trainInfoTable.setItem(r, 0, QtWidgets.QTableWidgetItem(tid))
            self.trainInfoTable.setItem(r, 1, QtWidgets.QTableWidgetItem(block))
            self.trainInfoTable.setItem(r, 2, QtWidgets.QTableWidgetItem(f"{mph:.1f}"))
            self.trainInfoTable.setItem(r, 3, QtWidgets.QTableWidgetItem(str(auth_m)))
            self.trainInfoTable.setItem(r, 4, QtWidgets.QTableWidgetItem(branch))
            self.trainInfoTable.setItem(r, 5, QtWidgets.QTableWidgetItem(str(auth_blocks)))

    # ---------- Upload schedule (minimal CSV: train_id,start_block[,authority_m]) ----------
    def _upload_schedule(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Upload Schedule", "", "CSV Files (*.csv)"
        )
        if not fname:
            return

        imported = 0
        try:
            with open(fname, "r", encoding="utf-8") as f:
                for line in f:
                    parts = [p.strip() for p in line.split(",") if p.strip() != ""]
                    if len(parts) < 2:
                        continue
                    tid, start = parts[0], parts[1]
                    self.state.add_train(tid, start)
                    if len(parts) >= 3:
                        try:
                            meters = float(parts[2])
                            self.state.set_suggested_authority(tid, meters)
                        except Exception:
                            pass
                    imported += 1
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Schedule Upload", f"Failed to load: {e}")
            return

        QtWidgets.QMessageBox.information(self, "Schedule Uploaded", f"Loaded {imported} train(s).")

    # ---------- Test Bench actions ----------
    def _apply_block_tools(self):
        bid = self.blockCombo.currentText()
        is_closed = (self.blockStatus.currentIndex() == 1)
        self.state.set_status(bid, "closed" if is_closed else "free")
        self.state.set_broken_rail(bid, self.brokenCheck.isChecked())
        self._reload_line(self.state.line_name)

    def _apply_switch_tools(self):
        sw = self.switchCombo.currentText()
        if not sw:
            QtWidgets.QMessageBox.information(self, "Switch tools", "No switches on this line.")
            return
        pos = self.switchPos.currentText()
        self.state.set_switch(sw, pos)
        self._reload_line(self.state.line_name)
        
    def _apply_crossing_tools(self):
        bid = self.crossingBlockCombo.currentText().strip()
        mode = self.crossingMode.currentText()
        # Map UI choice → Optional[bool]
        if "Auto" in mode:
            state = None        # Auto (derived)
        elif "Down" in mode:
            state = True        # Force DOWN
        else:
            state = False       # Force UP
        self.state.set_crossing_override(bid, state)
        self._reload_line(self.state.line_name)

    

    #def _apply_train_tools(self):
     #   tid = self.trainCombo.currentText()
     #   mph = float(self.speedSpinTB.value())
     #   mps = mph / MPS_TO_MPH
     #   meters = float(self.authSpinTB.value())
     #   self.state.set_suggested_speed(tid, mps)
     #   self.state.set_suggested_authority(tid, meters)
     #   QtWidgets.QMessageBox.information(
      #      self, "Train tools",
      #      f"Applied to {tid}: {mph:.1f} mph, {int(meters)} m."
      #  )

    # ---------- test bench: pause/step ----------
    def _toggle_pause(self):
        if self.timer.isActive():
            self.timer.stop()
            self.pauseBtn.setText("Resume")
            self.stepBtn.setEnabled(True)
        else:
            self.timer.start(1000)
            self.pauseBtn.setText("Pause")
            self.stepBtn.setEnabled(False)

    def _step_once(self):
        if not self.timer.isActive():
            self.state.stub_tick()
            self._reload_line(self.state.line_name)

    # ---------- simulation tick ----------
    def _tick(self):
        self.state.stub_tick()
        self._reload_line(self.state.line_name)


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    win = CTCWindow()
    win.resize(1000, 600)
    win.show()
    app.exec()