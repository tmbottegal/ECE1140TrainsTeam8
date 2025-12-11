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

from universal.global_clock import clock

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

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QTabWidget, QLineEdit, QHBoxLayout, 
    QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from sys import argv

class NetworkStatusUI(QWidget):
    """Test UI for displaying and interacting with the TrackNetworks."""
    def __init__(self, track_network1=None, track_network2=None):
        super().__init__()
        
        # initialize multiple TrackNetwork instances
        self.track_network1 = (track_network1 if track_network1 is not None 
                              else TrackNetwork())
        self.track_network2 = (track_network2 if track_network2 is not None 
                              else TrackNetwork())
        
        # track_network object points to the currently active network
        # initially points to track_network1
        self.track_network = self.track_network1
        # track which network is currently active (1 or 2)
        self.active_network_index = 1
        
        # flag to prevent recursive updates
        self.updating_temperature = False
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
        """Initializes the UI components and layout."""
        self.setWindowTitle("Track Model - Test Network Status")
        self.setGeometry(100, 100, 1400, 800)
        
        layout = QVBoxLayout()
        
        # top section with title and network selector
        top_section = QHBoxLayout()
        
        # title (left side)
        title = QLabel("Track Model - Test UI")
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
        
        # create segment info widget with editing controls
        self.segment_info_widget = self.create_segment_info_widget()
        
        # create track info widget with controls
        self.track_info_widget = self.create_track_info_widget()
        
        self.failure_table = QTableWidget()
        self.failure_table.setFont(QFont("Arial", 10))
        
        self.station_table = QTableWidget()
        self.station_table.setFont(QFont("Arial", 10))

        self.train_table = QTableWidget()
        self.train_table.setFont(QFont("Arial", 10))
        
        # create station info widget with station controls (after 
        # station_table is created)
        self.station_info_widget = self.create_station_info_widget()
        
        # add tables to tabs
        self.tab_widget.addTab(self.segment_info_widget, "Segment Info")
        self.tab_widget.addTab(self.train_table, "Train Info")
        self.tab_widget.addTab(self.station_info_widget, "Station Info")
        self.tab_widget.addTab(self.track_info_widget, "Network Info")
        self.tab_widget.addTab(self.failure_table, "Failure Log")

        layout.addWidget(self.tab_widget)
        
        # terminal section (compact layout)
        terminal_layout = QVBoxLayout()
        
        # status display (terminal output)
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setFont(QFont("Courier", 9))
        terminal_layout.addWidget(self.status_display)
        
        # command input
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
        
        # widget for terminal section
        terminal_widget = QWidget()
        terminal_widget.setLayout(terminal_layout)
        
        # add terminal section with stretch factor (20% of window)
        layout.addWidget(terminal_widget, 1)  # 1 part for terminal
        
        # set stretch 80%/20% tables/terminal
        layout.setStretchFactor(self.tab_widget, 4)  # 4 parts for tables
        layout.setStretchFactor(terminal_widget, 1)   # 1 part for terminal
        
        # bottom section with time display and refresh button
        bottom_layout = QHBoxLayout()
        
        # refresh button
        refresh_btn = QPushButton("Manually Refresh Status")
        refresh_btn.clicked.connect(self.refresh_status)
        bottom_layout.addWidget(refresh_btn, 1)  # stretch factor of 1
        
        # time display (only takes space it needs on the right)
        self.time_label = QLabel("Time: --/--/-- --:--")
        self.time_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)  # right-align the text
        self.time_label.setMinimumWidth(150)  # set minimum width for time display
        bottom_layout.addWidget(self.time_label, 0)  # give it stretch factor of 0
        
        layout.addLayout(bottom_layout)
        
        self.setLayout(layout)
        
    def create_track_info_widget(self):
        """Creates the Track Info tab with table and failure controls"""
        widget = QWidget()
        layout = QHBoxLayout()
        
        # left side - temperature table (fixed width)
        self.track_info_table = QTableWidget()
        self.track_info_table.setFont(QFont("Arial", 10))
        self.track_info_table.setMaximumWidth(250)
        layout.addWidget(self.track_info_table, 0)
        
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
    
    def create_segment_info_widget(self):
        """Creates the Segment Info tab with table and segment editing 
        controls."""
        widget = QWidget()
        layout = QHBoxLayout()
        
        # left side - segment table (stretchable)
        layout.addWidget(self.segment_table, 1)

        # right side - segment editing controls
        controls_layout = QVBoxLayout()
        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setMaximumWidth(250)
        
        # title for controls
        controls_title = QLabel("Edit Segment Properties")
        controls_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_layout.addWidget(controls_title)
        
        # segment selection dropdown
        segment_label = QLabel("Select Segment:")
        controls_layout.addWidget(segment_label)
        
        self.edit_segment_dropdown = QComboBox()
        self.edit_segment_dropdown.setMinimumWidth(150)
        self.edit_segment_dropdown.currentTextChanged.connect(
            self.on_edit_segment_selected)
        controls_layout.addWidget(self.edit_segment_dropdown)
        
        # occupancy dropdown
        occupancy_label = QLabel("Occupancy:")
        controls_layout.addWidget(occupancy_label)
        
        self.occupancy_dropdown = QComboBox()
        self.occupancy_dropdown.addItems(
            ["False (Unoccupied)", "True (Occupied)"])
        controls_layout.addWidget(self.occupancy_dropdown)
        
        # closed status dropdown
        closed_label = QLabel("Closed Status:")
        controls_layout.addWidget(closed_label)
        
        self.closed_dropdown = QComboBox()
        self.closed_dropdown.addItems(["False (Open)", "True (Closed)"])
        controls_layout.addWidget(self.closed_dropdown)
        
        # commanded speed input
        speed_label = QLabel("Commanded Speed (mph):")
        controls_layout.addWidget(speed_label)
        
        self.commanded_speed_input = QLineEdit()
        self.commanded_speed_input.setPlaceholderText("Enter speed in mph")
        controls_layout.addWidget(self.commanded_speed_input)
        
        # authority input
        authority_label = QLabel("Authority (yards):")
        controls_layout.addWidget(authority_label)
        
        self.authority_input = QLineEdit()
        self.authority_input.setPlaceholderText("Enter authority in yards")
        controls_layout.addWidget(self.authority_input)
        
        # apply button
        apply_segment_btn = QPushButton("Apply Changes")
        apply_segment_btn.clicked.connect(self.apply_segment_changes)
        controls_layout.addWidget(apply_segment_btn)
        
        # add spacing between segment editing and switch controls
        controls_layout.addSpacing(30)
        
        # switch control section
        switch_section_label = QLabel("Switch Control")
        switch_section_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_layout.addWidget(switch_section_label)
        
        # switch selection dropdown
        switch_label = QLabel("Select Switch:")
        controls_layout.addWidget(switch_label)
        
        self.switch_dropdown = QComboBox()
        self.switch_dropdown.setMinimumWidth(150)
        controls_layout.addWidget(self.switch_dropdown)
        
        # switch position dropdown
        position_label = QLabel("Position:")
        controls_layout.addWidget(position_label)
        
        self.switch_position_dropdown = QComboBox()
        self.switch_position_dropdown.addItems(
            ["0 (Straight)", "1 (Diverging)"])
        controls_layout.addWidget(self.switch_position_dropdown)
        
        # signal side dropdown
        signal_side_label = QLabel("Signal Side:")
        controls_layout.addWidget(signal_side_label)
        
        self.signal_side_dropdown = QComboBox()
        self.signal_side_dropdown.addItems(
            ["0 (Previous)", "1 (Straight)", "2 (Diverging)"])
        controls_layout.addWidget(self.signal_side_dropdown)
        
        # signal state dropdown
        signal_label = QLabel("Signal State:")
        controls_layout.addWidget(signal_label)
        
        self.signal_state_dropdown = QComboBox()
        self.signal_state_dropdown.addItems(
            ["RED", "YELLOW", "GREEN", "SUPERGREEN"])
        controls_layout.addWidget(self.signal_state_dropdown)
        
        # apply switch button
        apply_switch_btn = QPushButton("Apply Switch Position")
        apply_switch_btn.clicked.connect(self.apply_switch_position)
        controls_layout.addWidget(apply_switch_btn)
        
        # apply signal button
        apply_signal_btn = QPushButton("Apply Signal State")
        apply_signal_btn.clicked.connect(self.apply_signal_state)
        controls_layout.addWidget(apply_signal_btn)
        
        # add spacing to push controls to top
        controls_layout.addStretch()
        
        layout.addWidget(controls_widget, 0)  # fixed size
        
        widget.setLayout(layout)
        return widget
    
    def create_station_info_widget(self):
        """Creates the Station Info tab with table and station operation 
        controls."""
        widget = QWidget()
        layout = QHBoxLayout()
        
        # left side - station table (stretchable)
        layout.addWidget(self.station_table, 1)  # Takes most of the space
        
        # right side - station operation controls
        controls_layout = QVBoxLayout()
        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setMaximumWidth(280)
        
        # title for controls
        controls_title = QLabel("Station Operations")
        controls_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_layout.addWidget(controls_title)
        
        # station selection dropdown
        station_label = QLabel("Select Station:")
        controls_layout.addWidget(station_label)
        
        self.station_dropdown = QComboBox()
        self.station_dropdown.setMinimumWidth(200)
        controls_layout.addWidget(self.station_dropdown)
        
        # ticket sales section
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
        
        # passenger boarding section
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
        
        # passenger exiting section
        exiting_section_label = QLabel("Passenger Exiting")
        exiting_section_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        controls_layout.addWidget(exiting_section_label)
        
        exiting_train_id_label = QLabel("Train ID (required):")
        controls_layout.addWidget(exiting_train_id_label)
        
        self.exiting_train_id_input = QLineEdit()
        self.exiting_train_id_input.setPlaceholderText("Enter train ID")
        controls_layout.addWidget(self.exiting_train_id_input)
        
        exiting_count_label = QLabel("Count (required):")
        controls_layout.addWidget(exiting_count_label)
        
        self.exiting_count_input = QLineEdit()
        self.exiting_count_input.setPlaceholderText("Enter passenger count")
        controls_layout.addWidget(self.exiting_count_input)
        
        exit_passengers_btn = QPushButton("Exit Passengers")
        exit_passengers_btn.clicked.connect(self.exit_passengers)
        controls_layout.addWidget(exit_passengers_btn)
        
        # add spacing to push controls to top
        controls_layout.addStretch()
        
        layout.addWidget(controls_widget, 0)  # fixed size
        
        widget.setLayout(layout)
        return widget
    
    def broadcast_train_command(self): 
        """Broadcasts a train command with the specified parameters"""
        try:
            # get input values
            speed_str = self.commanded_speed_input.text().strip()
            authority_str = self.authority_input.text().strip()
            
            # validate inputs
            if not speed_str:
                self.status_display.append("Error: Commanded Speed is required")
                return
            if not authority_str:
                self.status_display.append("Error: Authority is required")
                return
            
            # convert to appropriate types
            try:
                commanded_speed_mph = int(speed_str)
            except ValueError:
                self.status_display.append(
                    f"Error: Commanded Speed must be an integer, got '{speed_str}'"
                )
                return
            
            # convert speed from mph to m/s for internal system
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
            
            # convert authority from yards to meters for internal system
            authority_meters = ConversionFunctions.yards_to_meters(
                authority_yards
            )
            
            # determine block_id from selected segment dropdowns (edit or general)
            edit_selection = self.edit_segment_dropdown.currentText()
            segment_selection = self.segment_dropdown.currentText()
            selected_segment = edit_selection or segment_selection
            if not selected_segment:
                err_message = "Error: No segment selected for broadcasting train command"
                self.status_display.append(err_message)
                return
            try:
                block_id = int(selected_segment)
            except (ValueError, TypeError):
                error_message = f"Error: Invalid segment id '{selected_segment}'"
                self.status_display.append(error_message)
                return

            # call the backend method with speed in m/s and authority in meters
            self.track_network.broadcast_train_command(
                block_id, commanded_speed_mps, authority_meters
            )

            self.status_display.append(
                f"Broadcast train command: Block ID={block_id}, "
                f"Speed={commanded_speed_mph} mph ({commanded_speed_mps:.2f} m/s), "
                f"Authority={authority_yards} yards ({authority_meters:.2f} m)"
            )

            # auto-refresh after broadcasting command
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(
                f"Error broadcasting train command: {str(e)}"
            )
        
    def load_track_layout_for_network(self, network, csv_filename):
        """Loads the track layout from CSV file for a specific network"""
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
        """Switches the active network between track_network1 and track_network2"""
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
        """Gets the name of the currently active network"""
        if hasattr(self.track_network, 'line_name'):
            return self.track_network.line_name
        else:
            return f"Network {self.active_network_index}"
    
    def populate_network_selector(self):
        """Populates the network selector dropdown with available networks"""
        try:
            # temporarily disconnect the signal to avoid triggering during population
            self.network_selector.currentTextChanged.disconnect()
            
            self.network_selector.clear()
            
            # get network names
            network1_name = (self.track_network1.line_name 
                           if hasattr(self.track_network1, 'line_name') 
                           else "Network 1")
            network2_name = (self.track_network2.line_name 
                           if hasattr(self.track_network2, 'line_name') 
                           else "Network 2")
            
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
            # make sure to reconnect the signal even if there's an error
            try:
                self.network_selector.currentTextChanged.connect(self.on_network_changed)
            except:
                pass
    
    def on_network_changed(self, network_name: str):
        """Handles network selection change from dropdown
        
            Args:
                network_name: The name of the selected network
        """
        try:
            self.status_display.append(f"Network dropdown changed to: '{network_name}'")
            
            # prevent processing during initialization or clearing
            if network_name == "Loading..." or not network_name:
                self.status_display.append("Ignoring network change (loading or empty)")
                return
            
            # determine which network was selected
            network1_name = (self.track_network1.line_name 
                           if hasattr(self.track_network1, 'line_name') 
                           else "Network 1")
            network2_name = (self.track_network2.line_name 
                           if hasattr(self.track_network2, 'line_name') 
                           else "Network 2")
            
            network_info = (f"Network 1 name: '{network1_name}', "
                          f"Network 2 name: '{network2_name}'")
            self.status_display.append(network_info)
            active_info = f"Current active network index: {self.active_network_index}"
            self.status_display.append(active_info)
            
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
    
    def refresh_status(self):
        """Manually refreshes the network status display"""
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
        """Automatically refreshes the network status display
        
            Args:
                current_time: The current time from the global clock (optional)
        """
        try:
            # get and display network status
            network_status = self.track_network.get_network_status()
            
            # display in table format
            self.populate_status_table(network_status)
        
        except Exception as e:
            self.status_display.append(f"Error refreshing status: {str(e)}")
        
    def load_and_display(self):
        """legacy method aiped - calls refresh_status"""
        self.refresh_status() 

    def populate_status_table(self, network_status):
        """Populates the status tables with network data
        
            Args:
                network_status: The network status data to display
        """
        if not network_status:
            self.status_display.append("No network status data available.")
            return
        
        # assuming network_status is a dictionary
        if isinstance(network_status, dict):
            # update time display if available
            if 'time' in network_status:
                time_obj = network_status['time']
                # format as MM/DD/YY HH:MM
                formatted_time = time_obj.strftime("%m/%d/%y %H:%M:%S")
                self.time_label.setText(f"Time: {formatted_time}")
            
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
                    temp_celsius
                )
                track_info['Environmental Temperature (°F)'] = f"{temp_fahrenheit:.1f}"
            if 'heater_threshold' in network_status:
                # convert threshold temperature from Celsius to Fahrenheit
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
                # convert rail temperature from Celsius to Fahrenheit
                rail_temp_celsius = network_status['rail_temperature']
                rail_temp_fahrenheit = ConversionFunctions.celsius_to_fahrenheit(
                    rail_temp_celsius
                )
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
                0, 0, QTableWidgetItem(str(network_status))
            )
    
    def populate_dict_as_table(
        self, table_widget, data_dict, 
        id_column_name="ID", details_column_name="Details"
    ):
        """Helper function to populate a table with dictionary data.
        Handles nested structures. Only updates cells that have changed.

            Args:
                table_widget: The QTableWidget to populate
                data_dict: The dictionary data to display
                id_column_name: The name of the ID column
                details_column_name: The name of the Details column
        """
        if not data_dict:
            # If no data, clear the table
            table_widget.setRowCount(0)
            table_widget.setColumnCount(0)
            return
        
        # attributes to exclude from segment info
        excluded_segment_attributes = {
            'diverging_segment', 'failures', 'closed',
            'passengers_boarded_total', 'passengers_exited_total', 
            'passengers_waiting', 'station_side', 'straight_segment', 
            'tickets_sold_total', 'station_name', 'underground'
        }
        
        # custom column order for segment info
        segment_column_order = [
            'block_id', 'type', 'occupied', 'prev_sig', 'str_sig', 'div_sig', 
            'speed_limit', 'length', 'grade', 'elevation', 'direction', 
            'cmd_speed', 'cmd_auth', 'prev_seg', 'next_seg', 'current_pos', 
            'gate_status', 'beacon_data',
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
                # use custom ordering for segments
                ordered_columns = []
                # first add the columns in the specified order
                for col in segment_column_order:
                    # check both original name and alias
                    alias_lookup = column_aliases.items()
                    original_col = next((k for k, v in alias_lookup if v == col), col)
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
                # only restructure if necessary
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
                                # apply unit conversions and formatting for 
                                # segment display
                                cell_value = value[original_col_name]
                                item = None
                                
                                if (original_col_name == 'length' and 
                                   isinstance(cell_value, (int, float))):
                                    # convert length from meters to yards
                                    yards_value = ConversionFunctions.meters_to_yards(
                                        cell_value
                                    )
                                    display_value = f"{yards_value:.2f} yds"
                                    item = QTableWidgetItem(display_value)
                                elif original_col_name == 'speed_limit' and isinstance(cell_value, (int, float)):
                                    # convert speed from m/s to mph
                                    mph_value = ConversionFunctions.mps_to_mph(cell_value)
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
                                    # convert direction to user-friendly display
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
                                signal_state_columns = ['previous_signal_state', 
                                                       'straight_signal_state', 
                                                       'diverging_signal_state']
                                if original_col_name in signal_state_columns:
                                    if hasattr(cell_value, 'name'):
                                        signal_name = cell_value.name
                                    else:
                                        signal_name = str(cell_value)
                                    
                                    if signal_name == 'RED' or str(cell_value) == 'SignalState.RED':
                                        display_value = "🔴 Red"
                                        color = QColor(255, 200, 200)
                                    elif signal_name == 'YELLOW' or str(cell_value) == 'SignalState.YELLOW':
                                        display_value = "🟡 Yellow"
                                        color = QColor(255, 255, 200)
                                    elif signal_name == 'GREEN' or str(cell_value) == 'SignalState.GREEN':
                                        display_value = "🟢 Green"
                                        color = QColor(200, 255, 200) 
                                    elif signal_name == 'SUPERGREEN' or str(cell_value) == 'SignalState.SUPERGREEN':
                                        display_value = "🟢 Super Green"
                                        color = QColor(150, 255, 150)
                                    else:
                                        display_value = str(cell_value)
                                        color = QColor(240, 240, 240) 
                                    
                                    item = QTableWidgetItem(display_value)
                                    item.setBackground(color)
                                elif original_col_name == 'occupied':
                                    if isinstance(cell_value, bool):
                                        if cell_value:
                                            display_value = "🟢 Occupied"
                                            color = QColor(200, 255, 200)  # light green background
                                        else:
                                            display_value = "🔴 Unoccupied"
                                            color = QColor(255, 200, 200)  # light red background
                                    else:
                                        # handle string representations
                                        str_value = str(cell_value).lower()
                                        if str_value in ['true', '1', 'occupied']:
                                            display_value = "🟢 Occupied"
                                            color = QColor(200, 255, 200)  # light green background
                                        else:
                                            display_value = "🔴 Unoccupied"
                                            color = QColor(255, 200, 200)  # light red background
                                    
                                    item = QTableWidgetItem(display_value)
                                    item.setBackground(color)
                                elif original_col_name == 'closed':
                                    if isinstance(cell_value, bool):
                                        if cell_value:
                                            display_value = "🔴 Closed"
                                            color = QColor(255, 200, 200)  # red background
                                        else:
                                            display_value = "🟢 Open"
                                            color = QColor(230, 255, 230)  # very light green background
                                    else:
                                        # handle string representations
                                        str_value = str(cell_value).lower()
                                        if str_value in ['true', '1', 'closed']:
                                            display_value = "🔴 Closed"
                                            color = QColor(255, 200, 200)  # red background
                                        else:
                                            display_value = "🟢 Open"
                                            color = QColor(230, 255, 230)  # very light green background
                                    
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
                                else:
                                    display_value = str(cell_value)
                                    item = QTableWidgetItem(display_value)
                                
                                # only update if the value has changed
                                existing_item = table_widget.item(row, col_idx)
                                if existing_item is None or existing_item.text() != display_value:
                                    table_widget.setItem(row, col_idx, item)
                            else:
                                # only clear if the cell has content
                                existing_item = table_widget.item(row, col_idx)
                                if existing_item is not None and existing_item.text() != "":
                                    table_widget.setItem(row, col_idx, QTableWidgetItem(""))
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
                                    table_widget.setItem(row, col_idx, QTableWidgetItem(new_value))
                            else:
                                existing_item = table_widget.item(row, col_idx)
                                if existing_item is not None and existing_item.text() != "":
                                    table_widget.setItem(row, col_idx, QTableWidgetItem(""))
                    row += 1
                else:
                    table_widget.setItem(row, 0, QTableWidgetItem(str(key)))
                    table_widget.setItem(row, 1, QTableWidgetItem(str(value)))
                    row += 1
        else:
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
        """Populates the segments table.
        
            Args:
                segments_data: The segments data to display
        """
        if not segments_data:
            return
            
        if isinstance(segments_data, dict):
            self.populate_dict_as_table(self.segment_table, segments_data, "Segment ID", "Properties")
            # hide row numbers for segment table
            self.segment_table.verticalHeader().setVisible(False)
        else:
            # if it's a list or other format
            self.segment_table.setRowCount(1)
            self.segment_table.setColumnCount(1)
            self.segment_table.setHorizontalHeaderLabels(["Segments"])
            self.segment_table.setItem(0, 0, QTableWidgetItem(str(segments_data)))
            # hide row numbers for segment table
            self.segment_table.verticalHeader().setVisible(False)
    
    def populate_track_info_table(self, track_info):
        """Populate the track info table.
        
            Args:
                track_info: The track information to display
        """
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
            property_item.setFlags(property_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.track_info_table.setItem(row, 0, property_item)
            
            # only skip updating editable cells if user is currently editing them
            # rail temperature should always update since it's read-only
            is_editable_field = "Temperature" in key or "Threshold" in key
            if row == editing_row and 1 == editing_col and is_editable_field:
                row += 1
                continue
            
            # create value cell
            value_item = QTableWidgetItem(str(value))
            
            # make temperature cells editable, others read-only
            if "Temperature" in key or "Threshold" in key:
                # store original celsius value as item data for temperature conversions
                if "Temperature" in key:
                    # extract the fahr value and convert back to celsius for storage
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
                # make read-only for non-temperature values
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.track_info_table.setItem(row, 1, value_item)
            row += 1
        
        # connect cell change signal to update backend
        self.track_info_table.cellChanged.connect(self.on_temperature_changed)
            
        self.track_info_table.resizeColumnsToContents()
    
    def on_temperature_changed(self, row, column):
        """Handles temperature value changes in the track info table.
        
            Args:
                row: The row index of the changed cell
                column: The column index of the changed cell
        """
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
            
            # update the display format to include fahr
            item.setText(f"{new_fahrenheit:.1f}")
            
            # store the celsius value for future reference
            item.setData(Qt.ItemDataRole.UserRole, new_celsius)
            
        except Exception as e:
            self.status_display.append(f"Error updating temperature: {str(e)}")
        finally:
            self.updating_temperature = False  # always reset the flag
    
    def execute_command(self):
        """Executes a backend command entered in the terminal."""
        command = self.command_input.text().strip()
        if not command:
            return
            
        # display the command in terminal
        self.status_display.append(f">>> {command}")
        
        try:
            # create a safe execution environment with access to backend methods
            safe_globals = {
                '__builtins__': {},
                'track_network': self.track_network,
                'TrackFailureType': TrackFailureType,
                'SignalState': SignalState,
                'StationSide': StationSide,
                'ConversionFunctions': ConversionFunctions,
                # add some helpful shortcuts
                'tn': self.track_network,  # shortcut for track_network
            }
            
            # allow common functions and methods
            safe_builtins = {
                'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
                'list': list, 'dict': dict, 'print': self.terminal_print,
                'range': range, 'enumerate': enumerate,
            }
            safe_globals['__builtins__'] = safe_builtins
            
            # if command doesn't start with track_network or tn, prepend it
            if not (command.startswith('track_network.') or command.startswith('tn.')):
                command = f"track_network.{command}"
            
            # execute the command
            result = eval(command, safe_globals, {})
            
            # display result if not None
            if result is not None:
                self.status_display.append(f"Result: {result}")
            else:
                self.status_display.append("Command executed successfully")
            
            # auto-refresh the network status after successful command execution
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error: {str(e)}")
        
        # clear input field
        self.command_input.clear()
        
        # auto-scroll to bottom
        self.status_display.verticalScrollBar().setValue(
            self.status_display.verticalScrollBar().maximum()
        )
    
    def apply_track_failures(self):
        """Applies or clears track failures based on checkbox states"""
        try:
            selected_segment = self.segment_dropdown.currentText()
            if not selected_segment:
                self.status_display.append("Error: No segment selected")
                return
                
            segment_id = int(selected_segment)
            
            # handle each failure type
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
            
            # report results
            if failures_applied:
                self.status_display.append(f"Applied failures to segment {segment_id}: {', '.join(failures_applied)}")
            if failures_cleared:
                self.status_display.append(f"Cleared failures from segment {segment_id}: {', '.join(failures_cleared)}")
            
            # auto-refresh after applying failures
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error applying track failures: {str(e)}")
    
    def on_edit_segment_selected(self):
        """Updates the control values when a segment is selected for editing"""
        try:
            selected_segment = self.edit_segment_dropdown.currentText()
            if not selected_segment:
                return
                
            segment_id = int(selected_segment)
            
            # get current segment status from network
            network_status = self.track_network.get_network_status()
            if network_status and 'segments' in network_status:
                segments = network_status['segments']
                if str(segment_id) in segments:
                    segment_data = segments[str(segment_id)]
                    
                    # update occupancy dropdown
                    current_occupied = segment_data.get('occupied', False)
                    if current_occupied:
                        self.occupancy_dropdown.setCurrentText("True (Occupied)")
                    else:
                        self.occupancy_dropdown.setCurrentText("False (Unoccupied)")
                    
                    # update closed dropdown
                    current_closed = segment_data.get('closed', False)
                    if current_closed:
                        self.closed_dropdown.setCurrentText("True (Closed)")
                    else:
                        self.closed_dropdown.setCurrentText("False (Open)")
                    
                    # update signal state dropdown
                    current_signal = segment_data.get('signal_state', SignalState.RED)
                    if hasattr(current_signal, 'name'):
                        signal_name = current_signal.name
                    else:
                        signal_name = str(current_signal).replace('SignalState.', '')
                    
                    # set dropdown to match current signal state
                    for i in range(self.signal_state_dropdown.count()):
                        if self.signal_state_dropdown.itemText(i) == signal_name:
                            self.signal_state_dropdown.setCurrentIndex(i)
                            break
                    
                    # update commanded speed and authority from active command if present
                    active_command = segment_data.get('active_command', None)
                    if active_command and isinstance(active_command, dict):
                        # convert speed from m/s to mph for display
                        speed_mps = active_command.get('commanded_speed', 0)
                        speed_mph = ConversionFunctions.mps_to_mph(speed_mps)
                        self.commanded_speed_input.setText(str(int(speed_mph)))
                        
                        # convert authority from meters to yards for display
                        authority_meters = active_command.get('authority', 0)
                        authority_yards = ConversionFunctions.meters_to_yards(authority_meters)
                        self.authority_input.setText(str(int(authority_yards)))
                    else:
                        # Clear fields if no active command
                        self.commanded_speed_input.clear()
                        self.authority_input.clear()
                    
        except Exception as e:
            self.status_display.append(f"Error updating segment controls: {str(e)}")
    
    def apply_segment_changes(self):
        """Applies the selected changes to the segment"""
        try:
            selected_segment = self.edit_segment_dropdown.currentText()
            if not selected_segment:
                self.status_display.append("Error: No segment selected")
                return
                
            segment_id = int(selected_segment)
            
            # get selected values
            occupancy_text = self.occupancy_dropdown.currentText()
            occupied = occupancy_text.startswith("True")
            
            closed_text = self.closed_dropdown.currentText()
            closed = closed_text.startswith("True")
            
            # apply changes using backend methods
            changes_made = []
            
            # set occupancy
            self.track_network.set_occupancy(segment_id, occupied)
            occupancy_status = "occupied" if occupied else "unoccupied"
            changes_made.append(f"occupancy={occupancy_status}")
            
            # set closed status
            if closed:
                self.track_network.close_block(segment_id)
                closed_status = "closed"
            else:
                self.track_network.open_block(segment_id)
                closed_status = "open"
            changes_made.append(f"closed={closed_status}")
            
            # handle train command if speed and authority are provided
            speed_str = self.commanded_speed_input.text().strip()
            authority_str = self.authority_input.text().strip()
            
            if speed_str or authority_str:
                # validate that both fields are provided if one is provided
                if not speed_str:
                    self.status_display.append("Error: Commanded Speed is required when Authority is provided")
                    return
                if not authority_str:
                    self.status_display.append("Error: Authority is required when Commanded Speed is provided")
                    return
                
                # convert and validate inputs
                try:
                    commanded_speed_mph = int(speed_str)
                    if commanded_speed_mph < 0:
                        self.status_display.append("Error: Commanded Speed must be non-negative")
                        return
                except ValueError:
                    self.status_display.append(f"Error: Commanded Speed must be an integer, got '{speed_str}'")
                    return
                
                try:
                    authority_yards = int(authority_str)
                    if authority_yards < 0:
                        self.status_display.append("Error: Authority must be non-negative")
                        return
                except ValueError:
                    self.status_display.append(f"Error: Authority must be an integer, got '{authority_str}'")
                    return
                
                # convert units for internal system
                commanded_speed_mps = ConversionFunctions.mph_to_mps(commanded_speed_mph)
                authority_meters = ConversionFunctions.yards_to_meters(authority_yards)
                
                # broadcast train command
                self.track_network.broadcast_train_command(
                    segment_id, commanded_speed_mps, authority_meters
                )
                
                changes_made.append(f"train_command(speed={commanded_speed_mph}mph, authority={authority_yards}yards)")
                
                # clear the input fields after successful command broadcast
                self.commanded_speed_input.clear()
                self.authority_input.clear()
            
            # report success
            self.status_display.append(f"Applied changes to segment {segment_id}: {', '.join(changes_made)}")
            
            # auto-refresh after applying changes
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error applying segment changes: {str(e)}")
    
    def apply_switch_position(self):
        """Applies the selected switch position"""
        try:
            selected_switch = self.switch_dropdown.currentText()
            if not selected_switch:
                self.status_display.append("Error: No switch selected")
                return
                
            switch_id = int(selected_switch)
            
            # get selected position
            position_text = self.switch_position_dropdown.currentText()
            position = 0 if position_text.startswith("0") else 1
            
            # apply switch position
            self.track_network.set_switch_position(switch_id, position)
            position_name = "straight" if position == 0 else "diverging"
            
            self.status_display.append(f"Applied switch position to switch {switch_id}: {position} ({position_name})")
            
            # auto-refresh after applying switch change
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error applying switch position: {str(e)}")
    
    def apply_signal_state(self):
        """Applies the selected signal state to the selected switch"""
        try:
            selected_switch = self.switch_dropdown.currentText()
            if not selected_switch:
                self.status_display.append("Error: No switch selected")
                return
                
            switch_id = int(selected_switch)
            
            # get selected signal side
            signal_side_text = self.signal_side_dropdown.currentText()
            signal_side = int(signal_side_text[0])  # extract number from friendly format
            
            # get selected signal state
            signal_state_text = self.signal_state_dropdown.currentText()
            
            # convert signal state text to enum
            signal_state_map = {
                'RED': SignalState.RED,
                'YELLOW': SignalState.YELLOW,
                'GREEN': SignalState.GREEN,
                'SUPERGREEN': SignalState.SUPERGREEN
            }
            signal_state = signal_state_map.get(signal_state_text, SignalState.RED)
            
            # convert signal side to friendly name
            signal_side_names = {
                0: "previous",
                1: "straight", 
                2: "diverging"
            }
            signal_side_name = signal_side_names.get(signal_side, "unknown")
            
            # apply signal state
            self.track_network.set_signal_state(switch_id, signal_side, signal_state)
            
            self.status_display.append(f"Applied signal state to switch {switch_id}: {signal_side_name} signal = {signal_state_text}")
            
            # auto-refresh after applying signal change
            self.refresh_status()
                
        except Exception as e:
            self.status_display.append(f"Error applying signal state: {str(e)}")
    
    def sell_tickets(self):
        """Sells tickets at the selected station"""
        try:
            selected_station = self.station_dropdown.currentText()
            if not selected_station:
                self.status_display.append("Error: No station selected")
                return
            
            # extract station block ID from dropdown text (assuming format "ID - Station Name")
            station_block_id = int(selected_station.split(' - ')[0])
            
            # get count if provided
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
            
            # call backend method
            if count is not None:
                self.track_network.sell_tickets(station_block_id, count)
                self.status_display.append(f"Sold {count} tickets at station {station_block_id}")
            else:
                self.track_network.sell_tickets(station_block_id)
                self.status_display.append(f"Sold random number of tickets at station {station_block_id}")
            
            # clear input and refresh
            self.tickets_count_input.clear()
            self.refresh_status()
            
        except Exception as e:
            self.status_display.append(f"Error selling tickets: {str(e)}")
    
    def board_passengers(self):
        """Boards passengers at the selected station"""
        try:
            selected_station = self.station_dropdown.currentText()
            if not selected_station:
                self.status_display.append("Error: No station selected")
                return
            
            # extract station block ID from dropdown text
            station_block_id = int(selected_station.split(' - ')[0])
            
            # get train ID (required)
            train_id_str = self.boarding_train_id_input.text().strip()
            if not train_id_str:
                self.status_display.append("Error: Train ID is required")
                return
            
            try:
                train_id = int(train_id_str)
            except ValueError:
                self.status_display.append(f"Error: Train ID must be an integer, got '{train_id_str}'")
                return
            
            # get count if provided
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
            
            # call backend method
            if count is not None:
                self.track_network.passengers_boarding(station_block_id, train_id, count)
                self.status_display.append(f"Boarded {count} passengers on train {train_id} at station {station_block_id}")
            else:
                self.track_network.passengers_boarding(station_block_id, train_id)
                self.status_display.append(f"Boarded random number of passengers on train {train_id} at station {station_block_id}")
            
            # clear inputs and refresh
            self.boarding_train_id_input.clear()
            self.boarding_count_input.clear()
            self.refresh_status()
            
        except Exception as e:
            self.status_display.append(f"Error boarding passengers: {str(e)}")
    
    def exit_passengers(self):
        """Make passengers exit at the selected station"""
        try:
            selected_station = self.station_dropdown.currentText()
            if not selected_station:
                self.status_display.append("Error: No station selected")
                return
            
            # extract station block ID from dropdown text
            station_block_id = int(selected_station.split(' - ')[0])
            
            # get train ID (required)
            train_id_str = self.exiting_train_id_input.text().strip()
            if not train_id_str:
                self.status_display.append("Error: Train ID is required")
                return
            
            try:
                train_id = int(train_id_str)
            except ValueError:
                self.status_display.append(f"Error: Train ID must be an integer, got '{train_id_str}'")
                return
            
            # get count (required)
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
            
            # call backend method
            self.track_network.passengers_exiting(station_block_id, train_id, count)
            self.status_display.append(f"Exited {count} passengers from train {train_id} at station {station_block_id}")
            
            # clear inputs and refresh
            self.exiting_train_id_input.clear()
            self.exiting_count_input.clear()
            self.refresh_status()
            
        except Exception as e:
            self.status_display.append(f"Error exiting passengers: {str(e)}")
    
    def populate_segment_dropdown(self, segments_data):
        """Populates the segment dropdown with available segments.
        
            Args:
                segments_data: The segments data to extract IDs from
        """
        self.segment_dropdown.clear()
        self.edit_segment_dropdown.clear()  # also clear the edit dropdown
        self.switch_dropdown.clear()  # also clear the switch dropdown
        
        if isinstance(segments_data, dict):
            # add segments to dropdown - handle both string and int keys
            segment_ids = []
            switch_ids = []
            
            for seg_id in segments_data.keys():
                try:
                    segment_ids.append(int(seg_id))
                    
                    # check if this segment is a switch by looking for switch-specific properties
                    segment_info = segments_data[seg_id]
                    if isinstance(segment_info, dict):
                        # look for switch-specific attributes
                        if ('current_position' in segment_info or 
                            'straight_segment' in segment_info or 
                            'diverging_segment' in segment_info or
                            segment_info.get('type') == 'TrackSwitch'):
                            switch_ids.append(int(seg_id))
                            
                except (ValueError, TypeError):
                    continue
            
            # populate segment dropdowns
            segment_ids.sort()
            for seg_id in segment_ids:
                self.segment_dropdown.addItem(str(seg_id))
                self.edit_segment_dropdown.addItem(str(seg_id))  # also add to edit dropdown
            
            # populate switch dropdown
            switch_ids.sort()
            for switch_id in switch_ids:
                self.switch_dropdown.addItem(str(switch_id))
    
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
                    if failures:  # only include segments with active failures
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
            # convert list to dict format for better table display
            if failure_data and isinstance(failure_data[0], dict):
                # if list contains dictionaries, convert to indexed dict
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
        
        # filter segments to only include those with stations
        station_data = {}
        station_columns = ['block_id', 'station_name', 'station_side', 'tickets_sold_total', 
                          'passengers_waiting', 'passengers_boarded_total', 'passengers_exited_total']
        
        # also collect station info for dropdown
        station_list = []
        
        if isinstance(segments_data, dict):
            for segment_id, segment_info in segments_data.items():
                if isinstance(segment_info, dict) and 'station_name' in segment_info:
                    # only include segments that have station information
                    if segment_info.get('station_name'):  # check if station_name is not empty/None
                        station_data[segment_id] = {col: segment_info.get(col, '') for col in station_columns}
                        # add to station list for dropdown
                        block_id = segment_info.get('block_id', segment_id)
                        station_name = segment_info.get('station_name', f'Station {block_id}')
                        station_list.append((block_id, station_name))
        
        #   populate station dropdown
        self.station_dropdown.clear()
        station_list.sort(key=lambda x: int(x[0]))  # Sort by block ID
        for block_id, station_name in station_list:
            self.station_dropdown.addItem(f"{block_id} - {station_name}")
        
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
        """Populates the train info table with train-specific data.
        
        
            Args:
                trains_data: The trains data to populate the table
        """
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
                            # convert displacement from meters to yards
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
            # fallback for unexpected data format
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
