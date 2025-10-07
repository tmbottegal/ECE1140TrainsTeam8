from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QScrollArea,
    QTableWidget, QHeaderView, QPushButton, QLineEdit, QSizePolicy, QTableWidgetItem,
    QDialog, QFormLayout, QDialogButtonBox, QSpinBox, QMessageBox, QApplication
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal


class ManualOverrideDialog(QDialog):
    applied = pyqtSignal()  # emitted whenever Apply is pressed or live-change applied

    def __init__(self, parent_ui):
        super().__init__(parent=parent_ui)
        self.ui = parent_ui
        self.setWindowTitle("Test UI")
        # keep dialog modeless so user can see live updates in main UI
        self.setModal(False)
        self.resize(420, 240)
        self._build()

        # Auto-connect applied to parent's refresh_tables if available.
        try:
            if hasattr(self.ui, "refresh_tables"):
                self.applied.connect(self.ui.refresh_tables)
        except Exception as e:
            print(f"[DEBUG] ManualOverrideDialog: failed to auto-connect applied -> refresh_tables: {e}")

        # Connect interactive controls for *live* updates
        self._connect_live_handlers()

    def _build(self):
        form = QFormLayout(self)

        # Block occupancy controls
        self.block_spin = QSpinBox()
        self.block_spin.setMinimum(1)
        self.block_spin.setMaximum(self.ui.backend.num_blocks)
        form.addRow("Block #", self.block_spin)

        self.occ_combo = QComboBox()
        self.occ_combo.addItems(["No", "Yes"])
        form.addRow("Occupancy", self.occ_combo)

        # Switch controls
        self.switch_combo = QComboBox()
        switch_ids = sorted(self.ui.backend.switches.keys())
        if not switch_ids:
            self.switch_combo.addItem("None")
            self.switch_combo.setEnabled(False)
        else:
            for sid in switch_ids:
                self.switch_combo.addItem(str(sid))
        form.addRow("Switch ID", self.switch_combo)

        self.switch_pos_combo = QComboBox()
        self.switch_pos_combo.addItems(["Normal", "Alternate"])
        form.addRow("Switch Position", self.switch_pos_combo)

        # Crossing controls
        self.crossing_combo = QComboBox()
        crossing_ids = sorted(self.ui.backend.crossings.keys())
        if not crossing_ids:
            self.crossing_combo.addItem("None")
            self.crossing_combo.setEnabled(False)
        else:
            for cid in crossing_ids:
                self.crossing_combo.addItem(str(cid))
        form.addRow("Crossing ID", self.crossing_combo)

        self.crossing_status_combo = QComboBox()
        self.crossing_status_combo.addItems(["Inactive", "Active"])
        form.addRow("Crossing Status", self.crossing_status_combo)

        # Signal control
        self.signal_combo = QComboBox()
        self.signal_combo.addItems(["Red", "Yellow", "Green", "Super Green"])
        form.addRow("Signal Color", self.signal_combo)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Apply")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._apply)
        form.addRow(buttons)

    def _connect_live_handlers(self):
        # Refresh fields when block number changes
        try:
            self.block_spin.valueChanged.connect(self._on_block_changed)
        except Exception:
            pass

        # Apply occupancy immediately when changed
        try:
            self.occ_combo.currentTextChanged.connect(self._on_occupancy_changed)
        except Exception:
            pass

        # Keep switch selection and position in sync; apply position changes immediately
        try:
            self.switch_combo.currentTextChanged.connect(self._on_switch_selection_changed)
            self.switch_pos_combo.currentTextChanged.connect(self._on_switch_position_changed)
        except Exception:
            pass

        # Crossings
        try:
            self.crossing_combo.currentTextChanged.connect(self._on_crossing_selection_changed)
            self.crossing_status_combo.currentTextChanged.connect(self._on_crossing_status_changed)
        except Exception:
            pass

        # Signal
        try:
            self.signal_combo.currentTextChanged.connect(self._on_signal_changed)
        except Exception:
            pass

    def refresh_from_backend(self):
        # update block max
        try:
            self.block_spin.setMaximum(self.ui.backend.num_blocks)
        except Exception:
            pass

        # occupancy default for selected block
        b = self.block_spin.value()
        occ = self.ui.backend.blocks.get(b, {}).get("occupied", False)
        self.occ_combo.setCurrentText("Yes" if occ else "No")

        # switches
        self.switch_combo.blockSignals(True)
        self.switch_pos_combo.blockSignals(True)
        try:
            self.switch_combo.clear()
            switch_ids = sorted(self.ui.backend.switches.keys())
            if switch_ids:
                self.switch_combo.setEnabled(True)
                for sid in switch_ids:
                    self.switch_combo.addItem(str(sid))
                # set the position for the first item
                try:
                    cur_sid_text = self.switch_combo.currentText()
                    cur_sid = int(cur_sid_text)
                    cur_pos = self.ui.backend.switches.get(cur_sid, "Normal")
                    self.switch_pos_combo.setCurrentText(cur_pos)
                except Exception:
                    self.switch_pos_combo.setCurrentText("Normal")
            else:
                self.switch_combo.addItem("None")
                self.switch_combo.setEnabled(False)
                self.switch_pos_combo.setCurrentText("Normal")
        finally:
            self.switch_combo.blockSignals(False)
            self.switch_pos_combo.blockSignals(False)

        # crossings
        self.crossing_combo.blockSignals(True)
        self.crossing_status_combo.blockSignals(True)
        try:
            self.crossing_combo.clear()
            crossing_ids = sorted(self.ui.backend.crossings.keys())
            if crossing_ids:
                self.crossing_combo.setEnabled(True)
                for cid in crossing_ids:
                    self.crossing_combo.addItem(str(cid))
                try:
                    cur_cid_text = self.crossing_combo.currentText()
                    cur_cid = int(cur_cid_text)
                    cur_status = self.ui.backend.crossings.get(cur_cid, "Inactive")
                    self.crossing_status_combo.setCurrentText(cur_status)
                except Exception:
                    self.crossing_status_combo.setCurrentText("Inactive")
            else:
                self.crossing_combo.addItem("None")
                self.crossing_combo.setEnabled(False)
                self.crossing_status_combo.setCurrentText("Inactive")
        finally:
            self.crossing_combo.blockSignals(False)
            self.crossing_status_combo.blockSignals(False)

        # signal color
        try:
            b = self.block_spin.value()
            sig = self.ui.backend.blocks.get(b, {}).get("signal", "Green")
            self.signal_combo.setCurrentText(sig)
        except Exception:
            self.signal_combo.setCurrentText("Green")

    # --- Live handlers ---
    def _on_block_changed(self, value):
        # when user changes block number, update dependent controls from backend
        try:
            self.refresh_from_backend()
        except Exception:
            pass

    def _on_occupancy_changed(self, txt):
        try:
            block = int(self.block_spin.value())
            occ = True if txt == "Yes" else False
            self.ui.backend.set_block_occupancy(block, occ)
            self.applied.emit()
        except Exception as e:
            QMessageBox.warning(self, "Manual Override: Occupancy Failed", str(e))

    def _on_switch_selection_changed(self, sid_text):
        # update switch position combobox to reflect backend
        try:
            sid = int(sid_text)
            pos = self.ui.backend.switches.get(sid, "Normal")
            # block signals while updating programmatically
            self.switch_pos_combo.blockSignals(True)
            self.switch_pos_combo.setCurrentText(pos)
            self.switch_pos_combo.blockSignals(False)
        except Exception:
            pass

    def _on_switch_position_changed(self, pos_text):
        # apply switch change immediately using backend.safe_set_switch
        try:
            if not self.switch_combo.isEnabled():
                return
            sid = int(self.switch_combo.currentText())
            # use the safe API present in backend
            try:
                self.ui.backend.safe_set_switch(sid, pos_text)
                self.applied.emit()
            except Exception as e:
                # show safety or value errors
                QMessageBox.warning(self, "Manual Override: Switch Failed", str(e))
                # refresh display to reflect actual backend state
                self.refresh_from_backend()
        except Exception as e:
            print(f"[DEBUG] switch apply error: {e}")

    def _on_crossing_selection_changed(self, cid_text):
        try:
            cid = int(cid_text)
            status = self.ui.backend.crossings.get(cid, "Inactive")
            self.crossing_status_combo.blockSignals(True)
            self.crossing_status_combo.setCurrentText(status)
            self.crossing_status_combo.blockSignals(False)
        except Exception:
            pass

    def _on_crossing_status_changed(self, status_text):
        try:
            if not self.crossing_combo.isEnabled():
                return
            cid = int(self.crossing_combo.currentText())
            try:
                self.ui.backend.safe_set_crossing(cid, status_text)
                self.applied.emit()
            except Exception as e:
                QMessageBox.warning(self, "Manual Override: Crossing Failed", str(e))
                self.refresh_from_backend()
        except Exception as e:
            print(f"[DEBUG] crossing apply error: {e}")

    def _on_signal_changed(self, color_text):
        try:
            block = int(self.block_spin.value())
            try:
                self.ui.backend.set_signal(block, color_text)
                self.applied.emit()
            except Exception as e:
                QMessageBox.warning(self, "Manual Override: Signal Failed", str(e))
                self.refresh_from_backend()
        except Exception as e:
            print(f"[DEBUG] signal apply error: {e}")

    def _apply(self):
        # Keep a compatible Apply that performs the same changes (useful if user expects a final confirmation)
        errors = []

        # Occupancy
        try:
            block = int(self.block_spin.value())
            occ = True if self.occ_combo.currentText() == "Yes" else False
            self.ui.backend.set_block_occupancy(block, occ)
        except Exception as e:
            errors.append(f"Block occupancy: {e}")

        # Switch
        try:
            if self.switch_combo.isEnabled():
                try:
                    sid = int(self.switch_combo.currentText())
                    pos = self.switch_pos_combo.currentText()
                    try:
                        self.ui.backend.safe_set_switch(sid, pos)
                    except Exception as e:
                        errors.append(f"Switch: {e}")
                except ValueError:
                    pass
        except Exception as e:
            errors.append(f"Switch: {e}")

        # Crossing
        try:
            if self.crossing_combo.isEnabled():
                try:
                    cid = int(self.crossing_combo.currentText())
                    status = self.crossing_status_combo.currentText()
                    try:
                        self.ui.backend.safe_set_crossing(cid, status)
                    except Exception as e:
                        errors.append(f"Crossing: {e}")
                except ValueError:
                    pass
        except Exception as e:
            errors.append(f"Crossing: {e}")

        # Signal
        try:
            block = int(self.block_spin.value())
            color = self.signal_combo.currentText()
            try:
                self.ui.backend.set_signal(block, color)
            except Exception as e:
                errors.append(f"Signal: {e}")
        except Exception as e:
            errors.append(f"Signal: {e}")

        # ensure main UI updates
        try:
            self.ui.refresh_tables()
        except Exception:
            pass

        QApplication.processEvents()

        # Emit applied so other listeners can react
        self.applied.emit()

        if errors:
            QMessageBox.warning(self, "Manual Override: Partial Failure", "\n".join(errors))
        else:
            QMessageBox.information(self, "Manual Override", "Changes applied.")
            # keep dialog open for further live edits; do not auto-close


