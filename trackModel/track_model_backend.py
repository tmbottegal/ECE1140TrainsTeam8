"""
Track Model Backend
"""
import csv
import re
import sys
import os
from datetime import datetime
from enum import Enum
from random import Random
from typing import Any, Dict, List, Optional, TYPE_CHECKING

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universal.universal import (
    SignalState, 
    TrainCommand
)
if TYPE_CHECKING:
    from trainModel.train_model_backend import Train


"""
temporary Train class pre-integration
class Train:
    def __init__(self, train_id: int) -> None:

        self.train_id = train_id
        self.network = None
        self.current_segment: Optional['TrackSegment'] = None
        self.segment_displacement: float = 0.0
        if self.current_segment is not None:
           self.current_segment.set_occupancy(True) 

    def get_next_segment(self) -> Optional['TrackSegment']:
        Get the next connected track segment.
        
        Returns:
            The next connected TrackSegment, or None if there is no connection.
        
        if self.current_segment is not None:
            return self.current_segment.get_next_segment()
        return None
    
    def get_previous_segment(self) -> Optional['TrackSegment']:
        Get the previous connected track segment.
        
        Returns:
            The previous connected TrackSegment, or None if there 
                    is no connection.
        
        if self.current_segment is not None:
            return self.current_segment.get_previous_segment()
        return None
    
    def move(self, distance: float) -> bool:
        Move the train along the track by a specified distance.
        
        Args:
            distance: Distance to move in meters.
        
        if self.current_segment is None:
            raise ValueError("Train is not currently on any track segment.")
        
        if distance < 0:
            if self.segment_displacement + distance < 0:
                prev_segment = self.get_previous_segment()   # issue: can't go back more than one segment (not my problem)
                if prev_segment is None:
                    raise ValueError(
                        "Cannot move backwards, no previous segment.")
                if (prev_segment.signal_state == SignalState.RED or 
                        prev_segment.closed):
                    self.segment_displacement = 0
                    return False
                else:
                    self.current_segment.set_occupancy(False)
                    self.current_segment = prev_segment
                    self.current_segment.set_occupancy(True)
                    self.segment_displacement = max(
                        0, (self.segment_displacement + distance + 
                            self.current_segment.length))
                    return True
            else:
                self.segment_displacement += distance
                return True
            
        if distance > 0:
            if (self.segment_displacement + distance > 
                    self.current_segment.length):
                #need to move to next segment
                next_segment = self.get_next_segment()      # issue: can't go back more than one segment (not my problem)
                if next_segment is None:
                    raise ValueError("Cannot move forwards, no next segment.")
                if (next_segment.signal_state == SignalState.RED or 
                        next_segment.closed):
                    self.segment_displacement = self.current_segment.length
                    return False
                else:
                    self.current_segment.set_occupancy(False)
                    self.current_segment = next_segment
                    self.current_segment.set_occupancy(True)
                    self.segment_displacement = min(
                        self.current_segment.length, 
                        (self.segment_displacement + distance - 
                         self.current_segment.length))
                    return True
            else:
                self.segment_displacement += distance
                return True
"""
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

class Direction(Enum):
    """Enumeration of allowed track directions.
    Forward is defined as increasing displacement (towards next segment),
    and Backwards is decreasing displacement (towards previous segment)."""
    FORWARD = "forward"
    BACKWARD = "backward"
    BIDIRECTIONAL = "bidirectional"

