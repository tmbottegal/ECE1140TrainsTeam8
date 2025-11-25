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
LINE_DATA = {
  
   "Red Line":   [],
   "Green Line": [
       # ----- Section A -----
   ("A", 1, "free", "", "", "", "", "", 8.0, 45),
   ("A", 2, "free", "Pioneer", "Left", "", "", "", 8.0, 45),
   ("A", 3, "free", "", "", "", "", "", 8.0, 45),


   # ----- Section B -----
   ("B", 4, "free", "", "", "", "", "", 8.0, 45),
   ("B", 5, "free", "", "", "", "", "", 8.0, 45),
   ("B", 6, "free", "", "", "", "", "", 8.0, 45),


   # ----- Section C -----
   ("C", 7, "free", "", "", "", "", "", 8.0, 45),
   ("C", 8, "free", "", "", "", "", "", 8.0, 45),
   ("C", 9, "free", "Edgebrook", "Left", "", "", "", 8.0, 45),
   ("C", 10, "free", "", "", "", "", "", 8.0, 45),
   ("C", 11, "free", "", "", "", "", "", 8.0, 45),
   ("C", 12, "free", "", "", "SWITCH (12-13; 1-13)", "", "", 8.0, 45),


   # ----- Section D -----
   ("D", 13, "free", "", "", "", "", "", 7.7, 70),
   ("D", 14, "free", "", "", "", "", "", 7.7, 70),
   ("D", 15, "free", "", "", "", "", "", 7.7, 70),
   ("D", 16, "free", "Station", "Left/Right", "", "", "", 7.7, 70),


   # ----- Section E -----
   ("E", 17, "free", "", "", "", "", "", 9.0, 60),
   ("E", 18, "free", "", "", "", "", "", 9.0, 60),
   ("E", 19, "free", "", "", "", "", "RAILWAY CROSSING", 9.0, 60),
   ("E", 20, "free", "", "", "", "", "", 9.0, 60),


   # ----- Section F -----
   ("F", 21, "free", "", "", "", "", "", 15.4, 70),
   ("F", 22, "free", "Whited", "Left/Right", "", "", "", 15.4, 70),
   ("F", 23, "free", "", "", "", "", "", 15.4, 70),
   ("F", 24, "free", "", "", "", "", "", 15.4, 70),
   ("F", 25, "free", "", "", "", "", "", 10.3, 70),
   ("F", 26, "free", "", "", "", "", "", 5.1, 70),
   ("F", 27, "free", "", "", "", "", "", 6.0, 30),
   ("F", 28, "free", "", "", "SWITCH (28-29; 150-28)", "", "", 6.0, 30),
       # ----- Section G -----
   ("G", 29, "free", "", "", "", "", "", 6.0, 30),
   ("G", 30, "free", "", "", "", "", "", 6.0, 30),
   ("G", 31, "free", "South Bank", "Left", "", "", "", 6.0, 30),
   ("G", 32, "free", "", "", "", "", "", 6.0, 30),


   # ----- Section H -----
   ("H", 33, "free", "", "", "", "", "", 6.0, 30),
   ("H", 34, "free", "", "", "", "", "", 6.0, 30),
   ("H", 35, "free", "", "", "", "", "", 6.0, 30),


   # ----- Section I -----
   ("I", 36, "free", "", "", "", "", "", 6.0, 30),
   ("I", 37, "free", "", "", "", "", "", 6.0, 30),
   ("I", 38, "free", "", "", "", "", "", 6.0, 30),
   ("I", 39, "free", "Central", "Right", "", "", "", 6.0, 30),
   ("I", 40, "free", "", "", "", "", "", 6.0, 30),
   ("I", 41, "free", "", "", "", "", "", 6.0, 30),
   ("I", 42, "free", "", "", "", "", "", 6.0, 30),
   ("I", 43, "free", "", "", "", "", "", 6.0, 30),
   ("I", 44, "free", "", "", "", "", "", 6.0, 30),
   ("I", 45, "free", "", "", "", "", "", 6.0, 30),
   ("I", 46, "free", "", "", "", "", "", 6.0, 30),
   ("I", 47, "free", "", "", "", "", "", 6.0, 30),
   ("I", 48, "free", "Inglewood", "Right", "", "", "", 6.0, 30),
   ("I", 49, "free", "", "", "", "", "", 6.0, 30),
   ("I", 50, "free", "", "", "", "", "", 6.0, 30),
   ("I", 51, "free", "", "", "", "", "", 6.0, 30),
   ("I", 52, "free", "", "", "", "", "", 6.0, 30),
   ("I", 53, "free", "", "", "", "", "", 6.0, 30),
   ("I", 54, "free", "", "", "", "", "", 6.0, 30),
   ("I", 55, "free", "", "", "", "", "", 6.0, 30),
   ("I", 56, "free", "", "", "", "", "", 6.0, 30),
   ("I", 57, "free", "Overbrook", "Right", "", "", "", 6.0, 30),


   # ----- Section J -----
   ("J", 58, "free", "", "", "SWITCH TO YARD (57-yard)", "", "", 6.0, 30),
   ("J", 59, "free", "", "", "", "", "", 6.0, 30),
   ("J", 60, "free", "", "", "", "", "", 6.0, 30),
   ("J", 61, "free", "", "", "", "", "", 6.0, 30),
   ("J", 62, "free", "", "", "SWITCH FROM YARD (Yard-63)", "", "", 6.0, 30),


   # ----- Section K -----
   ("K", 63, "free", "", "", "", "", "", 5.1, 70),
   ("K", 64, "free", "", "", "", "", "", 5.1, 70),
   ("K", 65, "free", "Glenbury", "Right", "", "", "", 10.3, 70),
   ("K", 66, "free", "", "", "", "", "", 10.3, 70),
   ("K", 67, "free", "", "", "", "", "", 9.0, 40),
   ("K", 68, "free", "", "", "", "", "", 9.0, 40),


   # ----- Section L -----
   ("L", 69, "free", "", "", "", "", "", 9.0, 40),
   ("L", 70, "free", "", "", "", "", "", 9.0, 40),
   ("L", 71, "free", "", "", "", "", "", 9.0, 40),
   ("L", 72, "free", "", "", "", "", "", 9.0, 40),
   ("L", 73, "free", "Dormont", "Right", "", "", "", 9.0, 40),


       # ----- Section M -----
   ("M", 74, "free", "", "", "", "", "", 9.0, 40),
   ("M", 75, "free", "", "", "", "", "", 9.0, 40),
   ("M", 76, "free", "", "", "SWITCH (76-77;77-101)", "", "", 9.0, 40),


   # ----- Section N -----
   ("N", 77, "free", "Mt Lebanon", "Left/Right", "", "", "", 15.4, 70),
   ("N", 78, "free", "", "", "", "", "", 15.4, 70),
   ("N", 79, "free", "", "", "", "", "", 15.4, 70),
   ("N", 80, "free", "", "", "", "", "", 15.4, 70),
   ("N", 81, "free", "", "", "", "", "", 15.4, 70),
   ("N", 82, "free", "", "", "", "", "", 15.4, 70),
   ("N", 83, "free", "", "", "", "", "", 15.4, 70),
   ("N", 84, "free", "", "", "", "", "", 15.4, 70),
   ("N", 85, "free", "", "", "SWITCH (85-86; 100-85)", "", "", 15.4, 70),


   # ----- Section O -----
   ("O", 86, "free", "", "", "", "", "", 14.4, 25),
   ("O", 87, "free", "", "", "", "", "", 12.5, 25),
   ("O", 88, "free", "Poplar", "Left", "", "", "", 14.4, 25),


   # ----- Section P -----
   ("P", 89, "free", "", "", "", "", "", 10.8, 25),
   ("P", 90, "free", "", "", "", "", "", 10.8, 25),
   ("P", 91, "free", "", "", "", "", "", 10.8, 25),
   ("P", 92, "free", "", "", "", "", "", 10.8, 25),
   ("P", 93, "free", "", "", "", "", "", 10.8, 25),
   ("P", 94, "free", "", "", "", "", "", 10.8, 25),
   ("P", 95, "free", "", "", "", "", "", 10.8, 25),
   ("P", 96, "free", "Castle Shannon", "Left", "", "", "", 10.8, 25),
   ("P", 97, "free", "", "", "", "", "", 10.8, 25),


   # ----- Section Q -----
   ("Q", 98, "free", "", "", "", "", "", 10.8, 25),
   ("Q", 99, "free", "", "", "", "", "", 10.8, 25),
   ("Q", 100, "free", "", "", "", "", "", 10.8, 25),


   # ----- Section R -----
   ("R", 101, "free", "", "", "", "", "", 4.8, 26),


   # ----- Section S -----
   ("S", 102, "free", "", "", "", "", "", 12.9, 28),
   ("S", 103, "free", "", "", "", "", "", 12.9, 28),
   ("S", 104, "free", "", "", "", "", "", 10.3, 28),


       # ----- Section T -----
   ("T", 105, "free", "Dormont", "Right", "", "", "", 12.9, 28),
   ("T", 106, "free", "", "", "", "", "", 12.9, 28),
   ("T", 107, "free", "", "", "", "", "", 11.6, 28),
   ("T", 108, "free", "", "", "", "", "RAILWAY CROSSING", 12.9, 28),
   ("T", 109, "free", "", "", "", "", "", 12.9, 28),


   # ----- Section U -----
   ("U", 110, "free", "", "", "", "", "", 12.0, 30),
   ("U", 111, "free", "", "", "", "", "", 12.0, 30),
   ("U", 112, "free", "", "", "", "", "", 12.0, 30),
   ("U", 113, "free", "", "", "", "", "", 12.0, 30),
   ("U", 114, "free", "Glenbury", "Right", "", "", "", 19.4, 30),
   ("U", 115, "free", "", "", "", "", "", 12.0, 30),
   ("U", 116, "free", "", "", "", "", "", 12.0, 30),


   # ----- Section V -----
   ("V", 117, "free", "", "", "", "", "", 12.0, 15),
   ("V", 118, "free", "", "", "", "", "", 12.0, 15),
   ("V", 119, "free", "", "", "", "", "", 9.6, 15),
   ("V", 120, "free", "", "", "", "", "", 12.0, 15),
   ("V", 121, "free", "", "", "", "", "", 12.0, 15),


   # ----- Section W -----
   ("W", 122, "free", "", "", "", "", "", 9.0, 20),
   ("W", 123, "free", "Overbrook", "Right", "", "", "", 9.0, 20),
   ("W", 124, "free", "", "", "", "", "", 9.0, 20),
   ("W", 125, "free", "", "", "", "", "", 9.0, 20),
   ("W", 126, "free", "", "", "", "", "", 9.0, 20),
   ("W", 127, "free", "", "", "", "", "", 9.0, 20),
   ("W", 128, "free", "", "", "", "", "", 9.0, 20),
   ("W", 129, "free", "", "", "", "", "", 9.0, 20),
   ("W", 130, "free", "", "", "", "", "", 9.0, 20),
   ("W", 131, "free", "", "", "", "", "", 9.0, 20),
   ("W", 132, "free", "Inglewood", "Left", "", "", "", 9.0, 20),
   ("W", 133, "free", "", "", "", "", "", 9.0, 20),
   ("W", 134, "free", "", "", "", "", "", 9.0, 20),
   ("W", 135, "free", "", "", "", "", "", 9.0, 20),
   ("W", 136, "free", "", "", "", "", "", 9.0, 20),
   ("W", 137, "free", "", "", "", "", "", 9.0, 20),
   ("W", 138, "free", "", "", "", "", "", 9.0, 20),
   ("W", 139, "free", "", "", "", "", "", 9.0, 20),
   ("W", 140, "free", "", "", "", "", "", 9.0, 20),
   ("W", 141, "free", "Central", "Right", "", "", "", 9.0, 20),
   ("W", 142, "free", "", "", "", "", "", 9.0, 20),
   ("W", 143, "free", "", "", "", "", "", 9.0, 20),


   # ----- Section X -----
   ("X", 144, "free", "", "", "", "", "", 9.0, 20),
   ("X", 145, "free", "", "", "", "", "", 9.0, 20),
   ("X", 146, "free", "", "", "", "", "", 9.0, 20),


   # ----- Section Y -----
   ("Y", 147, "free", "", "", "", "", "", 9.0, 20),
   ("Y", 148, "free", "", "", "", "", "", 33.1, 20),
   ("Y", 149, "free", "", "", "", "", "", 7.2, 20),


   # ----- Section Z -----
   ("Z", 150, "free", "", "", "", "", "", 6.3, 20),


   ],
}

