"""Main UI window for the Centralized Traffic Controller (CTC).

    This interface provides real-time monitoring and control of:
        • Track occupancy and block-level metadata
        • Manual or scheduled train dispatch
        • Schedule uploads
        • Maintenance mode interactions
        • Train telemetry (speed, authority, block)
        • Global simulation clock controls

    The UI communicates directly with TrackState, which manages the CTC backend,
    TrackModel, and TrackControllers. The UI refreshes at a rate determined by
    the global simulation clock speed.
    """

from PyQt6 import QtWidgets, QtCore, QtGui
from CTC_backend import TrackState
from universal.global_clock import clock
from trackModel.track_model_backend import TrackSwitch
import datetime


BLOCK_LEN_M = 50.0
MPS_TO_MPH = 2.23693629



class CTCWindow(QtWidgets.QMainWindow):
    def __init__(self, backend_by_line, parent=None):
        super().__init__(parent)

        self.backend_by_line = backend_by_line
        self.state = backend_by_line["Green Line"]

        self.setWindowTitle("Centralized Traffic Controller")
        self.resize(1100, 650)

        cw = QtWidgets.QWidget(self)
        self.setCentralWidget(cw)

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

        clock_toolbar = QtWidgets.QToolBar("Clock Control")
        clock_toolbar.setMovable(False)
        clock_toolbar.setStyleSheet("QToolBar { spacing: 10px; }")

        self.clock_start_btn = QtWidgets.QPushButton("Start")
        self.clock_pause_btn = QtWidgets.QPushButton("Pause")
        self.clock_normal_btn = QtWidgets.QPushButton("1× Speed")
        self.clock_fast_btn = QtWidgets.QPushButton("10× Speed")

        
        for btn in (self.clock_start_btn, self.clock_pause_btn, self.clock_normal_btn, self.clock_fast_btn):
            btn.setMinimumWidth(90)
            btn.setStyleSheet("font-weight:bold; font-size:12px;")

    
        clock_toolbar.addWidget(self.clock_start_btn)
        clock_toolbar.addWidget(self.clock_pause_btn)
        clock_toolbar.addSeparator()
        clock_toolbar.addWidget(self.clock_normal_btn)
        clock_toolbar.addWidget(self.clock_fast_btn)

    
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, clock_toolbar)

       
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

        self._trainInfoPage = None
        self._manualPage = None

        self.tabs = QtWidgets.QTabWidget()

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
        occLayout.addWidget(self.mapTable)
        self._reload_line("Green Line")

       
        self.infoBtn = QtWidgets.QPushButton("Train Information")
        self.uploadBtn = QtWidgets.QPushButton("Upload Schedule")
        self.maintBtn = QtWidgets.QPushButton("Maintenance / Inputs")
        self.dispatchBtn = QtWidgets.QPushButton("Dispatch Train")
        for b in ( self.infoBtn, self.uploadBtn, self.maintBtn, self.dispatchBtn):
            b.setMinimumHeight(40)
            b.setStyleSheet("font-size:14px; font-weight:bold;")

        btnRow = QtWidgets.QHBoxLayout()
        btnRow.addWidget(self.dispatchBtn)
      
        btnRow.addWidget(self.infoBtn)
        btnRow.addWidget(self.uploadBtn)
        btnRow.addWidget(self.maintBtn)
        occLayout.addLayout(btnRow)

       
        self.infoBtn.clicked.connect(self._train_info)
        self.uploadBtn.clicked.connect(self._upload_schedule)
        self.maintBtn.clicked.connect(self._maintenance_inputs)
        self.dispatchBtn.clicked.connect(self._dispatch_train)

       
        self.actionArea = QtWidgets.QStackedWidget()
        self.blankPage = QtWidgets.QWidget()
        self.actionArea.addWidget(self.blankPage)
        self.actionArea.setCurrentWidget(self.blankPage)
        occLayout.addWidget(self.actionArea)

        self.tabs.addTab(self.occupancyTab, "Occupancy")
        
        layout = QtWidgets.QVBoxLayout(cw)
        self.clockLabel = QtWidgets.QLabel(f"Sim Time: {clock.get_time_string()}")
        self.clockLabel.setStyleSheet("font-weight:bold; font-size:14px;")
        layout.addWidget(self.clockLabel)

        self.throughputLabel = QtWidgets.QLabel("Throughput: 0 passengers/hour")

        self.throughputLabel.setStyleSheet("font-weight:bold; font-size:14px;")
        layout.addWidget(self.throughputLabel)

        layout.addWidget(self.tabs, stretch=2)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)  #

        self._apply_clock_speed()

    def toggle_mode(self, enabled: bool):
        """Switch between Manual and Auto dispatching modes.

        Args:
            enabled: True if the toggle button is pressed (Manual Mode),
                    False if released (Auto Mode).

        Behavior:
            • Updates backend mode in TrackState
            • Enables or disables UI buttons accordingly
            • Displays updated styling and messaging
        """
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
       
        print(f"[CTC UI] Switched to {self.mode.upper()} mode.")

    def _apply_clock_speed(self):
        """Update UI timer interval according to simulation speed.

        The global simulation clock multiplier determines how often the UI should
        call _tick(). Faster simulation ⇒ shorter UI timer intervals.

        Ensures a minimum interval of 10ms to avoid UI overload.
        """

       
        multiplier = max(0.1, clock.time_multiplier)

        interval_ms = max(10, int(1000 / multiplier))  # min 10ms to stay safe

        self.timer.start(interval_ms)
        print(f"[UI] Timer interval set to {interval_ms} ms (speed={multiplier}×)")

    def _reload_line(self, line_name: str):
        """Reload block table and backend reference when a new line is selected.

        Args:
            line_name: Name of the transit line ("Red Line", "Green Line").

        Behavior:
            • Switches self.state to the chosen backend
            • Reconstructs & repopulates the occupancy table
            • Updates switch position, signals, crossings, and metadata
            • Refreshes train info table if currently displayed
        """
        
       
        self.state = self.backend_by_line[line_name]

        
        blocks = self.state.get_blocks()
        self.mapTable.setRowCount(len(blocks))

       
        for r, b in enumerate(blocks):
            seg = self.state.track_model.segments.get(b.block_id)

           
            if isinstance(seg, TrackSwitch):
                switch_text = "Straight" if seg.current_position == 0 else "Diverging"
            else:
                switch_text = ""

            rowdata = [
                b.section,
                b.block_id,
                b.status,
                b.station,
                b.station_side,
                switch_text,
                "--",
                ("Yes" if b.crossing else ""),
                f"{b.speed_limit:.0f} mph"
            ]

            for c, value in enumerate(rowdata):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

               
                if c == 2:  # Status column
                    if b.status == "occupied":
                        item.setBackground(QtGui.QColor("#2ecc71"))  # green
                        item.setForeground(QtGui.QColor("black"))
                    elif b.status == "unoccupied":
                        item.setBackground(QtGui.QColor("#e74c3c"))  # red
                        item.setForeground(QtGui.QColor("white"))
                    elif b.status == "closed":
                        item.setBackground(QtGui.QColor("gray"))
                        item.setForeground(QtGui.QColor("white"))

                
                if c == 6:
                    if isinstance(seg, TrackSwitch):
                        prev_sig = seg.previous_signal_state.name
                        straight_sig = seg.straight_signal_state.name
                        diverging_sig = seg.diverging_signal_state.name
                        text = f"P:{prev_sig}  S:{straight_sig}  D:{diverging_sig}"
                        item.setText(text)

                        if "RED" in [prev_sig, straight_sig, diverging_sig]:
                            item.setBackground(QtGui.QColor("#b00020"))
                            item.setForeground(QtGui.QColor("white"))
                        elif "YELLOW" in [prev_sig, straight_sig, diverging_sig]:
                            item.setBackground(QtGui.QColor("#d7b600"))
                            item.setForeground(QtGui.QColor("black"))
                        else:
                            item.setBackground(QtGui.QColor("#1b5e20"))
                            item.setForeground(QtGui.QColor("white"))
                    else:
                        item.setText("")

                self.mapTable.setItem(r, c, item)

       
        if self._trainInfoPage and self.actionArea.currentWidget() is self._trainInfoPage:
            self._populate_train_info_table()

    def _show_dispatch_options(self):
        """Present a modal dialog allowing the dispatcher to choose dispatch type.

    Options:
        • Instant dispatch → Immediately create a train
        • Scheduled dispatch → Specify arrival time for future dispatch
        • Cancel → Close dialog with no action
    """
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Dispatch Options")
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)

        label = QtWidgets.QLabel("Choose dispatch type:")
        label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(label)

        instant_btn = QtWidgets.QPushButton("Instant Dispatch")
        schedule_btn = QtWidgets.QPushButton("Schedule Dispatch")

        instant_btn.setMinimumHeight(35)
        schedule_btn.setMinimumHeight(35)

        layout.addWidget(instant_btn)
        layout.addWidget(schedule_btn)

        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setMinimumHeight(30)
        layout.addWidget(cancel_btn)

        instant_btn.clicked.connect(lambda: (dialog.accept(), self._instant_dispatch()))
        schedule_btn.clicked.connect(lambda: (dialog.accept(), self._scheduled_dispatch()))
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def _dispatch_train(self):
        """Entry point for the Dispatch Train button.

    Ensures the controller is in Manual Mode before allowing further actions.
    Opens the dispatch options modal if permitted.
    """
        if self.mode != "manual":
            QtWidgets.QMessageBox.warning(self, "Mode Error",
                                        "Switch to Manual Mode to dispatch a train.")
            return

        self._show_dispatch_options()

    def _instant_dispatch(self):
        """Perform a dispatcher-driven instant train dispatch.

    Prompts user for:
        • Train ID
        • Starting block
        • Destination block

    Behavior:
        • Computes safe speed and authority using backend
        • Dispatches train immediately via TrackState
        • Refreshes train info & block table
    """
        try:
           
            train_id, ok_id = QtWidgets.QInputDialog.getText(
                self, "Instant Dispatch", "Enter Train ID (e.g., T1):"
            )
            if not ok_id or not train_id.strip():
                return
            train_id = train_id.strip().upper()

          
            start_block, ok_block = QtWidgets.QInputDialog.getInt(
                self, "Starting Block", "Enter starting block number:", 0, 0, 150
            )
            if not ok_block:
                return
            
            dest_block, ok_dest = QtWidgets.QInputDialog.getInt(
                self, "Destination Block", "Enter final block number:", 0, 0, 150
            )
            if not ok_dest:
                return

            speed_mps, auth_m = self.state.compute_suggestions(start_block, dest_block)

        
            speed_mph = speed_mps * 2.23693629
            auth_yd = auth_m / 0.9144

          
            self.state.dispatch_train(train_id, start_block, dest_block, speed_mph, auth_yd)


            QtWidgets.QMessageBox.information(
                self,
                "Train Dispatched",
                f"{train_id} dispatched at block {start_block}\n"
                f"Destination: {dest_block}\n"
                f"Computed Speed: {speed_mph:.1f} mph\n"
                f"Computed Authority: {auth_yd:.1f} yd"
            )

           
            self._train_info()
            self._reload_line(self.state.line_name)

        except Exception as e:
            print("[CTC UI] Instant dispatch error:", e)

    def _scheduled_dispatch(self):
        """Create a new scheduled dispatch based on arrival time at a station.

    Dialog gathers:
        • Train ID
        • Start block
        • Destination station
        • Desired arrival time

    Behavior:
        • Converts arrival time to simulation seconds
        • Computes travel time & calculates dispatch timestamp
        • Stores pending dispatch via TrackState.schedule_manual_dispatch()
        • Shows confirmation and refreshes UI tables
    """
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Scheduled Dispatch")
        dialog.setModal(True)

        layout = QtWidgets.QFormLayout(dialog)

      
        train_id_input = QtWidgets.QLineEdit()
        train_id_input.setPlaceholderText("e.g., T1")
        layout.addRow("Train ID:", train_id_input)

      
        start_block_input = QtWidgets.QSpinBox()
        start_block_input.setRange(1, 150)
        layout.addRow("Starting Block:", start_block_input)

      
        station_dropdown = QtWidgets.QComboBox()
        station_names = [
            seg.station_name 
            for seg in self.state.track_model.segments.values()
            if hasattr(seg, "station_name") and seg.station_name
        ]

        station_dropdown.addItems(station_names)
        layout.addRow("Destination Station:", station_dropdown)

       
        arrival_input = QtWidgets.QTimeEdit()
        arrival_input.setDisplayFormat("HH:mm")
        arrival_input.setTime(QtCore.QTime.currentTime())
        layout.addRow("Arrival Time:", arrival_input)

      
        btn_row = QtWidgets.QHBoxLayout()
        confirm_btn = QtWidgets.QPushButton("Dispatch")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        btn_row.addWidget(confirm_btn)
        btn_row.addWidget(cancel_btn)
        layout.addRow(btn_row)

       
        def confirm():
            train_id = train_id_input.text().strip().upper()
            start_block = int(start_block_input.value())
            
         

            dest_station = station_dropdown.currentText()
            arrival_time = arrival_input.time().toString("HH:mm")

            if not train_id:
                QtWidgets.QMessageBox.warning(dialog, "Error", "Train ID cannot be empty.")
                return

           
            dest_block = self.state.station_to_block(dest_station)
            if dest_block is None:
                QtWidgets.QMessageBox.warning(dialog, "Error", f"Station {dest_station} has no block.")
                return


            speed_mps, auth_m = self.state.compute_suggestions(start_block, dest_block)
            speed_mph = speed_mps * 2.23693629
            auth_yd = auth_m / 0.9144

           
            sim_now = clock.get_time()

            arrival_qt = arrival_input.time()
            arr_h = arrival_qt.hour()
            arr_m = arrival_qt.minute()

            arrival_dt = sim_now.replace(hour=arr_h, minute=arr_m, second=0, microsecond=0)

            if arrival_dt < sim_now:
                arrival_dt += datetime.timedelta(days=1)

            midnight = sim_now.replace(hour=0, minute=0, second=0, microsecond=0)
            arrival_seconds = int((arrival_dt - midnight).total_seconds())

            travel_time_s = self.state.compute_travel_time(start_block, dest_block)

            departure_seconds = arrival_seconds - int(travel_time_s)

            dep_dt = midnight + datetime.timedelta(seconds=departure_seconds)
            departure_time_str = dep_dt.strftime("%H:%M:%S")

            self.state.schedule_manual_dispatch(
                train_id,
                start_block,
                dest_block,
                departure_seconds,
                speed_mph,
                auth_yd
            )

            QtWidgets.QMessageBox.information(
                self, "Scheduled Train Added",
                f"{train_id} scheduled for dispatch at {departure_time_str}\n"
                f"Destination: {dest_station} (Block {dest_block})\n"
                f"Arrival Time: {arrival_time}\n"
                f"Speed: {speed_mph:.1f} mph\n"
                f"Authority: {auth_yd:.1f} yd"
            )

            dialog.accept()

            self._train_info()
            self._reload_line(self.state.line_name)

        confirm_btn.clicked.connect(confirm)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def _toggle_maintenance_mode(self, enabled: bool):
        """Enable or disable maintenance mode for manual block/switch changes.

    Args:
        enabled: Whether maintenance mode is active.

    Behavior:
        • Updates backend state
        • Notifies both SW and HW controllers
        • Enables Maintenance/Inputs menu
    """
        print(f"[CTC UI] Maintenance mode {'ENABLED' if enabled else 'DISABLED'}")

        self.state.maintenance_enabled = enabled

        try:
            self.state.track_controller.set_maintenance_mode(enabled)
        except Exception as e:
            print(f"[CTC UI] Failed to notify TrackControllerBackend: {e}")

        try:
            self.state.track_controller_hw.set_maintenance_mode(enabled)
        except Exception:
            pass

        self.maintBtn.setEnabled(enabled)

    def _pause_sim(self):
        """Pause simulation clock and UI updates."""
        print("[UI] Simulation paused")
        self.timer.stop()
        clock.running = False

    def _resume_sim(self):
        """Resume simulation clock and restart periodic UI timer."""
        print("[UI] Simulation resumed")
        clock.running = True
        self.timer.start(1000)

    def _train_info(self):
        """Open the Train Information panel displaying live telemetry.

        Creates a table showing:
            • Train ID
            • Current block
            • Suggested speed (mph)
            • Suggested authority (yd)
            • Line

        Updates automatically during _tick().
        """
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
        """Fill the Train Information table with latest data from TrackState."""
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

    def _refresh_schedule_table(self):
        """Refresh schedule table entries from backend ScheduleManager."""
        entries = self.state.schedule.get_schedule()
        self.scheduleTable.setRowCount(len(entries))

        for r, entry in enumerate(entries):
            self.scheduleTable.setItem(r, 0, QtWidgets.QTableWidgetItem(entry["train_id"]))
            self.scheduleTable.setItem(r, 1, QtWidgets.QTableWidgetItem(entry["destination"]))
            self.scheduleTable.setItem(r, 2, QtWidgets.QTableWidgetItem(entry["arrival_time"]))

    def _add_schedule_entry(self):
        """Add a single user-entered schedule row to the backend.

    Collects:
        • Train ID
        • Destination station
        • Arrival time (HH:MM)

    Adds entry through ScheduleManager and refreshes UI.
    """
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

    def _load_schedule_csv(self):
        """Load a simple 3-column schedule CSV and update UI table."""
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

    def _maintenance_inputs(self):
        """Modify selected block's status or switch position (Maintenance Mode only).

    Allows dispatcher to:
        • Open/close a block
        • Change a switch’s position
        • Reload the block table after modifications
    """
        
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

       
        seg = self.state.track_model.segments.get(blk_id)
        is_switch = seg.__class__.__name__ == "TrackSwitch"

        
        if is_switch:

            
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
               
                self.state.track_controller.safe_set_switch(blk_id, pos)

                print(f"[CTC] Switch {blk_id} set to position {pos}")

            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Switch Error",
                    f"Failed to change switch: {e}"
                )

            self._reload_line(self.state.line_name)
            return

       
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

    def _upload_schedule(self):
        """Open the Schedule Manager tab.

        Enables users to:
            • View loaded schedule entries
            • Import Route A/B/C CSV files
            • Refresh schedule list in UI
        """
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)

        title = QtWidgets.QLabel("Train Schedule Manager")
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        layout.addWidget(title)

       
        self.scheduleTable = QtWidgets.QTableWidget(0, 3)
        self.scheduleTable.setHorizontalHeaderLabels(["Train ID", "Destination", "Arrival Time"])
        self.scheduleTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.scheduleTable.verticalHeader().setVisible(False)
        layout.addWidget(self.scheduleTable)

       
        btnRow = QtWidgets.QHBoxLayout()

      

        loadBtn = QtWidgets.QPushButton("Load From CSV")
        loadBtn.clicked.connect(self._load_route_a_csv)

        btnRow.addWidget(loadBtn)

        btnRow.addStretch(1)
        layout.addLayout(btnRow)

        self.actionArea.addWidget(page)
        self.actionArea.setCurrentWidget(page)

        self._refresh_schedule_table()

    def _load_route_a_csv(self):
        """Open file dialog to load a multi-stop Route A/B/C schedule CSV.

    Passes file to ScheduleManager.load_route_csv() and refreshes UI.
    """
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
        self._refresh_schedule_table()

    def _tick(self):
        
        """Main UI tick — called once per timer interval.

    Responsibilities:
        • Advance backend logic via TrackState.tick_all_modules()
        • Update simulation time label
        • Update throughput label
        • Refresh block table
        • Refresh train info panel (if visible)
    """
        try:
        
            self.state.tick_all_modules()
               
            self.clockLabel.setText(f"Sim Time: {clock.get_time_string()}")

            throughput = self.state.get_throughput_per_hour()
            self.throughputLabel.setText(
                f"Throughput: {throughput} passengers/hour"
            )

            self._reload_line(self.state.line_name)
            if self._trainInfoPage and self.actionArea.currentWidget() is self._trainInfoPage:
                self._populate_train_info_table()

            self.clockLabel.setText(f"Sim Time: {clock.get_time_string()}")

        except Exception as e:
            print(f"[CTC UI] Tick error: {e}")


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    win = CTCWindow()
    win.show()
    app.exec()