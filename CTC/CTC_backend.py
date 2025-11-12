from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math
import os

from universal.global_clock import clock
from trackModel.track_model_backend import TrackNetwork, Train
from trackControllerSW.track_controller_backend import TrackControllerBackend


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
# Data model for UI block representation
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


# ------------------------------------------------------------
# TrackState: CTC’s backend facade
# - Owns TrackNetwork + TrackControllerBackend
# - Receives time ticks from global clock
# - Dispatches trains and forwards CTC suggestions
# ------------------------------------------------------------
class TrackState:
    def __init__(self, line_name: str = "Green Line", line_tuples: List[Tuple] = GREEN_LINE_DATA):
        self.line_name = line_name
        self.track_model = TrackNetwork()

        # === NEW: Load the actual Green Line track CSV ===
        try:
            layout_path = os.path.join(os.path.dirname(__file__), "..", "trackModel", "green_line.csv")
            layout_path = os.path.abspath(layout_path)
            self.track_model.load_track_layout(layout_path)
            print(f"[CTC Backend] Loaded track layout from {layout_path}")
        except Exception as e:
            print(f"[CTC Backend] Warning: failed to load layout → {e}")

        self.track_controller = TrackControllerBackend(self.track_model, line_name)

        # Register the Track Model for time updates every clock tick
        clock.register_listener(self.track_model.set_time)

        # Simple UI mirror (keeps your table data structure)
        self._lines: Dict[str, List[Block]] = {}
        self._by_key: Dict[str, Block] = {}

        self.mode = "manual"
        self.set_line(line_name, line_tuples)

        print(f"[CTC Backend] Initialized for {self.line_name}")


    # --------------------------------------------------------
    # MODE CONTROL
    # --------------------------------------------------------
    def set_mode(self, mode: str):
        """Switch between MANUAL and AUTO mode."""
        mode = mode.lower()
        if mode not in ("manual", "auto"):
            raise ValueError(f"Invalid mode '{mode}'")
        self.mode = mode
        print(f"[CTC Backend] Mode set to {mode.upper()}")

    # --------------------------------------------------------
    # LINE + BLOCK HANDLING
    # --------------------------------------------------------
    def set_line(self, name: str, tuples: List[Tuple]):
        """Rebuild block table for UI rendering."""
        self.line_name = name
        blocks: List[Block] = []
        for t in tuples:
            section, bid, status, station, station_side, sw, light, crossing, _, speed_limit = t
            blocks.append(
                Block(
                    line=self.line_name,
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
        """Rebuild quick key lookup for UI table updates."""
        self._by_key.clear()
        for b in self._lines[self.line_name]:
            key = f"{b.section}{b.block_id}"
            self._by_key[key] = b

    def get_blocks(self) -> List[Block]:
        """Return the blocks for UI table display."""
        return self._lines.get(self.line_name, [])

    # --------------------------------------------------------
    # TRAIN DISPATCH + TRACK CONTROLLER INTERFACE
    # --------------------------------------------------------
    def dispatch_train(self, train_id: str, start_block: int, suggested_speed_mph: float, suggested_auth_yd: float):
        """Dispatch a train into the real TrackNetwork."""
        try:
            # Convert units
            suggested_speed_mps = suggested_speed_mph * 0.44704
            suggested_auth_m = suggested_auth_yd * 0.9144

            # Create train and register it in the network
            new_train = Train(train_id)

            self.track_model.add_train(new_train)

            # Connect to the start block
            start_block_int = int(start_block)
            self.track_model.connect_train(train_id, start_block_int, displacement=0.0)

            # Send initial speed/authority suggestion to Track Controller
            if self.track_controller:
                self.track_controller.receive_ctc_suggestion(
                    start_block_int, suggested_speed_mph, suggested_auth_yd
                )

            print(f"[CTC] Dispatched {train_id} → Block {start_block_int}: {suggested_speed_mph} mph, {suggested_auth_yd} yd")

        except Exception as e:
            print(f"[CTC] Error dispatching train: {e}")


    # --------------------------------------------------------
    # CLOCK TICK: synchronize all modules
    # --------------------------------------------------------
    def tick_all_modules(self):
        """
        Called once per tick by global clock.
        - Advances the global simulation time
        - Syncs Track Model + Track Controller states
        """
        clock.tick()  # advance global time
        try:
            self.track_controller._poll_track_model()
        except Exception as e:
            print(f"[CTC] Error during tick: {e}")

    # --------------------------------------------------------
    # MANUAL MAINTENANCE CONTROL
    # --------------------------------------------------------
    def set_block_closed(self, block_id: int, closed: bool):
        """Close or open a block for maintenance."""
        try:
            if closed:
                self.track_model.close_block(block_id)
            else:
                self.track_model.open_block(block_id)
            print(f"[CTC] Block {block_id} {'closed' if closed else 'opened'} for maintenance.")
        except Exception as e:
            print(f"[CTC] Failed to toggle maintenance on block {block_id}: {e}")

    # --------------------------------------------------------
    # STATUS ACCESSORS
    # --------------------------------------------------------
    def get_network_status(self) -> Dict:
        """Return full Track Model + Controller status for the UI."""
        try:
            net = self.track_model.get_network_status()
            wayside = self.track_controller.report_state()
            return {"track_model": net, "track_controller": wayside}
        except Exception as e:
            print(f"[CTC] Error retrieving network status: {e}")
            return {}

    # --------------------------------------------------------
    # UTILITY
    # --------------------------------------------------------
    def reset_all(self):
        """Reset simulation state (clears trains, reopens all blocks)."""
        self.track_model.trains.clear()
        for seg in self.track_model.segments.values():
            seg.set_occupancy(False)
            seg.open()
        print(f"[CTC Backend] Reset all track and train data for {self.line_name}")

    def get_trains(self):
        """Return a list of trains currently in the TrackNetwork."""
        trains_data = []
        for train_id, train in self.track_model.trains.items():
            seg = train.current_segment
            trains_data.append({
                "train_id": train_id,
                "block": seg.block_id if seg else None,
                "suggested_speed_mps": getattr(seg.active_command, "speed", 0.0) if seg and seg.active_command else 0.0,
                "suggested_authority_m": getattr(seg.active_command, "authority", 0.0) if seg and seg.active_command else 0.0,
                "line": self.line_name,
            })
        return trains_data