class TrackSegment:
    """Base class for all track segments in the railway network.
    
    Represents a single block in the track model with properties for
    occupancy tracking and failure states.
    
    Attributes:
        block_id: Unique identifier for the track block.
        length: Length of the segment in meters.
        grade: Grade percentage.
        speed_limit: Speed limit of the segment in m/s.
        elevation: Cumulative elevation in meters.
        underground: Whether the segment is underground (tunnel).
        direction: Allowed travel direction on this segment.
        connected_segments: List of segments directly reachable from this one.
        previous_segments: List of segments that lead into this one.
        occupied: Whether the block is currently occupied.
        failures: Set of current failure conditions on this block.
        beacon_data: Beacon information for trains entering this block.
        closed: Whether the block is closed for maintenance.
        active_command: Current active TrainCommand for this block.

    """
    
    def __init__(self, block_id: int, length: float, speed_limit: float,
                 grade: float, elevation: float, underground: bool,
                 direction: Direction) -> None:
        """Initialize a track segment.
        
        Args:
            block_id: Unique identifier for the track block.
            length: Length of the segment in meters.
            speed_limit: Speed limit of the segment in m/s.
            grade: Grade percentage (+ is uphill, - is downhill).
            elevation: Cumulative elevation in meters.
            underground: Whether the segment is underground (tunnel).
            direction: Allowed travel direction on this segment.
        """
        # Basic track properties
        self.block_id = block_id
        self.length = length            # meters
        self.speed_limit = speed_limit  # m/s
        self.grade = grade
        self.elevation = elevation      # meters
        self.underground = underground
        self.closed = False
        self.direction = direction
        
        # Graph connections
        self.next_segment: Optional['TrackSegment'] = None
        self.previous_segment: Optional['TrackSegment'] = None
        self.network = None
        
        # Track status
        self.occupied = False
        
        # Failure states
        self.failures: set[TrackFailureType] = set()

        # Beacon and track circuit information
        self.beacon_data = ""
        self.active_command: Optional['TrainCommand'] = None
        
    def set_occupancy(self, occupied: bool) -> None:
        """Update block occupancy status.
        
        Args:
            occupied: Whether the block is currently occupied.
        """
        if TrackFailureType.BROKEN_RAIL in self.failures:
            return
        self.occupied = occupied
        if not occupied:
            self.active_command = None

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
            self._report_track_failure(failure_type, active=True)

        if failure_type == TrackFailureType.BROKEN_RAIL:
            self.occupied = True

    def clear_track_failure(self, failure_type: TrackFailureType) -> None:
        """Clear a failure condition.
        
        Args:
            failure_type: The type of failure to clear.
        """
        if failure_type in self.failures:
            self.failures.remove(failure_type)
            self._report_track_failure(failure_type, active=False)

        if failure_type == TrackFailureType.BROKEN_RAIL:
            self.occupied = False

    def _report_track_failure(self, failure_type: TrackFailureType,
                              active: bool) -> None:
        """Report failure to necessary modules.
        
        Args:
            failure_type: The type of failure that occurred.
            active: Whether the failure is currently active (True) or has
                been repaired (False).
        """
        if self.network is not None:
            self.network.add_failure_log_entry(self.block_id, 
                                               failure_type, active)
        pass

    def get_next_segment(self) -> Optional['TrackSegment']:
        """Get the next connected track segment.
        
        Returns:
            The next connected TrackSegment, or None if there is no connection.
        """
        return self.next_segment
    
    def get_previous_segment(self) -> Optional['TrackSegment']:
        """Get the previous connected track segment.
        
        Returns:
            The previous connected TrackSegment, or None if there 
                    is no connection.
        """
        return self.previous_segment
    
    def broadcast_train_command(self, commanded_speed: int=None,
                                 authority: int=None) -> None:
        """Broadcast a command to any train on this segment.
        
        Args:
            commanded_speed: Speed command for the train in m/s.
            authority: Movement authority for the train in meters.
        """
        if TrackFailureType.TRACK_CIRCUIT_FAILURE in self.failures:
            return

        self.active_command = TrainCommand(commanded_speed, authority)
        for train in self.network.trains.values():
                train.train_command_interrupt(self.block_id)

    def close(self) -> None:
        """Close the block for maintenance."""
        self.closed = True

    def open(self) -> None:
        """Open the block after maintenance."""
        self.closed = False
        
class TrackSwitch(TrackSegment):
    """Switch segment that inherits from TrackSegment.
    
    Simple two-position switch that can route trains between two paths.
    Position 0 is straight through, Position 1 is diverging path.
    
    Additional Attributes:
        straight_segment: Segment for straight-through path (position 0).
        diverging_segment: Segment for diverging path (position 1).
        current_position: Current switch position (0 or 1).
    """

    def __init__(self, block_id: int, length: float, speed_limit: float, 
                 grade: float, elevation: float, underground: bool,
                 direction: Direction) -> None:
        """Initialize a track switch.
        
        Args:
            block_id: Unique identifier for the switch block.
            length: Length of the switch in meters.
            grade: Grade percentage (+ is uphill, - is downhill).
            elevation: Cumulative elevation in meters.
            underground: Whether the switch is underground.
            direction: Allowed travel direction on this segment.

            """
        super().__init__(block_id, length, speed_limit, grade, elevation, underground, direction)
        
        self.straight_segment: Optional['TrackSegment'] = None
        self.diverging_segment: Optional['TrackSegment'] = None
        self.current_position = 0

        self.signal_state = SignalState.RED

    def set_signal_state(self, state: SignalState) -> None:
        """Set the signal state for this track segment.
        
        Args:
            state: The new signal state to set.
        """
        if TrackFailureType.POWER_FAILURE in self.failures:
            return
        self.signal_state = state

    def set_switch_paths(self, straight_segment: 'TrackSegment', 
                        diverging_segment: 'TrackSegment') -> None:
        """Set the two possible paths for this switch.
        
        Args:
            straight_segment: Segment for straight-through path.
            diverging_segment: Segment for diverging path.
        """
        self.straight_segment = straight_segment
        self.diverging_segment = diverging_segment
        self._update_connected_segments()
        
    def set_switch_position(self, position: int) -> None:
        """Set switch to specified position.
        
        Args:
            position: Desired switch position (0 = straight, 1 = diverging).
        """
        if position not in [0, 1]:
            raise ValueError("Invalid switch position. Must be 0 or 1.")
        if TrackFailureType.POWER_FAILURE in self.failures:
            return
        self.current_position = position
        self._update_connected_segments()
        
        
    def _update_connected_segments(self) -> None:
        """Update connected segments based on current switch position."""
        match self.current_position:
            case 0:
                self.next_segment = self.straight_segment
                self.straight_signal_state = SignalState.GREEN
                self.diverging_signal_state = SignalState.RED
                if self.straight_segment is not None:
                    self.straight_segment.previous_segment = self
                if self.diverging_segment is not None:
                    # Remove this switch as previous segment when not selected
                    if self.diverging_segment.previous_segment == self:
                        self.diverging_segment.previous_segment = None

            case 1:
                self.next_segment = self.diverging_segment
                self.straight_signal_state = SignalState.RED
                self.diverging_signal_state = SignalState.GREEN
                if self.diverging_segment is not None:
                    self.diverging_segment.previous_segment = self
                if self.straight_segment is not None:
                    # Remove this switch as previous segment when not selected
                    if self.straight_segment.previous_segment == self:
                        self.straight_segment.previous_segment = None

    def is_straight(self) -> bool:
        """Check if switch is in straight position.
        
        Returns:
            True if switch is in straight position (0).
        """
        return self.current_position == 0
        
