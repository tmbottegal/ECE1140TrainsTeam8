"""CTC Backend — Centralized Traffic Control system.

This module unifies:
    • TrackModel (physical simulation)
    • Software TrackController (wayside logic)
    • Hardware TrackController (PLC-based wayside logic)
    • Global simulation clock
    • Schedule management
    • UI block mirror construction

The CTC drives all modules in a synchronous tick-based simulation.
It computes safe speed/authority, dispatches trains, manages dwell,
updates throughput, and processes wayside feedback.

This file is formatted per Google Python Style Guide.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import csv
from datetime import datetime, timedelta

# Extend import path so CTC can load sibling packages
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ------------------------------------------------------------
# Constants
# ------------------------------------------------------------
BLOCK_LEN_M = 50.0
BLOCK_TRAVEL_TIME_S = 7.0  # seconds to traverse one block
LINE_SPEED_LIMIT_MPS = BLOCK_LEN_M / BLOCK_TRAVEL_TIME_S  # ≈ 7.14 m/s

# ------------------------------------------------------------
# Core dependencies
# ------------------------------------------------------------
from universal.global_clock import clock

# Track Model
from trackModel.track_model_backend import TrackNetwork, TrackSwitch

# Train
from trainModel.train_model_backend import Train

# Track Controllers
from trackControllerSW.track_controller_backend import TrackControllerBackend
from trackControllerHW.track_controller_hw_backend import (
    HardwareTrackControllerBackend,
)


# ------------------------------------------------------------
# Block dataclass + lightweight mutator methods
# ------------------------------------------------------------
@dataclass
class Block:
    line: str
    section: str
    block_id: int
    status: str
    station: str
    station_side: str
    switch: str
    light: str
    crossing: bool
    speed_limit: float
    length_m: float     
    speed_limit_mps: float  


    # --- helper methods for UI updates ---
    def set_occupancy(self, occupied: bool):
        """Set the occupancy status for this block.

        Args:
            is_occupied: True if the block is occupied by a train, False otherwise.
        """
        self.status = "occupied" if occupied else "unoccupied"

    def set_signal_state(self, state: str):
        """Set the signal (light) indication for this block.

        Args:
            signal_state: The signal value (e.g., 'RED', 'GREEN').
        """
        self.light = state

    def set_switch_position(self, position: str):
        """Set the switch position text for this block.

        Args:
            switch_position: The textual switch position (e.g., 'STRAIGHT', 'DIVERGING').
        """
        self.switch = position

    def set_crossing_status(self, active: bool):
        """Set whether the level crossing is active.

        Args:
            is_active: True if the crossing is activated, False otherwise.
        """
        self.crossing = bool(active)


class ScheduleManager:
    """Manages dispatcher-uploaded train schedules.

    This class stores raw schedule rows for UI display and also manages
    expanded multi-stop route data used by the CTC for dispatching.
    It does not compute routing, authority, or train movement — it is
    purely a storage and parsing layer.
    """

    def __init__(self):
        """Initialize empty schedule and routing structures.

        Attributes:
            entries: List of flat schedule rows for UI display. Each entry is a
                dict with keys: train_id, destination, arrival_time, line.
            routes: Mapping of train_id → list of route-leg dictionaries.
            current_leg: Mapping of train_id → index of the currently active leg.
        """
        self.entries = []
        self.routes = {}          # train_id → list of legs
        self.current_leg = {}     # train_id → current leg index


    def add_schedule_entry(self, train_id: str, destination: str, arrival_time: str, line: str = "Green Line"):
        """Add a single schedule row for UI display.

        This does not compute routing or dispatch logic; it simply stores
        the data the dispatcher entered.

        Args:
            train_id: Identifier for the train (e.g., "T1").
            destination: The destination station name.
            arrival_time: The scheduled arrival time as a string (e.g., "14:35").
            line: Name of the line this entry applies to.
        """
        entry = {
            "train_id": train_id,
            "destination": destination,
            "arrival_time": arrival_time,
            "line": line
        }
        self.entries.append(entry)

    
    def load_from_csv(self, filepath: str):
        """Load a basic 3-column CSV schedule file.

        This method reads dispatcher-uploaded CSV files containing individual
        schedule rows (train_id, destination, arrival_time). It does not handle
        multi-stop route CSVs.

        Args:
            filepath: Path to the CSV file on disk.

        Raises:
            Prints an error message if the file cannot be read.
        """
        try:
            import csv
            with open(filepath, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Expect CSV columns: train_id, destination, arrival_time
                    self.add_schedule_entry(
                        row.get("train_id", "").strip(),
                        row.get("destination", "").strip(),
                        row.get("arrival_time", "").strip()
                    )
            print(f"[Schedule] Loaded schedule from {filepath}")
        except Exception as e:
            print(f"[Schedule] Failed to load CSV: {e}")


    def load_route_csv(self, filepath: str, ctc_backend):
        """Load a multi-stop route CSV and schedule all legs.

        This method processes a special CSV format used for full route
        schedules (e.g., Route A/B/C), computes dispatch times for each leg,
        and stores them for later train dispatching by the CTC.

        Args:
            filepath: Path to the route CSV file.
            ctc_backend: The TrackState instance used to resolve blocks,
                compute travel times, compute suggestions, and schedule dispatches.

        Behavior:
            - Reads station names and scheduled arrival times.
            - Converts arrival times into simulation timestamps.
            - Computes travel and departure times for each stop-to-stop leg.
            - Schedules the first dispatch immediately through the CTC.
            - Stores remaining legs in self.routes for automatic movement.
            - Adds UI-visible entries to self.entries.
        """

        
        print(f"[Schedule] Loading route schedule: {filepath}")

        # ----- Read CSV -----
        with open(filepath, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if len(rows) < 2:
            print("[Schedule] ERROR: CSV must contain header + times row.")
            return

        header = rows[0]
        times = rows[1]

        route_name = header[0].strip()
        print(f"[Schedule] Route name: {route_name}")

        TRAIN_NAMES = {
            "Route A": "Avocet",
            "Route B": "Bobolink",
            "Route C": "Cardinal"
        }
        train_id = TRAIN_NAMES.get(route_name, route_name.replace(" ", ""))
        print(f"[Schedule] Train assigned → {train_id}")

        # ----- Stations + times -----
        stations = header[1:]       # e.g. ["Yard","Glenbury","Dormont",...]
        arrival_times = times[1:]   # ["7:00 AM", "7:02 AM", ...]

        if len(stations) != len(arrival_times):
            print("[Schedule] ERROR: Station count must match arrival times.")
            return

        # ----- Convert arrival times into datetime objects -----
        sim_now = clock.get_time()
        midnight = sim_now.replace(hour=0, minute=0, second=0, microsecond=0)

        parsed_arrivals = []
        for t in arrival_times:
            t_dt = datetime.strptime(t.strip(), "%I:%M %p")
            arr_dt = midnight.replace(hour=t_dt.hour, minute=t_dt.minute)
            if arr_dt < sim_now:
                arr_dt += timedelta(days=1)
            parsed_arrivals.append(arr_dt)

        # ----- MULTIPLE STOP LOGIC -----
        num_stops = len(stations)

        for i in range(num_stops - 1):
            start_station = stations[i]
            dest_station = stations[i + 1]

            start_block = ctc_backend.station_to_block(start_station)
            dest_block = ctc_backend.station_to_block(dest_station)

            if start_block is None:
                print(f"[Schedule] ERROR: No block for station '{start_station}'")
                return
            if dest_block is None:
                print(f"[Schedule] ERROR: No block for station '{dest_station}'")
                return

            # arrival time at NEXT station
            arrival_dt = parsed_arrivals[i + 1]
            arrival_seconds = int((arrival_dt - midnight).total_seconds())

            # ---- travel time between these stops ----
            travel_s = ctc_backend.compute_travel_time(start_block, dest_block)

            # ---- departure time = arrival - travel ----
            departure_seconds = arrival_seconds - int(travel_s)

            # For first leg: THIS is the actual dispatch time
            is_first_leg = (i == 0)

            # compute suggestions
            speed_mps, auth_m = ctc_backend.compute_suggestions(start_block, dest_block)
            speed_mph = speed_mps * 2.23693629
            auth_yd = auth_m / 0.9144

            if is_first_leg:
                # schedule dispatch into the world
                ctc_backend.schedule_manual_dispatch(
                    train_id,
                    start_block,
                    dest_block,
                    departure_seconds,
                    speed_mph,
                    auth_yd
                )
                print(f"[Schedule] FIRST LEG dispatched → {train_id} at {departure_seconds}s")
            else:
                # future logic — store legs for automatic movement
                # ------------------------------
                # Store remaining legs in routes
                # ------------------------------
                if train_id not in self.routes:
                    self.routes[train_id] = []

                self.routes[train_id].append({
                    "from_block": start_block,
                    "to_block": dest_block,
                    "depart_seconds": departure_seconds,
                    "arrival_seconds": arrival_seconds
                })

                # Add an entry for UI display
                self.entries.append({
                    "train_id": train_id,
                    "destination": dest_station,
                    "arrival_time": arrival_dt.strftime("%I:%M %p"),
                    "line": ctc_backend.line_name
                })


                # first leg already dispatched above, so initialize index = 0
                self.current_leg[train_id] = 0

                print(f"[Schedule] Added leg {start_station} → {dest_station} for {train_id}")

        print(f"[Schedule] Loaded {num_stops - 1} legs for {train_id}")

   
    def get_schedule(self):
        """Return schedule entries for UI display.

        Returns:
            A shallow copy of all stored schedule rows.
        """
        return list(self.entries)

# ------------------------------------------------------------
# TrackState — the CTC backend interface
# ------------------------------------------------------------
class TrackState:
    """Centralized Traffic Control (CTC) backend state manager.

    This class unifies three major subsystems:

        • TrackModel — physical simulation (blocks, movement, stations)
        • Software TrackController — PLC-like logic for switches & signals
        • Hardware TrackController — hardware-based controller simulation

    TrackState drives the entire environment using the global simulation
    clock. It computes suggestions (speed/authority), dispatches trains,
    pushes block-wide commands to controllers, tracks dwell time, and
    maintains a UI-friendly mirror of block state.

    One TrackState instance corresponds to exactly one transit line
    (e.g., "Green Line" or "Red Line").
    """

    def __init__(self, line_name: str = "Green Line",  network: TrackNetwork = None):
        """Initialize full CTC backend state for a single transit line.

    Args:
        line_name: Human-readable line name ("Green Line", "Red Line").
        network: Optional pre-built TrackNetwork. If None, the track
            layout CSV for the line is loaded automatically.

    Behavior:
        - Loads the TrackModel (physical layout and segments).
        - Determines which blocks belong to software vs hardware controllers.
        - Initializes both SW and HW TrackController backends and links them
          back to this CTC instance.
        - Registers TrackModel as a global clock listener.
        - Creates internal data structures for:
            * train destinations
            * per-train suggestions (speed, authority)
            * dwell timing and station arrival detection
            * UI block mirrors for the dispatcher interface
            * schedule handling via ScheduleManager
        - Builds the initial block table for the UI via set_line().
    """
        self.line_name = line_name
        
        # Create and load the Track Model
        if network is not None:
            self.track_model = network
            self.section_map = self._load_section_letters()
            print(f"[CTC Backend] Using provided TrackNetwork for {network.line_name}")
        else:
            self.track_model = TrackNetwork()
            try:
                layout_file = f"{self.line_name.lower().replace(' ', '_')}.csv"
                layout_path = os.path.join(
                    os.path.dirname(__file__),
                    "..", "trackModel", layout_file
                )
                layout_path = os.path.abspath(layout_path)
                self.track_model.load_track_layout(layout_path)
                self.section_map = self._load_section_letters()

                print(f"[CTC Backend] Loaded track layout from {layout_path}")
               
                all_blocks = sorted(self.track_model.segments.keys())

                if self.line_name == "Green Line":
                    # Original mapping (confirmed)
                    self.sw_ranges = set(list(range(1, 63)) + list(range(122, 151)))
                    self.hw_ranges = set(all_blocks) - self.sw_ranges

                elif self.line_name == "Red Line":
                    # From your controller team: SW = 1–32
                    self.sw_ranges = set(range(1, 33))
                    self.hw_ranges = set(all_blocks) - self.sw_ranges

                else:
                    # Fallback for unknown lines
                    mid = len(all_blocks) // 2
                    self.sw_ranges = set(all_blocks[:mid])
                    self.hw_ranges = set(all_blocks[mid:])

            except Exception as e:
                print(f"[CTC Backend] Warning: failed to load layout → {e}")

        self._train_destinations: Dict[str, int] = {}

        #Build Track Controller backend and link both sides
        self.track_controller = TrackControllerBackend(self.track_model, line_name)
        self.track_controller.set_ctc_backend(self)  # Enables CTC ←→ Controller communication
        self.track_controller.start_live_link(poll_interval=1.0)

        #Build Track Controller HW backend and link both times 
        self.track_controller_hw = HardwareTrackControllerBackend(self.track_model, line_name)
        self.track_controller_hw.set_ctc_backend(self)
        self.track_controller_hw.start_live_link(poll_interval=1.0)
        self.passenger_throughput_hour = 0
        self._last_throughput_reset = clock.get_time()

        #Register Track Model as a clock listener (optional redundancy)
        clock.register_listener(self.track_model.set_time)

        #CTC operation mode
        self.mode = "manual"

        #Store per train suggestion state for resend
        self._train_suggestions: Dict[str, Tuple[float, float]] = {}
        self._train_progress: Dict[str, float] = {}   # cumulative distance per train
        self._pending_dispatches = []   # stores scheduled manual dispatches

        self._dwell_end = {}   # train_id → dwell end time in seconds
        self._last_block = {}  # train_id → last block id to detect arrivals

        self.maintenance_enabled = False

        #UI mirror of blocks
        self._lines: Dict[str, List[Block]] = {}
        self._by_key: Dict[str, Block] = {}

        self.set_line(line_name)
        self.schedule = ScheduleManager()
        self.train_throughput = 0   # how many full routes completed

        self.on_train_created = None

        print(f"[CTC Backend] Initialized for {self.line_name}")

    def set_mode(self, mode: str):
        """Set CTC operation mode.

    Args:
        mode: Either "manual" (CTC drives all logic) or "auto"
            (future extension for autonomous dispatch).

    Raises:
        ValueError: If mode is not one of {"manual", "auto"}.
    """

        mode = mode.lower()
        if mode not in ("manual", "auto"):
            raise ValueError(f"Invalid mode '{mode}'")
        self.mode = mode
        print(f"[CTC Backend] Mode set to {mode.upper()}")
   
    def compute_suggestions(self, start_block: int, dest_block: int):
        """Compute safe suggested speed and authority between two blocks.

        This method uses the actual graph connectivity of the TrackModel,
        not simplistic block ranges. The returned suggestion is conservative
        and based on:

            • Real block lengths
            • TrackModel speed limits
            • Beacon timing (if present)
            • Lowest safe speed along the chosen path

        Args:
            start_block: Block where the train currently resides.
            dest_block: Block that the train is authorized to reach.

        Returns:
            Tuple (speed_mps, authority_m):
                speed_mps: Suggested speed in meters/second.
                authority_m: Total movement authority in meters.

        Notes:
            Falls back to default speed and 50 m authority if no valid path
            exists or blocks are missing.
        """

        tm = self.track_model.segments

        # --- Validate blocks exist ---
        if start_block not in tm or dest_block not in tm:
            print("[CTC] Warning: compute_suggestions using fallback values")
            return LINE_SPEED_LIMIT_MPS, 50.0

        # --- NEW: use real graph traversal ---
        path = self.find_path(start_block, dest_block)
        print(f"[DEBUG] Path for {start_block} → {dest_block}: {path}")
        # If start and destination are the same block → no authority needed
        if start_block == dest_block:
            return LINE_SPEED_LIMIT_MPS, 0.0



        if not path:
            print(f"[CTC] No path {start_block} → {dest_block}, fallback used.")
            return LINE_SPEED_LIMIT_MPS, 50.0

        total_authority_m = 0.0
        possible_speeds = []

        # Iterate actual path blocks, NOT a numeric range
        for bid in path[:-1]:
            seg = tm.get(bid)
            if not seg:
                continue

            # (A) Real length (meters)
            length_m = seg.length

            # (B) TrackModel’s speed limit (already m/s)
            speed_from_limit = seg.speed_limit

            # (C) Traverse time
            try:
                traverse = float(seg.beacon_data.strip().replace("t=", ""))
            except:
                traverse = length_m / max(speed_from_limit, 0.1)

            # (D) Speed from traverse time
            speed_from_traverse = length_m / max(traverse, 0.1)

            # (E) Choose SAFEST (slowest)
            safe_speed = min(speed_from_limit, speed_from_traverse)
            possible_speeds.append(safe_speed)

            # (F) Accumulate authority
            total_authority_m += length_m

        # Final speed = bottleneck speed
        suggested_speed_mps = min(possible_speeds) if possible_speeds else LINE_SPEED_LIMIT_MPS

        return suggested_speed_mps, total_authority_m

    def controller_for_block(self, block_id: int):
        """Return which controller (SW or HW) governs the given block.

        Args:
            block_id: Numeric block identifier.

        Returns:
            TrackControllerBackend or HardwareTrackControllerBackend,
            depending on whether the block belongs to software-controlled
            or hardware-controlled territory.
        """

        if block_id in self.sw_ranges:
            return self.track_controller
        return self.track_controller_hw

    def compute_travel_time(self, start_block: int, dest_block: int) -> float:
       
        """Estimate total travel time between two blocks.

            Travel time is computed using:
                • Real movement authority from compute_suggestions()
                • Safe speed along the entire path
                • Dwell time at station blocks (30 seconds each)
                • Actual connected path through the TrackModel graph

            Args:
                start_block: Starting block number.
                dest_block: Destination block number.

            Returns:
                Total travel time in seconds. Returns infinity if speed is zero.
            """

        # Get speed + movement authority
        speed_mps, authority_m = self.compute_suggestions(start_block, dest_block)

        if speed_mps <= 0:
            return float('inf')

        # -----------------------------
        # 1. Get the real path
        # -----------------------------
        path = self.find_path(start_block, dest_block)

        if not path:
            # No path → fallback travel time
            return authority_m / speed_mps

        # -----------------------------
        # 2. Count station blocks in the path
        # -----------------------------
        station_count = 0
        for bid in path:
            seg = self.track_model.segments.get(bid)
            if seg and getattr(seg, "station_name", ""):
                station_count += 1

        # 30s dwell for each station in path
        dwell_time_s = station_count * 30

        # -----------------------------
        # 3. Movement time
        # -----------------------------
        moving_time_s = authority_m / speed_mps

        # -----------------------------
        # 4. Total time = movement + dwell
        # -----------------------------
        return moving_time_s + dwell_time_s

    def find_path(self, start_block: int, dest_block: int) -> List[int]:
        """Return a valid block-to-block path using BFS on the track graph.

    This pathfinder consults the TrackModel’s directional connections
    (next, previous, and diverging segments). It resolves special cases:

        • Block 0 is treated as the Yard and remapped automatically.
        • Avoids re-introducing block 0 into the graph.
        • Handles switches by adding diverging paths to the BFS queue.

    Args:
        start_block: Block where the train begins.
        dest_block: Block the train is trying to reach.

    Returns:
        A list of block IDs forming a valid path, or an empty list if
        no route exists.
    """
        from collections import deque
        
        yard_block = None
        for b, seg in self.track_model.segments.items():
            if hasattr(seg, "station_name") and seg.station_name and seg.station_name.lower() == "yard":
                yard_block = b
                break

        # Map block 0 → yard only if yard exists
        if start_block == 0 and yard_block is not None:
            start_block = yard_block
        if dest_block == 0 and yard_block is not None:
            dest_block = yard_block

        
        tm = self.track_model.segments
        visited = set()
        queue = deque([(start_block, [start_block])])

        while queue:
            block, path = queue.popleft()
            if block == dest_block:
                return path

            if block in visited:
                continue
            visited.add(block)

            seg = tm.get(block)
            if not seg:
                continue

            neighbors = []

            # Straight next
            if seg.next_segment:
                neighbors.append(seg.next_segment.block_id)

            # Diverging path (switch)
            if hasattr(seg, "diverging_segment") and seg.diverging_segment:
                neighbors.append(seg.diverging_segment.block_id)

            # Previous (reverse direction)
            if hasattr(seg, "previous_segment") and seg.previous_segment:
                neighbors.append(seg.previous_segment.block_id)

            for nb in neighbors:
                # 🔥 Do not allow yard-as-0 to ever enter the BFS
                if nb == 0:
                    nb = 63

                if nb not in visited:
                    queue.append((nb, path + [nb]))


            

        

        return []  # no path found

    def schedule_manual_dispatch(self, train_id, start_block, dest_block,
                                departure_seconds, speed_mph, auth_yd):
        """Queue a manual train dispatch for execution at a future simulation time.

    This method does not spawn a train immediately. Instead, it stores all
    parameters required for dispatch and waits until the global simulation
    clock reaches `departure_seconds`. At that moment, the dispatch is
    executed inside tick_all_modules().

    Args:
        train_id: Unique train identifier to be dispatched.
        start_block: Block ID where the train will spawn.
        dest_block: Block ID the train is initially authorized to travel toward.
        departure_seconds: Simulation time (seconds since midnight) when the
            dispatch should occur.
        speed_mph: Initial suggested speed in miles per hour.
        auth_yd: Initial suggested authority in yards.
    """
        entry = {
            "train_id": train_id,
            "start_block": start_block,
            "dest_block": dest_block,
            "departure_seconds": departure_seconds,
            "speed_mph": speed_mph,
            "auth_yd": auth_yd
        }

        self._pending_dispatches.append(entry)

        print(f"[CTC] Scheduled dispatch added → {train_id} at {departure_seconds}s")

    def _load_section_letters(self):
        """Load section letters (A, B, C, ...) from the track layout CSV.

        The CSV’s `name` column encodes a block's section using prefixes such as
        "A1", "B4", "C12". This method extracts the alphabetical portion and maps
        it to each block ID, allowing the UI to display section letters.

        Returns:
            A dict mapping block_id (int) → section letter(s) (str).
        """

        section_map = {}

        # Path to the same CSV TrackNetwork loads
        layout_file = f"{self.line_name.lower().replace(' ', '_')}.csv"
        layout_path = os.path.join(
            os.path.dirname(__file__),
            "..", "trackModel", layout_file
        )
        layout_path = os.path.abspath(layout_path)

        import csv
        with open(layout_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "").strip()  # e.g. "A1", "B4", "C12"
                if not name:
                    continue

                # Extract section: letters only
                section = "".join([c for c in name if c.isalpha()])
                # block_id stored separately
                block_id = int(row["block_id"])

                section_map[block_id] = section

        return section_map

    def set_line(self, name: str):
        """Build or rebuild the UI-facing block table for the selected line.

    This constructs a list of Block objects that mirrors the TrackModel
    segments, enriching them with UI-friendly data such as:

        • Section letter
        • Station name and platform side
        • Switch or crossing indication
        • Speed limits (converted for UI display)
        • Occupancy and status fields

    The result is stored in self._lines[name] and indexed for fast lookup.

    Args:
        name: Name of the transit line being activated.
    """
        self.line_name = name
        blocks: List[Block] = []

        for block_id, segment in self.track_model.segments.items():
           
            section = self.section_map.get(block_id, "")

            station = getattr(segment, "station_name", "")
            station_side = getattr(segment, "station_side", "")

            switch_text = "Switch" if segment.__class__.__name__ == "TrackSwitch" else ""

            #signal_state = getattr(segment, "signal_state", "")
            
            crossing = segment.__class__.__name__ == "LevelCrossing"

            speed_limit_mph = segment.speed_limit * 2.237  # convert m/s → mph

            blocks.append(
                Block(
                    line=name,
                    section=section,
                    block_id=block_id,
                    status="unoccupied",
                    station=station,
                    station_side=str(station_side),
                    switch=switch_text,
                    light="",
                    crossing=crossing,
                    speed_limit=speed_limit_mph,    
                    length_m=segment.length,         
                    speed_limit_mps=segment.speed_limit,
                )
            )

        blocks.sort(key=lambda b: b.block_id)
       
        if 0 not in [b.block_id for b in blocks]:
            blocks.insert(0, Block(
                line=name, section="", block_id=0, status="unoccupied",
                station="", station_side="", switch="", light="",
                crossing=False, speed_limit=0.0, length_m=0.0, speed_limit_mps=0.0
            ))

        self._lines[name] = blocks
        self._rebuild_index()

    def _rebuild_index(self):
        """Rebuild the lookup table mapping section+block_id → Block.

        This supports fast UI interaction by allowing blocks to be retrieved
        through composite keys like "A12" or "C7".
        """    

        self._by_key.clear()
        for b in self._lines[self.line_name]:
            self._by_key[f"{b.section}{b.block_id}"] = b

    def get_blocks(self) -> List[Block]:
        """Return the full list of UI block objects for the active line.

        Returns:
            A list of Block instances corresponding to one line’s track layout.
        """

        return self._lines.get(self.line_name, [])

    def dispatch_train(self, train_id: int, start_block: int, dest_block: int,
                    suggested_speed_mph: float, suggested_auth_yd: float):
        """Spawn a train into the TrackModel and send initial suggestions.

    This method is called when the dispatcher manually deploys a train.
    It creates a Train object, connects it to the TrackModel, sends the
    initial speed/authority to both SW and HW controllers, and records the
    train’s destination for later authority logic.

    Args:
        train_id: Unique numeric identifier for the train.
        start_block: Block ID where the train should spawn.
        dest_block: Destination block that determines authority pathing.
        suggested_speed_mph: Initial suggested speed (mph) from UI or schedule.
        suggested_auth_yd: Initial suggested authority (yards).
    """
        try:
          
            speed_mps = suggested_speed_mph * 0.44704
            auth_m = suggested_auth_yd * 0.9144

            new_train = Train(train_id)
            self.track_model.add_train(new_train)
            start_block = int(start_block)
            self.track_model.connect_train(train_id, start_block, displacement=0.0)

            self._train_destinations[train_id] = dest_block

            #controller = self.controller_for_block(start_block, self.track_controller, self.track_controller_hw)
            #controller = self.controller_for_block(start_block)
            
            self.track_controller.receive_ctc_suggestion(start_block, speed_mps, auth_m)
            self.track_controller_hw.receive_ctc_suggestion(start_block, speed_mps, auth_m)

            # Save for per-tick resend
            self._train_suggestions[train_id] = (speed_mps, auth_m)
            self._train_progress[train_id] = 0.0

            # print(f"[CTC] Dispatched {train_id} → Block {start_block}: {suggested_speed_mph} mph, {suggested_auth_yd} yd")

            if getattr(self, "on_train_created", None):
                self.on_train_created(train_id, self.line_name, start_block)

        except Exception as e:
            print(f"[CTC] Error dispatching train: {e}")

    def set_block_closed(self, block_id: int, closed: bool):
        """Toggle maintenance mode for a single block.

    When a block is closed:
        • The TrackModel flags it as unusable.
        • UI status is updated to "closed".
        • Trains approaching the block receive zero speed/authority.

    When a block is reopened:
        • TrackModel clears the closed flag.
        • UI status returns to "unoccupied".
        • Any train waiting before the block receives new safe suggestions.

    Args:
        block_id: Block number to open/close.
        closed: True to close the block; False to reopen it.
    """
        try:
            if closed:
                self.track_model.close_block(block_id)
            else:
                self.track_model.open_block(block_id)

                # 🔥 NEW: update UI mirror status
            for b in self._lines[self.line_name]:
                if b.block_id == block_id:
                    b.status = "closed" if closed else "unoccupied"
            #print(f"[CTC] Block {block_id} {'closed' if closed else 'opened'}.")
        except Exception as e:
            print(f"[CTC] Maintenance toggle failed: {e}")
            # NEW: When block is reopened, recalc pending train suggestions
        # --- When a block is reopened, resume any train waiting before it ---
        if not closed:
            for train_id, train in self.track_model.trains.items():
                seg = train.current_segment
                if not seg:
                    continue

                next_seg = seg.get_next_segment()
                if next_seg and next_seg.block_id == block_id:
                    # Pull the destination stored at dispatch time
                    dest_block = self._train_destinations.get(train_id)
                    if dest_block is None:
                        continue

                    # Recompute new safe suggestions
                    spd, auth = self.compute_suggestions(seg.block_id, dest_block)

                    # Store & push back to both controllers
                    self._train_suggestions[train_id] = (spd, auth)
                    #self.track_controller.receive_ctc_suggestion(seg.block_id, spd, auth)
                    #self.track_controller_hw.receive_ctc_suggestion(seg.block_id, spd, auth)
                    #controller = self.controller_for_block(seg.block_id, self.track_controller, self.track_controller_hw)
                    #controller = self.controller_for_block(seg.block_id)
                    
                    self.track_controller.receive_ctc_suggestion(seg.block_id, spd, auth)
                    self.track_controller_hw.receive_ctc_suggestion(seg.block_id, spd, auth)

                    #controller.receive_ctc_suggestion(seg.block_id, spd, auth)


                    print(f"[CTC] Block {block_id} reopened — resumed movement for train {train_id}")

    def get_network_status(self) -> Dict:
        """Return combined system status for UI or debugging.

    Returns:
        A dictionary containing:
            - "track_model": Current physical state snapshot from TrackModel.
            - "track_controller": Software controller state (signals, switches, etc.)

    Notes:
        Hardware controller status may be added later. If any subsystem
        fails during status generation, an empty dict is returned.
    """
        try:
            return {
                "track_model": self.track_model.get_network_status(),
                "track_controller": self.track_controller.report_state()
                
            }
        except Exception as e:
            print(f"[CTC] Network status error: {e}")
            return {}

    def get_trains(self) -> List[Dict]:
        """Return active train states, including block and CTC suggestions.

    For each train in the TrackModel, this returns:
        - train_id
        - current block ID
        - suggested speed (m/s)
        - suggested authority (m)
        - line name

    Returns:
        A list of dictionaries, one per train.
    """
        trains_data = []

        for train_id, train in self.track_model.trains.items():
            seg = train.current_segment

            # Pull speed/authority directly from CTC suggestions:
            speed_mps, auth_m = self._train_suggestions.get(train_id, (0.0, 0.0))

            trains_data.append({
                "train_id": train_id,
                "block": seg.block_id if seg else None,
                "suggested_speed_mps": speed_mps,
                "suggested_authority_m": auth_m,
                "line": self.line_name,
            })

        return trains_data

    def receive_wayside_status(self, line_name, status_updates, source=None):
        """Process periodic status updates from SW or HW TrackControllers.

    The controllers send block occupancy, signal states, switch positions,
    and crossing activations. TrackState filters the updates so that:

        - SW reports are ignored for HW-only territory.
        - HW reports are ignored for SW-only territory.

    Args:
        line_name: Name of line sending the update (should match this TrackState).
        status_updates: List of PLC/wayside status objects.
        source: Optional indicator ("SW" or "HW") specifying which controller
            generated the update.
    """
        for update in status_updates:
            bid = update.block_id

            # If SW is reporting HW territory → ignore
            if source == "SW" and bid in self.hw_ranges:
                continue

            # If HW is reporting SW territory → ignore
            if source == "HW" and bid in self.sw_ranges:
                continue

            # Otherwise accept the update
            self.update_block_occupancy(line_name, bid, update.occupied)
            self.update_signal_state(line_name, bid, update.signal_state)
            if update.switch_position is not None:
                self.update_switch_position(line_name, bid, update.switch_position)
            if update.crossing_status is not None:
                self.update_crossing_status(line_name, bid, update.crossing_status)

    def get_throughput_per_hour(self):
        """Return hourly passenger throughput for UI display.

    Throughput is computed from passengers boarded (or exited) at stations
    and updated internally each tick.

    Returns:
        Integer count of passengers processed in the last hour.
    """
        return self.passenger_throughput_hour
  
    def update_block_occupancy(self, line_name, block_id, occupied):
        """Apply occupancy changes reported by wayside controllers.

        Updates the TrackModel block state as well as the UI-facing mirrored
        Block object. Occupancy updates for other lines are ignored because
        a TrackState instance manages exactly one line.

        Args:
            line_name: Name of line sending the update.
            block_id: Block whose occupancy has changed.
            occupied: Boolean indicating whether the block is occupied.
        """
        if line_name != self.line_name:
            return

        try:
            block = self.track_model.get_block(block_id)
        except Exception:
            return

        block.occupied = occupied

        if block_id in self._by_key:
            self._by_key[block_id].occupied = occupied

        # Save last occupancy (for dwell timing etc.)
        self._last_block_occupancy[block_id] = occupied

    def update_signal_state(self, line_name, block_id, signal_state):
        """Apply signal state updates for switch blocks.

            Args:
                line_name: Name of the line sending the update.
                block_id: Block ID whose signal state changed.
                signal_state: Enum or string representing current signal state.

            Notes:
                - Non-switch blocks ignore signal updates.
                - "N/A" or missing states default to RED.
                - TrackState does not push signal changes to the UI here; this is
                reserved for switch logic handled in TrackController.
            """
        
        if hasattr(signal_state, "name"):
            signal_state = signal_state.name

        
        if not signal_state or signal_state == "N/A":
            signal_state = "RED"   # default to RED

        tm_seg = self.track_model.segments.get(block_id)

        if not isinstance(tm_seg, TrackSwitch):
            return  # ignore signal update for non-switch blocks

    def update_switch_position(self, line_name, block_id, position):
        """Update the UI-facing switch position for the specified block.

    Args:
        line_name: Name of the line sending updates.
        block_id: Block containing a switch.
        position: String or numeric switch position ("0", "1", etc.).
    """
        if line_name == self.line_name:

            for b in self._lines[line_name]:
                if b.block_id == block_id:
                    b.set_switch_position(position)
                    return

    def _update_throughput(self):
        """Recalculate passenger throughput from station-level counts.

    The total passengers boarded (or exited) across all station segments
    is summed once per tick. This value is presented as the hourly passenger
    throughput metric in the UI.
    """
        total_passengers = 0

        # count boardings OR exits at all stations
        for block_id, seg in self.track_model.segments.items():
            if hasattr(seg, "station_name"):
                # Option A: use boarded passengers
                total_passengers += seg.passengers_boarded_total
                # Option B: or use exited passengers (either works)
                # total_passengers += seg.passengers_exited_total

        self.passenger_throughput_hour = total_passengers

    def update_crossing_status(self, line_name, block_id, status):
        """Update UI mirror of level crossing activation.

        Args:
            line_name: Line reporting the status change.
            block_id: Block ID of the crossing.
            status: Boolean indicating whether the crossing is active.
        """
        if line_name == self.line_name:

            for b in self._lines[line_name]:
                if b.block_id == block_id:
                    b.set_crossing_status(status)
                    return

    def station_to_block(self, station_name: str):
        """Resolve a station name into a corresponding block ID.

    Performs:
        - Normalization of punctuation/spaces.
        - Alias mapping for user typos and alternative spellings.
        - Dynamic lookup of the Yard block.
        - Search of all TrackModel segments for a match.

    Args:
        station_name: Human-readable station name entered by UI or CSV.

    Returns:
        The integer block ID where the station exists, or None if not found.
    """
        normalized = station_name.lower().replace(".", "").replace(" ", "")

        ALIASES = {
            "yard": "Yard",
            "theyard": "Yard",
            "storageyard": "Yard",
            "glenbury": "Glenbury",
            "dormont": "Dormont",
            "mtlebanon": "Mt. Lebonon",    # map spelling
            "mtlebonon": "Mt. Lebonon",
            "central": "Central",
            "inglewood": "Inglewood"
        }

        # Replace with canonical map spelling if needed
        if normalized in ALIASES:
            station_name = ALIASES[normalized]
        
        # If user typed 'Yard', find the yard dynamically
        if station_name.lower() == "yard":
            for block, seg in self.track_model.segments.items():
                if hasattr(seg, "station_name") and seg.station_name and seg.station_name.lower() == "yard":
                    return block
            return None

        for block, seg in self.track_model.segments.items():
            if hasattr(seg, "station_name"):
                if seg.station_name.lower().replace(" ", "") == station_name.lower().replace(" ", ""):
                    return block

        return None




      # --------------------------------------------------------
    
    def push_full_block_suggestions(self):
        """Broadcast suggested speed/authority to every block in the line.

    Behavior:
        - Blocks not containing a train receive (0, 0).
        - Each train’s current block receives its current suggestion.
        - Both SW and HW TrackControllers receive commands for all blocks.

    Purpose:
        Ensures all wayside controllers always maintain a complete,
        synchronized view of CTC authority and speed commands.
    """

        line_blocks = sorted(self.track_model.segments.keys())

        
        speed_map = {bid: 0.0 for bid in line_blocks}
        auth_map  = {bid: 0.0 for bid in line_blocks}

        
        for train_id, (speed, auth) in self._train_suggestions.items():
            train = self.track_model.trains.get(train_id)
            if not train or not train.current_segment:
                continue
            block = train.current_segment.block_id
            speed_map[block] = speed
            auth_map[block] = auth

        
        for bid in line_blocks:
            self.track_controller.receive_ctc_suggestion(bid, speed_map[bid], auth_map[bid])
            self.track_controller_hw.receive_ctc_suggestion(bid, speed_map[bid], auth_map[bid])

    def tick_all_modules(self):
        """Advance the entire CTC system by one simulation tick.

        The global clock is manually advanced by the CTC, and this method
        synchronizes all major subsystems in the correct order:

        1. Process scheduled dispatches:
            - Trains whose departure time has arrived are spawned.

        2. Advance the global simulation clock:
            - Compute delta time since last tick.

        3. Update TrackModel:
            - Movement, block transitions, dwell timers, physics updates.

        4. Update wayside controllers:
            - SW controller: polls TrackModel and pushes status to CTC.
            - HW controller: same behavior with hardware logic.

        5. Sync UI block occupancy:
            - TrackModel → UI mirror.

        6. Update passenger throughput.

        7. Manual mode train control:
            - Apply dwell logic at station arrivals.
            - Detect end-of-leg for scheduled routes.
            - Compute fresh suggestions after dwell.
            - Stop trains approaching closed blocks.
            - Reduce authority every tick based on movement.
            - Send updated suggestions to controllers.
            - Push full-block suggestions for system-wide consistency.

        Notes:
            This loop is the heartbeat of the entire CTC simulation.
            Every subsystem depends on this method being called once per
            frame/tick in the UI.
        """
            
        current_seconds = clock.get_seconds_since_midnight()

        to_dispatch = []
        for entry in self._pending_dispatches:
            if current_seconds >= entry["departure_seconds"]:
                to_dispatch.append(entry)

        for entry in to_dispatch:
            print(f"[CTC] Executing scheduled dispatch → {entry['train_id']}")
            self.dispatch_train(
                entry["train_id"],
                entry["start_block"],
                entry["dest_block"],
                entry["speed_mph"],
                entry["auth_yd"]
            )
            self._pending_dispatches.remove(entry)

       
        if not hasattr(self, "_last_time"):
            self._last_time = clock.get_time()

        prev_time = self._last_time
        current_time = clock.tick()
        self._last_time = current_time

        delta_s = (current_time - prev_time).total_seconds()
       
        try:
            self.track_model.set_time(current_time)
        except Exception as e:
            print(f"[CTC] Track Model set_time error: {e}")

      
        try:
            self.track_controller._poll_track_model()
            self.track_controller._send_status_to_ctc()
        except Exception as e:
            print("[CTC] SW Controller manual poll error:", e)

        try:
            self.track_controller_hw._poll_track_model()
            self.track_controller_hw._send_status_to_ctc()
        except Exception as e:
            print("[CTC] HW Controller manual poll error:", e)

       
        try:
            blocks = self._lines[self.line_name]
            for ui_block in blocks:
                tm_segment = self.track_model.segments.get(ui_block.block_id)
                if tm_segment:
                    ui_block.set_occupancy(tm_segment.occupied)
                    if tm_segment.closed:
                        ui_block.status = "closed"
        except Exception as e:
            print(f"[CTC] Occupancy sync error: {e}")
        
        try:
            self._update_throughput()
        except Exception as e:
            print("[CTC] Throughput update error:", e)

        if self.mode == "manual":
            for train_id, (speed_mps, auth_m) in list(self._train_suggestions.items()):

               
                train = self.track_model.trains.get(train_id)
                if not train or not train.current_segment:
                    continue

                seg = train.current_segment
                block = seg.block_id
                current_seconds = clock.get_seconds_since_midnight()

                if train_id not in self._last_block:
                    self._last_block[train_id] = block

                
                if train_id in self._dwell_end:
                    if current_seconds < self._dwell_end[train_id]:
                        
                        #self.track_controller.receive_ctc_suggestion(block, speed_mps, auth_m)
                        #self.track_controller_hw.receive_ctc_suggestion(block, speed_mps, auth_m)
                        self.track_controller.receive_ctc_suggestion(block, 0.0, 0.0)
                        self.track_controller_hw.receive_ctc_suggestion(block, 0.0, 0.0)

                        self._train_suggestions[train_id] = (0.0, 0.0)
                        print(f"[DWELL] Train {train_id} dwelling at station block {block} "
                            f"for {int(self._dwell_end[train_id] - current_seconds)} more seconds")
                        continue
                    else:
                        print(f"[DWELL] Train {train_id} completed dwell at block {block}")
                        del self._dwell_end[train_id]
                       
                        if train_id in self.schedule.current_leg:

                            leg_index = self.schedule.current_leg[train_id]
                            if train_id in self.schedule.routes and leg_index < len(self.schedule.routes[train_id]):

                                current_leg = self.schedule.routes[train_id][leg_index]
                               
                                if block == current_leg["to_block"]:
                                    print(f"[SCHEDULE] Train {train_id} finished leg {leg_index}")
                                    next_index = leg_index + 1
                                    self.schedule.current_leg[train_id] = next_index
                                   
                                    if next_index < len(self.schedule.routes[train_id]):
                                        next_leg = self.schedule.routes[train_id][next_index]

                                        spd, auth = self.compute_suggestions(
                                            next_leg["from_block"],
                                            next_leg["to_block"]
                                        )
                                        spd_mph = spd * 2.23693629
                                        auth_yd = auth / 0.9144

                                        now_sec = clock.get_seconds_since_midnight()

                                        self.schedule_manual_dispatch(
                                            train_id,
                                            next_leg["from_block"],
                                            next_leg["to_block"],
                                            now_sec,      
                                            spd_mph,
                                            auth_yd
                                        )

                                        print(f"[SCHEDULE] Next leg dispatched immediately → "
                                            f"{next_leg['from_block']} → {next_leg['to_block']}")
                                    else:
                                        print(f"[SCHEDULE] Train {train_id} completed all legs.")
                                        self.train_throughput += 1
                                        print(f"[CTC] THROUGHPUT UPDATE → {self.train_throughput} trips completed")


                       
                        dest_block = self._train_destinations.get(train_id)
                        if dest_block is not None:
                            new_speed, new_auth = self.compute_suggestions(block, dest_block)
                            speed_mps, auth_m = new_speed, new_auth
                            print(f"[DWELL] Recomputed post-dwell suggestions → {speed_mps:.2f} m/s, {auth_m:.1f} m")

                        
                is_station = bool(getattr(seg, "station_name", ""))

                if is_station and self._last_block[train_id] != block:
                    dwell_time = 30
                    self._dwell_end[train_id] = current_seconds + dwell_time
                    print(f"[DWELL] Train {train_id} ARRIVED at station block {block}, starting {dwell_time}s dwell.")

                    
                    self.track_controller.receive_ctc_suggestion(block, 0.0, 0.0)
                    self.track_controller_hw.receive_ctc_suggestion(block, 0.0, 0.0)

                    self._train_suggestions[train_id] = (0.0, 0.0)

                    self._last_block[train_id] = block
                    continue

               
                next_seg = train.current_segment.get_next_segment()
                if next_seg and next_seg.closed:
                    new_speed = 0.0
                    new_auth = 0.0

                    #controller.receive_ctc_suggestion(block, new_speed, new_auth)
                    self.track_controller.receive_ctc_suggestion(block, new_speed, new_auth)
                    self.track_controller_hw.receive_ctc_suggestion(block, new_speed, new_auth)

                    self._train_suggestions[train_id] = (new_speed, new_auth)
                    print(f"[CTC] Train {train_id} STOPPED — Block {next_seg.block_id} is CLOSED")
                    continue
               
                distance_per_tick = speed_mps * delta_s
                new_auth = max(0.0, auth_m - distance_per_tick)

                if new_auth <= 0.0:
                    new_auth = 0.0
                    speed_mps = 0.0


                #controller.receive_ctc_suggestion(block, speed_mps, new_auth)
                self.track_controller.receive_ctc_suggestion(block, speed_mps, new_auth)
                self.track_controller_hw.receive_ctc_suggestion(block, speed_mps, new_auth)

                self._train_suggestions[train_id] = (speed_mps, new_auth)
              
                self._last_block[train_id] = block

                print("DEBUG TRAIN:", train_id, "seg=", train.current_segment)
                print(f"[CTC] Suggestion → Train {train_id} in block {block}: "
                    f"{speed_mps:.2f} m/s, {new_auth:.1f} m authority")
                
                self.push_full_block_suggestions()

    def reset_all(self):
        
        self.track_model.clear_trains()
        print(f"[CTC Backend] Reset all track and train data for {self.line_name}")