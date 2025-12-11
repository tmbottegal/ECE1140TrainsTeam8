"""
Track Model Frontend -- An LLM was used to help with creation of this.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universal.universal import (
    ConversionFunctions
)

from track_model_backend import (
    TrackNetwork, 
    TrackFailureType,
)

from universal.global_clock import clock

import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, 
    QTabWidget, QHBoxLayout, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

class NetworkStatusUI(QWidget):
    def __init__(self, track_network1=None, track_network2=None):
        super().__init__()
        
        # init multiple TrackNetwork instances
        self.track_network1 = track_network1 if track_network1 is not None else TrackNetwork()
        self.track_network2 = track_network2 if track_network2 is not None else TrackNetwork()
        
        # track_network object points to the currently active network
        # initially points to track_network1
        self.track_network = self.track_network1
        self.active_network_index = 1  # track which network is currently active (1 or 2)
        
        self.updating_temperature = False  # flag to prevent recursive temp updates
        self.init_ui()
        
        # load track layouts for both networks if not provided
        if not track_network1:
            self.load_track_layout_for_network(self.track_network1, "green_line.csv")
        if not track_network2:
            self.load_track_layout_for_network(self.track_network2, "red_line.csv")
        
        # populate network selector dropdown
        self.populate_network_selector()
        
        # display initial network status for the active network
        self.refresh_status()

        clock.register_listener(self.track_network1.set_time)
        clock.register_listener(self.track_network2.set_time)
        clock.register_listener(self.auto_refresh_status)
        
    def init_ui(self):
        self.setWindowTitle("Track Model - Network Status")
        self.setGeometry(100, 100, 1400, 800)
        
        layout = QVBoxLayout()
        
        # top section with title and network selector
        top_section = QHBoxLayout()
        
        # title (left side)
        title = QLabel("Track Model - Network Status")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        top_section.addWidget(title, 1)  # takes up available space
        
        # network selector (right side)
        network_selector_layout = QVBoxLayout()
        
        network_selector_label = QLabel("Active Network:")
        network_selector_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        network_selector_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        network_selector_layout.addWidget(network_selector_label)
        
        self.network_selector = QComboBox()
        self.network_selector.setMinimumWidth(150)
        self.network_selector.addItem("Loading...")  # placeholder, aiped
        self.network_selector.currentTextChanged.connect(self.on_network_changed)
        network_selector_layout.addWidget(self.network_selector)
        
        top_section.addLayout(network_selector_layout, 0)  # fixed size on right
        
        layout.addLayout(top_section)
        
        # create tab widget for different data categories
        self.tab_widget = QTabWidget()
        
        # create tables for each category
        self.segment_table = QTableWidget()
        self.segment_table.setFont(QFont("Arial", 9))
        
        # create track info widget with controls
        self.track_info_widget = self.create_track_info_widget()
        
        self.failure_table = QTableWidget()
        self.failure_table.setFont(QFont("Arial", 10))
        
        self.station_table = QTableWidget()
        self.station_table.setFont(QFont("Arial", 10))
        
        self.train_table = QTableWidget()
        self.train_table.setFont(QFont("Arial", 10))
        
        # add tables to tabs
        self.tab_widget.addTab(self.segment_table, "Segment Info")
        self.tab_widget.addTab(self.train_table, "Train Info")
        self.tab_widget.addTab(self.station_table, "Station Info")
        self.tab_widget.addTab(self.track_info_widget, "Network Info")
        self.tab_widget.addTab(self.failure_table, "Failure Log")
        
        layout.addWidget(self.tab_widget)
        
        # status display section (compact layout)
        status_layout = QVBoxLayout()
        
        # status display (read-only output)
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setFont(QFont("Courier", 9))
        status_layout.addWidget(self.status_display)
        
        # create a widget for the status section
        status_widget = QWidget()
        status_widget.setLayout(status_layout)
        
        # add status section with stretch factor (20% of window)
        layout.addWidget(status_widget, 1)  # 1 part for status
        
        # the tab widget should get the majority of space (80%)
        layout.setStretchFactor(self.tab_widget, 4)  # 4 parts for tables
        layout.setStretchFactor(status_widget, 1)   # 1 part for status
        
        # bottom layout with refresh button and time display
        bottom_layout = QHBoxLayout()
        
        # refresh button
        refresh_btn = QPushButton("Manually Refresh Status")
        refresh_btn.clicked.connect(self.refresh_status)
        bottom_layout.addWidget(refresh_btn, 1)  # stretch factor 1
        
        # time display
        self.time_label = QLabel("Time: --/--/-- --:--:--")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        bottom_layout.addWidget(self.time_label, 0)  # stretch factor 0
        
        layout.addLayout(bottom_layout)
        
        self.setLayout(layout)

    def create_track_info_widget(self):
        """Create the Track Info tab with table and failure controls"""
        widget = QWidget()
        layout = QHBoxLayout()
        
        # left side - Temperature table (fixed width)
        self.track_info_table = QTableWidget()
        self.track_info_table.setFont(QFont("Arial", 10))
        self.track_info_table.setMaximumWidth(250)  # fixed width
        layout.addWidget(self.track_info_table, 0)  # fixed size
        
        # middle - current failures table (stretchable)
        failures_widget = QWidget()
        failures_layout = QVBoxLayout()
        failures_widget.setLayout(failures_layout)
        # removed maximum width constraint to allow stretching
        
        # title for current failures
        current_failures_title = QLabel("Current Failures")
        current_failures_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        failures_layout.addWidget(current_failures_title)
        
        # current failures table
        self.current_failures_table = QTableWidget()
        self.current_failures_table.setFont(QFont("Arial", 9))
        failures_layout.addWidget(self.current_failures_table)
        
        layout.addWidget(failures_widget, 3)  # 3/5 of the space (stretchable)
        
        # right side - failure injection controls
        controls_layout = QVBoxLayout()
        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setMaximumWidth(200)
        
        # title for controls
        controls_title = QLabel("Failure Injection")
        controls_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_layout.addWidget(controls_title)
        
        # segment selection dropdown
        segment_label = QLabel("Select Segment:")
        controls_layout.addWidget(segment_label)
        
        self.segment_dropdown = QComboBox()
        self.segment_dropdown.setMinimumWidth(150)
        controls_layout.addWidget(self.segment_dropdown)
        
        # failure type checkboxes
        failures_label = QLabel("Failure Types:")
        failures_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        controls_layout.addWidget(failures_label)
        
        self.broken_rail_checkbox = QCheckBox("Broken Rail")
        controls_layout.addWidget(self.broken_rail_checkbox)
        
        self.circuit_failure_checkbox = QCheckBox("Track Circuit Failure")
        controls_layout.addWidget(self.circuit_failure_checkbox)
        
        self.power_failure_checkbox = QCheckBox("Power Failure")
        controls_layout.addWidget(self.power_failure_checkbox)
        
        # apply button
        apply_failures_btn = QPushButton("Apply Changes")
        apply_failures_btn.clicked.connect(self.apply_track_failures)
        controls_layout.addWidget(apply_failures_btn)
        
        # add spacing to push controls to top
        controls_layout.addStretch()
        
        layout.addWidget(controls_widget, 0)  # 0 stretch - fixed size
        
        widget.setLayout(layout)
        return widget
    
    def load_track_layout_for_network(self, network, csv_filename):
        """Load the track layout from CSV file for a specific network"""
        try:
            # load track layout with proper path
            csv_path = os.path.join(os.path.dirname(__file__), csv_filename)
            self.status_display.append(
                f"Loading track layout for network from {csv_path}..."
            )
            network.load_track_layout(csv_path)
            self.status_display.append(f"Track layout loaded successfully for network: {network.line_name}\n")
            
        except Exception as e:
            self.status_display.append(f"Error loading track layout for network: {str(e)}")
    
    def switch_active_network(self, network_index):
        """Switch the active network between track_network1 and track_network2"""
        try:
            # switch to the specified network
            if network_index == 1:
                self.track_network = self.track_network1
                self.active_network_index = 1
                self.status_display.append(f"Switched to Network 1: {self.track_network1.line_name}")
            elif network_index == 2:
                self.track_network = self.track_network2
                self.active_network_index = 2
                self.status_display.append(f"Switched to Network 2: {self.track_network2.line_name}")
            else:
                raise ValueError(f"Invalid network index: {network_index}. Must be 1 or 2.")
            
            # refresh the display with the new network
            self.refresh_status()
            
        except Exception as e:
            self.status_display.append(f"Error switching active network: {str(e)}")
    
    def get_active_network_name(self):
        """Get the name of the currently active network"""
        return self.track_network.line_name if hasattr(self.track_network, 'line_name') else f"Network {self.active_network_index}"
    
    def populate_network_selector(self):
        """Populate the network selector dropdown with available networks"""
        try:
            # temporarily disconnect the signal to avoid triggering during population
            self.network_selector.currentTextChanged.disconnect()
            
            self.network_selector.clear()
            
            # get network names
            network1_name = self.track_network1.line_name if hasattr(self.track_network1, 'line_name') else "Network 1"
            network2_name = self.track_network2.line_name if hasattr(self.track_network2, 'line_name') else "Network 2"
            
            self.status_display.append(f"Populating network selector with: '{network1_name}' and '{network2_name}'")
            
            # add networks to dropdown
            self.network_selector.addItem(network1_name)
            self.network_selector.addItem(network2_name)
            
            # set current selection based on active network
            if self.active_network_index == 1:
                self.network_selector.setCurrentIndex(0)
            else:
                self.network_selector.setCurrentIndex(1)
            
            # reconnect the signal
            self.network_selector.currentTextChanged.connect(self.on_network_changed)
            
            self.status_display.append(f"Network selector populated successfully. Active network: {self.active_network_index}")
                
        except Exception as e:
            self.status_display.append(f"Error populating network selector: {str(e)}")
            # reconnect the signal even if there's an error
            try:
                self.network_selector.currentTextChanged.connect(self.on_network_changed)
            except:
                pass
    
    def on_network_changed(self, network_name):
        """Handle network selection change from dropdown"""
        try:
            self.status_display.append(f"Network dropdown changed to: '{network_name}'")
            
            # prevent processing during initialization or clearing
            if network_name == "Loading..." or not network_name:
                self.status_display.append("Ignoring network change (loading or empty)")
                return
            
            # determine which network was selected
            network1_name = self.track_network1.line_name if hasattr(self.track_network1, 'line_name') else "Network 1"
            network2_name = self.track_network2.line_name if hasattr(self.track_network2, 'line_name') else "Network 2"
            
            self.status_display.append(f"Network 1 name: '{network1_name}', Network 2 name: '{network2_name}'")
            self.status_display.append(f"Current active network index: {self.active_network_index}")
            
            if network_name == network1_name and self.active_network_index != 1:
                self.status_display.append("Switching to Network 1...")
                self.switch_active_network(1)
            elif network_name == network2_name and self.active_network_index != 2:
                self.status_display.append("Switching to Network 2...")
                self.switch_active_network(2)
            else:
                self.status_display.append(f"No network switch needed (already on correct network or no match)")
                
        except Exception as e:
            self.status_display.append(f"Error changing network: {str(e)}")
        
    def load_track_layout(self):
        """Load the track layout from CSV file (called once on startup)"""
        try:
            # load track layout with proper path
            csv_path = os.path.join(os.path.dirname(__file__), "green_line.csv")
            self.status_display.append(
                f"Loading track layout from {csv_path}...")
            self.track_network.load_track_layout(csv_path)
            self.status_display.append("Track layout loaded successfully!\n")
            
            # display initial network status
            self.refresh_status()
            
        except Exception as e:
            self.status_display.append(f"Error loading track layout: {str(e)}")
    
    def refresh_status(self):
        """Manually efresh the network status display"""
        try:
            # get and display network status
            self.status_display.append("Refreshing network status...")
            network_status = self.track_network.get_network_status()
            
            # display in table format
            self.populate_status_table(network_status)
            
            self.status_display.append("Network status refreshed.")
            
        except Exception as e:
            self.status_display.append(f"Error refreshing status: {str(e)}")

    def auto_refresh_status(self, current_time=None):
        """Automatic refreshing the network status display"""
        try:
            # get and display network status
            network_status = self.track_network.get_network_status()
            
            # display in table format
            self.populate_status_table(network_status)
            
        except Exception as e:
            self.status_display.append(f"Error refreshing status: {str(e)}")

    def populate_status_table(self, network_status):
        """Populate the status tables with network data"""
        if not network_status:
            self.status_display.append("No network status data available.")
            return
        
        # assuming network_status is a dictionary
        if isinstance(network_status, dict):
            # update time display if available
            if 'time' in network_status:
                time_obj = network_status['time']
                # format as MM/DD/YY HH:MM:SS
                formatted_time = time_obj.strftime("%m/%d/%y %H:%M:%S")
                self.time_label.setText(f"Time: {formatted_time}")
            else:
                # fallback if time not available in network status
                self.time_label.setText("Time: --/--/-- --:--")
            
            # populate segments table
            if 'segments' in network_status:
                self.populate_segments_table(network_status['segments'])
                # also populate the segment dropdown for failure injection
                self.populate_segment_dropdown(network_status['segments'])
            
            # populate track info table
            track_info = {}
            if 'environmental_temperature' in network_status:
                # convert temperature from Celsius to Fahrenheit
                temp_celsius = network_status['environmental_temperature']
                temp_fahrenheit = ConversionFunctions.celsius_to_fahrenheit(
                    temp_celsius)
                track_info['Environmental Temperature (°F)'] = f"{temp_fahrenheit:.1f}"
            if 'heater_threshold' in network_status:
                # convert threshold temperature from Celsius to Fahrenheit
                threshold_celsius = network_status['heater_threshold']
                threshold_fahrenheit = ConversionFunctions.celsius_to_fahrenheit(
                    threshold_celsius)
                track_info['Heater Threshold (°F)'] = (
                    f"{threshold_fahrenheit:.1f}")
            if 'heaters_active' in network_status:
                track_info['Heaters Active'] = network_status['heaters_active']
            if 'rail_temperature' in network_status:
                # convert rail temperature from Celsius to Fahrenheit
                rail_temp_celsius = network_status['rail_temperature']
                rail_temp_fahrenheit = ConversionFunctions.celsius_to_fahrenheit(
                    rail_temp_celsius)
                track_info['Rail Temperature (°F)'] = f"{rail_temp_fahrenheit:.1f}"
            self.populate_track_info_table(track_info)
            
            # populate current failures table
            if 'segments' in network_status:
                self.populate_current_failures_table(network_status['segments'])
            
            # populate failure log table
            if 'failure_log' in network_status:
                self.populate_failure_table(network_status['failure_log'])
            
            # populate station info table
            if 'segments' in network_status:
                self.populate_station_table(network_status['segments'])
            
            # populate train info table
            if 'trains' in network_status:
                self.populate_train_table(network_status['trains'])
        else:
            # if it's not a dict, display as string in first tab
            self.segment_table.setRowCount(1)
            self.segment_table.setColumnCount(1)
            self.segment_table.setHorizontalHeaderLabels(["Network Status"])
            self.segment_table.setItem(
                0, 0, QTableWidgetItem(str(network_status)))
    
    def populate_dict_as_table(self, table_widget, data_dict, 
                               id_column_name="ID", 
                               details_column_name="Details"):
        """Helper function to populate a table with dictionary data.
        
        Handles nested structures for display. Only updates cells that have changed.
        """
        if not data_dict:
            # if no data, clear the table
            table_widget.setRowCount(0)
            table_widget.setColumnCount(0)
            return
        
        # attributes to exclude from Segment Info
        excluded_segment_attributes = {
            'diverging_segment', 'failures', 
            'passengers_boarded_total', 'closed', 'passengers_exited_total', 
            'passengers_waiting', 'station_side', 'straight_segment', 
            'tickets_sold_total', 'station_name', 'underground'
        }
        
        # custom column order for Segment Info
        segment_column_order = [
            'block_id', 'type', 'occupied', 'prev_sig', 'str_sig', 'div_sig', 'speed_limit', 'length', 'grade', 
            'elevation', 'direction', 'cmd_speed', 'cmd_auth', 'prev_seg', 'next_seg', 
            'current_pos', 'gate_status', 'beacon_data',
        ]
        
        # column aliases for display
        column_aliases = {
            'previous_signal_state': 'prev_sig',
            'straight_signal_state': 'str_sig',
            'diverging_signal_state': 'div_sig',
            'previous_segment': 'prev_seg',
            'next_segment': 'next_seg',
            'current_position': 'current_pos',
            'commanded_speed': 'cmd_speed',
            'commanded_authority': 'cmd_auth',
        }
        
        # check if this is being called for segments (based on table widget 
        # or column name)
        is_segment_table = ((table_widget == self.segment_table) or 
                           ("Segment" in id_column_name))
        
        # count total rows needed - one row per key in data_dict
        total_rows = len(data_dict)
        
        if total_rows == 0:
            return
        
        # pre-process data to split active_command into separate fields
        processed_data = {}
        for key, value in data_dict.items():
            if isinstance(value, dict):
                new_value = value.copy()
                # split active_command into commanded_speed and commanded_authority
                if 'active_command' in new_value and new_value['active_command'] is not None:
                    cmd = new_value['active_command']
                    if hasattr(cmd, 'commanded_speed'):
                        new_value['commanded_speed'] = cmd.commanded_speed
                    else:
                        new_value['commanded_speed'] = None
                    if hasattr(cmd, 'authority'):
                        new_value['commanded_authority'] = cmd.authority
                    else:
                        new_value['commanded_authority'] = None
                    # remove the original active_command
                    del new_value['active_command']
                else:
                    new_value['commanded_speed'] = None
                    new_value['commanded_authority'] = None
                    if 'active_command' in new_value:
                        del new_value['active_command']
                processed_data[key] = new_value
            else:
                processed_data[key] = value
        
        # use processed data instead of original
        data_dict = processed_data
            
        # determine columns based on data structure
        all_keys = set()
        for key, value in data_dict.items():
            if isinstance(value, dict):
                for sub_key in value.keys():
                    # filter out excluded attributes for segment tables
                    if not (is_segment_table and 
                           sub_key in excluded_segment_attributes):
                        all_keys.add(sub_key)
        
        if all_keys:
            # create columns for nested structure
            if is_segment_table:
                ordered_columns = []
                # first add the columns in the specified order
                for col in segment_column_order:
                    # check both original name and alias
                    original_col = next((k for k, v in column_aliases.items() if v == col), col)
                    if col in all_keys or original_col in all_keys:
                        ordered_columns.append(col)
                        all_keys.discard(col)
                        all_keys.discard(original_col)
                # add any remaining columns at the end
                ordered_columns.extend(sorted(list(all_keys)))
                columns = ordered_columns
            else:
                # default behavior for other tables
                columns = [id_column_name] + sorted(list(all_keys))
            
            # Check if we need to resize the table or if columns match
            current_col_count = table_widget.columnCount()
            current_row_count = table_widget.rowCount()
            needs_restructure = (current_col_count != len(columns) or 
                               current_row_count != total_rows)
            
            if needs_restructure:
                # Only restructure if necessary
                table_widget.setColumnCount(len(columns))
                table_widget.setHorizontalHeaderLabels(columns)
                table_widget.setRowCount(total_rows)
            
            # populate rows (yes this is disgusting, deal)
            row = 0
            for key, value in data_dict.items():
                if isinstance(value, dict):
                    if is_segment_table:
                        # for segments, don't add ID column
                        for col_idx, col_name in enumerate(columns):
                            # check if this is an alias, if so use the original name for data lookup
                            original_col_name = next((k for k, v in column_aliases.items() if v == col_name), col_name)
                            
                            if original_col_name in value:
                                # apply unit conversions and formatting 
                                # for segment display
                                cell_value = value[original_col_name]
                                item = None
                                
                                if (original_col_name == 'length' and 
                                        isinstance(cell_value, (int, float))):
                                    # convert length from meters to yards
                                    yards_value = (
                                        ConversionFunctions.meters_to_yards(
                                            cell_value))
                                    display_value = f"{yards_value:.2f} yds"
                                    item = QTableWidgetItem(display_value)
                                elif (original_col_name == 'speed_limit' and 
                                      isinstance(cell_value, (int, float))):
                                    # convert speed from m/s to mph
                                    mph_value = ConversionFunctions.mps_to_mph(
                                        cell_value)
                                    display_value = f"{mph_value:.1f} mph"
                                    item = QTableWidgetItem(display_value)
                                elif (original_col_name == 'grade' and 
                                      isinstance(cell_value, (int, float))):
                                    # convert grade from decimal to percentage
                                    display_value = f"{cell_value:.2f} %"
                                    item = QTableWidgetItem(display_value)
                                elif (original_col_name == 'elevation' and 
                                      isinstance(cell_value, (int, float))):
                                    # convert elevation from meters to yards
                                    yards_value = (
                                        ConversionFunctions.meters_to_yards(
                                            cell_value))
                                    display_value = f"{yards_value:.2f} yds"
                                    item = QTableWidgetItem(display_value)
                                elif original_col_name == 'direction':
                                    # convert direction to user-friendly display with arrows
                                    direction_str = str(cell_value).upper()
                                    
                                    if direction_str in ['DIRECTION.BIDIRECTIONAL']:
                                        display_value = "↔️ Bidirectional"
                                        color = QColor(230, 230, 255)  # light purple
                                    elif direction_str in ['DIRECTION.FORWARD']:
                                        display_value = "➡️ Forward"
                                        color = QColor(200, 255, 200)  # light green
                                    elif direction_str in ['DIRECTION.BACKWARD']:
                                        display_value = "⬅️ Backward"
                                        color = QColor(255, 220, 200)  # light red
                                    else:
                                        display_value = str(cell_value)
                                    
                                    item = QTableWidgetItem(display_value)
                                    item.setBackground(color)
                                elif original_col_name in ['previous_signal_state', 'straight_signal_state', 'diverging_signal_state']:

                                    if hasattr(cell_value, 'name'):
                                        signal_name = cell_value.name
                                    else:
                                        signal_name = str(cell_value)

                                    if (signal_name == 'RED' or 
                                            str(cell_value) == 'SignalState.RED'):
                                        display_value = "🔴 Red"
                                        color = QColor(255, 200, 200)
                                    elif (signal_name == 'YELLOW' or 
                                          str(cell_value) == 'SignalState.YELLOW'):
                                        display_value = "🟡 Yellow"
                                        color = QColor(255, 255, 200)
                                    elif (signal_name == 'GREEN' or 
                                          str(cell_value) == 'SignalState.GREEN'):
                                        display_value = "🟢 Green"
                                        color = QColor(200, 255, 200)
                                    elif (signal_name == 'SUPERGREEN' or 
                                          str(cell_value) == 
                                          'SignalState.SUPERGREEN'):
                                        display_value = "🟢 Super Green"
                                        color = QColor(150, 255, 150)
                                    else:
                                        display_value = str(cell_value)
                                        color = QColor(240, 240, 240)
                                    
                                    item = QTableWidgetItem(display_value)
                                    item.setBackground(color)
                                elif original_col_name == 'commanded_speed':
                                    # convert speed from m/s to mph
                                    if cell_value is not None and isinstance(cell_value, (int, float)):
                                        mph_value = ConversionFunctions.mps_to_mph(cell_value)
                                        display_value = f"{mph_value:.1f} mph"
                                    else:
                                        display_value = "None"
                                    item = QTableWidgetItem(display_value)
                                elif original_col_name == 'commanded_authority':
                                    # convert authority from meters to yards
                                    if cell_value is not None and isinstance(cell_value, (int, float)):
                                        yards_value = ConversionFunctions.meters_to_yards(cell_value)
                                        display_value = f"{yards_value:.2f} yds"
                                    else:
                                        display_value = "None"
                                    item = QTableWidgetItem(display_value)
                                elif original_col_name == 'occupied':
                                    if isinstance(cell_value, bool):
                                        if cell_value:
                                            display_value = "🟢 Occupied"
                                            color = QColor(200, 255, 200)
                                        else:
                                            display_value = "🔴 Unoccupied"
                                            color = QColor(255, 200, 200)
                                    else:
                                        # handle string representations
                                        str_value = str(cell_value).lower()
                                        if str_value in ['true', '1', 'occupied']:
                                            display_value = "🟢 Occupied"
                                            color = QColor(200, 255, 200)
                                        else:
                                            display_value = "🔴 Unoccupied"
                                            color = QColor(255, 200, 200)
                                    
                                    item = QTableWidgetItem(display_value)
                                    item.setBackground(color)
                                elif original_col_name == 'closed':
                                    # convert closed status to display with colors
                                    if isinstance(cell_value, bool):
                                        if cell_value:
                                            display_value = "🔴 Closed"
                                            color = QColor(255, 200, 200)
                                        else:
                                            display_value = "🟢 Open"
                                            color = QColor(230, 255, 230)
                                    else:
                                        # handle string representations
                                        str_value = str(cell_value).lower()
                                        if str_value in ['true', '1', 'closed']:
                                            display_value = "🔴 Closed"
                                            color = QColor(255, 200, 200)
                                        else:
                                            display_value = "🟢 Open"
                                            color = QColor(230, 255, 230)
                                    
                                    item = QTableWidgetItem(display_value)
                                    item.setBackground(color)
                                else:
                                    display_value = str(cell_value)
                                    item = QTableWidgetItem(display_value)
                                
                                # Only update if the value has changed
                                existing_item = table_widget.item(row, col_idx)
                                if existing_item is None or existing_item.text() != display_value:
                                    table_widget.setItem(row, col_idx, item)
                            else:
                                # Only clear if the cell has content
                                existing_item = table_widget.item(row, col_idx)
                                if existing_item is not None and existing_item.text() != "":
                                    table_widget.setItem(
                                        row, col_idx, QTableWidgetItem("")
                                    )
                    else:
                        # for other tables, add ID column
                        existing_id = table_widget.item(row, 0)
                        if existing_id is None or existing_id.text() != str(key):
                            table_widget.setItem(row, 0, QTableWidgetItem(str(key)))
                        
                        for col_idx, col_name in enumerate(columns[1:], 1):
                            if col_name in value:
                                new_value = str(value[col_name])
                                existing_item = table_widget.item(row, col_idx)
                                if existing_item is None or existing_item.text() != new_value:
                                    table_widget.setItem(
                                        row, col_idx, 
                                        QTableWidgetItem(new_value)
                                    )
                            else:
                                existing_item = table_widget.item(row, col_idx)
                                if existing_item is not None and existing_item.text() != "":
                                    table_widget.setItem(
                                        row, col_idx, QTableWidgetItem("")
                                    )
                    row += 1
                else:
                    table_widget.setItem(row, 0, QTableWidgetItem(str(key)))
                    table_widget.setItem(row, 1, QTableWidgetItem(str(value)))
                    row += 1
        else:
            table_widget.setColumnCount(2)
            table_widget.setHorizontalHeaderLabels(
                [id_column_name, details_column_name]
            )
            table_widget.setRowCount(len(data_dict))
            
            row = 0
            for key, value in data_dict.items():
                table_widget.setItem(row, 0, QTableWidgetItem(str(key)))
                table_widget.setItem(row, 1, QTableWidgetItem(str(value)))
                row += 1
        
        table_widget.resizeColumnsToContents()
    
    def populate_segments_table(self, segments_data):
        """Populate the segments table"""
        if not segments_data:
            return
            
        if isinstance(segments_data, dict):
            self.populate_dict_as_table(
                self.segment_table, segments_data, "Segment ID", "Properties"
            )
            # hide row numbers for segment table
            self.segment_table.verticalHeader().setVisible(False)
        else:
            # if it's a list or other format
            self.segment_table.setRowCount(1)
            self.segment_table.setColumnCount(1)
            self.segment_table.setHorizontalHeaderLabels(["Segments"])
            self.segment_table.setItem(
                0, 0, QTableWidgetItem(str(segments_data))
            )
            # hide row numbers for segment table
            self.segment_table.verticalHeader().setVisible(False)
    
    def populate_track_info_table(self, track_info):
        """Populate the track info table"""
        if not track_info:
            return
        
        # disconnect any existing signals to avoid multiple connections
        try:
            self.track_info_table.cellChanged.disconnect()
        except:
            pass  # no existing connections
        
        # check if user is currently editing a cell
        current_item = self.track_info_table.currentItem()
        editing_row = None
        editing_col = None
        if current_item and self.track_info_table.state() == QTableWidget.State.EditingState:
            editing_row = self.track_info_table.currentRow()
            editing_col = self.track_info_table.currentColumn()
            
        self.track_info_table.setRowCount(len(track_info))
        self.track_info_table.setColumnCount(2)
        self.track_info_table.setHorizontalHeaderLabels(["Property", "Value"])
        
        row = 0
        for key, value in track_info.items():
            # create property cell (read-only)
            property_item = QTableWidgetItem(str(key))
            property_item.setFlags(
                property_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            self.track_info_table.setItem(row, 0, property_item)
            
            # only skip updating editable cells if user is currently editing them
            is_editable_field = ("Environmental Temperature" in key or "Heater Threshold" in key) and "Rail Temperature" not in key
            if row == editing_row and 1 == editing_col and is_editable_field:
                row += 1
                continue
            
            # create value cell
            value_item = QTableWidgetItem(str(value))
            

            if ("Environmental Temperature" in key or "Heater Threshold" in key) and "Rail Temperature" not in key:
                # store original celsius value as item data for temperature conversions
                if "Temperature" in key:
                    # extract fahrenheit value and convert back to celsius for storage
                    fahrenheit_value = float(str(value).replace('°F', '').strip())
                    celsius_value = ConversionFunctions.fahrenheit_to_celsius(fahrenheit_value)
                    value_item.setData(Qt.ItemDataRole.UserRole, celsius_value)
                elif "Threshold" in key:
                    fahrenheit_value = float(str(value).replace('°F', '').strip())
                    celsius_value = ConversionFunctions.fahrenheit_to_celsius(fahrenheit_value)
                    value_item.setData(Qt.ItemDataRole.UserRole, celsius_value)
                
                # make editable and highlight
                value_item.setFlags(value_item.flags() | Qt.ItemFlag.ItemIsEditable)
                value_item.setBackground(QColor(240, 248, 255))  # Light blue background for editable cells
            else:
                # make read-only for all other values
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.track_info_table.setItem(row, 1, value_item)
            row += 1
        
        # connect cell change signal to update backend
        self.track_info_table.cellChanged.connect(self.on_temperature_changed)
            
        self.track_info_table.resizeColumnsToContents()
    
    def on_temperature_changed(self, row, column):
        """Handle temperature value changes in the track info table"""
        if column != 1:  # only handle value column changes
            return
        
        # prevent recursive updates
        if self.updating_temperature:
            return
            
        try:
            self.updating_temperature = True  # set flag to prevent recursion
            
            # get changed item
            item = self.track_info_table.item(row, column)
            property_item = self.track_info_table.item(row, 0)
            
            if not item or not property_item:
                return
                
            property_name = property_item.text()
            new_fahrenheit_str = item.text().replace('°F', '').strip()
            
            # validate input
            try:
                new_fahrenheit = float(new_fahrenheit_str)
            except ValueError:
                self.status_display.append(f"Error: Invalid temperature value '{new_fahrenheit_str}'. Please enter a number.")
                return
            
            # convert fahrenheit input to celsius for backend
            new_celsius = ConversionFunctions.fahrenheit_to_celsius(new_fahrenheit)
            
            # update backend based on property type
            if "Environmental Temperature" in property_name:
                self.track_network.set_environmental_temperature(new_celsius)
                self.status_display.append(f"Environmental temperature updated to {new_fahrenheit:.1f}°F ({new_celsius:.1f}°C)")

            elif "Heater Threshold" in property_name:
                self.track_network.set_heater_threshold(new_celsius)
                self.status_display.append(f"Heater threshold updated to {new_fahrenheit:.1f}°F ({new_celsius:.1f}°C)")
            
            elif "Rail Temperature" in property_name:
                # rail temp is read-only catch
                self.status_display.append("Error: Rail temperature is read-only and cannot be modified.")
                return
            
            # update the display format to include fahrenheight
            item.setText(f"{new_fahrenheit:.1f}")
            
            # store the celsius value for future reference
            item.setData(Qt.ItemDataRole.UserRole, new_celsius)
            
        except Exception as e:
            self.status_display.append(f"Error updating temperature: {str(e)}")
        finally:
            self.updating_temperature = False  # always reset flag
    
    def populate_segment_dropdown(self, segments_data):
        """Populate the segment dropdown with available segments"""
        self.segment_dropdown.clear()
        
        if isinstance(segments_data, dict):
            # add segments to dropdown
            segment_ids = []
            for seg_id in segments_data.keys():
                try:
                    segment_ids.append(int(seg_id))
                except (ValueError, TypeError):
                    continue
            
            segment_ids.sort()
            for seg_id in segment_ids:
                self.segment_dropdown.addItem(str(seg_id))
    
    def apply_track_failures(self):
        """Apply or clear track failures based on checkbox states"""
        try:
            selected_segment = self.segment_dropdown.currentText()
            if not selected_segment:
                self.status_display.append("Error: No segment selected")
                return
                
            segment_id = int(selected_segment)
            
            # handle each failure type
            failures_applied = []
            failures_cleared = []
            
            # broken Rail
            if self.broken_rail_checkbox.isChecked():
                self.track_network.set_track_failure(segment_id, TrackFailureType.BROKEN_RAIL)
                failures_applied.append("Broken Rail")
            else:
                self.track_network.clear_track_failure(segment_id, TrackFailureType.BROKEN_RAIL)
                failures_cleared.append("Broken Rail")
            
            # track circuit failure
            if self.circuit_failure_checkbox.isChecked():
                self.track_network.set_track_failure(segment_id, TrackFailureType.TRACK_CIRCUIT_FAILURE)
                failures_applied.append("Track Circuit Failure")
            else:
                self.track_network.clear_track_failure(segment_id, TrackFailureType.TRACK_CIRCUIT_FAILURE)
                failures_cleared.append("Track Circuit Failure")
            
            # power failure
            if self.power_failure_checkbox.isChecked():
                self.track_network.set_track_failure(segment_id, TrackFailureType.POWER_FAILURE)
                failures_applied.append("Power Failure")
            else:
                self.track_network.clear_track_failure(segment_id, TrackFailureType.POWER_FAILURE)
                failures_cleared.append("Power Failure")
            
            # report results
            if failures_applied:
                self.status_display.append(f"Applied failures to segment {segment_id}: {', '.join(failures_applied)}")
            if failures_cleared:
                self.status_display.append(f"Cleared failures from segment {segment_id}: {', '.join(failures_cleared)}")
            
            # auto-refresh after applying failures
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error applying track failures: {str(e)}")
    
    def populate_segment_dropdown(self, segments_data):
        """Populate the segment dropdown with available segments"""
        self.segment_dropdown.clear()
        
        if isinstance(segments_data, dict):
            # add segments to dropdown
            segment_ids = []
            for seg_id in segments_data.keys():
                try:
                    segment_ids.append(int(seg_id))
                except (ValueError, TypeError):
                    continue
            
            segment_ids.sort()
            for seg_id in segment_ids:
                self.segment_dropdown.addItem(str(seg_id))
    
    def populate_current_failures_table(self, segments_data):
        """Populate the current failures table with segments that have active failures"""
        if not segments_data:
            return
        
        # collect segments with failures
        failure_segments = []
        
        if isinstance(segments_data, dict):
            for segment_id, segment_info in segments_data.items():
                if isinstance(segment_info, dict) and 'failures' in segment_info:
                    failures = segment_info.get('failures', [])
                    if failures:
                        try:
                            block_id = segment_info.get('block_id', segment_id)
                            # convert failures list to readable format
                            failure_names = []
                            for failure in failures:
                                if hasattr(failure, 'name'):
                                    failure_names.append(failure.name)
                                else:
                                    failure_names.append(str(failure))
                            
                            failure_segments.append({
                                'block_id': str(block_id),
                                'failures': ', '.join(failure_names) if failure_names else 'None'
                            })
                        except Exception:
                            continue
        
        # set up the table
        if failure_segments:
            self.current_failures_table.setRowCount(len(failure_segments))
            self.current_failures_table.setColumnCount(2)
            self.current_failures_table.setHorizontalHeaderLabels(["Block ID", "Current Failures"])
            
            # populate rows
            for row, segment in enumerate(failure_segments):
                self.current_failures_table.setItem(row, 0, QTableWidgetItem(segment['block_id']))
                self.current_failures_table.setItem(row, 1, QTableWidgetItem(segment['failures']))
            
            # hide row numbers
            self.current_failures_table.verticalHeader().setVisible(False)
        else:
            # no failures found
            self.current_failures_table.setRowCount(1)
            self.current_failures_table.setColumnCount(2)
            self.current_failures_table.setHorizontalHeaderLabels(["Block ID", "Current Failures"])
            self.current_failures_table.setItem(0, 0, QTableWidgetItem("No failures"))
            self.current_failures_table.setItem(0, 1, QTableWidgetItem("System operational"))
            self.current_failures_table.verticalHeader().setVisible(False)
        
        self.current_failures_table.resizeColumnsToContents()
    
    def terminal_print(self, *args, **kwargs):
        """Custom print function for terminal output"""
        message = ' '.join(str(arg) for arg in args)
        self.status_display.append(message)
    
    def populate_failure_table(self, failure_data):
        """Populate the failure log table"""
        if not failure_data:
            return
            
        if isinstance(failure_data, dict):
            self.populate_dict_as_table(self.failure_table, failure_data, "Failure ID", "Properties")
        elif isinstance(failure_data, list):
            # convert list to dict format for table display
            if failure_data and isinstance(failure_data[0], dict):
                # if list contains dictionaries convert to indexed dict
                dict_data = {f"Failure_{i}": failure for i, failure in enumerate(failure_data)}
                self.populate_dict_as_table(self.failure_table, dict_data, "Failure ID", "Properties")
            else:
                # simple list display
                self.failure_table.setRowCount(len(failure_data))
                self.failure_table.setColumnCount(1)
                self.failure_table.setHorizontalHeaderLabels(["Failures"])
                
                for row, failure in enumerate(failure_data):
                    self.failure_table.setItem(row, 0, QTableWidgetItem(str(failure)))
        else:
            self.failure_table.setRowCount(1)
            self.failure_table.setColumnCount(1)
            self.failure_table.setHorizontalHeaderLabels(["Failures"])
            self.failure_table.setItem(0, 0, QTableWidgetItem(str(failure_data)))
            
        self.failure_table.resizeColumnsToContents()

    def populate_station_table(self, segments_data):
        """Populate the station info table with station-specific data"""
        if not segments_data:
            return
        
        # filter to stations
        station_data = {}
        station_columns = ['block_id', 'station_name', 'station_side', 'tickets_sold_total', 
                          'passengers_waiting', 'passengers_boarded_total', 'passengers_exited_total']
        
        if isinstance(segments_data, dict):
            for segment_id, segment_info in segments_data.items():
                if isinstance(segment_info, dict) and 'station_name' in segment_info:
                    # only include segments that have station information
                    if segment_info.get('station_name'):  # check if station_name is not empty/None
                        station_data[segment_id] = {col: segment_info.get(col, '') for col in station_columns}
        
        if station_data:
            # set up table for stations with custom column order
            self.station_table.setRowCount(len(station_data))
            self.station_table.setColumnCount(len(station_columns))
            self.station_table.setHorizontalHeaderLabels(station_columns)
            
            # populate rows
            for row, (segment_id, station_info) in enumerate(station_data.items()):
                for col_idx, col_name in enumerate(station_columns):
                    value = station_info.get(col_name, '')
                    self.station_table.setItem(row, col_idx, QTableWidgetItem(str(value)))
            
            # hide row numbers for station table
            self.station_table.verticalHeader().setVisible(False)
        else:
            # no stations found
            self.station_table.setRowCount(1)
            self.station_table.setColumnCount(1)
            self.station_table.setHorizontalHeaderLabels(["Station Info"])
            self.station_table.setItem(0, 0, QTableWidgetItem("No stations found"))
            self.station_table.verticalHeader().setVisible(False)
            
        self.station_table.resizeColumnsToContents()

    def populate_train_table(self, trains_data):
        """Populate the train info table with train-specific data"""
        if not trains_data:
            # no trains found
            self.train_table.setRowCount(1)
            self.train_table.setColumnCount(1)
            self.train_table.setHorizontalHeaderLabels(["Train Info"])
            self.train_table.setItem(0, 0, QTableWidgetItem("No trains found"))
            self.train_table.verticalHeader().setVisible(False)
            self.train_table.resizeColumnsToContents()
            return
        
        # define train columns
        train_columns = ['train_id', 'current_segment', 'segment_displacement']
        
        if isinstance(trains_data, dict):
            # set up table for trains with custom column order
            self.train_table.setRowCount(len(trains_data))
            self.train_table.setColumnCount(len(train_columns))
            self.train_table.setHorizontalHeaderLabels(train_columns)
            
            # populate rows
            for row, (train_id, train_info) in enumerate(trains_data.items()):
                for col_idx, col_name in enumerate(train_columns):
                    if isinstance(train_info, dict) and col_name in train_info:
                        cell_value = train_info[col_name]
                        
                        # apply unit conversions for segment displacement
                        if col_name == 'segment_displacement' and isinstance(cell_value, (int, float)):
                            yards_value = ConversionFunctions.meters_to_yards(cell_value)
                            display_value = f"{yards_value:.2f} yds"
                            item = QTableWidgetItem(display_value)
                        else:
                            display_value = str(cell_value) if cell_value is not None else 'N/A'
                            item = QTableWidgetItem(display_value)
                        
                        self.train_table.setItem(row, col_idx, item)
                    else:
                        self.train_table.setItem(row, col_idx, QTableWidgetItem('N/A'))
            
            # hide row numbers for train table
            self.train_table.verticalHeader().setVisible(False)
        else:
            # fallback - unexpected data format
            self.train_table.setRowCount(1)
            self.train_table.setColumnCount(1)
            self.train_table.setHorizontalHeaderLabels(["Train Info"])
            self.train_table.setItem(0, 0, QTableWidgetItem(str(trains_data)))
            self.train_table.verticalHeader().setVisible(False)
            
        self.train_table.resizeColumnsToContents()

if __name__ == "__main__":
    app = QApplication([])
    window = NetworkStatusUI()
    window.show()
    app.exec()