class LevelCrossing(TrackSegment):
    """Level crossing segment with road traffic gate control.

    Extends TrackSegment with functionality to handle road traffic crossings.
    Gate status is automatically tied to track occupancy.

    Attributes:
        gate_status: Whether the crossing gates are closed 
                (True = closed, False = open).
    """
    
    def __init__(self, block_id: int, length: float, 
                 speed_limit: float, grade: float, elevation: float, 
                 underground: bool, direction: Direction) -> None:
        """Initialize a level crossing segment.
        
        Args:
            block_id: Unique identifier for the crossing block.
            length: Length of the crossing in meters.
            speed_limit: Speed limit through the crossing in m/s.
            grade: Grade percentage (+ is uphill, - is downhill).
            elevation: Cumulative elevation in meters.
            underground: Whether the crossing is underground.
            direction: Allowed travel direction on this segment.
        """
        super().__init__(block_id, length, speed_limit, grade, elevation, underground, direction)
        
        # Level crossing specific properties
        self.gate_status = False  # False = open, True = closed
        

    def set_gate_status(self, status: bool) -> None:
        """ Update the gate status.

        Args:
            status: Whether the crossing gates are closed 
                    (True = closed, False = open)
        """

        self.gate_status = status

class Station(TrackSegment):
    """Station segment with passenger management capabilities.
    
    Extends TrackSegment with functionality for managing passengers,
    ticket sales, and station-specific operations.
    
    Additional attributes:
        station_name: Human-readable name of the station.
        passengers_waiting: Current number of passengers waiting.
        passengers_boarded_total: Total passengers boarded in total.
        passengers_exited_total: Total passengers who exited in total.
        tickets_sold_total: Number of tickets sold in total.
        ticket_sales_log: Historical record of ticket sales.
    """
    
    def __init__(self, block_id: int, length: float, speed_limit: float,
                 grade: float, elevation: float, underground: bool, 
                 direction: Direction, station_name: str,
                 station_side: StationSide) -> None:
        """Initialize a station.
        
        Args:
            block_id: Unique identifier for the station block.
            length: Length of the station segment in meters.
            grade: Grade percentage (+ is uphill, - is downhill).
            elevation: Cumulative elevation in meters.
            underground: Whether the station is underground.
            direction: Allowed travel direction on this segment.
            station_name: Human-readable name of the station.
            station_side: Side(s) of the platform (left, right, both).
        """
        super().__init__(block_id, length, speed_limit, grade, elevation, underground, direction)

        # Station-specific properties
        self.station_name = station_name
        self.station_side = station_side

        # Passenger management
        self.passengers_waiting = 0
        self.passengers_boarded_total = 0
        self.passengers_exited_total = 0
        self.passenger_rand_range = (1, 20)
        
        # Ticket sales tracking
        self.tickets_sold_total = 0

    def sell_tickets(self, count: Optional[int]=None) -> None:
        """Record ticket sales at the station.
        
        Args:
            count: Number of tickets sold.
            (If no count argument, randomly generates a number
            between set range.)
        """
        if count is not None and count < 0:
            raise ValueError("Ticket sale count cannot be negative.")
        if count is None:
            rng = Random()
            count = rng.randint(self.passenger_rand_range[0], 
                                self.passenger_rand_range[1])
        self.tickets_sold_total += count
        self.passengers_waiting += count
        pass

    def passengers_boarding(self, train_id: int = -1, 
                          count: Optional[int] = None) -> None:
        """Record passengers boarding. Adds to total number, and passes
        to the Train Model.
        
        Args:
            train_id: ID of the train that is boarding passengers.
            count: Number of passengers to board.
            (If no count argument, randomly generates a number
            between set range.)
        """
        if train_id is not None and train_id not in self.network.trains:
            raise ValueError(f"Train ID {train_id} not found in network.")
        if count is not None and count > self.passengers_waiting:
            raise ValueError("Cannot board more passengers than are waiting.")
        if count is not None and count < 0:
            raise ValueError("Passenger boarding count cannot be negative.")
        if count is None:
            rng = Random()
            if self.passengers_waiting > 0:
                count = rng.randint(self.passenger_rand_range[0], 
                                    max(self.passenger_rand_range[0], 
                                        min(self.passenger_rand_range[1], 
                                            self.passengers_waiting)))
            else:
                count = 0
        self.passengers_boarded_total += count
        self.passengers_waiting = max(0, self.passengers_waiting - count)
        train = self.network.trains.get(train_id)
        if train is not None:
            train.passengers_boarding(count)
        pass
        
    def passengers_exiting(self, count: int) -> None:
        """Record passengers exiting and add them to the total.
        Called by the Train Model.
        
        Args:
            count: Number of passengers exiting the train.
       """
        if count < 0:
            raise ValueError("Passenger exit count cannot be negative.")
        self.passengers_exited_total += count
        pass

    def get_throughput(self) -> List[int]:
        """Get passenger throughput statistics.
        
        Returns:
            List containing total boarded and total exited passengers.
        """
        return [self.tickets_sold_total, self.passengers_exited_total]

