# ============================================================
# CTC Backend (Integration-Ready Version)
# ------------------------------------------------------------
#    Uses the CTC’s global clock to drive time manually (no threads)
#    Keeps suggested speed/authority alive every tick
#   Fixes unit mismatches (imperial → metric)
#    Fixes references to self._lines and missing block update methods
#    Ready for integration with TrackControllerBackend + TrackModel
# ============================================================

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BLOCK_LEN_M = 50.0
BLOCK_TRAVEL_TIME_S = 7.0    # seconds to traverse one block
LINE_SPEED_LIMIT_MPS = BLOCK_LEN_M / BLOCK_TRAVEL_TIME_S  # ≈7.14 m/s


# The CTC owns the global simulation clock; every tick updates all modules.
from universal.global_clock import clock

# The Track Model simulates the physical railway (blocks, trains, etc.)
from trackModel.track_model_backend import TrackNetwork
from trainModel.train_model_backend import Train

# The Track Controller governs signals, switches, crossings, etc.
from trackControllerSW.track_controller_backend import TrackControllerBackend

from trackControllerHW.track_controller_hw_backend import HardwareTrackControllerBackend


# ------------------------------------------------------------
# LINE DATA (UI definitions)
# ------------------------------------------------------------


SW_RANGES = list(range(1, 63)) + list(range(122, 151))
HW_RANGES = list(range(63, 122))

def controller_for_block(block_id: int, sw, hw):
    """Return the correct controller (SW or HW) for a given block ID."""
    if block_id in SW_RANGES:
        return sw
    return hw


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
    length_m: float      # NEW: real block length pulled from TrackModel
    speed_limit_mps: float  # NEW: real speed limit (m/s)


    # --- helper methods for UI updates ---
    def set_occupancy(self, occupied: bool):
        self.status = "occupied" if occupied else "unoccupied"

    def set_signal_state(self, state: str):
        self.light = state

    def set_switch_position(self, position: str):
        self.switch = position

    def set_crossing_status(self, active: bool):
        self.crossing = bool(active)

