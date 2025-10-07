# track_controller_stub.py
from __future__ import annotations
from typing import Callable, Dict, List, Optional, Tuple

Snapshot = Dict[str, object]

# ---- demo speed policy constants (used by stub to show realistic speeds) ----

BLOCK_LEN_M = 50.0 # each block = 50 meters
LINE_SPEED_LIMIT_KMPH = 50
LINE_SPEED_LIMIT_MPS  = LINE_SPEED_LIMIT_KMPH * 1000.0 / 3600.0  # ≈13.8889 m/s
YELLOW_FACTOR = 0.60

# Only these blocks have signals on Blue:
CONTROL_SIGNALS = {"B6", "C11"}


class TrackControllerStub:
    def __init__(self, line_name: str, line_tuples: List[Tuple]):
        self.line_name = line_name

        # Metadata from layout
        self._order: List[str] = []
        self._station: Dict[str, str] = {}
        self._track_status: Dict[str, str] = {}
        self._switch_of_block: Dict[str, str] = {}
        self._has_crossing: Dict[str, bool] = {}
        self._beacon: Dict[str, str] = {}
        self._overrides: Dict[str, Dict[str, object]] = {}  # 🧠 NEW


        for t in line_tuples:
            sec, bid, status, station, track_status, sw, light, crossing, maintenance = t
            key = f"{sec}{bid}"
            self._order.append(key)
            self._station[key] = station or ""
            self._track_status[key] = track_status or "Open"
            self._switch_of_block[key] = sw or ""
            self._has_crossing[key] = (str(crossing).strip().lower() == "true")
            self._beacon[key] = maintenance or ""

        # --- Explicit topology (A → B or A → C only) ---
        self._a_chain = ["A1", "A2", "A3", "A4", "A5"]
        self._b_chain = ["B6", "B7", "B8", "B9", "B10"]          # EOL at B10
        self._c_chain = ["C11", "C12", "C13", "C14", "C15"]      # EOL at C15
        self._eol = {"B10", "C15"}                               # end-of-line blocks

        # Dynamic state
        self._occupancy: Dict[str, str] = {k: "free" for k in self._order}
        # Only create signal state for the actual controlled signal blocks
        self._signals: Dict[str, str] = {b: "GREEN" for b in CONTROL_SIGNALS}

        self._crossing_active: Dict[str, bool] = {k: False for k in self._order if self._has_crossing.get(k, False)}

        self._switch_pos: Dict[str, str] = {}            # "SW1" -> "STRAIGHT"/"DIVERGE"
        self._manual_switch_lock: bool = False
        self._auto_line: bool = True                     # NEW: auto-line SW1 unless locked
        self._broken_rail: Dict[str, bool] = {k: False for k in self._order}
        self._closed_by_maintenance: Dict[str, bool] = {k: False for k in self._order}

        # Trains start at Yard side; each has a desired branch (used only by auto-line)
        self._trains: Dict[str, Dict[str, object]] = {
            "T1": {"block": "A1", "speed_mps": 10.0, "authority_blocks": 20, "desired_branch": "B"},
            "T2": {"block": "A2", "speed_mps": 10.0, "authority_blocks": 20, "desired_branch": "C"},
        }
        self._recompute_occupancy()

        self._status_cb: Optional[Callable[[Snapshot], None]] = None
        self._tick = 0
    
    def _suggest_speed_for_train(self, cur: str) -> float:
        nxt = self._next(cur)
        if nxt is None:
            return 0.0
        if self._occupancy.get(nxt) in ("closed", "occupied"):
            return 0.0
        if self._broken_rail.get(nxt, False):
            return 0.0
        
        aspect = (self._signals.get(cur) or "").upper()

        if aspect == "RED":
            return 0.0
        if aspect == "YELLOW":
            return LINE_SPEED_LIMIT_MPS * YELLOW_FACTOR
        return LINE_SPEED_LIMIT_MPS

    # ---------- registration ----------
    def on_status(self, callback: Callable[[Snapshot], None]) -> None:
        self._status_cb = callback

    # ---------- CTC commands ----------
    def set_suggested_speed(self, train_id: str, mps: float) -> None:
        if train_id in self._trains:
            self._trains[train_id]["speed_mps"] = float(max(0.0, mps))

    def set_suggested_authority(self, train_id: str, blocks: int) -> None:
        if train_id in self._trains:
            self._trains[train_id]["authority_blocks"] = int(max(0, blocks))

    def set_block_maintenance(self, block_key: str, closed: bool) -> None:
        if block_key in self._closed_by_maintenance:
            self._closed_by_maintenance[block_key] = bool(closed)
            self._recompute_occupancy()

    def set_switch(self, switch_id: str, position: str) -> None:
        if switch_id:
            self._switch_pos[switch_id] = position.upper()
            self._manual_switch_lock = True  # user locked

    def unlock_switches(self) -> None:
        self._manual_switch_lock = False

    def set_broken_rail(self, block_key: str, broken: bool) -> None:
        if block_key in self._broken_rail:
            self._broken_rail[block_key] = bool(broken)

    def add_train(self, train_id: str, start_block: str, desired_branch: str = "B") -> None:
        if start_block in self._order:
            self._trains[train_id] = {
                "block": start_block, "speed_mps": 0.0, "authority_blocks": 0,
                "desired_branch": "B" if desired_branch.upper().startswith("B") else "C"
            }
            self._recompute_occupancy()

    # NEW: enable/disable automatic lining of SW1
    def set_auto_line(self, enabled: bool) -> None:
        self._auto_line = bool(enabled)
    
    def _is_blocked(self, blk: Optional[str]) -> bool:
        """Unsafe if missing/EOL, occupied/closed, or broken."""
        if blk is None:
            return True
        if self._occupancy.get(blk) in ("closed", "occupied"):
            return True
        if self._broken_rail.get(blk, False):
            return True
        return False

    def _aspect_at_signal(self, sig_blk: str) -> str:
        """
        3-aspect at the *signal block* only:
        - RED    if the block beyond the signal (following current switch) is unsafe
        - YELLOW if that block is safe but the following block is unsafe
        - GREEN  otherwise
        """
        nxt  = self._next(sig_blk)   # respects current switch alignment
        if self._is_blocked(nxt):
            return "RED"
        nxt2 = self._next(nxt)
        if self._is_blocked(nxt2):
            return "YELLOW"
        return "GREEN"

    def _distance_to_next_control_signal(self, cur: str, max_look: int = 6) -> tuple[int | None, str | None]:
        """
        Walk forward following _next() until you hit B6 or C11.
        Returns (distance_in_blocks, signal_block) or (None, None) if no signal ahead within max_look.
        """
        seen = set()
        blk = cur
        for d in range(0, max_look + 1):
            if blk in CONTROL_SIGNALS:
                return d, blk
            seen.add(blk)
            blk = self._next(blk)
            if blk is None or blk in seen:
                break
        return None, None

    # ===== Resets for Test Bench =====
    def reset_trains(self) -> None:
        """Put trains back at Yard with fresh authority; B/C split demo ready."""
        self._trains = {
            "T1": {"block": "A1", "speed_mps": 10.0, "authority_blocks": 20, "desired_branch": "B"},
            "T2": {"block": "A2", "speed_mps": 10.0, "authority_blocks": 20, "desired_branch": "C"},
        }
        self._recompute_occupancy()
        self._recompute_signals()
        self._recompute_crossings()

    def reset_infrastructure(self) -> None:
        """Reopen blocks, clear broken rails, and line SW1 STRAIGHT; unlock manual lock."""
        for k in self._closed_by_maintenance:
            self._closed_by_maintenance[k] = False
        for k in self._broken_rail:
            self._broken_rail[k] = False
        self._manual_switch_lock = False
        self._auto_line = True                         # restore auto-line
        self._switch_pos["SW1"] = "STRAIGHT"
        self._recompute_occupancy()
        self._recompute_signals()
        self._recompute_crossings()

    def reset_all(self) -> None:
        """Full clean slate."""
        self._tick = 0
        self.reset_infrastructure()
        self.reset_trains()
    def broadcast(self) -> None:
        """Send a snapshot without advancing simulation."""
        if self._status_cb:
            self._status_cb(self._make_snapshot())
    
    
    # ---------- simulation ----------
    def tick(self) -> None:
        self._tick += 1

        # Auto-line SW1 for approaching trains (optional) unless user locked it
        if self._auto_line and not self._manual_switch_lock:
            for tid in sorted(self._trains.keys()):
                cur = self._trains[tid]["block"]
                branch = str(self._trains[tid].get("desired_branch", "B")).upper()
                if cur in ("A4", "A5"):
                    self._switch_pos["SW1"] = "STRAIGHT" if branch == "B" else "DIVERGE"

        # Move trains (stop at EOL — no wrap)
                # Move trains (stop at EOL — no wrap)
        for tid in sorted(self._trains.keys()):
            cur = self._trains[tid]["block"]
            if cur in self._eol:
                self._trains[tid]["authority_blocks"] = 0
                continue

            auth = int(self._trains[tid]["authority_blocks"] or 0)
            if auth <= 0:
                # make sure snapshot always has the visible value
                self._trains[tid]["authority_blocks"] = 0
                continue

            # apply overrides
            ov = self._overrides.get(tid, {})
            if ov.get("enabled", False):
                if "speed_mps" in ov:
                    self._trains[tid]["speed_mps"] = float(ov["speed_mps"])
                if "authority_blocks" in ov:
                    auth = int(ov["authority_blocks"])

            # <-- publish the (possibly overridden) authority so UI sees it even if we don't move
            self._trains[tid]["authority_blocks"] = auth

            nxt = self._next_for_train(tid, cur)

            if nxt and self._is_enterable(nxt) and not self._is_occupied(nxt):
                self._trains[tid]["block"] = nxt
                # decrement only on successful advance
                self._trains[tid]["authority_blocks"] = max(0, auth - 1)
            elif nxt is None:
                self._trains[tid]["authority_blocks"] = 0


        self._recompute_occupancy()
        self._recompute_signals()
        self._recompute_crossings()

        # ---- set per-train suggested speed for UI visibility (policy inside stub) ----
        for tid, info in self._trains.items():
            cur = str(info["block"])
            suggested = self._suggest_speed_for_train(cur)

            # Display actual suggested speed if there's a valid move ahead
            if suggested > 0.0:
                info["speed_mps"] = suggested
            # Only force 0 if there's no possible next block or auth is gone
            elif info["block"] in self._eol or info["authority_blocks"] <= 0:
                info["speed_mps"] = 0.0
            # Otherwise: keep last known speed until move occurs
            else:
                info["speed_mps"] = suggested

            # ✅ fix: always push correct authority to the snapshot
            self._trains[tid]["authority_blocks"] = self._trains[tid].get("authority_blocks", 0)

        # then broadcast snapshot once for all trains
        if self._status_cb:
            self._status_cb(self._make_snapshot())


    # ---------- derived state ----------
    def _recompute_occupancy(self) -> None:
        for b in self._order:
            closed = self._closed_by_maintenance[b] or (self._track_status.get(b, "Open") == "Closed")
            self._occupancy[b] = "closed" if closed else "free"
        for tinfo in self._trains.values():
            b = tinfo["block"]
            if self._occupancy.get(b) != "closed":
                self._occupancy[b] = "occupied"
    
    def set_train_overrides(self, overrides: Dict[str, Dict[str, object]]) -> None:
        """Receives manual override settings from the CTC backend."""
        self._overrides = overrides or {}


    def _recompute_signals(self) -> None:
        """ABS-style two-block look-ahead at B6 (5→6→7) and C11 (5→11→12)."""

        def is_clear(b: str) -> bool:
            if b not in self._order:
                return False
            if self._occupancy.get(b) in ("occupied", "closed"):
                return False
            if self._broken_rail.get(b, False):
                return False
            return True

        sw1 = (self._switch_pos.get("SW1", "STRAIGHT") or "STRAIGHT").upper()

        # ----- Signal at B6: governs 5→6→7 (requires SW1 = STRAIGHT) -----
        if "B6" in CONTROL_SIGNALS:
            if sw1 != "STRAIGHT":
                self._signals["B6"] = "RED"
            else:
                first, second = "B6", "B7"
                if not is_clear(first):
                    self._signals["B6"] = "RED"
                elif not is_clear(second):
                    self._signals["B6"] = "YELLOW"
                else:
                    self._signals["B6"] = "GREEN"

        # ----- Signal at C11: governs 5→11→12 (requires SW1 = DIVERGE) -----
        if "C11" in CONTROL_SIGNALS:
            if sw1 != "DIVERGE":
                self._signals["C11"] = "RED"
            else:
                first, second = "C11", "C12"
                if not is_clear(first):
                    self._signals["C11"] = "RED"
                elif not is_clear(second):
                    self._signals["C11"] = "YELLOW"
                else:
                    self._signals["C11"] = "GREEN"


    def _recompute_crossings(self) -> None:
        active = {}
        occ = {b for b, s in self._occupancy.items() if s == "occupied"}
        # Crossing near A3: treat A2/A3/A4 neighborhood
        for b, has in self._has_crossing.items():
            if not has:
                continue
            if b == "A3":
                neighbors = {"A2", "A3", "A4"}
            else:
                neighbors = {b}
            active[b] = any(nb in occ for nb in neighbors)
        self._crossing_active = active

    # ---------- topology helpers ----------
    def _is_occupied(self, block_key: str) -> bool:
        return self._occupancy.get(block_key) == "occupied"

    def _is_enterable(self, block_key: str) -> bool:
        if block_key not in self._order:
            return False
        if self._occupancy.get(block_key) == "closed":
            return False
        if self._broken_rail.get(block_key, False):
            return False
        return True

    def _next_for_train(self, tid: str, cur: str) -> Optional[str]:
        """Route at A5 by PHYSICAL switch; None at end-of-line to stop."""
        if cur in self._a_chain:
            if cur != "A5":
                return self._succ_in_chain(cur, self._a_chain)
            # Follow the physical switch position at A5
            pos = self._switch_pos.get("SW1", "STRAIGHT").upper()
            return "B6" if pos == "STRAIGHT" else "C11"

        if cur in self._b_chain:
            return self._succ_in_chain(cur, self._b_chain, wrap_to=None)  # None if at B10

        if cur in self._c_chain:
            return self._succ_in_chain(cur, self._c_chain, wrap_to=None)   # None if at C15

        return None

    def _next(self, cur: str) -> Optional[str]:
        """Generic next() for signals; uses current switch position; None at EOL."""
        if cur in self._a_chain:
            if cur != "A5":
                return self._succ_in_chain(cur, self._a_chain)
            pos = self._switch_pos.get("SW1", "STRAIGHT").upper()
            return "B6" if pos == "STRAIGHT" else "C11"
        if cur in self._b_chain:
            return self._succ_in_chain(cur, self._b_chain, wrap_to=None)
        if cur in self._c_chain:
            return self._succ_in_chain(cur, self._c_chain, wrap_to=None)
        return None

    @staticmethod
    def _succ_in_chain(b: str, chain: List[str], wrap_to: Optional[str] = None) -> Optional[str]:
        i = chain.index(b)
        if i + 1 < len(chain):
            return chain[i + 1]
        return wrap_to

    # ---- suggested speed helper (stub-side policy for the demo) ----
    def _suggest_speed_for_train(self, cur: str) -> float:
        nxt = self._next_for_train(self._find_tid_at_block(cur), cur) if hasattr(self, "_find_tid_at_block") else self._next(cur)
        if nxt is None:
            return 0.0
        if self._occupancy.get(nxt) in ("occupied", "closed"):
            return 0.0
        if self._broken_rail.get(nxt, False):
            return 0.0

        # Only slow if the NEXT block is itself a controlled-signal block and it's YELLOW
        if nxt in CONTROL_SIGNALS and self._signals.get(nxt) == "YELLOW":
            return YELLOW_FACTOR * LINE_SPEED_LIMIT_MPS

        return LINE_SPEED_LIMIT_MPS



    # ---------- snapshot ----------
    def _make_snapshot(self) -> Snapshot:
        blocks_payload: List[Dict[str, object]] = []

        for b in self._order:
            sec, num = b[0], int(b[1:])

            blocks_payload.append({
                "key": b,
                "section": sec,
                "block_id": num,

                # Use .get() with defaults to avoid KeyError during early init
                "occupancy": self._occupancy.get(b, "free"),
                "station":   self._station.get(b, ""),

                # Only B6/C11 exist in self._signals; others will resolve to ""
                "signal":    self._signals.get(b, ""),

                # Metadata from static maps
                "switch":    self._switch_of_block.get(b, ""),

                # Crossings and faults
                "crossing":      bool(self._crossing_active.get(b, False)),
                "beacon":        self._beacon.get(b, ""),
                "broken_rail":   bool(self._broken_rail.get(b, False)),
            })

        # (Optional) include trains snapshot if your UI expects it
        trains_payload = []
        for tid, info in self._trains.items():
            trains_payload.append({
                "train_id": str(tid),                            # <-- was "id"
                "block":     info.get("block", ""),
                "suggested_speed_mps": float(info.get("speed_mps", 0.0)),
                "authority_blocks": int(info.get("authority_blocks", 0)),
            })


        return {
            "line": self.line_name,
            "tick": self._tick,
            "blocks": blocks_payload,
            "trains": trains_payload,
            "switch_pos": dict(self._switch_pos),   # e.g., {"SW1":"STRAIGHT"}
        }


        trains_payload = []
        for tid in self._trains:
            tinfo = self._trains[tid]
            trains_payload.append({
                "train_id": tid,
                "block": tinfo["block"],
                "suggested_speed_mps": float(tinfo.get("speed_mps", 0.0)),
                "authority_blocks": int(tinfo.get("authority_blocks", 0)),
                "desired_branch": str(tinfo.get("desired_branch", "B")),
            })


        return {
            "line": self.line_name,
            "blocks": blocks_payload,
            "switches": {k: v for k, v in self._switch_pos.items()},  # {"SW1":"STRAIGHT"/"DIVERGE"}
            "trains": trains_payload,
        }