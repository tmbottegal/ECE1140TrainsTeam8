from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math

from .track_controller_stub import TrackControllerStub

#Global Policies 
BLOCK_LEN_M: float = 50.0
LINE_SPEED_LIMIT_MPS: float = 13.9
YELLOW_FACTOR: float = 0.60
SAFETY_BLOCKS: int = 0
CONTROL_SIGNALS = {"B6", "C11"}

#Line topology 
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
    signal: str
    switch: str
    light: str
    crossing: str
    maintenance: str

# -------------------------
# TrackState: CTC backend facade
# - Owns the current line's block list
# - Maintains a fast index by block key 
# - Hosts the TrackControllerStub and applies its snapshots to UI data
# - Computes policy each tick (speeds/authority) and forwards to stub
# -------------------------
class TrackState:
    def __init__(self, line_name: str, line_tuples: List[Tuple]):
        self.line_name = line_name
        self._lines: Dict[str, List[Block]] = {}            #list of block object 
        self._by_key: Dict[str, Block] = {}                 #each block 
        self._stub: Optional[TrackControllerStub] = None    #sim peer 

        self._last_snapshot: Dict[str, object] = {}
        self._overrides: Dict[str, Dict[str, object]] = {}

        self.set_line(line_name, line_tuples)

    # Replace the active line and rebuild indexes; (re)attach stub and subscribe to its updates
    def set_line(self, name: str, tuples: List[Tuple]):
        self.line_name = name
        blocks = [Block(*t) for t in tuples]
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
            key = f"{b.line}{b.block_id}"
            self._by_key[key] = b

    # ----- UI -> backend (forward to stub) -----
    #Mark/unmark a block under maintainace closed or setting it back 
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
    def set_train_override(self, tid: str, enabled: bool, speed_mps: Optional[float] = None,authority_m: Optional[float] = None,) -> None:
        # Convert meters → blocks (using your global/block constant)
        blocks: Optional[int] = None
        if authority_m is not None:
            try:
                meters = float(authority_m)
            except (TypeError, ValueError):
                meters = 0.0
            # Use your project constant instead of a magic 50.0
            blocks = max(0, int(round(meters / BLOCK_LEN_M)))

        # Singular per-train API (fixes earlier crash when plural signature was used)****
        self._stub.set_train_override(
            str(tid),
            bool(enabled),
            speed_mps=speed_mps,
            authority_blocks=blocks,
        )

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
            blk.maintenance = "Broken" if pb.get("broken_rail", False) else str(pb.get("beacon", "") or "")
            blk.crossing = "True" if bool(pb.get("crossing", False)) else ""

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
        if self._stub:
            self._stub.set_train_overrides(self._overrides)
            self._stub.tick()         #  run movement first to update snapshot
            self._policy_tick()       #  now we can plan using fresh snapshot
            self._stub.broadcast()   

    #deciding suggested speed and suggested authority 
    def _policy_tick(self):
        if not self._last_snapshot:
            print("[CTC backend]  No snapshot yet — skipping policy tick.")
            return

        switches = dict(self._last_snapshot.get("switches", {}))
        blocks_payload: List[Dict[str, object]] = self._last_snapshot.get("blocks", [])
        occ_map = {b["key"]: b.get("occupancy", "free") for b in blocks_payload}
        broken_map = {b["key"]: bool(b.get("broken_rail", False)) for b in blocks_payload}
        light_map = {b["key"]: str(b.get("signal", "")) for b in blocks_payload}

        for t in self._last_snapshot.get("trains", []):
            tid = str(t["train_id"])
            cur = str(t["block"])
            nxt = self._next_block(cur, switches)

            if nxt is None or cur in EOL:
                speed_mps = 0.0
            else:
                nxt_occ = occ_map.get(nxt, "free")
                nxt_broken = broken_map.get(nxt, False)
                nxt_light = light_map.get(nxt, "")
                if nxt_occ in ("closed", "occupied") or nxt_broken or nxt_light == "RED":
                    speed_mps = 0.0
                elif nxt_light == "YELLOW":
                    speed_mps = LINE_SPEED_LIMIT_MPS * YELLOW_FACTOR
                else:
                    speed_mps = LINE_SPEED_LIMIT_MPS

            authority_m = self._lookahead_authority_m(cur, switches, occ_map, broken_map)

            ov = self._overrides.get(tid, {})
            if ov.get("enabled", False):
                speed_mps = float(ov.get("speed_mps", speed_mps))
                authority_m = float(ov.get("authority_m", authority_m))

            self.set_suggested_speed(tid, speed_mps)
            self.set_suggested_authority(tid, authority_m)

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