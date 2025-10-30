"""
Track Model Frontend -- Claude Sonnet 4 was used to help with creation of this.
My first time experimenting with an LLM for code generation.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universal.universal import (
    SignalState,
    TrainCommand,
    ConversionFunctions
)

from track_model_backend import (
    TrackNetwork, 
    TrackSegment, 
    TrackSwitch, 
    LevelCrossing,
    Station,
    TrackFailureType,
    StationSide
)
from typing import List, Dict, Optional
import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QTabWidget, QLineEdit, QHBoxLayout, 
    QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from sys import argv

#TODO: #92 remove broadcasting tab and integrate commands into segment tab
#TODO: #60 add support for multiple TrackNetwork (red line and green line)
class NetworkStatusUI(QWidget):
    def __init__(self):
        super().__init__()
        self.track_network = TrackNetwork()
        self.updating_temperature = False  # Flag to prevent recursive updates
        self.init_ui()
        self.load_track_layout()  # Load CSV on startup
        
    def init_ui(self):
        self.setWindowTitle("Track Model - Test Network Status")
        self.setGeometry(100, 100, 1400, 800)
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Network Status - Test UI")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Create tab widget for different data categories
        self.tab_widget = QTabWidget()
        
        # Create tables for each category
        self.segment_table = QTableWidget()
        self.segment_table.setFont(QFont("Arial", 9))
        
        # Create Segment Info widget with editing controls
        self.segment_info_widget = self.create_segment_info_widget()
        
        # Create Track Info widget with controls
        self.track_info_widget = self.create_track_info_widget()
        
        # Create Command Info widget with broadcast controls
        self.command_info_widget = self.create_command_info_widget()
        
        self.failure_table = QTableWidget()
        self.failure_table.setFont(QFont("Arial", 10))
        
        self.station_table = QTableWidget()
        self.station_table.setFont(QFont("Arial", 10))
        
        # Create Station Info widget with station controls (after 
        # station_table is created)
        self.station_info_widget = self.create_station_info_widget()
        
        # Add tables to tabs
        self.tab_widget.addTab(self.segment_info_widget, "Segment Info")
        self.tab_widget.addTab(self.station_info_widget, "Station Info")
        self.tab_widget.addTab(self.track_info_widget, "Network Info")
        self.tab_widget.addTab(self.failure_table, "Failure Log")
        self.tab_widget.addTab(self.command_info_widget, "Command Info") #TODO #92 remove


        
        layout.addWidget(self.tab_widget)
        
        # Terminal section (compact layout)
        terminal_layout = QVBoxLayout()
        
        # Status display (terminal output) - no label needed
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setFont(QFont("Courier", 9))
        # Remove fixed height - let it be flexible
        terminal_layout.addWidget(self.status_display)
        
        # Command input
        input_layout = QHBoxLayout()
        
        command_label = QLabel(">>> ")
        command_label.setFont(QFont("Courier", 9, QFont.Weight.Bold))
        input_layout.addWidget(command_label)
        
        self.command_input = QLineEdit()
        self.command_input.setFont(QFont("Courier", 9))
        self.command_input.setPlaceholderText(
            "Enter backend command (e.g., set_environmental_temperature(25.0))")
        self.command_input.returnPressed.connect(self.execute_command)
        input_layout.addWidget(self.command_input)
        
        execute_btn = QPushButton("Execute")
        execute_btn.clicked.connect(self.execute_command)
        input_layout.addWidget(execute_btn)
        
        terminal_layout.addLayout(input_layout)
        
        # Create a widget for the terminal section
        terminal_widget = QWidget()
        terminal_widget.setLayout(terminal_layout)
        
        # Add terminal section with stretch factor (20% of window)
        layout.addWidget(terminal_widget, 1)  # 1 part for terminal
        
        # The tab widget should get the majority of space (80%)
        layout.setStretchFactor(self.tab_widget, 4)  # 4 parts for tables
        layout.setStretchFactor(terminal_widget, 1)   # 1 part for terminal
        
        # Refresh button
        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.clicked.connect(self.refresh_status)
        layout.addWidget(refresh_btn)
        
        self.setLayout(layout)
        
    def create_track_info_widget(self):
        """Create the Track Info tab with table and failure controls"""
        widget = QWidget()
        layout = QHBoxLayout()
        
        # Left side - Temperature table (fixed width)
        self.track_info_table = QTableWidget()
        self.track_info_table.setFont(QFont("Arial", 10))
        self.track_info_table.setMaximumWidth(250)  # Fixed width like before
        layout.addWidget(self.track_info_table, 0)  # 0 stretch - fixed size
        
        # Middle - Current Failures table (stretchable)
        failures_widget = QWidget()
        failures_layout = QVBoxLayout()
        failures_widget.setLayout(failures_layout)
        # Removed maximum width constraint to allow stretching
        
        # Title for current failures
        current_failures_title = QLabel("Current Failures")
        current_failures_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        failures_layout.addWidget(current_failures_title)
        
        # Current failures table
        self.current_failures_table = QTableWidget()
        self.current_failures_table.setFont(QFont("Arial", 9))
        failures_layout.addWidget(self.current_failures_table)
        
        layout.addWidget(failures_widget, 3)  # 3/5 of the space (stretchable)
        
        # Right side - Failure injection controls
        controls_layout = QVBoxLayout()
        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setMaximumWidth(200)
        
        # Title for controls
        controls_title = QLabel("Failure Injection")
        controls_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_layout.addWidget(controls_title)
        
        # Segment selection dropdown
        segment_label = QLabel("Select Segment:")
        controls_layout.addWidget(segment_label)
        
        self.segment_dropdown = QComboBox()
        self.segment_dropdown.setMinimumWidth(150)
        controls_layout.addWidget(self.segment_dropdown)
        
        # Failure type checkboxes
        failures_label = QLabel("Failure Types:")
        failures_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        controls_layout.addWidget(failures_label)
        
        self.broken_rail_checkbox = QCheckBox("Broken Rail")
        controls_layout.addWidget(self.broken_rail_checkbox)
        
        self.circuit_failure_checkbox = QCheckBox("Track Circuit Failure")
        controls_layout.addWidget(self.circuit_failure_checkbox)
        
        self.power_failure_checkbox = QCheckBox("Power Failure")
        controls_layout.addWidget(self.power_failure_checkbox)
        
        # Apply button
        apply_failures_btn = QPushButton("Apply Changes")
        apply_failures_btn.clicked.connect(self.apply_track_failures)
        controls_layout.addWidget(apply_failures_btn)
        
        # Add spacing to push controls to top
        controls_layout.addStretch()
        
        layout.addWidget(controls_widget, 0)  # 0 stretch - fixed size
        
        widget.setLayout(layout)
        return widget
    
    def create_command_info_widget(self):  #TODO #92 remove
        """Create the Command Info tab with table and broadcast command 
        controls."""
        widget = QWidget()
        layout = QHBoxLayout()
        
        # Left side - Command table (stretchable)
        self.command_table = QTableWidget()
        self.command_table.setFont(QFont("Arial", 10))
        layout.addWidget(self.command_table, 1)  # Takes most of the space
        
        # Right side - Broadcast Train Command controls
        controls_layout = QVBoxLayout()
        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setMaximumWidth(250)
        
        # Title for controls
        controls_title = QLabel("Broadcast Train Command")
        controls_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_layout.addWidget(controls_title)
        
        # Train ID input
        train_id_label = QLabel("Train ID:")
        controls_layout.addWidget(train_id_label)
        
        self.train_id_input = QLineEdit()
        self.train_id_input.setPlaceholderText("Enter train ID (e.g., 1)")
        controls_layout.addWidget(self.train_id_input)
        
        # Commanded Speed input
        speed_label = QLabel("Commanded Speed (mph):")
        controls_layout.addWidget(speed_label)
        
        self.commanded_speed_input = QLineEdit()
        self.commanded_speed_input.setPlaceholderText("Enter speed (e.g., 25)")
        controls_layout.addWidget(self.commanded_speed_input)
        
        # Authority input
        authority_label = QLabel("Authority (yards):")
        controls_layout.addWidget(authority_label)
        
        self.authority_input = QLineEdit()
        self.authority_input.setPlaceholderText("Enter authority (e.g., 100)")
        controls_layout.addWidget(self.authority_input)
        
        # Apply button
        apply_command_btn = QPushButton("Broadcast Command")
        apply_command_btn.clicked.connect(self.broadcast_train_command)
        controls_layout.addWidget(apply_command_btn)
        
        # Add spacing to push controls to top
        controls_layout.addStretch()
        
        layout.addWidget(controls_widget, 0)  # Fixed size
        
        widget.setLayout(layout)
        return widget
    
    def create_segment_info_widget(self):
        """Create the Segment Info tab with table and segment editing 
        controls."""
        widget = QWidget()
        layout = QHBoxLayout()
        
        # Left side - Segment table (stretchable)
        layout.addWidget(self.segment_table, 1)  # Takes most of the space
        
        # Right side - Segment editing controls
        controls_layout = QVBoxLayout()
        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setMaximumWidth(250)
        
        # Title for controls
        controls_title = QLabel("Edit Segment Properties")
        controls_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_layout.addWidget(controls_title)
        
        # Segment selection dropdown
        segment_label = QLabel("Select Segment:")
        controls_layout.addWidget(segment_label)
        
        self.edit_segment_dropdown = QComboBox()
        self.edit_segment_dropdown.setMinimumWidth(150)
        self.edit_segment_dropdown.currentTextChanged.connect(
            self.on_edit_segment_selected)
        controls_layout.addWidget(self.edit_segment_dropdown)
        
        # Occupancy dropdown
        occupancy_label = QLabel("Occupancy:")
        controls_layout.addWidget(occupancy_label)
        
        self.occupancy_dropdown = QComboBox()
        self.occupancy_dropdown.addItems(
            ["True (Occupied)", "False (Unoccupied)"])
        controls_layout.addWidget(self.occupancy_dropdown)
        
        # Closed status dropdown
        closed_label = QLabel("Closed Status:")
        controls_layout.addWidget(closed_label)
        
        self.closed_dropdown = QComboBox()
        self.closed_dropdown.addItems(["False (Open)", "True (Closed)"])
        controls_layout.addWidget(self.closed_dropdown)
        
        # Signal state dropdown
        signal_label = QLabel("Signal State:")
        controls_layout.addWidget(signal_label)
        
        self.signal_state_dropdown = QComboBox()
        self.signal_state_dropdown.addItems(
            ["RED", "YELLOW", "GREEN", "SUPERGREEN"])
        controls_layout.addWidget(self.signal_state_dropdown)
        
        # Apply button
        apply_segment_btn = QPushButton("Apply Changes")
        apply_segment_btn.clicked.connect(self.apply_segment_changes)
        controls_layout.addWidget(apply_segment_btn)
        
        # Add spacing between segment editing and switch controls
        controls_layout.addSpacing(30)
        
        # === Switch Control Section ===
        switch_section_label = QLabel("Switch Control")
        switch_section_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_layout.addWidget(switch_section_label)
        
        # Switch selection dropdown
        switch_label = QLabel("Select Switch:")
        controls_layout.addWidget(switch_label)
        
        self.switch_dropdown = QComboBox()
        self.switch_dropdown.setMinimumWidth(150)
        controls_layout.addWidget(self.switch_dropdown)
        
        # Switch position dropdown
        position_label = QLabel("Position:")
        controls_layout.addWidget(position_label)
        
        self.switch_position_dropdown = QComboBox()
        self.switch_position_dropdown.addItems(
            ["0 (Straight)", "1 (Diverging)"])
        controls_layout.addWidget(self.switch_position_dropdown)
        
        # Apply switch button
        apply_switch_btn = QPushButton("Apply Switch Position")
        apply_switch_btn.clicked.connect(self.apply_switch_position)
        controls_layout.addWidget(apply_switch_btn)
        
        # Add spacing to push controls to top
        controls_layout.addStretch()
        
        layout.addWidget(controls_widget, 0)  # Fixed size
        
        widget.setLayout(layout)
        return widget
    
    def create_station_info_widget(self):
        """Create the Station Info tab with table and station operation 
        controls."""
        widget = QWidget()
        layout = QHBoxLayout()
        
        # Left side - Station table (stretchable)
        layout.addWidget(self.station_table, 1)  # Takes most of the space
        
        # Right side - Station operation controls
        controls_layout = QVBoxLayout()
        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setMaximumWidth(280)
        
        # Title for controls
        controls_title = QLabel("Station Operations")
        controls_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_layout.addWidget(controls_title)
        
        # Station selection dropdown
        station_label = QLabel("Select Station:")
        controls_layout.addWidget(station_label)
        
        self.station_dropdown = QComboBox()
        self.station_dropdown.setMinimumWidth(200)
        controls_layout.addWidget(self.station_dropdown)
        
        # === Ticket Sales Section ===
        tickets_section_label = QLabel("Ticket Sales")
        tickets_section_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        controls_layout.addWidget(tickets_section_label)
        
        tickets_count_label = QLabel("Count (optional):")
        controls_layout.addWidget(tickets_count_label)
        
        self.tickets_count_input = QLineEdit()
        self.tickets_count_input.setPlaceholderText("Leave empty for random")
        controls_layout.addWidget(self.tickets_count_input)
        
        sell_tickets_btn = QPushButton("Sell Tickets")
        sell_tickets_btn.clicked.connect(self.sell_tickets)
        controls_layout.addWidget(sell_tickets_btn)
        
        # === Passenger Boarding Section ===
        boarding_section_label = QLabel("Passenger Boarding")
        boarding_section_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        controls_layout.addWidget(boarding_section_label)
        
        train_id_label = QLabel("Train ID (required):")
        controls_layout.addWidget(train_id_label)
        
        self.boarding_train_id_input = QLineEdit()
        self.boarding_train_id_input.setPlaceholderText("Enter train ID")
        controls_layout.addWidget(self.boarding_train_id_input)
        
        boarding_count_label = QLabel("Count (optional):")
        controls_layout.addWidget(boarding_count_label)
        
        self.boarding_count_input = QLineEdit()
        self.boarding_count_input.setPlaceholderText("Leave empty for random")
        controls_layout.addWidget(self.boarding_count_input)
        
        board_passengers_btn = QPushButton("Board Passengers")
        board_passengers_btn.clicked.connect(self.board_passengers)
        controls_layout.addWidget(board_passengers_btn)
        
        # === Passenger Exiting Section ===
        exiting_section_label = QLabel("Passenger Exiting")
        exiting_section_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        controls_layout.addWidget(exiting_section_label)
        
        exiting_count_label = QLabel("Count (required):")
        controls_layout.addWidget(exiting_count_label)
        
        self.exiting_count_input = QLineEdit()
        self.exiting_count_input.setPlaceholderText("Enter passenger count")
        controls_layout.addWidget(self.exiting_count_input)
        
        exit_passengers_btn = QPushButton("Exit Passengers")
        exit_passengers_btn.clicked.connect(self.exit_passengers)
        controls_layout.addWidget(exit_passengers_btn)
        
        # Add spacing to push controls to top
        controls_layout.addStretch()
        
        layout.addWidget(controls_widget, 0)  # Fixed size
        
        widget.setLayout(layout)
        return widget
    
    def broadcast_train_command(self):   # TODO #92 modify to only have new TrainCommand
        """Broadcast a train command with the specified parameters"""
        try:
            # Get input values
            train_id_str = self.train_id_input.text().strip()
            speed_str = self.commanded_speed_input.text().strip()
            authority_str = self.authority_input.text().strip()
            
            # Validate inputs
            if not train_id_str:
                self.status_display.append("Error: Train ID is required")
                return
            if not speed_str:
                self.status_display.append("Error: Commanded Speed is required")
                return
            if not authority_str:
                self.status_display.append("Error: Authority is required")
                return
            
            # Convert to appropriate types
            try:
                train_id = int(train_id_str)
            except ValueError:
                self.status_display.append(
                    f"Error: Train ID must be an integer, got '{train_id_str}'"
                )
                return
                
            try:
                commanded_speed_mph = int(speed_str)
            except ValueError:
                self.status_display.append(
                    f"Error: Commanded Speed must be an integer, got '{speed_str}'"
                )
                return
            
            # Convert speed from mph to m/s for internal system
            commanded_speed_mps = ConversionFunctions.mph_to_mps(
                commanded_speed_mph
            )
                
            try:
                authority_yards = int(authority_str)
            except ValueError:
                self.status_display.append(
                    f"Error: Authority must be an integer, got '{authority_str}'"
                )
                return
            
            # Convert authority from yards to meters for internal system
            authority_meters = ConversionFunctions.yards_to_meters(
                authority_yards
            )
            
            # Call the backend method with speed in m/s and authority in meters
            self.track_network.broadcast_train_command(
                train_id, commanded_speed_mps, authority_meters
            )

            self.status_display.append(
                f"Broadcast train command: Train ID={train_id}, "
                f"Speed={commanded_speed_mph} mph ({commanded_speed_mps:.2f} m/s), "
                f"Authority={authority_yards} yards ({authority_meters:.2f} m)"
            )

            # Auto-refresh after broadcasting command
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(
                f"Error broadcasting train command: {str(e)}"
            )
        
    def load_track_layout(self):
        """Load the track layout from CSV file (called once on startup)"""
        try:
            # Load track layout with proper path
            csv_path = os.path.join(os.path.dirname(__file__), "red_line.csv")
            self.status_display.append(
                f"Loading track layout from {csv_path}..."
            )
            self.track_network.load_track_layout(csv_path)
            self.status_display.append("Track layout loaded successfully!\n")
            
            # Display initial network status
            self.refresh_status()
            
        except Exception as e:
            self.status_display.append(f"Error loading track layout: {str(e)}")
    
    def refresh_status(self):
        """Refresh the network status display (without reloading CSV)"""
        try:
            self.track_network.temperature_sim()
            # Get and display network status
            self.status_display.append("Refreshing network status...")
            network_status = self.track_network.get_network_status()
            
            # Display in table format
            self.populate_status_table(network_status)
            
            self.status_display.append("Network status refreshed.")
            
        except Exception as e:
            self.status_display.append(f"Error refreshing status: {str(e)}")
        
    def load_and_display(self):
        """Legacy method - now just calls refresh_status"""
        self.refresh_status()

    def populate_status_table(self, network_status):
        """Populate the status tables with network data"""
        if not network_status:
            self.status_display.append("No network status data available.")
            return
            
        # Clear all tables first
        self.clear_all_tables()
        
        # Assuming network_status is a dictionary
        if isinstance(network_status, dict):
            # Populate segments table
            if 'segments' in network_status:
                self.populate_segments_table(network_status['segments'])
                # Also populate the segment dropdown for failure injection
                self.populate_segment_dropdown(network_status['segments'])
            
            # Populate track info table
            track_info = {}
            if 'environmental_temperature' in network_status:
                # Convert temperature from Celsius to Fahrenheit
                temp_celsius = network_status['environmental_temperature']
                temp_fahrenheit = ConversionFunctions.celsius_to_fahrenheit(
                    temp_celsius
                )
                track_info['Environmental Temperature (°F)'] = f"{temp_fahrenheit:.1f}"
            if 'heater_threshold' in network_status:
                # Convert threshold temperature from Celsius to Fahrenheit
                threshold_celsius = network_status['heater_threshold']
                threshold_fahrenheit = ConversionFunctions.celsius_to_fahrenheit(
                    threshold_celsius
                )
                track_info['Heater Threshold (°F)'] = (
                    f"{threshold_fahrenheit:.1f}"
                )
            if 'heaters_active' in network_status:
                track_info['Heaters Active'] = network_status['heaters_active']
            if 'rail_temperature' in network_status:
                # Convert rail temperature from Celsius to Fahrenheit
                rail_temp_celsius = network_status['rail_temperature']
                rail_temp_fahrenheit = ConversionFunctions.celsius_to_fahrenheit(
                    rail_temp_celsius
                )
                track_info['Rail Temperature (°F)'] = f"{rail_temp_fahrenheit:.1f}"
            self.populate_track_info_table(track_info)
            
            # Populate current failures table
            if 'segments' in network_status:
                self.populate_current_failures_table(network_status['segments'])
            
            # Populate command info table
            if 'active_commands' in network_status:
                self.populate_command_table(network_status['active_commands']) #TODO #92 remove
            
            # Populate failure log table
            if 'failure_log' in network_status:
                self.populate_failure_table(network_status['failure_log'])
            
            # Populate station info table
            if 'segments' in network_status:
                self.populate_station_table(network_status['segments'])
        else:
            # If it's not a dict, display as string in first tab
            self.segment_table.setRowCount(1)
            self.segment_table.setColumnCount(1)
            self.segment_table.setHorizontalHeaderLabels(["Network Status"])
            self.segment_table.setItem(
                0, 0, QTableWidgetItem(str(network_status))
            )
    
    def clear_all_tables(self):
        """Clear all tables"""
        self.segment_table.clear()
        self.track_info_table.clear()
        self.current_failures_table.clear()
        self.command_table.clear()
        self.failure_table.clear()
        self.station_table.clear()
    
    def populate_dict_as_table(
        self, table_widget, data_dict, 
        id_column_name="ID", details_column_name="Details"
    ):
        """Helper function to populate a table with dictionary data.
        
        Handles nested structures.
        """
        if not data_dict:
            return
        
        # Define attributes to exclude from Segment Info
        excluded_segment_attributes = {
            'diverging_segment', 'failures', 
            'passengers_boarded_total', 'passengers_exited_total', 
            'passengers_waiting', 'station_side', 'straight_segment', 
            'tickets_sold_total', 'station_name', 'underground'
        }
        
        # Define custom column order for Segment Info
        segment_column_order = [
            'block_id', 'type', 'occupied', 'closed', 'signal_state', 
            'speed_limit', 'length', 'grade', 'active_command',
            'previous_segment', 'next_segment', 'current_position',
            'gate_status', 'beacon_data',
        ]
        
        # Check if this is being called for segments (based on table widget 
        # or column name)
        is_segment_table = ((table_widget == self.segment_table) or 
                           ("Segment" in id_column_name))
        
        # Count total rows needed (including nested dict items)
        total_rows = 0
        for key, value in data_dict.items():
            if isinstance(value, dict):
                total_rows += len(value)
            else:
                total_rows += 1
        
        if total_rows == 0:
            return
            
        # Determine columns based on data structure
        all_keys = set()
        for key, value in data_dict.items():
            if isinstance(value, dict):
                for sub_key in value.keys():
                    # Filter out excluded attributes for segment tables
                    if not (is_segment_table and 
                           sub_key in excluded_segment_attributes):
                        all_keys.add(sub_key)
        
        if all_keys:
            # Create columns for nested structure
            if is_segment_table:
                # Use custom ordering for segments, no ID column
                ordered_columns = []
                # First add the columns in the specified order
                for col in segment_column_order:
                    if col in all_keys:
                        ordered_columns.append(col)
                        all_keys.remove(col)
                # Add any remaining columns at the end
                ordered_columns.extend(sorted(list(all_keys)))
                columns = ordered_columns
            else:
                # Default behavior for other tables
                columns = [id_column_name] + sorted(list(all_keys))
            
            table_widget.setColumnCount(len(columns))
            table_widget.setHorizontalHeaderLabels(columns)
            
            # Populate rows
            row = 0
            for key, value in data_dict.items():
                if isinstance(value, dict):
                    table_widget.setRowCount(
                        max(table_widget.rowCount(), row + 1)
                    )
                    
                    if is_segment_table:
                        # For segments, don't add ID column
                        for col_idx, col_name in enumerate(columns):
                            if col_name in value:
                                # Apply unit conversions and formatting for 
                                # segment display
                                cell_value = value[col_name]
                                item = None
                                
                                if (col_name == 'length' and 
                                   isinstance(cell_value, (int, float))):
                                    # Convert length from meters to yards
                                    yards_value = ConversionFunctions.meters_to_yards(
                                        cell_value
                                    )
                                    display_value = f"{yards_value:.2f} yds"
                                    item = QTableWidgetItem(display_value)
                                elif col_name == 'speed_limit' and isinstance(cell_value, (int, float)):
                                    # Convert speed from m/s to mph
                                    mph_value = ConversionFunctions.mps_to_mph(cell_value)
                                    display_value = f"{mph_value:.1f} mph"
                                    item = QTableWidgetItem(display_value)
                                elif col_name == 'signal_state':
                                    # Convert signal state to user-friendly display with colors
                                    if hasattr(cell_value, 'name'):
                                        signal_name = cell_value.name
                                    else:
                                        signal_name = str(cell_value)
                                    
                                    # Map signal states to user-friendly names and colors
                                    if signal_name == 'RED' or str(cell_value) == 'SignalState.RED':
                                        display_value = "🔴 Red"
                                        color = QColor(255, 200, 200)  # Light red background
                                    elif signal_name == 'YELLOW' or str(cell_value) == 'SignalState.YELLOW':
                                        display_value = "🟡 Yellow"
                                        color = QColor(255, 255, 200)  # Light yellow background
                                    elif signal_name == 'GREEN' or str(cell_value) == 'SignalState.GREEN':
                                        display_value = "🟢 Green"
                                        color = QColor(200, 255, 200)  # Light green background
                                    elif signal_name == 'SUPERGREEN' or str(cell_value) == 'SignalState.SUPERGREEN':
                                        display_value = "🟢 Super Green"
                                        color = QColor(150, 255, 150)  # Brighter green background
                                    else:
                                        display_value = str(cell_value)
                                        color = QColor(240, 240, 240)  # Light gray background
                                    
                                    item = QTableWidgetItem(display_value)
                                    item.setBackground(color)
                                elif col_name == 'occupied':
                                    # Convert occupied status to user-friendly display with colors
                                    if isinstance(cell_value, bool):
                                        if cell_value:  # True = occupied
                                            display_value = "🟢 Occupied"
                                            color = QColor(200, 255, 200)  # Light green background
                                        else:  # False = unoccupied
                                            display_value = "🔴 Unoccupied"
                                            color = QColor(255, 200, 200)  # Light red background
                                    else:
                                        # Handle string representations
                                        str_value = str(cell_value).lower()
                                        if str_value in ['true', '1', 'occupied']:
                                            display_value = "🟢 Occupied"
                                            color = QColor(200, 255, 200)  # Light green background
                                        else:
                                            display_value = "🔴 Unoccupied"
                                            color = QColor(255, 200, 200)  # Light red background
                                    
                                    item = QTableWidgetItem(display_value)
                                    item.setBackground(color)
                                elif col_name == 'closed':
                                    # Convert closed status to user-friendly display with colors
                                    if isinstance(cell_value, bool):
                                        if cell_value:  # True = closed
                                            display_value = "🔴 Closed"
                                            color = QColor(255, 200, 200)  # Red background
                                        else:  # False = open
                                            display_value = "🟢 Open"
                                            color = QColor(230, 255, 230)  # Very light green background
                                    else:
                                        # Handle string representations
                                        str_value = str(cell_value).lower()
                                        if str_value in ['true', '1', 'closed']:
                                            display_value = "🔴 Closed"
                                            color = QColor(255, 200, 200)  # Red background
                                        else:
                                            display_value = "🟢 Open"
                                            color = QColor(230, 255, 230)  # Very light green background
                                    
                                    item = QTableWidgetItem(display_value)
                                    item.setBackground(color)
                                else:
                                    display_value = str(cell_value)
                                    item = QTableWidgetItem(display_value)
                                
                                table_widget.setItem(row, col_idx, item)
                            else:
                                table_widget.setItem(row, col_idx, QTableWidgetItem(""))
                    else:
                        # For other tables, add ID column
                        table_widget.setItem(row, 0, QTableWidgetItem(str(key)))
                        for col_idx, col_name in enumerate(columns[1:], 1):
                            if col_name in value:
                                table_widget.setItem(row, col_idx, QTableWidgetItem(str(value[col_name])))
                            else:
                                table_widget.setItem(row, col_idx, QTableWidgetItem(""))
                    row += 1
                else:
                    # Simple key-value pair
                    table_widget.setRowCount(max(table_widget.rowCount(), row + 1))
                    table_widget.setItem(row, 0, QTableWidgetItem(str(key)))
                    table_widget.setItem(row, 1, QTableWidgetItem(str(value)))
                    row += 1
        else:
            # Simple key-value structure
            table_widget.setColumnCount(2)
            table_widget.setHorizontalHeaderLabels([id_column_name, details_column_name])
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
            self.populate_dict_as_table(self.segment_table, segments_data, "Segment ID", "Properties")
            # Hide row numbers for segment table
            self.segment_table.verticalHeader().setVisible(False)
        else:
            # If it's a list or other format
            self.segment_table.setRowCount(1)
            self.segment_table.setColumnCount(1)
            self.segment_table.setHorizontalHeaderLabels(["Segments"])
            self.segment_table.setItem(0, 0, QTableWidgetItem(str(segments_data)))
            # Hide row numbers for segment table
            self.segment_table.verticalHeader().setVisible(False)
    
    def populate_track_info_table(self, track_info):
        """Populate the track info table"""
        if not track_info:
            return
        
        # Disconnect any existing signals to avoid multiple connections
        try:
            self.track_info_table.cellChanged.disconnect()
        except:
            pass  # No existing connections
            
        self.track_info_table.setRowCount(len(track_info))
        self.track_info_table.setColumnCount(2)
        self.track_info_table.setHorizontalHeaderLabels(["Property", "Value"])
        
        row = 0
        for key, value in track_info.items():
            # Create property cell (read-only)
            property_item = QTableWidgetItem(str(key))
            property_item.setFlags(property_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.track_info_table.setItem(row, 0, property_item)
            
            # Create value cell
            value_item = QTableWidgetItem(str(value))
            
            # Make temperature cells editable, others read-only
            if "Temperature" in key or "Threshold" in key:
                # Store original Celsius value as item data for temperature conversions
                if "Temperature" in key:
                    # Extract the Fahrenheit value and convert back to Celsius for storage
                    fahrenheit_value = float(str(value).replace('°F', '').strip())
                    celsius_value = ConversionFunctions.fahrenheit_to_celsius(fahrenheit_value)
                    value_item.setData(Qt.ItemDataRole.UserRole, celsius_value)
                elif "Threshold" in key:
                    fahrenheit_value = float(str(value).replace('°F', '').strip())
                    celsius_value = ConversionFunctions.fahrenheit_to_celsius(fahrenheit_value)
                    value_item.setData(Qt.ItemDataRole.UserRole, celsius_value)
                
                # Make editable and highlight
                value_item.setFlags(value_item.flags() | Qt.ItemFlag.ItemIsEditable)
                value_item.setBackground(QColor(240, 248, 255))  # Light blue background for editable cells
            else:
                # Make read-only for non-temperature values
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.track_info_table.setItem(row, 1, value_item)
            row += 1
        
        # Connect cell change signal to update backend
        self.track_info_table.cellChanged.connect(self.on_temperature_changed)
            
        self.track_info_table.resizeColumnsToContents()
    
    def on_temperature_changed(self, row, column):
        """Handle temperature value changes in the track info table"""
        if column != 1:  # Only handle value column changes
            return
        
        # Prevent recursive updates
        if self.updating_temperature:
            return
            
        try:
            self.updating_temperature = True  # Set flag to prevent recursion
            
            # Get the changed item
            item = self.track_info_table.item(row, column)
            property_item = self.track_info_table.item(row, 0)
            
            if not item or not property_item:
                return
                
            property_name = property_item.text()
            new_fahrenheit_str = item.text().replace('°F', '').strip()
            
            # Validate input
            try:
                new_fahrenheit = float(new_fahrenheit_str)
            except ValueError:
                self.status_display.append(f"Error: Invalid temperature value '{new_fahrenheit_str}'. Please enter a number.")
                return
            
            # Convert Fahrenheit input to Celsius for backend
            new_celsius = ConversionFunctions.fahrenheit_to_celsius(new_fahrenheit)
            
            # Update backend based on property type
            if "Environmental Temperature" in property_name:
                self.track_network.set_environmental_temperature(new_celsius)
                self.status_display.append(f"Environmental temperature updated to {new_fahrenheit:.1f}°F ({new_celsius:.1f}°C)")

            elif "Heater Threshold" in property_name:
                self.track_network.set_heater_threshold(new_celsius)
                self.status_display.append(f"Heater threshold updated to {new_fahrenheit:.1f}°F ({new_celsius:.1f}°C)")
            
            # Update the display format to include °F
            item.setText(f"{new_fahrenheit:.1f}")
            
            # Store the Celsius value for future reference
            item.setData(Qt.ItemDataRole.UserRole, new_celsius)
            
        except Exception as e:
            self.status_display.append(f"Error updating temperature: {str(e)}")
        finally:
            self.updating_temperature = False  # Always reset the flag
    
    def execute_command(self):
        """Execute a backend command entered in the terminal"""
        command = self.command_input.text().strip()
        if not command:
            return
            
        # Display the command in terminal
        self.status_display.append(f">>> {command}")
        
        try:
            # Create a safe execution environment with access to backend methods
            safe_globals = {
                '__builtins__': {},
                'track_network': self.track_network,
                'TrackFailureType': TrackFailureType,
                'SignalState': SignalState,
                'StationSide': StationSide,
                'ConversionFunctions': ConversionFunctions,
                # Add some helpful shortcuts
                'tn': self.track_network,  # Shortcut for track_network
            }
            
            # Allow common functions and methods
            safe_builtins = {
                'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
                'list': list, 'dict': dict, 'print': self.terminal_print,
                'range': range, 'enumerate': enumerate,
            }
            safe_globals['__builtins__'] = safe_builtins
            
            # If command doesn't start with track_network or tn, prepend it
            if not (command.startswith('track_network.') or command.startswith('tn.')):
                command = f"track_network.{command}"
            
            # Execute the command
            result = eval(command, safe_globals, {})
            
            # Display result if not None
            if result is not None:
                self.status_display.append(f"Result: {result}")
            else:
                self.status_display.append("Command executed successfully")
            
            # Auto-refresh the network status after successful command execution
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error: {str(e)}")
        
        # Clear the input field
        self.command_input.clear()
        
        # Auto-scroll to bottom
        self.status_display.verticalScrollBar().setValue(
            self.status_display.verticalScrollBar().maximum()
        )
    
    def apply_track_failures(self):
        """Apply or clear track failures based on checkbox states"""
        try:
            selected_segment = self.segment_dropdown.currentText()
            if not selected_segment:
                self.status_display.append("Error: No segment selected")
                return
                
            segment_id = int(selected_segment)
            
            # Handle each failure type
            failures_applied = []
            failures_cleared = []
            
            # Broken Rail
            if self.broken_rail_checkbox.isChecked():
                self.track_network.set_track_failure(segment_id, TrackFailureType.BROKEN_RAIL)
                failures_applied.append("Broken Rail")
            else:
                self.track_network.clear_track_failure(segment_id, TrackFailureType.BROKEN_RAIL)
                failures_cleared.append("Broken Rail")
            
            # Track Circuit Failure
            if self.circuit_failure_checkbox.isChecked():
                self.track_network.set_track_failure(segment_id, TrackFailureType.TRACK_CIRCUIT_FAILURE)
                failures_applied.append("Track Circuit Failure")
            else:
                self.track_network.clear_track_failure(segment_id, TrackFailureType.TRACK_CIRCUIT_FAILURE)
                failures_cleared.append("Track Circuit Failure")
            
            # Power Failure
            if self.power_failure_checkbox.isChecked():
                self.track_network.set_track_failure(segment_id, TrackFailureType.POWER_FAILURE)
                failures_applied.append("Power Failure")
            else:
                self.track_network.clear_track_failure(segment_id, TrackFailureType.POWER_FAILURE)
                failures_cleared.append("Power Failure")
            
            # Report results
            if failures_applied:
                self.status_display.append(f"Applied failures to segment {segment_id}: {', '.join(failures_applied)}")
            if failures_cleared:
                self.status_display.append(f"Cleared failures from segment {segment_id}: {', '.join(failures_cleared)}")
            
            # Auto-refresh after applying failures
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error applying track failures: {str(e)}")
    
    def on_edit_segment_selected(self):
        """Update the control values when a segment is selected for editing"""
        try:
            selected_segment = self.edit_segment_dropdown.currentText()
            if not selected_segment:
                return
                
            segment_id = int(selected_segment)
            
            # Get current segment status from network
            network_status = self.track_network.get_network_status()
            if network_status and 'segments' in network_status:
                segments = network_status['segments']
                if str(segment_id) in segments:
                    segment_data = segments[str(segment_id)]
                    
                    # Update occupancy dropdown
                    current_occupied = segment_data.get('occupied', False)
                    if current_occupied:
                        self.occupancy_dropdown.setCurrentText("True (Occupied)")
                    else:
                        self.occupancy_dropdown.setCurrentText("False (Unoccupied)")
                    
                    # Update closed dropdown
                    current_closed = segment_data.get('closed', False)
                    if current_closed:
                        self.closed_dropdown.setCurrentText("True (Closed)")
                    else:
                        self.closed_dropdown.setCurrentText("False (Open)")
                    
                    # Update signal state dropdown
                    current_signal = segment_data.get('signal_state', SignalState.RED)
                    if hasattr(current_signal, 'name'):
                        signal_name = current_signal.name
                    else:
                        signal_name = str(current_signal).replace('SignalState.', '')
                    
                    # Set dropdown to match current signal state
                    for i in range(self.signal_state_dropdown.count()):
                        if self.signal_state_dropdown.itemText(i) == signal_name:
                            self.signal_state_dropdown.setCurrentIndex(i)
                            break
                    
        except Exception as e:
            self.status_display.append(f"Error updating segment controls: {str(e)}")
    
    def apply_segment_changes(self):
        """Apply the selected changes to the segment"""
        try:
            selected_segment = self.edit_segment_dropdown.currentText()
            if not selected_segment:
                self.status_display.append("Error: No segment selected")
                return
                
            segment_id = int(selected_segment)
            
            # Get selected values
            occupancy_text = self.occupancy_dropdown.currentText()
            occupied = occupancy_text.startswith("True")
            
            closed_text = self.closed_dropdown.currentText()
            closed = closed_text.startswith("True")
            
            signal_state_text = self.signal_state_dropdown.currentText()
            
            # Convert signal state text to enum
            signal_state_map = {
                'RED': SignalState.RED,
                'YELLOW': SignalState.YELLOW,
                'GREEN': SignalState.GREEN,
                'SUPERGREEN': SignalState.SUPERGREEN
            }
            signal_state = signal_state_map.get(signal_state_text, SignalState.RED)
            
            # Apply changes using backend methods
            changes_made = []
            
            # Set occupancy
            self.track_network.set_occupancy(segment_id, occupied)
            occupancy_status = "occupied" if occupied else "unoccupied"
            changes_made.append(f"occupancy={occupancy_status}")
            
            # Set closed status
            if closed:
                self.track_network.close_block(segment_id)
                closed_status = "closed"
            else:
                self.track_network.open_block(segment_id)
                closed_status = "open"
            changes_made.append(f"closed={closed_status}")
            
            # Set signal state
            self.track_network.set_signal_state(segment_id, signal_state)
            changes_made.append(f"signal_state={signal_state_text}")
            
            # Report success
            self.status_display.append(f"Applied changes to segment {segment_id}: {', '.join(changes_made)}")
            
            # Auto-refresh after applying changes
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error applying segment changes: {str(e)}")
    
    def apply_switch_position(self):
        """Apply the selected switch position"""
        try:
            selected_switch = self.switch_dropdown.currentText()
            if not selected_switch:
                self.status_display.append("Error: No switch selected")
                return
                
            switch_id = int(selected_switch)
            
            # Get selected position
            position_text = self.switch_position_dropdown.currentText()
            position = 0 if position_text.startswith("0") else 1
            
            # Apply switch position using backend method
            self.track_network.set_switch_position(switch_id, position)
            
            position_name = "straight" if position == 0 else "diverging"
            self.status_display.append(f"Set switch {switch_id} to position {position} ({position_name})")
            
            # Auto-refresh after applying switch change
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error applying switch position: {str(e)}")
    
    def sell_tickets(self):
        """Sell tickets at the selected station"""
        try:
            selected_station = self.station_dropdown.currentText()
            if not selected_station:
                self.status_display.append("Error: No station selected")
                return
            
            # Extract station block ID from dropdown text (assuming format "ID - Station Name")
            station_block_id = int(selected_station.split(' - ')[0])
            
            # Get count if provided
            count_str = self.tickets_count_input.text().strip()
            count = None
            if count_str:
                try:
                    count = int(count_str)
                    if count < 0:
                        self.status_display.append("Error: Count must be non-negative")
                        return
                except ValueError:
                    self.status_display.append(f"Error: Count must be an integer, got '{count_str}'")
                    return
            
            # Call backend method
            if count is not None:
                self.track_network.sell_tickets(station_block_id, count)
                self.status_display.append(f"Sold {count} tickets at station {station_block_id}")
            else:
                self.track_network.sell_tickets(station_block_id)
                self.status_display.append(f"Sold random number of tickets at station {station_block_id}")
            
            # Clear input and refresh
            self.tickets_count_input.clear()
            self.refresh_status()
            
        except Exception as e:
            self.status_display.append(f"Error selling tickets: {str(e)}")
    
    def board_passengers(self):
        """Board passengers at the selected station"""
        try:
            selected_station = self.station_dropdown.currentText()
            if not selected_station:
                self.status_display.append("Error: No station selected")
                return
            
            # Extract station block ID from dropdown text
            station_block_id = int(selected_station.split(' - ')[0])
            
            # Get train ID (required)
            train_id_str = self.boarding_train_id_input.text().strip()
            if not train_id_str:
                self.status_display.append("Error: Train ID is required")
                return
            
            try:
                train_id = int(train_id_str)
            except ValueError:
                self.status_display.append(f"Error: Train ID must be an integer, got '{train_id_str}'")
                return
            
            # Get count if provided
            count_str = self.boarding_count_input.text().strip()
            count = None
            if count_str:
                try:
                    count = int(count_str)
                    if count < 0:
                        self.status_display.append("Error: Count must be non-negative")
                        return
                except ValueError:
                    self.status_display.append(f"Error: Count must be an integer, got '{count_str}'")
                    return
            
            # Call backend method
            if count is not None:
                self.track_network.passengers_boarding(station_block_id, train_id, count)
                self.status_display.append(f"Boarded {count} passengers on train {train_id} at station {station_block_id}")
            else:
                self.track_network.passengers_boarding(station_block_id, train_id)
                self.status_display.append(f"Boarded random number of passengers on train {train_id} at station {station_block_id}")
            
            # Clear inputs and refresh
            self.boarding_train_id_input.clear()
            self.boarding_count_input.clear()
            self.refresh_status()
            
        except Exception as e:
            self.status_display.append(f"Error boarding passengers: {str(e)}")
    
    def exit_passengers(self):
        """Exit passengers at the selected station"""
        try:
            selected_station = self.station_dropdown.currentText()
            if not selected_station:
                self.status_display.append("Error: No station selected")
                return
            
            # Extract station block ID from dropdown text
            station_block_id = int(selected_station.split(' - ')[0])
            
            # Get count (required)
            count_str = self.exiting_count_input.text().strip()
            if not count_str:
                self.status_display.append("Error: Passenger count is required")
                return
            
            try:
                count = int(count_str)
                if count < 0:
                    self.status_display.append("Error: Count must be non-negative")
                    return
            except ValueError:
                self.status_display.append(f"Error: Count must be an integer, got '{count_str}'")
                return
            
            # Call backend method
            self.track_network.passengers_exiting(station_block_id, count)
            self.status_display.append(f"Exited {count} passengers at station {station_block_id}")
            
            # Clear input and refresh
            self.exiting_count_input.clear()
            self.refresh_status()
            
        except Exception as e:
            self.status_display.append(f"Error exiting passengers: {str(e)}")
    
    def populate_segment_dropdown(self, segments_data):
        """Populate the segment dropdown with available segments"""
        self.segment_dropdown.clear()
        self.edit_segment_dropdown.clear()  # Also clear the edit dropdown
        self.switch_dropdown.clear()  # Also clear the switch dropdown
        
        if isinstance(segments_data, dict):
            # Add segments to dropdown - handle both string and int keys
            segment_ids = []
            switch_ids = []
            
            for seg_id in segments_data.keys():
                try:
                    segment_ids.append(int(seg_id))
                    
                    # Check if this segment is a switch by looking for switch-specific properties
                    segment_info = segments_data[seg_id]
                    if isinstance(segment_info, dict):
                        # Look for switch-specific attributes
                        if ('current_position' in segment_info or 
                            'straight_segment' in segment_info or 
                            'diverging_segment' in segment_info or
                            segment_info.get('type') == 'TrackSwitch'):
                            switch_ids.append(int(seg_id))
                            
                except (ValueError, TypeError):
                    continue
            
            # Populate segment dropdowns
            segment_ids.sort()
            for seg_id in segment_ids:
                self.segment_dropdown.addItem(str(seg_id))
                self.edit_segment_dropdown.addItem(str(seg_id))  # Also add to edit dropdown
            
            # Populate switch dropdown
            switch_ids.sort()
            for switch_id in switch_ids:
                self.switch_dropdown.addItem(str(switch_id))
    
    def populate_current_failures_table(self, segments_data):
        """Populate the current failures table with segments that have active failures"""
        if not segments_data:
            return
        
        # Collect segments with failures
        failure_segments = []
        
        if isinstance(segments_data, dict):
            for segment_id, segment_info in segments_data.items():
                if isinstance(segment_info, dict) and 'failures' in segment_info:
                    failures = segment_info.get('failures', [])
                    if failures:  # Only include segments with active failures
                        try:
                            block_id = segment_info.get('block_id', segment_id)
                            # Convert failures list to readable format
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
        
        # Set up the table
        if failure_segments:
            self.current_failures_table.setRowCount(len(failure_segments))
            self.current_failures_table.setColumnCount(2)
            self.current_failures_table.setHorizontalHeaderLabels(["Block ID", "Current Failures"])
            
            # Populate rows
            for row, segment in enumerate(failure_segments):
                self.current_failures_table.setItem(row, 0, QTableWidgetItem(segment['block_id']))
                self.current_failures_table.setItem(row, 1, QTableWidgetItem(segment['failures']))
            
            # Hide row numbers
            self.current_failures_table.verticalHeader().setVisible(False)
        else:
            # No failures found
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
    
    def populate_command_table(self, commands_data):
        """Populate the command info table"""
        if not commands_data:
            return
            
        if isinstance(commands_data, dict):
            # Check if values are TrainCommand objects
            first_value = next(iter(commands_data.values())) if commands_data else None
            if first_value and hasattr(first_value, 'train_id'):
                # Handle TrainCommand objects
                self.command_table.setRowCount(len(commands_data))
                self.command_table.setColumnCount(4)
                self.command_table.setHorizontalHeaderLabels(["Command ID", "Train ID", "Commanded Speed", "Authority"])
                
                for row, (cmd_id, cmd_obj) in enumerate(commands_data.items()):
                    self.command_table.setItem(row, 0, QTableWidgetItem(str(cmd_id)))
                    self.command_table.setItem(row, 1, QTableWidgetItem(str(cmd_obj.train_id)))
                    
                    # Convert commanded speed from m/s to mph
                    if isinstance(cmd_obj.commanded_speed, (int, float)):
                        mph_value = ConversionFunctions.mps_to_mph(cmd_obj.commanded_speed)
                        speed_display = f"{mph_value:.1f} mph"
                    else:
                        speed_display = str(cmd_obj.commanded_speed)
                    self.command_table.setItem(row, 2, QTableWidgetItem(speed_display))
                    
                    # Convert authority from m to yds
                    if isinstance(cmd_obj.authority, (int, float)):
                        yards_value = ConversionFunctions.meters_to_yards(cmd_obj.authority)
                        authority_display = f"{yards_value:.2f} yds"
                    else:
                        authority_display = str(cmd_obj.authority)
                    self.command_table.setItem(row, 3, QTableWidgetItem(authority_display))
            else:
                # Handle nested dictionaries or simple key-value pairs
                has_nested_dicts = any(isinstance(v, dict) for v in commands_data.values())
                if has_nested_dicts:
                    self.populate_dict_as_table(self.command_table, commands_data, "Command ID", "Properties")
                else:
                    # Simple key-value pairs
                    self.command_table.setRowCount(len(commands_data))
                    self.command_table.setColumnCount(2)
                    self.command_table.setHorizontalHeaderLabels(["Command ID", "Value"])
                    
                    for row, (key, value) in enumerate(commands_data.items()):
                        self.command_table.setItem(row, 0, QTableWidgetItem(str(key)))
                        self.command_table.setItem(row, 1, QTableWidgetItem(str(value)))
                        
        elif isinstance(commands_data, list):
            # Check if list contains TrainCommand objects
            if commands_data and hasattr(commands_data[0], 'train_id'):
                # Handle list of TrainCommand objects
                self.command_table.setRowCount(len(commands_data))
                self.command_table.setColumnCount(3)
                self.command_table.setHorizontalHeaderLabels(["Train ID", "Commanded Speed", "Authority"])
                
                for row, cmd_obj in enumerate(commands_data):
                    self.command_table.setItem(row, 0, QTableWidgetItem(str(cmd_obj.train_id)))
                    
                    # Convert commanded speed from m/s to mph
                    if isinstance(cmd_obj.commanded_speed, (int, float)):
                        mph_value = ConversionFunctions.mps_to_mph(cmd_obj.commanded_speed)
                        speed_display = f"{mph_value:.1f} mph"
                    else:
                        speed_display = str(cmd_obj.commanded_speed)
                    self.command_table.setItem(row, 1, QTableWidgetItem(speed_display))
                    
                    # Convert authority from m to yds
                    if isinstance(cmd_obj.authority, (int, float)):
                        yards_value = ConversionFunctions.meters_to_yards(cmd_obj.authority)
                        authority_display = f"{yards_value:.2f} yds"
                    else:
                        authority_display = str(cmd_obj.authority)
                    self.command_table.setItem(row, 2, QTableWidgetItem(authority_display))
            elif commands_data and isinstance(commands_data[0], dict):
                # Convert list to dict format for better table display
                dict_data = {f"Command_{i}": cmd for i, cmd in enumerate(commands_data)}
                self.populate_dict_as_table(self.command_table, dict_data, "Command ID", "Properties")
            else:
                # Simple list display
                self.command_table.setRowCount(len(commands_data))
                self.command_table.setColumnCount(1)
                self.command_table.setHorizontalHeaderLabels(["Commands"])
                
                for row, cmd in enumerate(commands_data):
                    self.command_table.setItem(row, 0, QTableWidgetItem(str(cmd)))
        else:
            # Fallback for other data types
            self.command_table.setRowCount(1)
            self.command_table.setColumnCount(1)
            self.command_table.setHorizontalHeaderLabels(["Commands"])
            self.command_table.setItem(0, 0, QTableWidgetItem(str(commands_data)))
            
        self.command_table.resizeColumnsToContents()
    
    def populate_failure_table(self, failure_data):
        """Populate the failure log table"""
        if not failure_data:
            return
            
        if isinstance(failure_data, dict):
            self.populate_dict_as_table(self.failure_table, failure_data, "Failure ID", "Properties")
        elif isinstance(failure_data, list):
            # Convert list to dict format for better table display
            if failure_data and isinstance(failure_data[0], dict):
                # If list contains dictionaries, convert to indexed dict
                dict_data = {f"Failure_{i}": failure for i, failure in enumerate(failure_data)}
                self.populate_dict_as_table(self.failure_table, dict_data, "Failure ID", "Properties")
            else:
                # Simple list display
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
        
        # Filter segments to only include those with stations
        station_data = {}
        station_columns = ['block_id', 'station_name', 'station_side', 'tickets_sold_total', 
                          'passengers_waiting', 'passengers_boarded_total', 'passengers_exited_total']
        
        # Also collect station info for dropdown
        station_list = []
        
        if isinstance(segments_data, dict):
            for segment_id, segment_info in segments_data.items():
                if isinstance(segment_info, dict) and 'station_name' in segment_info:
                    # Only include segments that have station information
                    if segment_info.get('station_name'):  # Check if station_name is not empty/None
                        station_data[segment_id] = {col: segment_info.get(col, '') for col in station_columns}
                        # Add to station list for dropdown
                        block_id = segment_info.get('block_id', segment_id)
                        station_name = segment_info.get('station_name', f'Station {block_id}')
                        station_list.append((block_id, station_name))
        
        # Populate station dropdown
        self.station_dropdown.clear()
        station_list.sort(key=lambda x: int(x[0]))  # Sort by block ID
        for block_id, station_name in station_list:
            self.station_dropdown.addItem(f"{block_id} - {station_name}")
        
        if station_data:
            # Set up table for stations with custom column order
            self.station_table.setRowCount(len(station_data))
            self.station_table.setColumnCount(len(station_columns))
            self.station_table.setHorizontalHeaderLabels(station_columns)
            
            # Populate rows
            for row, (segment_id, station_info) in enumerate(station_data.items()):
                for col_idx, col_name in enumerate(station_columns):
                    value = station_info.get(col_name, '')
                    self.station_table.setItem(row, col_idx, QTableWidgetItem(str(value)))
            
            # Hide row numbers for station table
            self.station_table.verticalHeader().setVisible(False)
        else:
            # No stations found
            self.station_table.setRowCount(1)
            self.station_table.setColumnCount(1)
            self.station_table.setHorizontalHeaderLabels(["Station Info"])
            self.station_table.setItem(0, 0, QTableWidgetItem("No stations found"))
            self.station_table.verticalHeader().setVisible(False)
            
        self.station_table.resizeColumnsToContents()

if __name__ == "__main__":
    app = QApplication([])
    window = NetworkStatusUI()
    window.show()
    app.exec()
