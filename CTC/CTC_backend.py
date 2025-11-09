from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math
from universal.global_clock import clock
import pandas as pd
import os


#will change this to be importing from trackControllerSW
from .track_controller_stub import TrackControllerStub

#Global Policies
# **Check with Green Line  
BLOCK_LEN_M: float = 50.0
LINE_SPEED_LIMIT_MPS: float = 13.9
YELLOW_FACTOR: float = 0.60
SAFETY_BLOCKS: int = 0
CONTROL_SIGNALS = {"B6", "C11"}

#Change to Green Line topology 
A_CHAIN = ["A1", "A2", "A3", "A4", "A5"]
B_CHAIN = ["B6", "B7", "B8", "B9", "B10"]
C_CHAIN = ["C11", "C12", "C13", "C14", "C15"]
EOL = {"B10", "C15"}

#data model for block row in UI table 
@dataclass
class Block:
    line: str
    block_id: int
    status: str
    station: str
    #change to bool 
    signal: str
    #change to bool 
    switch: str
    light: str
    beacon:str 
   
    has_crossing: bool          # presence (from LINE_DATA)
    broken_rail: bool = False
    crossing_open: bool = True   # status (True=open, False=closed) default open


"""Load Green Line CSV and return a list of Block objects with proper attributes."""
def load_green_line_csv():
    
    csv_path = os.path.join(os.path.dirname(__file__), "greenLine.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Missing track data file: {csv_path}")

    df = pd.read_csv(csv_path)

    blocks = []
    for _, row in df.iterrows():
        line = "Green"
        block_id = int(row["block_id"])
        station = str(row["station_name"]) if not pd.isna(row["station_name"]) else ""
        type_str = str(row["Type"]).lower() if "Type" in row and not pd.isna(row["Type"]) else ""
        crossing = type_str == "levelcrossing"

        b = Block(
            line=line,
            block_id=block_id,
            status="free",
            station=station,
            signal="",
            switch="",
            light="",
            beacon="",
            has_crossing=crossing
        )
        blocks.append(b)

    print(f"[Backend] Loaded {len(blocks)} Green Line blocks (including {sum(b.has_crossing for b in blocks)} crossings).")
    return blocks

