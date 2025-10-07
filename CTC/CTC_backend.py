# CTC_backend.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math

from .track_controller_stub import TrackControllerStub

BLOCK_LEN_M: float = 50.0
LINE_SPEED_LIMIT_MPS: float = 13.9
YELLOW_FACTOR: float = 0.60
SAFETY_BLOCKS: int = 0

A_CHAIN = ["A1", "A2", "A3", "A4", "A5"]
B_CHAIN = ["B6", "B7", "B8", "B9", "B10"]
C_CHAIN = ["C11", "C12", "C13", "C14", "C15"]
EOL = {"B10", "C15"}

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

class TrackState:
    def __init__(self, line_name: str, line_tuples: List[Tuple]):
        self.line_name = line_name
        self._lines: Dict[str, List[Block]] = {}
        self._by_key: Dict[str, Block] = {}
        self._stub: Optional[TrackControllerStub] = None

        self._last_snapshot: Dict[str, object] = {}
        self._overrides: Dict[str, Dict[str, object]] = {}

        self.set_line(line_name, line_tuples)

    def set_line(self, name: str, tuples: List[Tuple]):
        self.line_name = name
        blocks = [Block(*t) for t in tuples]
        self._lines[name] = blocks
        self._rebuild_index()
        self._stub = TrackControllerStub(name, tuples)
        self._stub.on_status(self.apply_snapshot)

    def get_blocks(self) -> List[Block]:
        return self._lines.get(self.line_name, [])

    def _rebuild_index(self):
        self._by_key.clear()
        for b in self.get_blocks():
            key = f"{b.line}{b.block_id}"
            self._by_key[key] = b

    # ----- UI -> backend (forward to stub) -----
    def set_status(self, bid: str, new_status: str):
        if self._stub:
            self._stub.set_block_maintenance(bid, new_status == "closed")

    def set_suggested_speed(self, tid: str, mps: float):
        if self._stub:
            self._stub.set_suggested_speed(tid, mps)

    def set_suggested_authority(self, tid: str, meters: float):
        if not self._stub:
            return
        blocks = max(0, math.ceil(float(meters) / BLOCK_LEN_M))
        self._stub.set_suggested_authority(tid, blocks)

    def set_switch(self, switch_id: str, position: str):
        if self._stub:
            self._stub.set_switch(switch_id, position)

    def set_broken_rail(self, block_key: str, broken: bool):
        if self._stub:
            self._stub.set_broken_rail(block_key, broken)

    def add_train(self, train_id: str, start_block: str):
        if self._stub:
            self._stub.add_train(train_id, start_block)

    # NEW: auto-line control pass-through
    def set_auto_line(self, enabled: bool):
        if self._stub:
            self._stub.set_auto_line(bool(enabled))

    # ----- test-bench resets -----
    def reset_trains(self):
        if self._stub:
            self._stub.reset_trains()

    def reset_infrastructure(self):
        if self._stub:
            self._stub.reset_infrastructure()

    def reset_all(self):
        if self._stub:
            self._stub.reset_all()

    # ----- Dispatcher overrides -----
    def set_train_override(self, tid: str, enabled: bool, *, speed_mps: Optional[float] = None,
                           authority_m: Optional[float] = None):
        self._overrides.setdefault(tid, {})
        self._overrides[tid]["enabled"] = bool(enabled)
        if speed_mps is not None:
            self._overrides[tid]["speed_mps"] = max(0.0, float(speed_mps))
        if authority_m is not None:
            self._overrides[tid]["authority_m"] = max(0.0, float(authority_m))

    # ----- telemetry from stub -----
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

    def get_trains(self) -> List[Dict[str, object]]:
        return list(self._last_snapshot.get("trains", []))

    def _advance_one_step(self):
        pass

    def stub_tick(self):
        if self._stub:
            # 🧠 NEW: Forward current manual overrides to the Track Controller Stub
            self._stub.set_train_overrides(self._overrides)

            # 🧠 Apply policy (calculates suggested speed & authority)
            self._policy_tick()

            # 🚄 Then simulate the physical movement in the stub
            self._stub.tick()


    # ----- policy -----
    def _policy_tick(self):
        if not self._last_snapshot:
            return
        switches = dict(self._last_snapshot.get("switches", {}))
        blocks_payload: List[Dict[str, object]] = self._last_snapshot.get("blocks", [])
        occ_map = {b["key"]: b.get("occupancy", "free") for b in blocks_payload}
        broken_map = {b["key"]: bool(b.get("broken_rail", False)) for b in blocks_payload}
        light_map = {b["key"]: str(b.get("signal", "")) for b in blocks_payload}

        for t in self._last_snapshot.get("trains", []):
            tid = str(t["train_id"]); cur = str(t["block"])
            nxt = self._next_block(cur, switches)
            # speed
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
            # authority
            authority_m = self._lookahead_authority_m(cur, switches, occ_map, broken_map)

            ov = self._overrides.get(tid, {})
            if ov.get("enabled", False):
                speed_mps = float(ov.get("speed_mps", speed_mps))
                authority_m = float(ov.get("authority_m", authority_m))

            self.set_suggested_speed(tid, speed_mps)
            self.set_suggested_authority(tid, authority_m)

    def _next_block(self, cur: str, switches: Dict[str, str]) -> Optional[str]:
        if cur in A_CHAIN:
            if cur != "A5":
                return self._succ_in_chain(cur, A_CHAIN)
            pos = (switches.get("SW1") or "STRAIGHT").upper()
            return "B6" if pos == "STRAIGHT" else "C11"
        if cur in B_CHAIN:
            return self._succ_in_chain(cur, B_CHAIN, wrap_to=None)
        if cur in C_CHAIN:
            return self._succ_in_chain(cur, C_CHAIN, wrap_to=None)
        return None

    def _lookahead_authority_m(self, cur: str, switches: Dict[str, str],
                               occ_map: Dict[str, str], broken_map: Dict[str, bool]) -> float:
        path: List[str] = []
        nxt = self._next_block(cur, switches)
        while nxt is not None:
            path.append(nxt)
            if nxt in EOL:
                break
            nxt = self._next_block(nxt, switches)
        if SAFETY_BLOCKS > 0 and len(path) > 0:
            path = path[:-SAFETY_BLOCKS] if len(path) > SAFETY_BLOCKS else []
        total_m = 0.0
        for b in path:
            if occ_map.get(b, "free") in ("closed", "occupied"): break
            if broken_map.get(b, False): break
            total_m += BLOCK_LEN_M
        return total_m

    @staticmethod
    def _succ_in_chain(b: str, chain: List[str], wrap_to: Optional[str] = None) -> Optional[str]:
        i = chain.index(b)
        if i + 1 < len(chain):
            return chain[i + 1]
        return wrap_to