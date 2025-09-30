"""
Track Model Backend
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from random import Random

import sys
sys.path.append('../')

from universal.universal import (
    SignalState, 
    TrainCommand
)

class TrackFailureType(Enum):
    """Enumeration of possible track failure types."""
    BROKEN_RAIL = "broken_rail"
    TRACK_CIRCUIT_FAILURE = "track_circuit_failure"
    POWER_FAILURE = "power_failure"


class StationSide(Enum):
    """Enumeration of station platform sides."""
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"

class TrackSegment:
    """Base class for all track segments in the railway network.
    
    Represents a single block in the track model with properties for
    occupancy tracking and failure states.
    
    Attributes:
        block_id: Unique identifier for the track block.
        length: Length of the segment in meters.
        grade: Grade percentage.
        connected_segments: List of segments directly reachable from this one.
        previous_segments: List of segments that lead into this one.
        occupied: Whether the block is currently occupied.
        failures: Set of current failure conditions on this block.
        signal_state: Current signal state for this block.
        is_station: Whether this block is a station.
        station_name: Name of the station if applicable.
        passengers_waiting: Number of passengers currently waiting at the station if applicable.
        beacon_data: Beacon information for trains entering this block.

    """
    
    def __init__(self, block_id: str, length: int, speed_limit:int, grade: float, underground: bool) -> None:
        """Initialize a track segment.
        
        Args:
            block_id: Unique identifier for the track block.
            length: Length of the segment in meters.
            speed_limit: Speed limit of the segment in m/s.
            grade: Grade percentage (+ is uphill, - is downhill).
            underground: Whether the segment is underground (tunnel).
        """
        # Basic track properties
        self.block_id = block_id
        self.length = length
        self.speed_limit = speed_limit
        self.grade = grade
        self.underground = underground
        
        # Graph connections
        self.connected_segments: List['TrackSegment'] = []
        self.previous_segments: List['TrackSegment'] = []
        
        # Track status
        self.occupied = False
        
        # Failure states
        self.failures: set[TrackFailureType] = set()
        
        # Signal status
        self.signal_state = SignalState.RED
        
        # Station properties
        self.is_station = False
        self.station_name = None
        self.passengers_waiting = 0
        
        # Beacon information
        self.beacon_data = ""
        
    def set_occupancy(self, occupied: bool) -> None:
        """Update block occupancy status.
        
        Args:
            occupied: Whether the block is currently occupied.
        """
        self.occupied = occupied

    def set_signal_state(self, state: SignalState) -> None:
        """Set the signal state for this track segment.
        
        Args:
            state: The new signal state to set.
        """       
        self.signal_state = state

    def set_beacon_data(self, beacon_data: str) -> None:
        """Set beacon data for this track segment.
        
        Args:
            beacon_data: The beacon information to set.
        """
        self.beacon_data = beacon_data
        
    def set_track_failure(self, failure_type: TrackFailureType) -> None:
        """Add a failure condition (activated by Murphy).
        
        Args:
            failure_type: The type of failure to add.
        """
        if failure_type not in self.failures:
            self.failures.add(failure_type)
            self._report_track_failure(failure_type)

    def clear_track_failure(self, failure_type: TrackFailureType) -> None:
        """Clear a failure condition.
        
        Args:
            failure_type: The type of failure to clear.
        """
        if failure_type in self.failures:
            self.failures.remove(failure_type)

    def _report_track_failure(self, failure_type: TrackFailureType) -> None:
        """Report failure to necessary modules.
        
        Args:
            failure_type: The type of failure that occurred.
        """
        #TODO pseudo: log failure event with timestamp
        # report to track controller
        pass
        
class TrackSwitch(TrackSegment):
    """Switch segment that inherits from TrackSegment.
    
    Simple two-position switch that can route trains between two paths.
    Position 0 is straight through, Position 1 is diverging path.
    
    Additional Attributes:
        straight_segment: Segment for straight-through path (position 0).
        diverging_segment: Segment for diverging path (position 1).
        current_position: Current switch position (0 or 1).
    """
    
    def __init__(self, block_id: str, length: int, grade: float) -> None:
        """Initialize a track switch.
        
        Args:
            block_id: Unique identifier for the switch block.
            length: Length of the switch in meters.
            grade: Grade percentage (+ is uphill, - is downhill).
        """
        super().__init__(block_id, length, grade)
        
        # Switch-specific properties
        self.straight_segment: Optional['TrackSegment'] = None
        self.diverging_segment: Optional['TrackSegment'] = None
        self.current_position = 0
        
    def set_switch_paths(self, straight_segment: 'TrackSegment', 
                        diverging_segment: 'TrackSegment') -> None:
        """Set the two possible paths for this switch.
        
        Args:
            straight_segment: Segment for straight-through path.
            diverging_segment: Segment for diverging path.
        """
        #pseudo: self.straight_segment = straight_segment
        #      self.diverging_segment = diverging_segment
        pass
        
    def set_switch_position(self, position: int) -> bool:
        """Set switch to specified position.
        
        Args:
            position: Desired switch position (0 = straight, 1 = diverging).
            
        Returns:
            True if switch was successfully set, False otherwise.
        """
        #pseudo: if position in [0, 1]:
        #          self.current_position = position
        #          return True
        #      else:
        #          return False
        pass
        
    def get_active_segment(self) -> Optional['TrackSegment']:
        """Get the currently active next segment.
        
        Returns:
            The active segment based on current position.
        """
        # psedo:  return self.straight_segment if self.current_position == 0 else self.diverging_segment
        pass
            
    def is_straight(self) -> bool:
        """Check if switch is in straight position.
        
        Returns:
            True if switch is in straight position (0).
        """
        #pseudo: return self.current_position == 0
        pass
        
class LevelCrossing(TrackSegment):
    """Level crossing segment with road traffic gate control.

    Extends TrackSegment with functionality to handle road traffic crossings.
    Gate status is automatically tied to track occupancy.

    Attributes:
        gate_status: Whether the crossing gates are closed (True = closed, False = open).
    """
    
    def __init__(self, block_id: str, length: int, speed_limit: int, grade: float, underground: bool) -> None:
        """Initialize a level crossing segment.
        
        Args:
            block_id: Unique identifier for the crossing block.
            length: Length of the crossing in meters.
            speed_limit: Speed limit through the crossing in m/s.
            grade: Grade percentage (+ is uphill, - is downhill).
            underground: Whether the crossing is underground.
        """
        super().__init__(block_id, length, speed_limit, grade, underground)
        
        # Level crossing specific properties
        self.gate_status = False  # False = open, True = closed
        
    def set_occupancy(self, occupied: bool) -> None:
        """Update block occupancy status and gate status.
        
        Overrides the parent method to tie gate status to occupancy.
        When occupied = True, gates close (gate_status = True).
        When occupied = False, gates open (gate_status = False).
        
        Args:
            occupied: Whether the block is currently occupied.
        """
        # Call parent method
        super().set_occupancy(occupied)
        
        # Set gate status to match occupancy
        self.gate_status = occupied

    def set_gate_status(self, status: bool) -> None:
        """ Update the gate status independantly of the occupaancy.

        Args:
            status: Whether the crossing gates are closed (True = closed, False = open)
        """

        self.gate_status = status

class Station(TrackSegment):
    """Station segment with passenger management capabilities.
    
    Extends TrackSegment with functionality for managing passengers,
    ticket sales, and station-specific operations.
    
    Attributes:
        station_name: Human-readable name of the station.
        passengers_waiting: Current number of passengers waiting.
        passengers_boarded_total: Total passengers boarded in total.
        passengers_exited_total: Total passengers who exited in total.
        tickets_sold_total: Number of tickets sold in total.
        ticket_sales_log: Historical record of ticket sales.
    """
    
    def __init__(self, block_id: str, length: int, speed_limit: int, grade: float, station_name: str, station_side: StationSide) -> None:
        """Initialize a station.
        
        Args:
            block_id: Unique identifier for the station block.
            length: Length of the station segment in meters.
            grade: Grade percentage (+ is uphill, - is downhill).
            station_name: Human-readable name of the station.
            station_side: Side(s) of the platform (left, right, both).
        """
        super().__init__(block_id, length, speed_limit, grade, underground=False)
       
        # Station-specific properties
        self.is_station = True
        self.station_name = station_name
        self.station_side = station_side

        # Passenger management
        self.passengers_waiting = 0
        self.passengers_boarded_total = 0
        self.passengers_exited_total = 0
        self.passenger_rand_range = (1, 20)
        
        # Ticket sales tracking
        self.tickets_sold_total = 0
    
    def sell_tickets(self, count: int=None) -> None:
        """Record ticket sales at the station.
        
        Args:
            count: Number of tickets sold.
            (If no count argument, randomly generates a number between set range.)
        """
        if count is None:
            rng = Random()
            count = rng.randint(self.passenger_rand_range[0], self.passenger_rand_range[1])
        self.tickets_sold_total += count
        self.passengers_waiting += count
        pass
    
    def passengers_boarding(self, trainID: int, count: int=None) -> None:
        """Record passengers boarding. Adds to total number, and passes to the Train Model.
        
        Args:
            trainID: ID of the train that is boarding passengers.
            count: Number of passengers to board.
            (If no count argument, randomly generates a number between set range.)
        """
        if count is None:
            rng = Random()
            count = rng.randint(self.passenger_rand_range[0], self.passenger_rand_range[1])
        self.passengers_boarded_total += count
        self.passengers_waiting = max(0, self.passengers_waiting - count)
        # EVENTUAL pseudo: train_model.board_passengers(trainID, count)
        pass
        
    def passengers_exiting(self, count: int) -> None:
        """Record passengers exiting and add them to the total. Called by the Train Model.
        
        Args:
            count: Number of passengers exiting the train.
       """
        self.passengers_exited_total += count
        pass

class TrackNetwork:
    """Main Track Model class implementing the Model through a graph data structure.
    
    Manages the entire railway network including segments, switches, and stations.
    Provides interfaces for track layout loading, failure injection, and status
    reporting.
    
    Attributes:
        segments: Dictionary mapping block IDs to TrackSegment objects.
        switches: Dictionary mapping switch IDs to TrackSwitch objects.
        stations: Dictionary mapping station IDs to Station objects.
        global_temperature: System-wide environmental temperature.
        heater_threshold: Temperature threshold for heater activation.
        heaters_active: Current status of global track heaters.
        failure_log: Historical record of system failures.
    """
    
    def __init__(self) -> None:
        """Initialize an empty track network."""
        self.segments: Dict[str, TrackSegment] = {}
        self.switches: Dict[str, TrackSwitch] = {}
        self.stations: Dict[str, Station] = {}
        
        # System-wide properties
        self.global_temperature = 20       # Celsius
        self.heater_threshold = 0          # Celsius
        self.heaters_active = False
        
        # Command broadcasting system
        self.active_commands: List[TrainCommand] = []
        self.command_history: List[TrainCommand] = []
        self.current_command_id = 0
        
        # Logging
        self.failure_log: List[Dict] = []
        
    def add_segment(self, segment: TrackSegment) -> None:
        """Add a track segment to the network.
        
        Args:
            segment: The track segment to add to the network.
        """
        # TODO pseudo: self.segments[segment.block_id] = segment
        pass
            
    def connect_segments(self, seg1_id: str, seg2_id: str, 
                        bidirectional: bool = True) -> None:
        """Connect two segments in the graph.
        
        Args:
            seg1_id: ID of the first segment.
            seg2_id: ID of the second segment.
            bidirectional: Whether connection works in both directions.
        """
        # TODO pseudo: find segments by ID and update connected_segments and previous_segments lists
        pass
                
    def load_track_layout(self, layout_file: str) -> None:
        """Load track layout from file.
        
        Args:
            layout_file: Path to the track layout configuration file.
        """
        #TODO pseudo: parse file and create segments, switches, stations, and connections
        # connect segments based on file data
        pass
        
    def set_global_temperature(self, temperature: int) -> None:
        """Set environmental temperature (Murphy interface).
        
        Args:
            temperature: New global temperature in Celsius.
        """
        # TODO pseudo: self.global_temperature = temperature
        #self._manage_heaters()
        pass
        
    def _manage_heaters(self) -> None:
        """Automatically manage track heaters based on global temperature."""
        # TODO pseudo: if self.global_temperature < self.heater_threshold:
        #          self.heaters_active = True
        #      else:
        #          self.heaters_active = False
        pass
                        
    def get_heater_status(self) -> bool:
        """Get current status of global track heaters.
        
        Returns:
            True if heaters are active, False otherwise.
        """
        return self.heaters_active
 
    def set_heater_threshold(self, threshold: int) -> None:
        """Set temperature threshold for heater activation.
        
        Args:
            threshold: Temperature in Celsius below which heaters activate.
        """
        self.heater_threshold = threshold
        self._manage_heaters()
        pass
        
    def broadcast_train_command(self, train_id: int, commanded_speed: int, 
                               authority: int) -> None:
        """Broadcast a command to a specific train through all track segments.
        
        Args:
            train_id: ID of the target train.
            commanded_speed: Speed command for the train in m/s.
            authority: Movement authority for the train in meters.
        """
        # search for existing command to update
        # if found, update commanded_speed and authority
        # else
        # create TrainCommand object
        # add to active_commands and command_history
        pass
        
    def get_active_commands(self) -> List[TrainCommand]:
        """Get all currently active train commands.
        
        Returns:
            List of active command packets that trains can receive.
        """
        # TODO pseudo: return copy of active_commands
        pass
        
    def get_commands_for_train(self, train_id: int) -> List[TrainCommand]:
        """Get all active commands for a specific train.
        
        Args:
            train_id: ID of the train to get commands for.
            
        Returns:
            List of command packets intended for the specified train.
        """
        # TODOpseudo: filter active_commands for train_id
        pass
        
    def clear_train_commands(self, train_id: int) -> None:
        """Clear all active commands for a specific train.
        
        Args:
            train_id: ID of the train to clear commands for.
        """
        # TODO pseudo: remove commands from active_commands for train_id
        pass
            
    def inject_track_failure(self, block_id: int, failure_type: TrackFailureType) -> None:
        """Inject failure for testing (Murphy interface).
        
        Args:
            block_id: ID of the block to inject failure into.
            failure_type: Type of failure to inject.
        """
        # TODO pseudo: find segment by block_id and call set_track_failure
        pass
            
    def get_network_status(self) -> Dict[str, Any]:
        """Get complete network status for Track Builder display.
        
        Returns:
            Dictionary containing comprehensive network status information.
        """
        # TODO pseudo: iterate over all segments and compile status into a dictionary
        pass
        
    def _get_segment_status(self, segment: TrackSegment) -> Dict[str, Any]:
        """Get status information for a single segment.
        
        Args:
            segment: The track segment to get status for.
            
        Returns:
            Dictionary containing segment status information.
        """
        # TODO pseudo: compile segment properties into a dictionary
        pass
            