# -------------------------
# TrackState: CTC backend facade
# - Owns the current line's block list
# - Maintains a fast index by block key 
# - Hosts the TrackControllerStub and applies its snapshots to UI data
# - Computes policy each tick (speeds/authority) and forwards to stub
# -------------------------
class TrackState:

    def __init__(self, line_name: str, line_tuples = None):
        self.line_name = line_name
        self._lines: Dict[str, List[Block]] = {}            # {line_name: [Block, ...]}
        self._by_key: Dict[str, Block] = {}                 # {“GreenA1”: Block}
        self._stub: Optional[TrackControllerStub] = None    #sim peer 

        self._last_snapshot: Dict[str, object] = {}         # latest snapshot from stub
        self._overrides: Dict[str, Dict[str, object]] = {}  # manual overrides from UI
        self._oneshot_auth: Dict[str, int] = {}             # temporary (1-tick) authorities
                # ---- Route schedule (Excel-driven) ----
        self._route_schedule: List[Dict[str, object]] = []  # rows: {tid,t,start_block,branch,dest_block,spawned}
        self._schedule_clock_s: int = 0
        self._dest_by_tid: Dict[str, str] = {}              # maps train_id → destination block

        # References to external subsystems 
        self.trackModel = None
        self.trainModel = None
        self.trackControllerHW = None
        self.trackControllerSW = None
        self.trainControllerHW = None
        self.trainControllerSW = None

        #CTC-internal copies of infrastructure state:
        self.blocks = {}
        self.trains = {}
        self.line_name = line_name
        self.maintenance_blocks = set()
        self.switch_states = {}
        self.crossings = {}
        self.active_trains = []

        #If no topology is provided, automatically loads the Green Line CSV and then calls set_line().
        if not line_tuples:
            # Auto-load Green Line CSV if none provided
            if line_name.lower() == "green":
                from .CTC_backend import load_green_line_csv
                line_tuples = load_green_line_csv()
            else:
                line_tuples = []

        self.set_line(line_name, line_tuples)

    #Connects your CTC backend to a line and initializes the stub.
    def set_line(self, name: str, tuples: List[Tuple]):

        self.line_name = name
        blocks: List[object] = []

        # Register all blocks for this line
        for b in tuples:
            # Use the same Block object directly
            blocks.append(b)
            bid = getattr(b, "block_id", "")
            self.blocks[bid] = b  # store reference for lookup

        # Store + build fast lookup
        self._lines[name] = blocks
        self._rebuild_index()

        # Create stub simulator (acts like Track Controller)
        self._stub = TrackControllerStub(name, tuples)

         # Connect stub callbacks → apply_snapshot()
        self._stub.on_status(self.apply_snapshot)
        self._stub.on_broadcast(self.apply_snapshot)

        print(f"[Backend DEBUG] Connected stub broadcast → apply_snapshot")

        # Get initial snapshot to fill UI tables
        self._stub.broadcast()

        print(f"[CTC Backend] TrackControllerStub connected for {name} line.")

    #Return list of all Block objects for current line (used for UI tables).
    def get_blocks(self) -> List[Block]:
        return self._lines.get(self.line_name, [])

    #Create key→Block lookup map (e.g. 'GreenA1' → Block).
    def _rebuild_index(self):
        self._by_key.clear()
        for b in self.get_blocks():
            key = f"{b.line}{b.block_id}"
            self._by_key[key] = b

    # ----- UI -> backend (forward to stub) -----
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
    def add_train(self, train_id: str, start_block: str, destination: str = ""):
        """Add a new train at a given block with optional destination."""
        if self._stub:
            print(f"[CTC Backend] Adding train {train_id} at block {start_block}, dest={destination}")
            self._stub.add_train(train_id, str(start_block), desired_branch=destination)
        else:
            print("[CTC Backend] Warning: no stub connected.")

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
        # clear schedule/clock/destinations
        self._route_schedule = []
        self._schedule_clock_s = 0
        self._dest_by_tid.clear()
        self._policy_tick()

        # ---------- Schedule: load/clear (route-based) ----------
    
    #Handles excel uploads 
    """Converts rows into structured dicts with train_id, start_block, dest_block, etc.
        Sorts by start time.
        Resets the simulation clock for schedules."""
    def load_route_schedule(self, rows: List[Tuple[str, int, str, str]]) -> int:
        """
        rows: list of (train_id, start_time_s, origin, destination)
              origin: "YARD" or "A" (both map to A1 on this demo line)
              destination: "A", "B", or "YARD"  (A/YARD -> A1, B -> B10)
        """
        def origin_to_start_block(origin: str) -> str:
            o = (origin or "").strip().upper()
            return "A1"  # both YARD and A spawn at A1 on this demo line

        def dest_to_block(dest: str) -> Tuple[str, str]:
            d = (dest or "").strip().upper()
            if d == "B":
                return "B10", "B"   # Station B → branch B
            if d == "C":
                return "C15", "C"   # Station C → branch C
            # A or YARD → A1 (same physical spot on demo), no travel needed
            return "A1", "B"        # branch value doesn’t matter; authority will cap at A1

        parsed: List[Dict[str, object]] = []
        for tid, t_s, origin, dest in rows:
            tid = str(tid).strip()
            if not tid:
                continue
            try:
                t_val = int(t_s)
            except Exception:
                continue
            start_block = origin_to_start_block(origin)
            dest_block, branch = dest_to_block(dest)
            parsed.append({
                "tid": tid,
                "t": t_val,
                "start_block": start_block,
                "branch": branch,         # used to set desired_branch (B)
                "dest_block": dest_block, # authority cap target
                "spawned": False,
            })
        self._route_schedule = sorted(parsed, key=lambda r: int(r["t"]))
        self._schedule_clock_s = 0
        # destinations mapping will be set when each train actually spawns
        return len(self._route_schedule)

    def clear_route_schedule(self) -> None:
        self._route_schedule = []
        self._schedule_clock_s = 0
        self._dest_by_tid.clear()



    # Per-train manual override from UI. Converts meters→blocks and forwards to stub.
    #*****
    # CTC_backend.py  (inside TrackState)
    #Stores temporary or persistent train overrides (manual speed, authority).
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


    #Receives a live snapshot from the stub (all block & train states)
    #and updates the backend’s Block objects for the UI tables. 
    """Updates occupancy (“free”, “occupied”, “closed”)
        Syncs signal lights, switches, broken rails, and beacons
        Updates crossing status for blocks that have crossings"""
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
            print(f"[Backend DEBUG] {key} occupancy={occ}")
            if occ.lower() in ("occupied", "true", "yes", "1"):
                blk.status = "occupied"
            elif occ.lower() in ("closed"):
                blk.status = "closed"
            else:
                blk.status = "free"
            print(f"[Backend DEBUG] Block {key} → {blk.status}")

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

    # One UI tick:
    # 1) push any overrides to stub
    # 2) tell stub to advance movement
    # 3) compute CTC policy using the fresh snapshot
    # 4) broadcast updated state to UI 

    """This runs every UI tick (e.g., once per second):
        Advances the global clock
        ***Syncs time to other modules (commented for now)
        Spawns new trains if their scheduled start time has arrived
        Computes and applies new speed/authority policy
        Applies manual overrides
        Advances the stub (tick())
        Broadcasts updated snapshot → UI
        This is the central event loop of your simulation."""
    def simulation_tick(self):
        # === Global Clock Update ===
        # Every simulation tick, the CTC backend advances the universal simulation clock.
        # This ensures that all modules share the exact same simulated time reference each update.
        clock.tick()

       # -------------------------------------------------------
        # Future integration hooks 
        # When other subsystems are ready, uncomment these lines.
        # They will notify each module that the simulation time has advanced.
        # -------------------------------------------------------
        # if hasattr(self, "trackModel") and self.trackModel:
        #   self.trackModel.set_time(clock.get_time())
        #if hasattr(self, "trackControllerHW") and self.trackControllerHW:
        #    self.trackControllerHW.set_time(clock.get_time())
        #if hasattr(self, "trackControllerSW") and self.trackControllerSW:
        #    self.trackControllerSW.set_time(clock.get_time())
        #if hasattr(self, "trainModel") and self.trainModel:
        #    self.trainModel.set_time(clock.get_time())
        #if hasattr(self, "trainControllerHW") and self.trainControllerHW:
        #    self.trainControllerHW.set_time(clock.get_time())
        #if hasattr(self, "trainControllerSW") and self.trainControllerSW:
        #    self.trainControllerSW.set_time(clock.get_time())
        # -------------------------------------------------------

        # (temporary) print to confirm time advancing
        print(f"[CTC Clock] Simulation time: {clock}")

        if not self._stub:
            return

        # ---- Route schedule clock & spawns ----
        self._schedule_clock_s += 1




        # spawn any due trains (not yet spawned and start_time <= clock)
        if self._route_schedule:
            for row in self._route_schedule:
                if row.get("spawned"):
                    continue
                if int(row["t"]) <= self._schedule_clock_s:
                    tid        = str(row["tid"])
                    start_blk  = str(row["start_block"])
                    branch     = str(row["branch"])       # e.g., "B"
                    dest_block = str(row["dest_block"])   # e.g., "B10" or "A1"

                    # create the train with branch intent; stub will set desired_branch
                    self._stub.add_train(tid, start_blk, branch)

                    # remember destination so policy can cap authority in _policy_tick()
                    self._dest_by_tid[tid] = dest_block

                    row["spawned"] = True

        # 1) Compute policy using the last snapshot (uses _dest_by_tid to cap authority)
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
    def _get_destination_block_for_train_on(self, cur_block: str) -> Optional[str]:
        # Find the train occupying cur_block, then return its destination block (if any)
        for t in self._last_snapshot.get("trains", []):
            if str(t.get("block", "")) == str(cur_block):
                tid = str(t.get("train_id", ""))
                return self._dest_by_tid.get(tid)
        return None

    """Implements the CTC’s automatic decision-making:
        Looks at snapshot (occupancy, broken rails, signals)
        Determines suggested speed:
        Red/occupied/broken → 0 m/s
        Yellow → 60% line speed
        Green → full speed
        Computes authority (m) by scanning ahead until an obstacle
        Applies overrides if active
        Sends both to stub for each train"""
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
            
            # --- Optional fallback ---
            #  simplified version ignores signals, occupancy, or safety conditions.
            #  simply commands a constant cruise speed for the train

            # Example constant speed in m/s (≈70 km/h)
            # LINE_SPEED_LIMIT_MPS = 19.4  # Uncomment if you want a faster constant speed
            # constant_speed_mps = 19.4

            # for t in self._last_snapshot.get("trains", []):
            #     tid = str(t["train_id"])
            #     cur = str(t["block"])
            #
            #     # Use the same constant speed for every train, unless it's at end-of-line
            #     if cur in EOL:
            #         speed_mps = 0.0
            #     else:
            #         speed_mps = constant_speed_mps
            #
            #     # Forward suggestion to the Track Controller (or stub)
            #     self.set_suggested_speed(tid, speed_mps)
            #
            #     # Authority is still computed dynamically (safe stopping distance)
            #     dest_blk = self._get_destination_block_for_train_on(cur)
            #     authority_m = self._lookahead_authority_m(cur, switches, occ_map, broken_map)
            #     self.set_suggested_authority(tid, authority_m)

            # --- End of optional fallback ---


            # --- authority lookahead ---
            dest_blk = self._get_destination_block_for_train_on(cur)
            authority_m = self._lookahead_authority_m(cur, switches, occ_map, broken_map)

            # --- apply ONLY sticky speed override here ---
            ov = self._overrides.get(tid, {})
            if ov.get("enabled", False) and "speed_mps" in ov:
                speed_mps = float(ov["speed_mps"])

            # send to stub or track controller 
            self.set_suggested_speed(tid, speed_mps)
            self.set_suggested_authority(tid, authority_m)


     # Compute the next block given current block and active switch positions
    
    """These handle track topology logic — determining where a train goes next and how far it can move safely.
        _next_block: chooses the next block given current and switches
        _lookahead_authority_m: walks forward through track list until end, obstacle, or destination, summing meters
        _get_desired_branch_for_train: reads a train’s intended path (B or C)
        _succ_in_chain: gets the next item in a linear chain like ["A1", "A2", ...]"""
    
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
    def _lookahead_authority_m(
        self,
        cur: str,
        switches: Dict[str, str],
        occ_map: Dict[str, str],
        broken_map: Dict[str, bool],
        dest_block: Optional[str] = None
    ) -> float:
        path: List[str] = []
        nxt = cur
        while True:
            nxt = self._next_block(nxt, switches)
            if nxt is None:
                break
            path.append(nxt)
            # stop path if destination is reached
            if dest_block and nxt == dest_block:
                break
            if nxt in EOL:
                break

        if SAFETY_BLOCKS > 0 and len(path) > 0:
            path = path[:-SAFETY_BLOCKS] if len(path) > SAFETY_BLOCKS else []

        total_m = 0.0
        for b in path:
            if occ_map.get(b, "free") in ("closed", "occupied"):
                break
            if broken_map.get(b, False):
                break
            total_m += BLOCK_LEN_M
        return total_m


    def _get_desired_branch_for_train(self, cur_block: str) -> str:
        for t in self._last_snapshot.get("trains", []):
            if str(t["block"]) == cur_block:
                return str(t.get("desired_branch", "B")).upper()
        return "B"
    
    #REMOVED SCENARIO_LOAD
   
    @staticmethod
    # Utility: successor inside a linear chain;
    def _succ_in_chain(b: str, chain: List[str], wrap_to: Optional[str] = None) -> Optional[str]:
        i = chain.index(b)
        if i + 1 < len(chain):
            return chain[i + 1]
        return wrap_to

 
 # Test to see if the global clock works 
if __name__ == "__main__":
    from time import sleep
    print("Starting clock test...")
    for i in range(5):
        clock.tick()
        print(f"Tick {i+1}: {clock}")
        sleep(1)

if __name__ == "__main__":
    blocks = load_green_line_csv()
    print(f"First 5 blocks: {blocks[:5]}")

    