GREEN_LINE_DATA = LINE_DATA["Green Line"]



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

    def __init__(self, line_name: str = "Green Line", line_tuples: List[Tuple] = GREEN_LINE_DATA, network: TrackNetwork = None):
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
                print(f"[CTC Backend] Loaded track layout from {layout_path}")
            except Exception as e:
                print(f"[CTC Backend] Warning: failed to load layout → {e}")

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


        self.set_line(line_name, line_tuples)
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
        Computes safe suggested speed (m/s) and authority (m)
        using the CTC's UI block table (self._lines) instead of TrackNetwork.
        """

        # ---- 1. Get speed limit from the UI's mirrored block list ----
        limit_mps = LINE_SPEED_LIMIT_MPS  # fallback

        for b in self._lines[self.line_name]:
            if b.block_id == start_block:
                # b.speed_limit is in km/h (your UI label shows km/h)
                # Convert km/h → m/s
                limit_mps = b.speed_limit * (1000/3600)
                break

        # ---- 2. Compute authority distance based on number of blocks ----
        if dest_block >= start_block:
            num_blocks = dest_block - start_block
        else:
            num_blocks = start_block - dest_block

        authority_m = num_blocks * BLOCK_LEN_M
        authority_m = max(authority_m, 25.0)   # ensure > 0

        return limit_mps, authority_m

    # --------------------------------------------------------
    # Line + block table setup for UI
    # --------------------------------------------------------
    def set_line(self, name: str, tuples: List[Tuple]):
        """Rebuilds UI table of blocks."""
        self.line_name = name
        blocks: List[Block] = []
        for t in tuples:
            section, bid, status, station, station_side, sw, light, crossing, _, speed_limit = t
            blocks.append(
                Block(
                    line=name,
                    section=section,
                    block_id=bid,
                    status=status,
                    station=station,
                    station_side=station_side,
                    switch=sw,
                    light=light,
                    crossing=bool(crossing),
                    speed_limit=float(speed_limit),
                )
            )
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
    def dispatch_train(self, train_id: str, start_block: int, suggested_speed_mph: float, suggested_auth_yd: float):
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

            # Send to Track Controller (in metric!)
            self.track_controller.receive_ctc_suggestion(start_block, speed_mps, auth_m)
            self.track_controller_hw.receive_ctc_suggestion(start_block, speed_mps,auth_m )

            # Save for per-tick resend
            self._train_suggestions[train_id] = (speed_mps, auth_m)
            self._train_progress[train_id] = 0.0


            print(f"[CTC] Dispatched {train_id} → Block {start_block}: {suggested_speed_mph} mph, {suggested_auth_yd} yd")

        except Exception as e:
            print(f"[CTC] Error dispatching train: {e}")

    # --------------------------------------------------------
    # Manual tick: CTC drives time for all subsystems
    # --------------------------------------------------------
    def tick_all_modules(self):
        """
        Advances simulation by one global clock tick.
        CTC manually synchronizes Track Model + Track Controller.
        """
        current_time = clock.tick()

        # --- Update Track Model (trains, occupancy) ---
        try:
            self.track_model.set_time(current_time)
        except Exception as e:
            print(f"[CTC] Track Model set_time error: {e}")

        # --- Update Track Controller (signals, switches, crossings) ---
        try:
            self.track_controller.set_time(current_time)
            self.track_controller_hw.set_time(current_time)
        except Exception:
            pass

        # --- Re-send and update active train suggestions ---
        # --- Re-send and update active train suggestions ---
        # --- Re-send and update active train suggestions ---
        if self.mode == "manual":

            for train_id, (speed_mps, auth_m) in list(self._train_suggestions.items()):
                train = self.track_model.trains.get(train_id)
                if not train or not train.current_segment:
                    continue

                block = train.current_segment.block_id

                # Decrease authority based on actual distance traveled:
                distance_per_tick = speed_mps * clock.tick_interval   # meters
                new_auth = max(0.0, auth_m - distance_per_tick)

                # Send updated suggestion to Track Controller
                self.track_controller.receive_ctc_suggestion(block, speed_mps, new_auth)
                self.track_controller_hw.receive_ctc_suggestion(block, speed_mps, new_auth )

                # Save updated authority
                self._train_suggestions[train_id] = (speed_mps, new_auth)

                print(f"[CTC] Suggestion → Train {train_id} in block {block}: "
                    f"{speed_mps:.2f} m/s, {new_auth:.1f} m authority")



    # --------------------------------------------------------
    # Maintenance control
    # --------------------------------------------------------
    def set_block_closed(self, block_id: int, closed: bool):
        try:
            if closed:
                self.track_model.close_block(block_id)
            else:
                self.track_model.open_block(block_id)
            print(f"[CTC] Block {block_id} {'closed' if closed else 'opened'}.")
        except Exception as e:
            print(f"[CTC] Maintenance toggle failed: {e}")

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
            trains_data.append({
                "train_id": train_id,
                "block": seg.block_id if seg else None,
                "suggested_speed_mps": getattr(seg.active_command, "speed", 0.0)
                    if seg and seg.active_command else 0.0,
                "suggested_authority_m": getattr(seg.active_command, "authority", 0.0)
                    if seg and seg.active_command else 0.0,
                "line": self.line_name,
            })
        return trains_data

    # --------------------------------------------------------
    # Wayside status callbacks (Track Controller → CTC)
    # --------------------------------------------------------
    def receive_wayside_status(self, line_name, status_updates):
        for update in status_updates:
            self.update_block_occupancy(line_name, update.block_id, update.occupied)
            self.update_signal_state(line_name, update.block_id, update.signal_state)
            if update.switch_position is not None:
                self.update_switch_position(line_name, update.block_id, update.switch_position)
            if update.crossing_status is not None:
                self.update_crossing_status(line_name, update.block_id, update.crossing_status)

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

    # --------------------------------------------------------
    # Reset utilities
    # --------------------------------------------------------

    def reset_all(self):
        self.track_model.clear_trains()
       # self.track_model.load_track_layout(os.path.join(os.path.dirname(__file__), "..", "trackModel", "green_line.csv"))
        print(f"[CTC Backend] Reset all track and train data for {self.line_name}")