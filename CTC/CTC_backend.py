from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math
from universal.global_clock import clock
from .track_controller_stub import TrackControllerStub
from trackModel.track_model_backend import TrackNetwork
from trackControllerSW.track_controller_backend import TrackControllerBackend

#Global Policies 
#Remove 
BLOCK_LEN_M: float = 50.0
LINE_SPEED_LIMIT_MPS: float = 13.9
YELLOW_FACTOR: float = 0.60
SAFETY_BLOCKS: int = 0
CONTROL_SIGNALS = {"B6", "C11"}

#Line topology 
#Remove
A_CHAIN = ["A1", "A2", "A3", "A4", "A5"]
B_CHAIN = ["B6", "B7", "B8", "B9", "B10"]
C_CHAIN = ["C11", "C12", "C13", "C14", "C15"]
EOL = {"B10", "C15"}

#Green and Red line Data 
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

# Convenience alias for UI imports
GREEN_LINE_DATA = LINE_DATA["Green Line"]


#data model for block row in UI table 
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



# -------------------------
# TrackState: CTC backend facade
# - Owns the current line's block list
# - Maintains a fast index by block key 
# - Hosts the TrackControllerStub and applies its snapshots to UI data *** 
# - Computes policy each tick (speeds/authority) and forwards to stub
# -------------------------
class TrackState:
    def __init__(self, line_name: str, line_tuples: List[Tuple]):
        self.line_name = line_name
        self.track_model = TrackNetwork()
        self.mode = "auto"  # default mode
        clock.register_listener(self.track_model.set_time)
        #will add for other modules later 
        self._lines: Dict[str, List[Block]] = {}            #list of block object 
        self._by_key: Dict[str, Block] = {}                 #each block 
        self._stub: Optional[TrackControllerStub] = None    #sim peer 

        self._last_snapshot: Dict[str, object] = {}
        self._overrides: Dict[str, Dict[str, object]] = {}
        self._oneshot_auth: Dict[str, int] = {}              # <-- NEW: on

        self.set_line(line_name, line_tuples)

        #self.track_model = TrackNetwork("Green Line")
        self.track_controller = TrackControllerBackend(self.track_model, "Green Line")

    def set_mode(self, mode: str):
        """Update CTC mode between 'manual' and 'auto'."""
        mode = mode.lower()
        if mode not in ("manual", "auto"):
            raise ValueError(f"Invalid mode '{mode}'")
        self.mode = mode
        print(f"[CTC Backend] Mode set to {mode.upper()}")
    
    def test_send_to_track_controller(self):
        """
        Temporary integration test — manually send a suggested speed and authority
        from CTC to the real Track Controller backend (no train dispatch needed).
        """
        try:
            # Example values (change as needed for your demo)
            block_id = 12           # any valid Blue Line block (1–15)
            suggested_speed = 25   # mph
            suggested_auth = 200   # yards

            if hasattr(self, "track_controller") and self.track_controller is not None:
                self.track_controller.receive_ctc_suggestion(block_id, suggested_speed, suggested_auth)
                print(f"[CTC] Sent test suggestion → Block {block_id}: {suggested_speed} mph, {suggested_auth} yd")
            else:
                print("[CTC] Track Controller not connected — could not send suggestion")

        except Exception as e:
            print(f"[CTC] Error while sending test suggestion: {e}")

    
    def dispatch_train(self, train_id: str, start_block: int, suggested_speed: int, suggested_auth: int):
        """
        Manual dispatch entry point for the UI:
        - Adds a train locally to the stub (so UI shows it)
        - Sends suggested speed/authority to the Track Controller backend
        """
        # 1️⃣ Add to stub simulation (optional but keeps UI in sync)
        if self._stub:
            block_key = f"A{start_block}" if isinstance(start_block, int) else str(start_block)
            self._stub.add_train(train_id, block_key)
            self._stub.broadcast()
            print(f"[CTC] Added {train_id} to stub at {block_key}")

        # 2️⃣ Send initial suggestion to real Track Controller
        if hasattr(self, "track_controller") and self.track_controller is not None:
            self.track_controller.receive_ctc_suggestion(start_block, suggested_speed, suggested_auth)
            print(f"[CTC] Dispatched {train_id} → Block {start_block}: {suggested_speed} mph, {suggested_auth} yd")
        else:
            print("[CTC] Track Controller not connected — could not send suggestion.")


    def set_line(self, name: str, tuples: List[Tuple]):
        self.line_name = name
        # tuples are: (line, block_id, status, station, signal, switch, light, crossing, maintenance/beacon)
        blocks: List[Block] = []
        for t in tuples:
            section, bid, status, station, station_side, sw, light, crossing, traverse_time, speed_limit = t
            blocks.append(Block(
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
            ))

        self._lines[name] = blocks
        self._rebuild_index()
        self._stub = TrackControllerStub(name, tuples)
        self._stub.on_status(self.apply_snapshot)
        self._stub.tick()

    #Access the current line's Block objects (for tables/map rendering)
    def get_blocks(self) -> List[Block]:
        return self._lines.get(self.line_name, [])

    #Block lookup 
    def _rebuild_index(self):
        self._by_key.clear()
        for b in self.get_blocks():
            key = f"{b.section}{b.block_id}"
            self._by_key[key] = b


    # ----- UI -> backend (forward to stub) -----
    #Mark/unmark a block under maintainace closed or setting it back 

    def unlock_switches(self) -> None:
        if self._stub:
            self._stub.unlock_switches()

    def get_switch_positions(self) -> Dict[str, str]:
        sp = self._last_snapshot.get("switch_pos", {})
        # normalize to {id: POS} as strings
        return {str(k): str(v) for k, v in sp.items()}

    def set_status(self, block_id: str, status: str) -> None:
        # Only toggle the maintenance closure; do NOT touch the static track_status
        is_closed = (str(status).lower() == "closed")
        self._stub.set_block_maintenance(block_id, is_closed)

    #Set the speed of the train 
    #CTC's op to train controller via stub 
    def set_suggested_speed(self, tid: str, mps: float):
        if self._stub:
            self._stub.set_suggested_speed(tid, mps)

    #Suggests authorty (meters -> blocks)
    def set_suggested_authority(self, tid: str, meters: float):
        blocks = max(0, math.ceil(float(meters) / BLOCK_LEN_M))
        print(f"[CTC] set_suggested_authority: {tid} → {meters:.1f}m = {blocks} blocks")
        if self._stub:
            self._stub.set_suggested_authority(tid, blocks)

    def set_crossing_override(self, block_id: str, state: Optional[bool]) -> None:
            """
            state:
            None  → Auto (derived)
            True  → Force DOWN
            False → Force UP
            """
            if self._stub:
                self._stub.set_crossing_override(block_id, state)
        
    #Move a switch if indicated by stub 
    def set_switch(self, switch_id: str, position: str):
        if self._stub:
            self._stub.set_switch(switch_id, position)

    def set_broken_rail(self, block_key: str, broken: bool):
        if self._stub:
            self._stub.set_broken_rail(block_key, broken)

    #add train at a starting block ****
    def add_train(self, train_id: str, start_block: str):
        if self._stub:
            self._stub.add_train(train_id, start_block)
            self._stub.broadcast()        # send snapshot right away
            self._last_snapshot = self._stub.get_snapshot()


    def get_snapshot(self):
        return self._snapshot

    #enable/disable stubs automatic line movement ***
    def set_auto_line(self, enabled: bool):
        if self._stub:
            self._stub.set_auto_line(bool(enabled))

    #Reset trains and recompute policy 
    def reset_trains(self):
        if self._stub:
            self._stub.reset_trains()
        self._policy_tick()

    def reset_infrastructure(self):
        if self._stub:
            self._stub.reset_infrastructure()

    def reset_all(self):
        if self._stub:
            self._stub.reset_all()
        self._policy_tick()

    # Per-train manual override from UI. Converts meters→blocks and forwards to stub.
    #*****
    # CTC_backend.py  (inside TrackState)

    def set_train_override(
        self,
        tid: str,
        enabled: bool,
        speed_mps: Optional[float] = None,
        authority_m: Optional[float] = None,
    ) -> None:
        tid = str(tid)

        if not enabled:
            # Clear both sticky and pending one-shot for this train
            self._overrides.pop(tid, None)
            self._oneshot_auth.pop(tid, None)
            return

        # Ensure sticky container exists
        ov = self._overrides.get(tid, {})
        ov["enabled"] = True

        # Sticky speed (keeps applying every tick until disabled)
        if speed_mps is not None:
            ov["speed_mps"] = float(speed_mps)
        self._overrides[tid] = ov

        # One-shot authority (meters -> blocks) — only sent next tick once
        if authority_m is not None:
            try:
                meters = float(authority_m)
            except (TypeError, ValueError):
                meters = 0.0
            blocks = max(0, int(round(meters / BLOCK_LEN_M)))
            self._oneshot_auth[tid] = blocks


    #snapshot appl 
    def apply_snapshot(self, snapshot: Dict[str, object]) -> None:
        if snapshot.get("line") != self.line_name:
            return
        self._last_snapshot = snapshot
        if not self._by_key:
            self._rebuild_index()
        for pb in snapshot.get("blocks", []):
            key = str(pb["key"])
            blk = self._by_key.get(key)
            if not blk:
                continue
            occ = str(pb.get("occupancy", "free"))
            blk.status = "closed" if occ == "closed" else ("occupied" if occ == "occupied" else "free")
            blk.light = str(pb.get("signal", "") or "")
            sw = str(pb.get("switch", "") or "")
            if sw:
                blk.switch = sw
            blk.station = str(pb.get("station", "") or "")

            blk.broken_rail = bool(pb.get("broken_rail", False))  # True/False
            blk.beacon = str(pb.get("beacon", "") or blk.beacon) 

            if blk.has_crossing:
                # Use the stub’s telemetry (True=open, False=closed/down). May be None early.
                co = pb.get("crossing_open", None)
                if isinstance(co, bool):
                    blk.crossing_open = co
                else:
                    # default to True if missing, to avoid confusing UI
                    blk.crossing_open = True

    #return list of trains from the last snapshot 
    def get_trains(self) -> List[Dict[str, object]]:
        return list(self._last_snapshot.get("trains", []))

    #delete 
    def _advance_one_step(self):
        pass

    # One UI tick:
    # 1) push any overrides to stub
    # 2) tell stub to advance movement
    # 3) compute CTC policy using the fresh snapshot
    # 4) broadcast updated state to UI 
    def stub_tick(self):
        if not self._stub:
            return

        clock.tick()

        # 1) Compute policy using the last snapshot
        self._policy_tick()

        # 2) Prepare the one-tick override payload to the stub
        send_ov: Dict[str, Dict[str, object]] = {}
        for tid, ov in (self._overrides or {}).items():
            if not ov.get("enabled"):
                continue
            entry = {"enabled": True}
            if "speed_mps" in ov:
                entry["speed_mps"] = float(ov["speed_mps"])
            if tid in self._oneshot_auth:
                entry["authority_blocks"] = int(self._oneshot_auth[tid])
            send_ov[tid] = entry

        # 3) Push overrides (speed sticky, authority one-shot)
        self._stub.set_train_overrides(send_ov)

        # 4) Advance the simulation one tick (movement happens here)
        self._stub.tick()

        # 5) Clear one-shot authorities after they’ve been used
        self._oneshot_auth.clear()

        # 6) Broadcast the new snapshot for the UI
        self._stub.broadcast()

    #deciding suggested speed and suggested authority 
    def _policy_tick(self):
        if not self._last_snapshot:
            print("[CTC backend]  No snapshot yet — skipping policy tick.")
            return

        # NOTE: stub snapshot uses "switch_pos", not "switches"
        switches = dict(self._last_snapshot.get("switch_pos", {}))

        blocks_payload: List[Dict[str, object]] = self._last_snapshot.get("blocks", [])
        occ_map    = {b["key"]: b.get("occupancy", "free") for b in blocks_payload}
        broken_map = {b["key"]: bool(b.get("broken_rail", False)) for b in blocks_payload}
        light_map  = {b["key"]: str(b.get("signal", "")) for b in blocks_payload}

        for t in self._last_snapshot.get("trains", []):
            tid = str(t["train_id"])
            cur = str(t["block"])
            nxt = self._next_block(cur, switches)

            # --- speed policy based on next block state ---
            if nxt is None or cur in EOL:
                speed_mps = 0.0
            else:
                nxt_occ   = occ_map.get(nxt, "free")
                nxt_broke = broken_map.get(nxt, False)
                nxt_light = light_map.get(nxt, "")
                if nxt_occ in ("closed", "occupied") or nxt_broke or nxt_light == "RED":
                    speed_mps = 0.0
                elif nxt_light == "YELLOW":
                    speed_mps = LINE_SPEED_LIMIT_MPS * YELLOW_FACTOR
                else:
                    speed_mps = LINE_SPEED_LIMIT_MPS

            # --- authority lookahead ---
            authority_m = self._lookahead_authority_m(cur, switches, occ_map, broken_map)

            # --- apply ONLY sticky speed override here ---
            ov = self._overrides.get(tid, {})
            if ov.get("enabled", False) and "speed_mps" in ov:
                speed_mps = float(ov["speed_mps"])

            # send to stub
            self.set_suggested_speed(tid, speed_mps)
            self.set_suggested_authority(tid, authority_m)

            # also send to the real Track Controller backend (if attached)
            if hasattr(self, "track_controller") and self.track_controller is not None:
                try:
                    # Find the block number (integer) from the train's current position
                    # Example: "B6" → 6
                    block_str = cur
                    block_id = int(''.join(filter(str.isdigit, block_str)))
                    speed_mph = round(speed_mps * 2.237, 1)   # convert m/s → mph
                    auth_yd = round(authority_m * 1.094, 1)   # convert m → yd

                    self.track_controller.receive_ctc_suggestion(block_id, speed_mph, auth_yd)
                    print(f"[CTC→TC] Sent → block {block_id}: {speed_mph} mph, {auth_yd} yd")
                except Exception as e:
                    print(f"[CTC→TC] Error sending to TrackController: {e}")


     # Compute the next block given current block and active switch positions
    def _next_block(self, cur: str, switches: Dict[str, str]) -> Optional[str]:
        if cur in A_CHAIN:
            if cur != "A5":
                return self._succ_in_chain(cur, A_CHAIN)
            desired_branch = self._get_desired_branch_for_train(cur)
            return "B6" if desired_branch == "B" else "C11"
        if cur in B_CHAIN:
            return self._succ_in_chain(cur, B_CHAIN)
        if cur in C_CHAIN:
            return self._succ_in_chain(cur, C_CHAIN)
        return None

    # Look ahead from 'cur' until EOL or first blockage, summing safe distance
    def _lookahead_authority_m(self, cur: str, switches: Dict[str, str],
                               occ_map: Dict[str, str], broken_map: Dict[str, bool]) -> float:
        path: List[str] = []
        nxt = cur
        while True:
            nxt = self._next_block(nxt, switches)
            if nxt is None:
                break
            path.append(nxt)
            if nxt in EOL:
                break
        if SAFETY_BLOCKS > 0 and len(path) > 0:
            path = path[:-SAFETY_BLOCKS] if len(path) > SAFETY_BLOCKS else []
        total_m = 0.0
        for b in path:
            if occ_map.get(b, "free") in ("closed", "occupied"): break
            if broken_map.get(b, False): break
            total_m += BLOCK_LEN_M
        # If immediately blocked ahead, grant a 1-block hold so UI isn’t blank
        return total_m

    def _get_desired_branch_for_train(self, cur_block: str) -> str:
        for t in self._last_snapshot.get("trains", []):
            if str(t["block"]) == cur_block:
                return str(t.get("desired_branch", "B")).upper()
        return "B"
    
    #Call into the stub to set initial positions/states
    def scenario_load(self, name: str) -> str:
        if not self._stub:
            return "no-stub"
        name = (name or "").strip()
        if name == "Manual Sandbox":
            self._stub.seed_manual_sandbox()
            return "Manual Sandbox loaded"
        if name == "Meet-and-Branch":
            self._stub.seed_meet_and_branch()
            return "Meet-and-Branch loaded"
        if name == "Maintenance Detour":
            self._stub.seed_maintenance_detour()
            return "Maintenance Detour loaded"
        if name == "Broken Rail":
            self._stub.seed_broken_rail()
            return "Broken Rail loaded"
        if name == "Crossing Gate Demo":
            self._stub.seed_crossing_demo()
            return "Crossing Gate Demo loaded"
        # fallback
        self._stub.seed_manual_sandbox()
        return "Manual Sandbox loaded"


    @staticmethod
    # Utility: successor inside a linear chain;
    def _succ_in_chain(b: str, chain: List[str], wrap_to: Optional[str] = None) -> Optional[str]:
        i = chain.index(b)
        if i + 1 < len(chain):
            return chain[i + 1]
        return wrap_to