class TrackNetwork:
    """Main Track Model class implementing the Model through a graph
    data structure.
    
    Manages the entire network including segments, switches, and stations.
    Provides interfaces for track layout loading, failure injection, and status reporting.
    
    Attributes:
        segments: Dictionary of TrackSegment objects.
        trains: Dictionary of Train objects.
        line_name: Name of the line.
        environmental_temperature: System-wide environmental temperature.
        heater_threshold: Temperature threshold for heater activation.
        heaters_active: Current status of global track heaters.
        active_commands: List of currently active train commands.
        failure_log: Historical record of system failures.
    """
    
    def __init__(self) -> None:
        """Initialize an empty track network."""
        self.segments: Dict[TrackSegment] = {}
        # EVENTUAL: import train class from train model
        self.trains: Dict['Train'] = {}
        # System-wide properties
        self.line_name = ""
        self.time = datetime(2000,1,1,0,0,0)
        self.environmental_temperature = 20       # Celsius
        self.rail_temperature = self.environmental_temperature
        self.heater_threshold = 0                 # Celsius
        self.heaters_active = False
        
        # Logging
        self.failure_log: List[Dict] = []
        
    def add_segment(self, segment: TrackSegment) -> None:
        """Add a track segment to the network.
        
        Args:
            segment: The track segment to add to the network.
        """
        block_id = segment.block_id
        if block_id in self.segments:
            raise ValueError(f"Block ID {block_id} already exists in network.")
        segment.network = self
        self.segments[segment.block_id] = segment
        pass

    def connect_segments(self, seg1_block_id: int, seg2_block_id: int,
                         bidirectional: bool = False,
                         diverging_seg_block_id: int = None) -> None:
        """Connect two segments in the graph.
        
        Args:
            seg1_block_id: ID of the first segment.
            seg2_block_id: ID of the second segment.
            bidirectional: Whether connection works in both directions.
            diverging_seg_block_id: ID of diverging segment if connecting
                a switch.
        """

        segment1 = self.segments.get(seg1_block_id)
        segment2 = self.segments.get(seg2_block_id)
        diverging_segment = (
            self.segments.get(diverging_seg_block_id)
            if diverging_seg_block_id else None
        )

        if ((segment1 is None and segment2 is not None) or
                (segment1 is not None and segment2 is None)):
            raise ValueError(
                f"One of the segment IDs ({seg1_block_id}, "
                f"{seg2_block_id}) not found in track network."
            )
        if segment1 is None and segment2 is None:
            raise ValueError("Both segment IDs not found in track network.")
        
        if isinstance(segment1, TrackSwitch):
            if diverging_segment is None:
                raise ValueError(
                    "Diverging segment must be provided for switch connections."
                )
            segment1.set_switch_paths(segment2, diverging_segment)
            if bidirectional:
                segment2.previous_segment = segment1
                diverging_segment.previous_segment = segment1
            else:
                segment2.previous_segment = None
                diverging_segment.previous_segment = None


        else:
            if diverging_segment is not None:
                raise ValueError(
                    "Diverging segment should only be provided when "
                    "connecting a switch."
                )
            segment1.next_segment = segment2
            if bidirectional:
                segment2.previous_segment = segment1
            else:
                segment2.previous_segment = None

    def _set_connections(self, block_id: int, previous_id: int, 
                         next_id: int = None, straight_id: int = None, 
                         diverging_id: int = None) -> None:
        """Set connections between track segments.

        Args:
            block_id: ID of the segment being manipulated.
            previous_id: ID of the previous segment.
            next_id: ID of the next segment.
            straight_id: ID of the straight segment (if applicable).
            diverging_id: ID of the diverging segment (if applicable).
        """
        manipulated_segment = self.segments.get(block_id)
        if manipulated_segment is None:
            raise ValueError(
                f"Block ID {block_id} not found when setting connections.")
            
        previous_segment = (
            self.segments.get(previous_id) if previous_id is not None 
            else None)
        next_segment = (
            self.segments.get(next_id) if next_id is not None else None)
        straight_segment = (
            self.segments.get(straight_id) if straight_id is not None 
            else None)
        diverging_segment = (
            self.segments.get(diverging_id) if diverging_id is not None 
            else None)

        manipulated_segment.previous_segment = previous_segment
        if isinstance(manipulated_segment, TrackSwitch):
            manipulated_segment.straight_segment = straight_segment
            manipulated_segment.diverging_segment = diverging_segment
            manipulated_segment._update_connected_segments()
        else:
            manipulated_segment.next_segment = next_segment

    #TODO: #104 improve error messages to be more specific about required formatting
    def load_track_layout(self, layout_file: str) -> None: 
        """Load track layout from file.
        
        Args:
            layout_file: Path to the track layout configuration file.
        """
        print("[TrackNetwork] Loading track layout from file:", layout_file)
        self.line_name = os.path.splitext(os.path.basename(layout_file))[0]

        # First pass to create segments
        with open(layout_file, mode='r') as file:
            csvFile = csv.DictReader(file)
            current_line = 0
            for lines in csvFile:
                if not lines["Type"].strip() and not lines["block_id"].strip():
                    current_line += 1
                    continue
                if lines["block_id"] in self.segments:
                    raise ValueError(
                        f"Block ID {lines['block_id']} already exists in "
                        "network.")
                if ("Type" not in lines or 
                        not re.match("^[a-zA-Z]+$", lines["Type"])):
                    raise ValueError(
                        f"Invalid 'Type' field in layout file at row "
                        f"{current_line}.")
                if ("block_id" not in lines or 
                        not re.match("^[0-9]+$", lines["block_id"])):
                    raise ValueError(
                        f"Invalid 'block_id' field in layout file at row "
                        f"{current_line}.")
                if ("length" not in lines or 
                        not re.match("^[0-9.-]+$", lines["length"])):
                    raise ValueError(
                        f"Invalid 'length' field in layout file at row "
                        f"{current_line}.")
                if ("speed_limit" not in lines or 
                        not re.match("^[0-9.-]+$", lines["speed_limit"])):
                    raise ValueError(
                        f"Invalid 'speed_limit' field in layout file at row "
                        f"{current_line}.")
                if ("grade" not in lines or 
                        not re.match("^[0-9.-]+$", lines["grade"])):
                    raise ValueError(
                        f"Invalid 'grade' field in layout file at row "
                        f"{current_line}.")
                if ("elevation" not in lines or 
                        not re.match("^[0-9.-]+$", lines["elevation"])):
                    raise ValueError(
                        f"Invalid 'elevation' field in layout file at row "
                        f"{current_line}.")
                if ("underground" not in lines or 
                        not re.match("^(TRUE|FALSE|true|false)$", 
                                   lines["underground"])):
                
                    raise ValueError(
                        f"Invalid 'underground' field in layout file at row "
                        f"{current_line}.")
                if ("direction" not in lines or 
                        not re.match("^(FORWARD|BACKWARD|BIDIRECTIONAL)$", 
                                   lines["direction"], re.IGNORECASE)):
                    raise ValueError(
                        f"Invalid 'direction' field in layout file at row "
                        f"{current_line}.")

                match lines["Type"]:
                    case "TrackSegment":
                        segment = TrackSegment(
                            block_id=int(lines["block_id"]),
                            length=float(lines["length"]),
                            speed_limit=float(lines["speed_limit"]),
                            grade=float(lines["grade"]),
                            elevation=float(lines["elevation"]),
                            underground=lines["underground"].lower() == "true",
                            direction=Direction(lines["direction"].lower())
                        )
                        if "beacon_data" in lines and lines["beacon_data"].strip():
                            segment.set_beacon_data(lines["beacon_data"])
                        self.add_segment(segment)
                    case "TrackSwitch":
                        switch = TrackSwitch(
                            block_id=int(lines["block_id"]),
                            length=float(lines["length"]),
                            speed_limit=float(lines["speed_limit"]),
                            grade=float(lines["grade"]),
                            elevation=float(lines["elevation"]),
                            underground=lines["underground"].lower() == "true",
                            direction=Direction(lines["direction"].lower())
                        )
                        if "beacon_data" in lines and lines["beacon_data"].strip():
                            switch.set_beacon_data(lines["beacon_data"])
                        self.add_segment(switch)
                    case "LevelCrossing":
                        crossing = LevelCrossing(
                            block_id=int(lines["block_id"]),
                            length=float(lines["length"]),
                            speed_limit=float(lines["speed_limit"]),
                            grade=float(lines["grade"]),
                            elevation=float(lines["elevation"]),
                            underground=lines["underground"].lower() == "true",
                            direction=Direction(lines["direction"].lower())
                        )
                        if "beacon_data" in lines and lines["beacon_data"].strip():
                            crossing.set_beacon_data(lines["beacon_data"])
                        self.add_segment(crossing)
                    case "Station":
                        if ("station_name" not in lines or 
                                not re.match(r"^[\w\s\.\'\-\u00C0-\u017F]+$", 
                                           lines["station_name"])):
                            raise ValueError(
                                f"Invalid 'station_name' field in layout "
                                f"file at row {current_line}.")
                        if ("station_side" not in lines or 
                                not re.match("^(left|right|both)$", 
                                           lines["station_side"], 
                                           re.IGNORECASE)):
                            raise ValueError(
                                f"Invalid 'station_side' field in layout "
                                f"file at row {current_line}.")
                        station = Station(
                            block_id=int(lines["block_id"]),
                            length=float(lines["length"]),
                            speed_limit=float(lines["speed_limit"]),
                            grade=float(lines["grade"]),
                            elevation=float(lines["elevation"]),
                            underground=lines["underground"].lower() == "true",
                            direction=Direction(lines["direction"].lower()),
                            station_name=lines["station_name"],
                            station_side=StationSide(
                                lines["station_side"].lower()))
                        if "beacon_data" in lines and lines["beacon_data"].strip():
                            station.set_beacon_data(lines["beacon_data"])
                        self.add_segment(station)
                    case _:
                        raise ValueError(
                            f"Unknown segment type {lines['Type']} at row "
                            f"{current_line}.")
                current_line += 1

        # Second pass to set connections
        current_line = 0
        with open(layout_file, mode='r') as file:
            csvFile = csv.DictReader(file)
            for lines in csvFile:
                if not lines["Type"].strip() and not lines["block_id"].strip():
                    current_line += 1
                    continue
                if (lines["previous_segment"] is not None and 
                        not re.match("(^[0-9]+$|^$)", 
                                   lines["previous_segment"])):
                    raise ValueError(
                        f"Invalid 'previous_segment' field in layout file "
                        f"at row {current_line}.")
                if (lines["next_segment"] is not None and 
                        not re.match("(^[0-9]+$|^$)", lines["next_segment"])):
                    raise ValueError(
                        f"Invalid 'next_segment' field in layout file at "
                        f"row {current_line}.")
                if (lines["straight_segment"] is not None and 
                        not re.match("(^[0-9]+$|^$)", 
                                   lines["straight_segment"])):
                    raise ValueError(
                        f"Invalid 'straight_segment' field in layout file "
                        f"at row {current_line}.")
                if (lines["diverging_segment"] is not None and 
                        not re.match("(^[0-9]+$|^$)", 
                                   lines["diverging_segment"])):
                    raise ValueError(
                        f"Invalid 'diverging_segment' field in layout file "
                        f"at row {current_line}.")
                match lines["Type"]:
                    case "TrackSegment" | "LevelCrossing" | "Station":
                        self._set_connections(
                            int(lines["block_id"]), 
                            (int(lines["previous_segment"]) 
                             if lines["previous_segment"] else None), 
                            (int(lines["next_segment"]) 
                             if lines["next_segment"] else None), 
                            None, 
                            None)
                    case "TrackSwitch":
                        self._set_connections(
                            int(lines["block_id"]), 
                            (int(lines["previous_segment"]) 
                             if lines["previous_segment"] else None), 
                            None, 
                            (int(lines["straight_segment"]) 
                             if lines["straight_segment"] else None), 
                            (int(lines["diverging_segment"]) 
                             if lines["diverging_segment"] else None))
                    case _:
                        raise ValueError(
                            f"Unknown segment type {lines['Type']} at row "
                            f"{current_line}.")
                current_line += 1

        for segment in self.segments.values():
            if isinstance(segment, TrackSwitch):
                segment._update_connected_segments()
        pass

    def set_environmental_temperature(self, temperature: int) -> None:
        """Set environmental temperature (Murphy interface).
        
        Args:
            temperature: New global temperature in Celsius.
        """
        self.environmental_temperature = temperature
        self._manage_heaters()
        pass
        
    def set_heater_threshold(self, threshold: int) -> None:
        """Set temperature threshold for heater activation.

        Args:
            threshold: Temperature in Celsius below which heaters activate.
        """
        self.heater_threshold = threshold
        self._manage_heaters()
        pass

    def _manage_heaters(self) -> None:
        """Automatically manage track heaters based on rail temperature."""
        if self.rail_temperature < self.heater_threshold:
            self.heaters_active = True
        else:
            self.heaters_active = False

    def temperature_sim(self) -> None:
        """Simulate temperature changes over time."""
        if self.heaters_active:
            self.rail_temperature += 2
            self._manage_heaters()

        if self.rail_temperature > self.environmental_temperature:
            self.rail_temperature = max(self.rail_temperature - 1, self.environmental_temperature)
            self._manage_heaters()
        else:
            self.rail_temperature = min(self.rail_temperature + 1, self.environmental_temperature)
            self._manage_heaters()
        
                        
    def get_heater_status(self) -> bool:
        """Get current status of global track heaters.
        
        Returns:
            True if heaters are active, False otherwise.
        """
        return self.heaters_active
 
    def broadcast_train_command(self, block_id: int, commanded_speed: int, 
                               authority: int) -> None:
        """Broadcast a command to a specific train through all track segments.
        
        Args:
            train_id: ID of the target train.
            commanded_speed: Speed command for the train in m/s.
            authority: Movement authority for the train in meters.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        segment.broadcast_train_command(commanded_speed, authority)
        pass

    
    def set_occupancy(self, block_id: int, occupied: bool) -> None:
        """Set occupancy status for a specific block.
        
        Args:
            block_id: ID of the block to set occupancy for.
            occupied: Whether the block is currently occupied.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        segment.set_occupancy(occupied)
        pass
    
    def set_signal_state(self, block_id: int,
                         signal_state: SignalState) -> None:
        """Set the signal state for a specific block.
        
        Args:
            block_id: ID of the block to set signal for.
            signal_state: The new signal state to set.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        if not isinstance(segment, TrackSwitch):
            raise ValueError(f"Block ID {block_id} is not a switch.")
        segment.set_signal_state(signal_state)
        pass

    def set_beacon_data(self, block_id: int, beacon_data: str) -> None:
        """Set beacon data for a specific block.
        
        Args:
            block_id: ID of the block to set beacon data for.
            beacon_data: The beacon information to set.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        segment.set_beacon_data(beacon_data)
        pass

    def set_track_failure(self, block_id: int,
                          failure_type: TrackFailureType) -> None:
        """Inject failure for testing (Murphy interface).

        Args:
            block_id: ID of the block to inject failure into.
            failure_type: Type of failure to inject.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        segment.set_track_failure(failure_type)
        pass

    def clear_track_failure(self, block_id: int,
                            failure_type: TrackFailureType) -> None:
        """Repair a specific failure on a block.
        
        Args:
            block_id: ID of the block to repair.
            failure_type: Type of failure to repair.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        segment.clear_track_failure(failure_type)
        pass
    
    def add_failure_log_entry(self, block_id: int,
                              failure_type: TrackFailureType,
                              active: bool) -> None:
        """Add an entry to the failure log.
        
        Args:
            block_id: ID of the block where the failure occurred.
            failure_type: Type of failure that occurred.
            active: Whether the failure is currently active (True) or has
                been repaired (False).
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        
        entry = {
            "timestamp": self.time,
            "block_id": block_id,
            "failure_type": failure_type,
            "active": active
        }
        self.failure_log.append(entry)

    def get_failure_log(self) -> List[Dict[str, Any]]:
        """Get the complete failure log.
        
        Returns:
            List of failure log entries.
        """
        return self.failure_log
    
    def get_next_segment(self, block_id: int) -> Optional[TrackSegment]:
        """Get the next connected segment for a specific block.
        
        Args:
            block_id: ID of the block to get the next segment for.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        return segment.next_segment
    
    def get_previous_segment(self, block_id: int) -> Optional[TrackSegment]:
        """Get the previous connected segment for a specific block.
        
        Args:
            block_id: ID of the block to get the previous segment for.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        return segment.previous_segment

    def close_block(self, block_id: int) -> None:
        """Close a specific block for maintenance.
        
        Args:
            block_id: ID of the block to close.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        segment.close()
        pass

    def open_block(self, block_id: int) -> None:
        """Open a specific block after maintenance.
        
        Args:
            block_id: ID of the block to open.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        segment.open()
        pass

    def set_gate_status(self, block_id: int, status: bool) -> None:
        """ Set the gate status of a specific level crossing.

        Args:
            block_id: ID of the level crossing block to set gate status for.
            status: Whether the crossing gates are closed 
                    (True = closed, False = open)
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        if not isinstance(segment, LevelCrossing):
            raise ValueError(f"Block ID {block_id} is not a level crossing.")
        segment.set_gate_status(status)
        pass

    def sell_tickets(self, block_id: int, count: int=None) -> None:
        """Sell tickets at a specific station.
        
        Args:
            block_id: ID of the station block to sell tickets at.
            count: Number of tickets to sell.
            (If no count argument, randomly generates a number
            between set range.)
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        if not isinstance(segment, Station):
            raise ValueError(f"Block ID {block_id} is not a station.")
        segment.sell_tickets(count)
        pass

    def passengers_boarding(self, block_id: int, train_id: int = -1, 
                          count: int = None) -> None:
        """Record passengers boarding at a specific station.
        
        Args:
            block_id: ID of the station block where passengers are boarding.
            train_id: ID of the train that is boarding passengers.
            count: Number of passengers to board.
            (If no count argument, randomly generates a number
            between set range.)
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        if not isinstance(segment, Station):
            raise ValueError(f"Block ID {block_id} is not a station.")
        segment.passengers_boarding(train_id, count)
        # TODO: remove -1 count when train model is integrated
        pass

    def get_throughput(self, block_id: int) -> List[int]:
        """Get passenger throughput statistics for a specific block.

        Args:
            block_id: ID of the block to get throughput for.

        Returns:
            List containing total tickets sold and total passengers exited.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        if not isinstance(segment, Station):
            raise ValueError(f"Block ID {block_id} is not a station.")
        return segment.get_throughput()

    def passengers_exiting(self, block_id: int, count: int) -> None:
        """Record passengers exiting at a specific station.
        
        Args:
            block_id: ID of the station block where passengers are exiting.
            count: Number of passengers exiting the train.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        if not isinstance(segment, Station):
            raise ValueError(f"Block ID {block_id} is not a station.")
        segment.passengers_exiting(count)
        pass

    
    def set_switch_position(self, block_id: int, position: int) -> None:
        """Set the position of a specific track switch.
        
        Args:
            block_id: ID of the switch block to set position for.
            position: Desired switch position (0 = straight, 1 = diverging).
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        if not isinstance(segment, TrackSwitch):
            raise ValueError(f"Block ID {block_id} is not a switch.")
        segment.set_switch_position(position)
        pass
    
    def set_signal_state(self, block_id: int,
                         signal_state: SignalState) -> None:
        """Set the signal state for a specific block.
        Args:
            block_id: ID of the block to set signal for.
            signal_state: The new signal state to set.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        segment.set_signal_state(signal_state)
        pass

    def set_occupancy(self, block_id: int, occupied: bool) -> None:
        """Set occupancy status for a specific block.
        
        Args:
            block_id: ID of the block to set occupancy for.
            occupied: Whether the block is currently occupied.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        segment.set_occupancy(occupied)
        pass

    def set_time(self, new_time: datetime) -> None:
        """Set the current time in the track network.
        Args:
            new_time: The new time to set.
        """
        self.time = new_time
        self.temperature_sim()

    def manual_set_time(self, year: int, month: int, day: int,
                        hour: int, minute: int, second: int) -> None:
        """Manually set the current time in the track network.
        
        Args:
            year: Year component of the new time.
            month: Month component of the new time.
            day: Day component of the new time.
            hour: Hour component of the new time.
            minute: Minute component of the new time.
            second: Second component of the new time.
        """
        self.time = datetime(year, month, day, hour, minute, second)
        self.temperature_sim()
        pass
    
    def get_segment_status(self, block_id: int) -> Dict[str, Any]:
        """Get status information for a single segment.
        
        Args:
            block_id: The ID of the track segment to get status for.
        Returns:
            Dictionary containing segment status information.
        """
        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        
        segment_status = {
            "block_id": segment.block_id,
            "type": type(segment).__name__,
            "length": segment.length,
            "speed_limit": segment.speed_limit,
            "grade": segment.grade,
            "elevation": segment.elevation,
            "underground": segment.underground,
            "direction": segment.direction,
            "occupied": segment.occupied,
            "failures": list(segment.failures),
            "beacon_data": segment.beacon_data,
            "active_command": segment.active_command,
            "closed": segment.closed,
            "next_segment": (
                segment.next_segment.block_id
                if segment.next_segment else None
            ),
            "previous_segment": (
                segment.previous_segment.block_id
                if segment.previous_segment else None
            ),
        }

        if isinstance(segment, LevelCrossing):
            segment_status["gate_status"] = segment.gate_status

        if isinstance(segment, Station):
            segment_status["station_name"] = segment.station_name
            segment_status["station_side"] = segment.station_side
            segment_status["passengers_waiting"] = segment.passengers_waiting
            segment_status["passengers_boarded_total"] = (
                segment.passengers_boarded_total
            )
            segment_status["passengers_exited_total"] = (
                segment.passengers_exited_total
            )
            segment_status["tickets_sold_total"] = segment.tickets_sold_total
        
        if isinstance(segment, TrackSwitch):
            segment_status["signal_state"] = segment.signal_state
            segment_status["current_position"] = segment.current_position
            segment_status["straight_segment"] = (
                segment.straight_segment.block_id
                if segment.straight_segment else None
            )
            segment_status["diverging_segment"] = (
                segment.diverging_segment.block_id
                if segment.diverging_segment else None
            )

        return segment_status
    
    def get_train_status(self, train_id: int) -> Dict[str, Any]:
        """Get status information for a specific train.
        
        Args:
            train_id: The ID of the train to get status for.
        Returns:
            Dictionary containing train status information.
        """
        train = self.trains.get(train_id)
        if train is None:
            raise ValueError(f"Train ID {train_id} not found in track network.")
        
        train_status = {
            "train_id": train.train_id,
            "current_segment": (
                train.current_segment.block_id
                if train.current_segment else None
            ),
            "segment_displacement": train.segment_displacement_m,
        }
        return train_status

    
    def _get_wayside_segment_status(self, block_id: int) -> Dict[str, Any]:
        """Get status information for a single track segment relevant to wayside operations.
        
        Args:
            block_id: The ID of the track segment to get status for.
        Returns:
            Dictionary containing status information relevant to wayside operations.
        """

        segment = self.segments.get(block_id)
        if segment is None:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        
        segment_status = {
            "block_id": segment.block_id,
            "type": type(segment).__name__,
            "length": segment.length,
            "speed_limit": segment.speed_limit,
            "occupied": segment.occupied,
            "beacon_data": segment.beacon_data,
            "active_command": segment.active_command,
            "closed": segment.closed,
            "next_segment": (
                segment.next_segment.block_id
                if segment.next_segment else None
            ),
            "previous_segment": (
                segment.previous_segment.block_id
                if segment.previous_segment else None
            ),
        }

        if isinstance(segment, LevelCrossing):
            segment_status["gate_status"] = segment.gate_status
        
        if isinstance(segment, TrackSwitch):
            segment_status["current_position"] = segment.current_position
            segment_status["signal_state"] = segment.signal_state

        return segment_status

    def get_wayside_status(self) -> Dict[str, Any]:
        """Get complete wayside status.

        Returns:
            Dictionary containing wayside-relevant status information.
        """
        wayside_status = {
            "segments": {
                block_id: self._get_wayside_segment_status(block_id)
                for block_id in self.segments
            },
            "line_name": self.line_name,
            "time": self.time,
        }
        return wayside_status
    
    def get_network_status(self) -> Dict[str, Any]:
        """Get complete network status.

        Returns:
            Dictionary containing comprehensive network status information.
        """

        current_time = self.time if self.time is not None else datetime(2000, 1, 1, 0, 0, 0)

        network_status = {
            "segments": {
                block_id: self.get_segment_status(block_id)
                for block_id in self.segments
            },
            "trains": {
                train_id: self.get_train_status(train_id)
                for train_id in self.trains
            },
            "line_name": self.line_name,
            "time": current_time,
            "environmental_temperature": self.environmental_temperature,
            "rail_temperature": self.rail_temperature,
            "heater_threshold": self.heater_threshold,
            "heaters_active": self.heaters_active,
            "failure_log": self.get_failure_log()
        }
        return network_status
    
    def add_train(self, train: 'Train') -> None:
        """Add a train to the network for tracking purposes.
        
        Args:
            train: The Train object to add to the network.
        """
        if train.train_id in self.trains:
            raise ValueError(
                f"Train ID {train.train_id} already exists in network.")
        self.trains[train.train_id] = train
        train.network = self
        pass

    def connect_train(self, train_id: int, block_id: int, 
                      displacement: float) -> None:
        """Add a train to the network for tracking purposes.
        
        Args:
            train_id: ID of the train to add.
            block_id: ID of the block the train is currently on.
            displacement: The displacement of the train within the block.
        """
        if block_id not in self.segments:
            raise ValueError(f"Block ID {block_id} not found in track network.")
        
        train = self.trains.get(train_id)
        if train is None:
            raise ValueError(f"Train ID {train_id} not found in track network.")
        train.current_segment = self.segments[block_id]
        train.segment_displacement_m = displacement
        train.network = self
        print(f"[TrackNetwork] Connected Train {train_id} to Block {block_id} at displacement {displacement} m on network {self.line_name}.")
        train.current_segment.set_occupancy(True)
        pass

    def clear_trains(self) -> None:
        """Remove all trains from the network."""
        self.trains.clear()
        pass

    def gti(self, train_id: int) -> None:    #DEBUG
        train = self.trains.get(train_id)
        if train is None:
            raise ValueError(f"Train ID {train_id} not found in track network.")
        print(f"[TrackNetwork] Train Info: Train ID: {train.train_id}, Current Segment: {train.current_segment.block_id if train.current_segment else 'None'}, Displacement: {train.segment_displacement_m} m")
        pass

    def mto(self, train_id: int, distance: float) -> None:   #DEBUG
        """Move a train by a specified distance, overriding normal movement logic.
        
        Args:
            train_id: ID of the train to move.
            distance: Distance in meters to move the train.
        """
        train = self.trains.get(train_id)
        if train is None:
            raise ValueError(f"Train ID {train_id} not found in track network.")
        success = train.mto(distance)
        print(f"[TrackNetwork] Moved Train {train_id} by {distance} m: {'Success' if success else 'Blocked'}.")
        pass