class TrackControllerUI(QWidget):
    def __init__(self, network, parent=None):
        super().__init__(parent)
        self.network = network
        self.backend = network.get_line("Blue Line")
        try:
            self.backend.add_listener(self.refresh_tables)
        except Exception:
            pass

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Track dropdown
        top_row = QHBoxLayout()
        self.dropdown_text = QLabel("Track: Blue Line")
        font_droptext = self.dropdown_text.font()
        font_droptext.setPointSize(16)
        font_droptext.setBold(True)
        self.dropdown_text.setFont(font_droptext)
        top_row.addWidget(self.dropdown_text)
        top_row.addStretch()

        self.track_picker = QComboBox()
        self.track_picker.addItems(["Blue Line", "Red Line", "Green Line"])
        self.track_picker.setCurrentIndex(0)
        self.track_picker.setFixedHeight(32)
        self.track_picker.setFixedWidth(160)
        font_drop = QFont()
        font_drop.setPointSize(14)
        self.track_picker.setFont(font_drop)
        self.track_picker.currentTextChanged.connect(self.switch_line)
        top_row.addWidget(self.track_picker)
        layout.addLayout(top_row)

        # Scroll area for tables
        self.table_hud = QScrollArea()
        self.table_hud.setWidgetResizable(True)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)

        # Main block table
        self.tablemain = QTableWidget()
        self.container_layout.addWidget(self.tablemain)

        # Switches
        self.container_layout.addWidget(QLabel("Switches"))
        self.tableswitch = QTableWidget()
        self.container_layout.addWidget(self.tableswitch)

        # Crossings
        self.container_layout.addWidget(QLabel("Railway Crossings"))
        self.tablecrossing = QTableWidget()
        self.container_layout.addWidget(self.tablecrossing)

        # Broken Rails
        self.container_layout.addWidget(QLabel("Broken Rails"))
        self.tablebroken = QTableWidget()
        self.container_layout.addWidget(self.tablebroken)

        # Signal States
        self.container_layout.addWidget(QLabel("Signal States"))
        self.tablesignal = QTableWidget()
        self.container_layout.addWidget(self.tablesignal)

        self.table_hud.setWidget(self.container)
        layout.addWidget(self.table_hud)

        # Bottom row
        bottom_row = QHBoxLayout()
        self.plc_button = QPushButton("PLC File Upload")
        bigboi = self.plc_button.sizeHint()
        self.plc_button.setFixedSize(bigboi.width() * 2, bigboi.height() * 2)
        bottom_row.addWidget(self.plc_button)

        self.filename_box = QLineEdit("File: None")
        self.filename_box.setReadOnly(True)
        self.filename_box.setFixedWidth(800)
        font_text: QFont = self.filename_box.font()
        font_text.setPointSize(14)
        self.filename_box.setFont(font_text)
        self.filename_box.setFixedHeight(bigboi.height() * 2)
        bottom_row.addWidget(self.filename_box)
        bottom_row.addStretch()
        self.manual_button = QPushButton("Test UI")
        self.manual_button.clicked.connect(self.open_manual_override)
        self.plc_button.setFixedSize(bigboi.width() * 2, bigboi.height() * 2)
        bottom_row.addWidget(self.manual_button)
        layout.addLayout(bottom_row)

    def switch_line(self, line_name: str):
        self.dropdown_text.setText(f"Track: {line_name}")
        # remove previous listener (if any)
        try:
            old_backend = self.backend
            old_backend.remove_listener(self.refresh_tables)
        except Exception:
            pass

        # set new backend and register listener
        self.backend = self.network.get_line(line_name)
        try:
            self.backend.add_listener(self.refresh_tables)
        except Exception:
            pass

        self.refresh_tables()

    def open_manual_override(self):
        dlg = ManualOverrideDialog(self)
        # Ensure dialog reflects current backend (important if user switched lines)
        dlg.refresh_from_backend()
        try:
            dlg.applied.connect(self.refresh_tables)
        except Exception:
            pass
        # show modeless so user can keep it open and see live updates
        dlg.show()

    def refresh_tables(self):
        # Reset tables
        try:
            self.tablemain.setRowCount(self.backend.num_blocks)
            self.tablemain.setColumnCount(6)
            self.tablemain.setHorizontalHeaderLabels([
                "Block",
                "Suggested Speed",
                "Commanded Speed",
                "Occupancy",
                "Suggested Authority",
                "Commanded Authority"
            ])
            self.tablemain.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.tablemain.verticalHeader().setVisible(False)

            for i, (block, data) in enumerate(self.backend.blocks.items()):
                self.tablemain.setItem(i, 0, QTableWidgetItem(str(block)))
                self.tablemain.setItem(i, 1, QTableWidgetItem(str(data["suggested_speed"])))
                self.tablemain.setItem(i, 2, QTableWidgetItem(str(data["commanded_speed"])))
                self.tablemain.setItem(i, 3, QTableWidgetItem("Yes" if data["occupied"] else "No"))
                self.tablemain.setItem(i, 4, QTableWidgetItem(str(data["suggested_auth"])))
                self.tablemain.setItem(i, 5, QTableWidgetItem(str(data["commanded_auth"])))

            # Switches
            self.tableswitch.setRowCount(len(self.backend.switches))
            self.tableswitch.setColumnCount(3)
            self.tableswitch.setHorizontalHeaderLabels(["Switch ID", "Blocks", "Position"])
            self.tableswitch.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for i, (sid, pos) in enumerate(self.backend.switches.items()):
                self.tableswitch.setItem(i, 0, QTableWidgetItem(str(sid)))
                blocks = self.backend.switch_map.get(sid, ())
                self.tableswitch.setItem(i, 1, QTableWidgetItem(str(blocks)))
                self.tableswitch.setItem(i, 2, QTableWidgetItem(pos))

            # Crossings
            self.tablecrossing.setRowCount(len(self.backend.crossings))
            self.tablecrossing.setColumnCount(3)
            self.tablecrossing.setHorizontalHeaderLabels(["Crossing ID", "Block", "Status"])
            self.tablecrossing.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for i, (cid, status) in enumerate(self.backend.crossings.items()):
                block = self.backend.crossing_blocks.get(cid, "-")
                self.tablecrossing.setItem(i, 0, QTableWidgetItem(str(cid)))
                self.tablecrossing.setItem(i, 1, QTableWidgetItem(str(block)))
                self.tablecrossing.setItem(i, 2, QTableWidgetItem(status))

            # Broken Rails
            broken_blocks = [b for b, d in self.backend.blocks.items() if d["broken"]]
            self.tablebroken.setRowCount(len(broken_blocks))
            self.tablebroken.setColumnCount(2)
            self.tablebroken.setHorizontalHeaderLabels(["Block", "Status"])
            self.tablebroken.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

            for row, b in enumerate(broken_blocks):
                self.tablebroken.setItem(row, 0, QTableWidgetItem(str(b)))
                self.tablebroken.setItem(row, 1, QTableWidgetItem("Broken"))

            # Signal States
            self.tablesignal.setRowCount(self.backend.num_blocks)
            self.tablesignal.setColumnCount(2)
            self.tablesignal.setHorizontalHeaderLabels(["Block", "Signal"])
            self.tablesignal.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for i, (block, data) in enumerate(self.backend.blocks.items()):
                self.tablesignal.setItem(i, 0, QTableWidgetItem(str(block)))
                self.tablesignal.setItem(i, 1, QTableWidgetItem(data.get("signal", "Green")))

        except Exception as e:
            print(f"[DEBUG] refresh_tables error: {e}")
