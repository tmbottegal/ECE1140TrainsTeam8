# ============================================================
# Centralized Traffic Controller (CTC) UI
# ------------------------------------------------------------
#   Syncs directly with new TrackState backend
#    Updates train & block tables every tick
#    Handles manual dispatch (manual mode only)
#    Shows simulation clock driven by global clock
#    Ready for integration with TrackControllerBackend + TrackModel
# ============================================================

from PyQt6 import QtWidgets, QtCore, QtGui
from CTC_backend import TrackState
from universal.global_clock import clock

BLOCK_LEN_M = 50.0
MPS_TO_MPH = 2.23693629



class CTCWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Centralized Traffic Controller")
        self.resize(1100, 650)

        cw = QtWidgets.QWidget(self)
        self.setCentralWidget(cw)

        # === Mode toggle toolbar (Manual / Auto) ===
        self.mode = "auto"
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

                # === CLOCK CONTROL TOOLBAR ===
        clock_toolbar = QtWidgets.QToolBar("Clock Control")
        clock_toolbar.setMovable(False)
        clock_toolbar.setStyleSheet("QToolBar { spacing: 10px; }")

        # Buttons
        self.clock_start_btn = QtWidgets.QPushButton("Start")
        self.clock_pause_btn = QtWidgets.QPushButton("Pause")
        self.clock_normal_btn = QtWidgets.QPushButton("1× Speed")
        self.clock_fast_btn = QtWidgets.QPushButton("10× Speed")

        
    


        for btn in (self.clock_start_btn, self.clock_pause_btn, self.clock_normal_btn, self.clock_fast_btn):
            btn.setMinimumWidth(90)
            btn.setStyleSheet("font-weight:bold; font-size:12px;")

        # Add to toolbar
        clock_toolbar.addWidget(self.clock_start_btn)
        clock_toolbar.addWidget(self.clock_pause_btn)
        clock_toolbar.addSeparator()
        clock_toolbar.addWidget(self.clock_normal_btn)
        clock_toolbar.addWidget(self.clock_fast_btn)

        # Add toolbar to window
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, clock_toolbar)

        # === CONNECT BUTTONS TO GLOBAL CLOCK ===
        self.clock_start_btn.clicked.connect(lambda: clock.resume())
        self.clock_pause_btn.clicked.connect(lambda: clock.pause())
        self.clock_normal_btn.clicked.connect(
            lambda: (clock.set_speed(1.0), self._apply_clock_speed())
        )
        self.clock_fast_btn.clicked.connect(
            lambda: (clock.set_speed(10.0), self._apply_clock_speed())
        )


        self.clock_start_btn.clicked.connect(self._resume_sim)
        self.clock_pause_btn.clicked.connect(self._pause_sim)
        self.clock_normal_btn.clicked.connect(
            lambda: (clock.set_speed(1.0), self._apply_clock_speed())
        )
        self.clock_fast_btn.clicked.connect(
            lambda: (clock.set_speed(10.0), self._apply_clock_speed())
        )



        # === Maintenance Mode Toggle (independent from Auto/Manual) ===
        self.maintenance_mode = False
        self.maint_checkbox = QtWidgets.QCheckBox("Maintenance Mode")
        self.maint_checkbox.setChecked(False)
        self.maint_checkbox.toggled.connect(self._toggle_maintenance_mode)
        toolbar.addSeparator()
        toolbar.addWidget(self.maint_checkbox)


        toolbar.addWidget(self.mode_label)
        toolbar.addWidget(self.mode_toggle_button)
        toolbar.addSeparator()
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, toolbar)

        # === Backend state ===
        self.state = TrackState("Green Line")
        self._trainInfoPage = None
        self._manualPage = None

        # === Tabs container ===
        self.tabs = QtWidgets.QTabWidget()

        # === OCCUPANCY TAB ===
        self.occupancyTab = QtWidgets.QWidget()
        occLayout = QtWidgets.QVBoxLayout(self.occupancyTab)

        selectorRow = QtWidgets.QHBoxLayout()
        selectorRow.addWidget(QtWidgets.QLabel("Select Line:"))
        self.lineSelector = QtWidgets.QComboBox()
        self.lineSelector.addItems(["Red Line", "Green Line"])
        self.lineSelector.setCurrentText("Green Line")
        self.lineSelector.currentTextChanged.connect(self._reload_line)
        selectorRow.addWidget(self.lineSelector)
        selectorRow.addStretch(1)
        occLayout.addLayout(selectorRow)

        # === Track table ===
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

        # === Bottom buttons ===
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

        # === Connect buttons ===
        self.manualBtn.clicked.connect(self._manual_override)
        self.infoBtn.clicked.connect(self._train_info)
        self.uploadBtn.clicked.connect(self._upload_schedule)
        self.maintBtn.clicked.connect(self._maintenance_inputs)
        self.dispatchBtn.clicked.connect(self._dispatch_train)

        # === Action area (below buttons) ===
        self.actionArea = QtWidgets.QStackedWidget()
        self.blankPage = QtWidgets.QWidget()
        self.actionArea.addWidget(self.blankPage)
        self.actionArea.setCurrentWidget(self.blankPage)
        occLayout.addWidget(self.actionArea)

       

        # === Tabs ===
        self.tabs.addTab(self.occupancyTab, "Occupancy")
        

        # === Layout ===
        layout = QtWidgets.QVBoxLayout(cw)
        self.clockLabel = QtWidgets.QLabel(f"Sim Time: {clock.get_time_string()}")
        self.clockLabel.setStyleSheet("font-weight:bold; font-size:14px;")
        layout.addWidget(self.clockLabel)

        self.throughputLabel = QtWidgets.QLabel("Throughput: 0 trips completed")
        self.throughputLabel.setStyleSheet("font-weight:bold; font-size:14px;")
        layout.addWidget(self.throughputLabel)

        layout.addWidget(self.tabs, stretch=2)

        # === Simulation timer (drives all modules) ===
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)  # 1s per simulated tick

        self._apply_clock_speed()


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
        self.uploadBtn.setEnabled(self.mode == "auto")
        # self.addEntryBtn.setEnabled(self.mode == "auto")
        print(f"[CTC UI] Switched to {self.mode.upper()} mode.")

    def _apply_clock_speed(self):
        """
        Adjust UI tick interval so simulation updates faster when speed increases.
        """
        # prevent divide-by-zero
        multiplier = max(0.1, clock.time_multiplier)

        # Determine new UI tick frequency
        interval_ms = max(10, int(1000 / multiplier))  # min 10ms to stay safe

        self.timer.start(interval_ms)
        print(f"[UI] Timer interval set to {interval_ms} ms (speed={multiplier}×)")

    # ---------------------------------------------------------
    # Reload line table from backend
    # ---------------------------------------------------------
    def _reload_line(self, line_name: str):
        """Refresh occupancy + signals from backend."""
        if line_name != self.state.line_name:
            self.state.set_line(line_name)

        blocks = self.state.get_blocks()
        self.mapTable.setRowCount(len(blocks))

        for r, b in enumerate(blocks):
            # --- Pull real segment from TrackModel ---
            seg = self.state.track_model.segments.get(b.block_id)
            
            # --- Determine switch display text ---
            if seg and seg.__class__.__name__ == "TrackSwitch":
                if seg.current_position == 0:
                    switch_text = "Straight"
                else:
                    switch_text = "Diverging"
            else:
                switch_text = ""  # Non-switch blocks

            rowdata = [
                b.section,
                b.block_id,
                b.status,
                b.station,
                b.station_side,
                switch_text,                     # ⭐ FIXED SWITCH COLUMN
                b.light,
                ("Yes" if b.crossing else ""),
                #f"{b.speed_limit * 0.621371:.0f} mph"
                f"{b.speed_limit:.0f} mph"

            ]

            for c, value in enumerate(rowdata):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

               
                # --- STATUS COLORING ---
                if c == 2:
                    if b.status == "occupied":
                        # OCCUPIED = GREEN
                        item.setBackground(QtGui.QColor("#2ecc71"))   # bright green
                        item.setForeground(QtGui.QColor("black"))

                    elif b.status == "unoccupied":
                        # UNOCCUPIED = RED
                        item.setBackground(QtGui.QColor("#e74c3c"))   # bright red
                        item.setForeground(QtGui.QColor("white"))

                    elif b.status == "closed":
                        # CLOSED = GRAY
                        item.setBackground(QtGui.QColor("gray"))
                        item.setForeground(QtGui.QColor("white"))


                # --- SIGNAL LIGHT COLORING ---
                if c == 6:
                    light = str(value).upper()

                    if light == "N/A":
                        item.setText("")  # hide N/A
                    elif light == "RED":
                        item.setBackground(QtGui.QColor("#b00020"))
                        item.setForeground(QtGui.QColor("white"))
                    elif light == "YELLOW":
                        item.setBackground(QtGui.QColor("#d7b600"))
                        item.setForeground(QtGui.QColor("black"))
                    elif light == "GREEN":
                        item.setBackground(QtGui.QColor("#1b5e20"))
                        item.setForeground(QtGui.QColor("white"))

                self.mapTable.setItem(r, c, item)

        # Update train info if needed
        if self._trainInfoPage and self.actionArea.currentWidget() is self._trainInfoPage:
            self._populate_train_info_table()



    def _show_dispatch_options(self):
        """Modal dialog: choose Instant vs Scheduled dispatch."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Dispatch Options")
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)

        label = QtWidgets.QLabel("Choose dispatch type:")
        label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(label)

        # Buttons
        instant_btn = QtWidgets.QPushButton("Instant Dispatch")
        schedule_btn = QtWidgets.QPushButton("Schedule Dispatch")

        instant_btn.setMinimumHeight(35)
        schedule_btn.setMinimumHeight(35)

        layout.addWidget(instant_btn)
        layout.addWidget(schedule_btn)

        # Close button
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setMinimumHeight(30)
        layout.addWidget(cancel_btn)

        # ---- Connections ----
        instant_btn.clicked.connect(lambda: (dialog.accept(), self._instant_dispatch()))
        schedule_btn.clicked.connect(lambda: (dialog.accept(), self._scheduled_dispatch()))
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    # ---------------------------------------------------------
    # Dispatch Train
    # ---------------------------------------------------------
    def _dispatch_train(self):
        if self.mode != "manual":
            QtWidgets.QMessageBox.warning(self, "Mode Error",
                                        "Switch to Manual Mode to dispatch a train.")
            return

        # SHOW THE OPTIONS POPUP
        self._show_dispatch_options()

    def _instant_dispatch(self):
        """
        Instant dispatch: dispatcher selects train ID, start block, dest block.
        CTC computes speed + authority automatically.
        """
        try:
            # === 1. Train ID ===
            train_id, ok_id = QtWidgets.QInputDialog.getText(
                self, "Instant Dispatch", "Enter Train ID (e.g., T1):"
            )
            if not ok_id or not train_id.strip():
                return
            train_id = train_id.strip().upper()

            # === 2. Starting Block ===
            start_block, ok_block = QtWidgets.QInputDialog.getInt(
                self, "Starting Block", "Enter starting block number:", 0, 0, 150
            )
            if not ok_block:
                return
            


            # === 3. Destination Block ===
            dest_block, ok_dest = QtWidgets.QInputDialog.getInt(
                self, "Destination Block", "Enter final block number:", 0, 0, 150
            )
            if not ok_dest:
                return

            # === 4. Compute the safe speed & authority ===
            # backend function: compute_suggestions(start_block, dest_block)
            speed_mps, auth_m = self.state.compute_suggestions(start_block, dest_block)

        
            speed_mph = speed_mps * 2.23693629
            auth_yd = auth_m / 0.9144

            # === 5. Dispatch using backend — STILL IN METRIC ===
            self.state.dispatch_train(train_id, start_block, dest_block, speed_mph, auth_yd)


            QtWidgets.QMessageBox.information(
                self,
                "Train Dispatched",
                f"{train_id} dispatched at block {start_block}\n"
                f"Destination: {dest_block}\n"
                f"Computed Speed: {speed_mph:.1f} mph\n"
                f"Computed Authority: {auth_yd:.1f} yd"
            )

            # Show train info screen
            self._train_info()
            self._reload_line(self.state.line_name)

        except Exception as e:
            print("[CTC UI] Instant dispatch error:", e)

    def _scheduled_dispatch(self):
        """
        Dispatcher wants to dispatch a train to a station with an arrival time.
        This dialog gathers: train ID, start block, destination station, arrival time.
        """
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Scheduled Dispatch")
        dialog.setModal(True)

        layout = QtWidgets.QFormLayout(dialog)

        # --- Train ID ---
        train_id_input = QtWidgets.QLineEdit()
        train_id_input.setPlaceholderText("e.g., T1")
        layout.addRow("Train ID:", train_id_input)

        # --- Starting Block ---
        start_block_input = QtWidgets.QSpinBox()
        start_block_input.setRange(1, 150)
        layout.addRow("Starting Block:", start_block_input)

        # --- Destination Station (Dropdown) ---
        station_dropdown = QtWidgets.QComboBox()
        station_names = [
            seg.station_name 
            for seg in self.state.track_model.segments.values()
            if hasattr(seg, "station_name") and seg.station_name
        ]

        station_dropdown.addItems(station_names)
        layout.addRow("Destination Station:", station_dropdown)

        # --- Arrival Time ---
        arrival_input = QtWidgets.QTimeEdit()
        arrival_input.setDisplayFormat("HH:mm")
        arrival_input.setTime(QtCore.QTime.currentTime())
        layout.addRow("Arrival Time:", arrival_input)

        # --- Buttons ---
        btn_row = QtWidgets.QHBoxLayout()
        confirm_btn = QtWidgets.QPushButton("Dispatch")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        btn_row.addWidget(confirm_btn)
        btn_row.addWidget(cancel_btn)
        layout.addRow(btn_row)

       



        # ---- BUTTON LOGIC ----
        def confirm():
            train_id = train_id_input.text().strip().upper()
            start_block = int(start_block_input.value())
            
         

            dest_station = station_dropdown.currentText()
            arrival_time = arrival_input.time().toString("HH:mm")

            if not train_id:
                QtWidgets.QMessageBox.warning(dialog, "Error", "Train ID cannot be empty.")
                return

            # 1. Map station → block
            dest_block = self.state.station_to_block(dest_station)
            if dest_block is None:
                QtWidgets.QMessageBox.warning(dialog, "Error", f"Station {dest_station} has no block.")
                return


            # 2. Compute suggestions (reuse your instant logic)
            speed_mps, auth_m = self.state.compute_suggestions(start_block, dest_block)
            speed_mph = speed_mps * 2.23693629
            auth_yd = auth_m / 0.9144

            import datetime
            # Get sim clock time (a datetime object)
            sim_now = clock.get_time()

            # Read arrival time from UI
            arrival_qt = arrival_input.time()
            arr_h = arrival_qt.hour()
            arr_m = arrival_qt.minute()

            # Build arrival datetime ON THE SIMULATION'S DATE
            arrival_dt = sim_now.replace(hour=arr_h, minute=arr_m, second=0, microsecond=0)

            # If arrival time is earlier than current simulation time → assume tomorrow
            if arrival_dt < sim_now:
                arrival_dt += datetime.timedelta(days=1)

            # Compute arrival seconds since simulation-midnight
            midnight = sim_now.replace(hour=0, minute=0, second=0, microsecond=0)
            arrival_seconds = int((arrival_dt - midnight).total_seconds())

            # Travel time based on real path & speed
            travel_time_s = self.state.compute_travel_time(start_block, dest_block)

            # Compute departure time (in seconds from midnight)
            departure_seconds = arrival_seconds - int(travel_time_s)


            # For UI feedback
            dep_dt = midnight + datetime.timedelta(seconds=departure_seconds)
            departure_time_str = dep_dt.strftime("%H:%M:%S")


            # 3. Dispatch train exactly like instant dispatch
            self.state.schedule_manual_dispatch(
                train_id,
                start_block,
                dest_block,
                departure_seconds,
                speed_mph,
                auth_yd
            )



            # 4. Feedback
            QtWidgets.QMessageBox.information(
                self, "Scheduled Train Added",
                f"{train_id} scheduled for dispatch at {departure_time_str}\n"
                f"Destination: {dest_station} (Block {dest_block})\n"
                f"Arrival Time: {arrival_time}\n"
                f"Speed: {speed_mph:.1f} mph\n"
                f"Authority: {auth_yd:.1f} yd"
            )


            dialog.accept()

            # 5. Show it in Train Info immediately
            self._train_info()
            self._reload_line(self.state.line_name)




        confirm_btn.clicked.connect(confirm)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()


    def _toggle_maintenance_mode(self, enabled: bool):
        print(f"[CTC UI] Maintenance mode {'ENABLED' if enabled else 'DISABLED'}")

        # 1️⃣ Update CTC backend internal flag (if you use it)
        self.state.maintenance_enabled = enabled

        # 2️⃣ Notify software track controller
        try:
            self.state.track_controller.set_maintenance_mode(enabled)
        except Exception as e:
            print(f"[CTC UI] Failed to notify TrackControllerBackend: {e}")

        # 3️⃣ Notify hardware controller (if exists)
        try:
            self.state.track_controller_hw.set_maintenance_mode(enabled)
        except Exception:
            pass

        # 4️⃣ Enable maintenance button
        self.maintBtn.setEnabled(enabled)

        # ---------------------------------------------------------
    # Simulation Pause / Resume
    # ---------------------------------------------------------
    def _pause_sim(self):
        print("[UI] Simulation paused")
        self.timer.stop()
        clock.running = False

    def _resume_sim(self):
        print("[UI] Simulation resumed")
        clock.running = True
        self.timer.start(1000)


    # ---------------------------------------------------------
    # Train Info Page
    # ---------------------------------------------------------
    def _train_info(self):
        page = QtWidgets.QWidget()
        self._trainInfoPage = page
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Train Information (live telemetry)"))

        self.trainInfoTable = QtWidgets.QTableWidget(0, 5)
        self.trainInfoTable.setHorizontalHeaderLabels(
            ["Train ID", "Current Block", "Suggested Speed (mph)", "Suggested Authority (yd)", "Line"]
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
            tid = t.get("train_id", "")
            block = t.get("block", "")
            spd_mps = float(t.get("suggested_speed_mps", 0.0))
            mph = spd_mps * MPS_TO_MPH
            auth_m = float(t.get("suggested_authority_m", 0.0))
            auth_yd = auth_m / 0.9144   
            line = t.get("line", self.state.line_name)

            self.trainInfoTable.setItem(r, 0, QtWidgets.QTableWidgetItem(str(tid)))
            self.trainInfoTable.setItem(r, 1, QtWidgets.QTableWidgetItem(str(block)))
            self.trainInfoTable.setItem(r, 2, QtWidgets.QTableWidgetItem(f"{mph:.1f}"))
            self.trainInfoTable.setItem(r, 3, QtWidgets.QTableWidgetItem(f"{auth_yd:.1f}"))
            self.trainInfoTable.setItem(r, 4, QtWidgets.QTableWidgetItem(line))

    # ---------------------------------------------------------
    # Schedule helper: Refresh table
    # ---------------------------------------------------------
    def _refresh_schedule_table(self):
        entries = self.state.schedule.get_schedule()
        self.scheduleTable.setRowCount(len(entries))

        for r, entry in enumerate(entries):
            self.scheduleTable.setItem(r, 0, QtWidgets.QTableWidgetItem(entry["train_id"]))
            self.scheduleTable.setItem(r, 1, QtWidgets.QTableWidgetItem(entry["destination"]))
            self.scheduleTable.setItem(r, 2, QtWidgets.QTableWidgetItem(entry["arrival_time"]))

    # ---------------------------------------------------------
    # Add schedule entry
    # ---------------------------------------------------------
    def _add_schedule_entry(self):
        # Train ID input
        train_id, ok1 = QtWidgets.QInputDialog.getText(self, "Train ID", "Enter train ID (e.g., T1):")
        if not ok1 or not train_id.strip():
            return

        # Destination input
        destination, ok2 = QtWidgets.QInputDialog.getText(self, "Destination", "Enter destination (station name):")
        if not ok2 or not destination.strip():
            return

        # Arrival time input (HH:MM)
        arrival, ok3 = QtWidgets.QInputDialog.getText(self, "Arrival Time", "Enter arrival time (HH:MM):")
        if not ok3 or not arrival.strip():
            return

        # Store in backend schedule manager
        self.state.schedule.add_schedule_entry(train_id.strip(), destination.strip(), arrival.strip())

        # Refresh table
        self._refresh_schedule_table()

    # ---------------------------------------------------------
    # Load schedule from CSV
    # ---------------------------------------------------------
    def _load_schedule_csv(self):
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Schedule CSV",
            "",
            "CSV Files (*.csv)"
        )
        if not filepath:
            return

        self.state.schedule.load_from_csv(filepath)
        self._refresh_schedule_table()

    # ---------------------------------------------------------
    # Maintenance / Upload placeholders
    # ---------------------------------------------------------
    def _maintenance_inputs(self):
        # Only allowed in maintenance mode
        if not self.maint_checkbox.isChecked():
            QtWidgets.QMessageBox.warning(
                self,
                "Enable Maintenance Mode",
                "Enable Maintenance Mode to modify blocks."
            )
            return

        row = self.mapTable.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Select a block first.")
            return

        blk_id = int(self.mapTable.item(row, 1).text())

        # ---- Check if this block is a switch ----
        seg = self.state.track_model.segments.get(blk_id)
        is_switch = seg.__class__.__name__ == "TrackSwitch"

        # ============================================================
        # CASE 1: SWITCH — use TrackControllerBackend.safe_set_switch()
        # ============================================================
        if is_switch:

            # Ask the dispatcher for the new position
            choice, ok = QtWidgets.QInputDialog.getItem(
                self,
                f"Switch {blk_id}",
                "Select switch position:",
                ["Straight (0)", "Diverging (1)"],
                0,
                False
            )

            if not ok:
                return

            pos = 0 if "0" in choice else 1

            try:
                # ⭐⭐ The ONLY correct call ⭐⭐
                self.state.track_controller.safe_set_switch(blk_id, pos)

                print(f"[CTC] Switch {blk_id} set to position {pos}")

            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Switch Error",
                    f"Failed to change switch: {e}"
                )

            # Refresh UI
            self._reload_line(self.state.line_name)
            return

        # ============================================================
        # CASE 2: NOT A SWITCH → block open/close toggle
        # ============================================================
        choice, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Maintenance",
            f"Toggle status for block {blk_id}:",
            ["Open (unoccupied)", "Closed"],
            0,
            False
        )

        if ok:
            closed = "Closed" in choice
            self.state.set_block_closed(blk_id, closed)
            self._reload_line(self.state.line_name)


    def _manual_override(self):
        QtWidgets.QMessageBox.information(self, "Manual Override", "Manual Override page coming soon.")

    def _upload_schedule(self):
        """
        Opens the schedule management page.
        Allows:
            - Viewing loaded schedule
            - Adding entries manually
            - Loading CSV into ScheduleManager
        """
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)

        title = QtWidgets.QLabel("Train Schedule Manager")
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        layout.addWidget(title)

        # -----------------------------
        # Schedule table (read-only)
        # -----------------------------
        self.scheduleTable = QtWidgets.QTableWidget(0, 3)
        self.scheduleTable.setHorizontalHeaderLabels(["Train ID", "Destination", "Arrival Time"])
        self.scheduleTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.scheduleTable.verticalHeader().setVisible(False)
        layout.addWidget(self.scheduleTable)

        # -----------------------------
        # Buttons row (Add + Load CSV)
        # -----------------------------
        btnRow = QtWidgets.QHBoxLayout()

        #addBtn = QtWidgets.QPushButton("Add Entry")
        #addBtn.clicked.connect(self._add_schedule_entry)
        #btnRow.addWidget(addBtn)

        loadBtn = QtWidgets.QPushButton("Load From CSV")
        #loadBtn.clicked.connect(self._load_schedule_csv)
        loadBtn.clicked.connect(self._load_route_a_csv)

        btnRow.addWidget(loadBtn)

        btnRow.addStretch(1)
        layout.addLayout(btnRow)

        # Display page
        self.actionArea.addWidget(page)
        self.actionArea.setCurrentWidget(page)

        # Fill table with any existing schedule entries
        self._refresh_schedule_table()

    def _load_route_a_csv(self):
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load Route Schedule",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not filepath:
            return

        print(f"[UI] Loading schedule CSV: {filepath}")
        self.state.schedule.load_route_csv(filepath, self.state)

    # ---------------------------------------------------------
    # Global Tick — drives simulation + UI
    # ---------------------------------------------------------
    def _tick(self):

       
        try:
            # 1️⃣ Advance simulation time (CTC controls all modules)
            #self.state.tick_all_modules()
            #speed = int(clock.time_multiplier)
            #for _ in range(speed):
            self.state.tick_all_modules()
                # update the label for each simulated tick
            self.clockLabel.setText(f"Sim Time: {clock.get_time_string()}")

            self.throughputLabel.setText(
                f"Throughput: {self.state.train_throughput} trips completed"
            )




            # 2️⃣ Refresh occupancy & train info
            self._reload_line(self.state.line_name)
            if self._trainInfoPage and self.actionArea.currentWidget() is self._trainInfoPage:
                self._populate_train_info_table()

            # 3️⃣ Update the simulation clock display
            self.clockLabel.setText(f"Sim Time: {clock.get_time_string()}")

        except Exception as e:
            print(f"[CTC UI] Tick error: {e}")


# -------------------------------------------------------------
# Main Entry Point
# -------------------------------------------------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    win = CTCWindow()
    win.show()
    app.exec()