# ------------------------------------------------------------
# Schedule Manager (Iteration 4 Foundation)
# ------------------------------------------------------------
class ScheduleManager:
    """
    Stores train schedules uploaded by the dispatcher.
    Provides:
        - schedule storage
        - adding entries manually
        - loading from CSV (empty placeholder for now)
        - retrieving schedule for UI
    NOTE: Does NOT handle routing, dispatching, or authority yet.
          This is ONLY the storage layer.
    """

    def __init__(self):
        # List of schedule entries
        # Each entry will be a dict:
        # {
        #   "train_id": "T1",
        #   "destination": "Edgebrook",
        #   "arrival_time": "14:35",
        #   "line": "Green Line"
        # }
        self.entries = []
        self.routes = {}          # train_id → list of legs
        self.current_leg = {}     # train_id → current leg index


    # --------------------------------------------------------
    # Add a single schedule entry (called from UI later)
    # --------------------------------------------------------
    def add_schedule_entry(self, train_id: str, destination: str, arrival_time: str, line: str = "Green Line"):
        """
        Add one schedule row. No routing or dispatching yet.
        Pure storage.
        """
        entry = {
            "train_id": train_id,
            "destination": destination,
            "arrival_time": arrival_time,
            "line": line
        }
        self.entries.append(entry)

    # --------------------------------------------------------
    # Load schedule from CSV (placeholder for now)
    # --------------------------------------------------------
    def load_from_csv(self, filepath: str):
        """
        Accept a CSV file path and load schedule entries.
        This is a placeholder — UI wiring will be done later.
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
        """
        Load a route CSV with multiple stops and schedule
        ALL legs of the trip based on arrival times.
        """

        import csv
        from datetime import datetime, timedelta

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

                # first leg already dispatched above, so initialize index = 0
                self.current_leg[train_id] = 0

                print(f"[Schedule] Added leg {start_station} → {dest_station} for {train_id}")

        print(f"[Schedule] Loaded {num_stops - 1} legs for {train_id}")

    # --------------------------------------------------------
    # Retrieve entries for UI table
    # --------------------------------------------------------
    def get_schedule(self):
        """Return list of schedule entries for UI to display."""
        return list(self.entries)

# ------------------------------------------------------------
# TrackState — the CTC backend interface
# ------------------------------------------------------------
class TrackState:
    """
    CTC’s backend interface that unifies:
        - TrackModel (physical simulation)
        - TrackControllerBackend (wayside control)
    CTC manually drives simulation time each tick.
    """

    def __init__(self, line_name: str = "Green Line",  network: TrackNetwork = None):
        self.line_name = line_name

        # Create and load the Track Model
        if network is not None:
            self.track_model = network
            print(f"[CTC Backend] Using provided TrackNetwork for {network.line_name}")
        else:
            self.track_model = TrackNetwork()
            try:
                layout_path = os.path.join(os.path.dirname(__file__), "..", "trackModel", "green_line.csv")
                layout_path = os.path.abspath(layout_path)
                self.track_model.load_track_layout(layout_path)
                self.section_map = self._load_section_letters()

                print(f"[CTC Backend] Loaded track layout from {layout_path}")
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

        

        #Register Track Model as a clock listener (optional redundancy)
        clock.register_listener(self.track_model.set_time)

        #UI mirror of blocks
        self._lines: Dict[str, List[Block]] = {}
        self._by_key: Dict[str, Block] = {}

        

        #CTC operation mode
        self.mode = "manual"

        #Store per train suggestion state for resend
        self._train_suggestions: Dict[str, Tuple[float, float]] = {}
        self._train_progress: Dict[str, float] = {}   # cumulative distance per train
        self._pending_dispatches = []   # stores scheduled manual dispatches

        self._dwell_end = {}   # train_id → dwell end time in seconds
        self._last_block = {}  # train_id → last block id to detect arrivals

        self.maintenance_enabled = False


        self.set_line(line_name)
        self.schedule = ScheduleManager()
        self.train_throughput = 0   # how many full routes completed

        print(f"[CTC Backend] Initialized for {self.line_name}")

    # --------------------------------------------------------
    # Mode control
    # --------------------------------------------------------
    def set_mode(self, mode: str):
        mode = mode.lower()
        if mode not in ("manual", "auto"):
            raise ValueError(f"Invalid mode '{mode}'")
        self.mode = mode
        print(f"[CTC Backend] Mode set to {mode.upper()}")
   
    def compute_suggestions(self, start_block: int, dest_block: int):
        """
        Compute suggested speed (m/s) and total authority (m) using the REAL graph path,
        not block-number ranges.
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

    def compute_travel_time(self, start_block: int, dest_block: int) -> float:
        """
        Returns total travel time in seconds using:
        - real track lengths
        - safe speed from compute_suggestions()
        - dwell time (30s per station block reached, including destination)
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
        """Return the actual connected block path using the track model graph."""
        from collections import deque
        # 🔥 Fix TrackModel bug: block 0 is actually Yard (63)
        if start_block == 0:
            start_block = 63
        if dest_block == 0:
            dest_block = 63
        
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
        """
        Store a scheduled manual dispatch to execute later when the time comes.
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
        """Load section letters (A, B, C…) from the CSV file's 'name' column."""
        section_map = {}

        # Path to the same CSV TrackNetwork loads
        layout_path = os.path.join(
            os.path.dirname(__file__), 
            "..", "trackModel", "green_line.csv"
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

    # --------------------------------------------------------
    # Line + block table setup for UI
    # --------------------------------------------------------
    def set_line(self, name: str):
        """
        Build the UI block table *directly from the TrackNetwork*.
        No more LINE_DATA / tuples.
        """
        self.line_name = name
        blocks: List[Block] = []

        for block_id, segment in self.track_model.segments.items():

            # SECTION LETTER -----------------------------------------------------
            # Extract leading letters from the CSV 'name' convention:  A1, B4, C12...
            # TrackNetwork does not store the block name directly -> infer section:
            # We assume the "name" column prefix was SectionLetter(s)+block_id.
            # If block_id = 12 and CSV name was "C12", section = "C".
            # We recover this by checking TrackModel's ordering or fallback.
            #section = "".join([c for c in str(segment.__class__.__name__) if c.isalpha()])[:1]
            section = self.section_map.get(block_id, "")

            # If you later store full block names in TrackNetwork, update here.

            # STATION INFO -------------------------------------------------------
            station = getattr(segment, "station_name", "")
            station_side = getattr(segment, "station_side", "")

            # SWITCH INFO --------------------------------------------------------
            switch_text = "Switch" if segment.__class__.__name__ == "TrackSwitch" else ""

            # SIGNAL -------------------------------------------------------------
            #signal_state = getattr(segment, "signal_state", "")
            
            # CROSSING -----------------------------------------------------------
            crossing = segment.__class__.__name__ == "LevelCrossing"

            # SPEED LIMIT DISPLAY (mph) -----------------------------------------
            speed_limit_mph = segment.speed_limit * 2.237  # convert m/s → mph

            # BUILD BLOCK --------------------------------------------------------
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
                    speed_limit=speed_limit_mph,    # UI shows mph
                    length_m=segment.length,         # backend real values
                    speed_limit_mps=segment.speed_limit,
                )
            )

        # Sort based on numeric block order for UI
        blocks.sort(key=lambda b: b.block_id)
        # ⭐ Ensure Yard (block 0) exists in UI list
        if 0 not in [b.block_id for b in blocks]:
            blocks.insert(0, Block(
                line=name, section="", block_id=0, status="unoccupied",
                station="", station_side="", switch="", light="",
                crossing=False, speed_limit=0.0, length_m=0.0, speed_limit_mps=0.0
            ))

        self._lines[name] = blocks
        self._rebuild_index()

    def _rebuild_index(self):
        """Rebuilds quick block lookup by section+ID."""
        self._by_key.clear()
        for b in self._lines[self.line_name]:
            self._by_key[f"{b.section}{b.block_id}"] = b

    def get_blocks(self) -> List[Block]:
        return self._lines.get(self.line_name, [])

    # --------------------------------------------------------
    # Train dispatching
    # --------------------------------------------------------
    def dispatch_train(self, train_id: str, start_block: int, dest_block: int,
                    suggested_speed_mph: float, suggested_auth_yd: float):
        """
        Dispatcher adds a train manually to TrackModel, with an initial
        suggested speed/authority sent to Track Controller.
        """
        try:
            # Convert to metric for simulation
            speed_mps = suggested_speed_mph * 0.44704
            auth_m = suggested_auth_yd * 0.9144

            new_train = Train(train_id)
            self.track_model.add_train(new_train)
            start_block = int(start_block)
            self.track_model.connect_train(train_id, start_block, displacement=0.0)
            #self.track_model.connect_train(train_id, start_block, displacement=0.0, direction="FORWARD")


            # ⭐ STORE DESTINATION FOR AUTHORITY LOGIC
            self._train_destinations[train_id] = dest_block

            # Send to Track Controller (in metric!)
            #self.track_controller.receive_ctc_suggestion(start_block, speed_mps, auth_m)
            #self.track_controller_hw.receive_ctc_suggestion(start_block, speed_mps, auth_m)

            controller = controller_for_block(start_block, self.track_controller, self.track_controller_hw)
            controller.receive_ctc_suggestion(start_block, speed_mps, auth_m)


            # Save for per-tick resend
            self._train_suggestions[train_id] = (speed_mps, auth_m)
            self._train_progress[train_id] = 0.0

            print(f"[CTC] Dispatched {train_id} → Block {start_block}: {suggested_speed_mph} mph, {suggested_auth_yd} yd")

        except Exception as e:
            print(f"[CTC] Error dispatching train: {e}")


    # --------------------------------------------------------
    # Maintenance control
    # --------------------------------------------------------
    def set_block_closed(self, block_id: int, closed: bool):
        try:
            if closed:
                self.track_model.close_block(block_id)
            else:
                self.track_model.open_block(block_id)

                # 🔥 NEW: update UI mirror status
            for b in self._lines[self.line_name]:
                if b.block_id == block_id:
                    b.status = "closed" if closed else "unoccupied"
            print(f"[CTC] Block {block_id} {'closed' if closed else 'opened'}.")
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
                    controller = controller_for_block(seg.block_id, self.track_controller, self.track_controller_hw)
                    controller.receive_ctc_suggestion(seg.block_id, spd, auth)


                    print(f"[CTC] Block {block_id} reopened — resumed movement for train {train_id}")


    # --------------------------------------------------------
    # Status accessors for UI
    # --------------------------------------------------------
    def get_network_status(self) -> Dict:
        try:
            return {
                "track_model": self.track_model.get_network_status(),
                "track_controller": self.track_controller.report_state()
                
            }
        except Exception as e:
            print(f"[CTC] Network status error: {e}")
            return {}

    def get_trains(self) -> List[Dict]:
        """Returns all active trains with current block + command data."""
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

    # --------------------------------------------------------
    # Wayside status callbacks (Track Controller → CTC)
    # --------------------------------------------------------
    def receive_wayside_status(self, line_name, status_updates, source=None):
        for update in status_updates:
            bid = update.block_id

            # If SW is reporting HW territory → ignore
            if source == "SW" and bid in HW_RANGES:
                continue

            # If HW is reporting SW territory → ignore
            if source == "HW" and bid in SW_RANGES:
                continue

            # Otherwise accept the update
            self.update_block_occupancy(line_name, bid, update.occupied)
            self.update_signal_state(line_name, bid, update.signal_state)
            if update.switch_position is not None:
                self.update_switch_position(line_name, bid, update.switch_position)
            if update.crossing_status is not None:
                self.update_crossing_status(line_name, bid, update.crossing_status)


    def update_block_occupancy(self, line_name, block_id, occupied):
        if line_name in self._lines:
            for b in self._lines[line_name]:
                if b.block_id == block_id:
                    b.set_occupancy(occupied)
                    print(f"[CTC] {line_name} Block {block_id} occupancy → {occupied}")
                    return

    def update_signal_state(self, line_name, block_id, signal_state):
        print(f"[CTC DEBUG] GOT SIGNAL UPDATE: block={block_id}, state={signal_state}")

        # Convert enum → string
        if hasattr(signal_state, "name"):
            signal_state = signal_state.name

        # TrackController sends "N/A" when no PLC logic exists
        if not signal_state or signal_state == "N/A":
            signal_state = "RED"   # default to RED

        for b in self._lines[line_name]:
            if b.block_id == block_id:
                b.set_signal_state(signal_state)
                print(f"[CTC] {line_name} Block {block_id} signal → {signal_state}")
                return



    def update_switch_position(self, line_name, block_id, position):
        if line_name in self._lines:
            for b in self._lines[line_name]:
                if b.block_id == block_id:
                    b.set_switch_position(position)
                    print(f"[CTC] {line_name} Switch {block_id} position → {position}")
                    return

    def update_crossing_status(self, line_name, block_id, status):
        if line_name in self._lines:
            for b in self._lines[line_name]:
                if b.block_id == block_id:
                    b.set_crossing_status(status)
                    print(f"[CTC] {line_name} Crossing {block_id} → {status}")
                    return

    def station_to_block(self, station_name: str):
        # Normalize common typos and variations
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
        
        if station_name == "Yard":
            return 63     # ALWAYS block 63

        # Search all station segments in the track model
        for block, seg in self.track_model.segments.items():
            if hasattr(seg, "station_name"):
                if seg.station_name.lower().replace(" ", "") == station_name.lower().replace(" ", ""):
                    return block

        return None




      # --------------------------------------------------------
    
    # Manual tick: CTC drives time for all subsystems
    # --------------------------------------------------------
    def tick_all_modules(self):
        """
        Advances simulation by one global clock tick.
        CTC manually synchronizes Track Model + Track Controller.
        """

        # ----------------------------------------------------------
        # 0. CHECK SCHEDULED DISPATCHES *BEFORE* CLOCK TICKS
        # ----------------------------------------------------------
        current_seconds = clock.get_seconds_since_midnight()

        to_dispatch = []
        for entry in self._pending_dispatches:
            if current_seconds >= entry["departure_seconds"]:
                to_dispatch.append(entry)

        # Perform dispatches at exact simulation time
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

        # ----------------------------------------------------------
        # 1. NOW tick the clock
        # ----------------------------------------------------------
        if not hasattr(self, "_last_time"):
            self._last_time = clock.get_time()

        prev_time = self._last_time
        current_time = clock.tick()
        self._last_time = current_time

        delta_s = (current_time - prev_time).total_seconds()
        # print(f"DEBUG: delta_s = {delta_s}")

        # ----------------------------------------------------------
        # 2. Update Track Model
        # ----------------------------------------------------------
        try:
            self.track_model.set_time(current_time)
        except Exception as e:
            print(f"[CTC] Track Model set_time error: {e}")

        # ----------------------------------------------------------
        # 3. Update Track Controller
        # ----------------------------------------------------------
        # SW Track Controller has no tick() method — manually poll it
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

        # ----------------------------------------------------------
        # 4. Sync occupancy
        # ----------------------------------------------------------
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

        if self.mode == "manual":
            for train_id, (speed_mps, auth_m) in list(self._train_suggestions.items()):

                # -------------------------
                # REQUIRED: get train + segment
                # -------------------------
                train = self.track_model.trains.get(train_id)
                if not train or not train.current_segment:
                    continue

                seg = train.current_segment
                block = seg.block_id
                current_seconds = clock.get_seconds_since_midnight()

                # Track last block for station arrival detection
                if train_id not in self._last_block:
                    self._last_block[train_id] = block

                # -------------------------------
                # 1. IF TRAIN IS CURRENTLY DWELLING
                # -------------------------------
                if train_id in self._dwell_end:
                    if current_seconds < self._dwell_end[train_id]:
                        controller = controller_for_block(block, self.track_controller, self.track_controller_hw)
                        controller.receive_ctc_suggestion(block, 0.0, 0.0)
                        self._train_suggestions[train_id] = (0.0, 0.0)
                        print(f"[DWELL] Train {train_id} dwelling at station block {block} "
                            f"for {int(self._dwell_end[train_id] - current_seconds)} more seconds")
                        continue
                    else:
                        print(f"[DWELL] Train {train_id} completed dwell at block {block}")
                        del self._dwell_end[train_id]
                        # -------------------------------------------------------
                        # CHECK IF TRAIN HAS FINISHED A SCHEDULED LEG
                        # -------------------------------------------------------
                        if train_id in self.schedule.current_leg:

                            leg_index = self.schedule.current_leg[train_id]
                            if train_id in self.schedule.routes and leg_index < len(self.schedule.routes[train_id]):

                                current_leg = self.schedule.routes[train_id][leg_index]

                                # Did the train reach the destination block of this leg?
                                if block == current_leg["to_block"]:
                                    print(f"[SCHEDULE] Train {train_id} finished leg {leg_index}")

                                    # Move to the next leg
                                    next_index = leg_index + 1
                                    self.schedule.current_leg[train_id] = next_index

                                    # If more legs remain → dispatch next immediately (Option A)
                                    if next_index < len(self.schedule.routes[train_id]):
                                        next_leg = self.schedule.routes[train_id][next_index]

                                        # Compute fresh suggestions for next leg
                                        spd, auth = self.compute_suggestions(
                                            next_leg["from_block"],
                                            next_leg["to_block"]
                                        )
                                        spd_mph = spd * 2.23693629
                                        auth_yd = auth / 0.9144

                                        # Immediate dispatch (Option A)
                                        now_sec = clock.get_seconds_since_midnight()

                                        self.schedule_manual_dispatch(
                                            train_id,
                                            next_leg["from_block"],
                                            next_leg["to_block"],
                                            now_sec,      # depart NOW
                                            spd_mph,
                                            auth_yd
                                        )

                                        print(f"[SCHEDULE] Next leg dispatched immediately → "
                                            f"{next_leg['from_block']} → {next_leg['to_block']}")
                                    else:
                                        print(f"[SCHEDULE] Train {train_id} completed all legs.")
                                        self.train_throughput += 1
                                        print(f"[CTC] THROUGHPUT UPDATE → {self.train_throughput} trips completed")


                        # Recompute speed/authority now that dwell is done
                        dest_block = self._train_destinations.get(train_id)
                        if dest_block is not None:
                            new_speed, new_auth = self.compute_suggestions(block, dest_block)
                            speed_mps, auth_m = new_speed, new_auth
                            print(f"[DWELL] Recomputed post-dwell suggestions → {speed_mps:.2f} m/s, {auth_m:.1f} m")

                        # fall through

                # -------------------------------
                # 2. DETECT ARRIVAL INTO A STATION
                # -------------------------------
                is_station = bool(getattr(seg, "station_name", ""))

                if is_station and self._last_block[train_id] != block:
                    dwell_time = 30
                    self._dwell_end[train_id] = current_seconds + dwell_time
                    print(f"[DWELL] Train {train_id} ARRIVED at station block {block}, starting {dwell_time}s dwell.")

                    controller = controller_for_block(block, self.track_controller, self.track_controller_hw)
                    controller.receive_ctc_suggestion(block, 0.0, 0.0)
                    self._train_suggestions[train_id] = (0.0, 0.0)

                    self._last_block[train_id] = block
                    continue

                # -------------------------------
                # 3. BLOCK CLOSED? STOP TRAIN
                # -------------------------------
                next_seg = train.current_segment.get_next_segment()
                if next_seg and next_seg.closed:
                    new_speed = 0.0
                    new_auth = 0.0

                    controller = controller_for_block(block, self.track_controller, self.track_controller_hw)
                    controller.receive_ctc_suggestion(block, new_speed, new_auth)

                    self._train_suggestions[train_id] = (new_speed, new_auth)
                    print(f"[CTC] Train {train_id} STOPPED — Block {next_seg.block_id} is CLOSED")
                    continue

                # -------------------------------
                # 4. NORMAL MOVEMENT
                # -------------------------------
                distance_per_tick = speed_mps * delta_s
                new_auth = max(0.0, auth_m - distance_per_tick)

                if new_auth <= 0.0:
                    new_auth = 0.0
                    speed_mps = 0.0

                controller = controller_for_block(block, self.track_controller, self.track_controller_hw)
                controller.receive_ctc_suggestion(block, speed_mps, new_auth)

                self._train_suggestions[train_id] = (speed_mps, new_auth)

                # -------------------------------
                # 5. UPDATE last_block FOR NEXT TICK
                # -------------------------------
                self._last_block[train_id] = block

                print("DEBUG TRAIN:", train_id, "seg=", train.current_segment)
                print(f"[CTC] Suggestion → Train {train_id} in block {block}: "
                    f"{speed_mps:.2f} m/s, {new_auth:.1f} m authority")


    # --------------------------------------------------------
    # Reset utilities
    # --------------------------------------------------------

    def reset_all(self):
        self.track_model.clear_trains()
       # self.track_model.load_track_layout(os.path.join(os.path.dirname(__file__), "..", "trackModel", "green_line.csv"))
        print(f"[CTC Backend] Reset all track and train data for {self.line_name}")