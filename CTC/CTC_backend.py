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
        self.status = "occupied" if occupied else "free"

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


        self.maintenance_enabled = False


        self.set_line(line_name)
        self.schedule = ScheduleManager()
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
        Returns travel time in seconds using real TrackModel lengths
        and the computed safe speed from compute_suggestions().
        """
        speed_mps, authority_m = self.compute_suggestions(start_block, dest_block)

        if speed_mps <= 0:
            return float('inf')

        return authority_m / speed_mps

    def find_path(self, start_block: int, dest_block: int) -> List[int]:
        """Return the actual connected block path using the track model graph."""
        from collections import deque
        
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
            signal_state = getattr(segment, "signal_state", "")
            
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
                    status="free",
                    station=station,
                    station_side=str(station_side),
                    switch=switch_text,
                    light=str(signal_state),
                    crossing=crossing,
                    speed_limit=speed_limit_mph,    # UI shows mph
                    length_m=segment.length,         # backend real values
                    speed_limit_mps=segment.speed_limit,
                )
            )

        # Sort based on numeric block order for UI
        blocks.sort(key=lambda b: b.block_id)

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
                    b.status = "closed" if closed else "free"
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
        if line_name in self._lines:
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

    def station_to_block(self, station_name: str) -> Optional[int]:
        """
        Given a station name, return the block_id from the UI mirror (self._lines).
        """
        for b in self._lines[self.line_name]:
            if b.station.strip().lower() == station_name.strip().lower():
                return b.block_id
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
        try:
            self.track_controller.tick(current_time, delta_s)
            self.track_controller_hw.tick(current_time, delta_s)
        except Exception:
            pass

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

        # ----------------------------------------------------------
        # 5. Suggest speed & authority for trains (manual mode)
        # ----------------------------------------------------------
        if self.mode == "manual":
            for train_id, (speed_mps, auth_m) in list(self._train_suggestions.items()):
                train = self.track_model.trains.get(train_id)
                if not train or not train.current_segment:
                    continue

                block = train.current_segment.block_id

                distance_per_tick = speed_mps * delta_s

                next_seg = train.current_segment.get_next_segment()
                if next_seg and next_seg.closed:
                    new_speed = 0.0
                    new_auth = 0.0

                    self.track_controller.receive_ctc_suggestion(block, new_speed, new_auth)
                    self.track_controller_hw.receive_ctc_suggestion(block, new_speed, new_auth)

                    self._train_suggestions[train_id] = (new_speed, new_auth)
                    print(f"[CTC] Train {train_id} STOPPED — Block {next_seg.block_id} is CLOSED")
                    continue

                # new_auth based on movement
                new_auth = max(0.0, auth_m - distance_per_tick)

                if new_auth <= 0.0:
                    new_auth = 0.0
                    speed_mps = 0.0

                # send to correct controller
                controller = controller_for_block(block, self.track_controller, self.track_controller_hw)
                controller.receive_ctc_suggestion(block, speed_mps, new_auth)

                self._train_suggestions[train_id] = (speed_mps, new_auth)

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