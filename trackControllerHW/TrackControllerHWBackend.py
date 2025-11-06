# TrackControllerHWBackend.py
from __future__ import annotations
import time, threading, logging
from typing import Dict, Tuple, Any, Callable, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# -------------------- Public enums & adapters (UI expects these) --------------------
class SignalState(str, Enum):
    RED = "Red"
    YELLOW = "Yellow"
    GREEN = "Green"

class TrackSegment:
    def __init__(self, block_id: int) -> None:
        self.block_id = block_id
        self.occupied = False
        self.signal_state: SignalState | str = "N/A"
    def set_occupancy(self, occ: bool) -> None:
        self.occupied = bool(occ)
    def set_signal_state(self, state: SignalState) -> None:
        self.signal_state = state

class TrackSwitch(TrackSegment):
    def __init__(self, block_id: int) -> None:
        super().__init__(block_id)
        self.current_position = 0
    def set_switch_position(self, pos: int) -> None:
        self.current_position = int(pos)

class LevelCrossing(TrackSegment):
    def __init__(self, block_id: int) -> None:
        super().__init__(block_id)
        self.gate_status = False
    def set_gate_status(self, closed: bool) -> None:
        self.gate_status = bool(closed)

class TrackModelAdapter:
    """Minimal local track-model so the backend can run standalone."""
    def __init__(self) -> None:
        self.segments: Dict[int, TrackSegment] = {}
    def ensure_blocks(self, ids: List[int]) -> None:
        for i in ids:
            if i not in self.segments:
                self.segments[i] = TrackSegment(i)
    def set_signal_state(self, block_id: int, state: SignalState) -> None:
        seg = self.segments.get(block_id)
        if seg:
            seg.set_signal_state(state)

# -------------------- Line partition (your HW ownership) --------------------
HW_LINE_BLOCK_MAP: Dict[str, range] = {
    "Blue Line":  range(1, 16),     # 1..15
    "Red Line":   range(74, 151),   # 74..150
    "Green Line": range(1, 151),    # 1..150
}

# -------------------- Unified Backend (standalone; no external imports) --------------------
class HardwareTrackControllerBackend:
    """
    Single, original backend that includes:
      - data/state for blocks, switches, crossings
      - suggested/commanded speed & authority
      - maintenance-mode protections
      - live polling loop and guard-block polling
      - simple PLC upload no-op (so UI never crashes)
    """
    def __init__(self, track_model: TrackModelAdapter, line_name: str = "Blue Line") -> None:
        # External handles
        self.track_model = track_model
        self.line_name = line_name

        # Event/listener system for the UI
        self._listeners: List[Callable[[], None]] = []

        # State exposed to UI
        self.switches: Dict[int, str] = {}            # switch_id -> "Normal"/"Alternate"
        self.switch_map: Dict[int, Tuple[int, ...]] = {}  # switch_id -> (root, straight, diverging)
        self.crossings: Dict[int, str] = {}           # crossing_id -> "Active"/"Inactive"
        self.crossing_blocks: Dict[int, int] = {}     # crossing_id -> block_id

        # Per-block telemetry/state caches
        self._known_occupancy: Dict[int, bool] = {}
        self._known_signal: Dict[int, SignalState] = {}

        # Per-block movement authority/speed (suggested/commanded)
        self._suggested_speed_mph: Dict[int, int] = {}
        self._suggested_auth_yd: Dict[int, int] = {}
        self._commanded_speed_mph: Dict[int, int] = {}
        self._commanded_auth_yd: Dict[int, int] = {}

        # Modes/threads
        self.maintenance_mode: bool = False
        self._live_thread_running = False

        # Cache my line blocks now for speed
        self._line_blocks = list(HW_LINE_BLOCK_MAP.get(self.line_name, []))

        # Guard blocks just outside our ownership (blind-spot mitigation)
        self._guard_blocks: List[int] = []
        rng = HW_LINE_BLOCK_MAP.get(self.line_name)
        if isinstance(rng, range):
            first, last = rng.start, rng.stop - 1
            before, after = first - 1, last + 1
            if before in self.track_model.segments: self._guard_blocks.append(before)
            if after  in self.track_model.segments: self._guard_blocks.append(after)
        self._guard_thread_running = False
        self._guard_poll_interval = 1.0

    # ---------- Listener handling ----------
    def add_listener(self, cb: Callable[[], None]) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                logger.exception("Listener raised")

    # ---------- Live link & polling ----------
    def start_live_link(self, poll_interval: float = 1.0) -> None:
        """Start background polling that mirrors the Track Model into this backend."""
        if self._live_thread_running:
            return
        self._live_thread_running = True

        def loop():
            while self._live_thread_running:
                try:
                    self._poll_track_model()
                except Exception:
                    logger.exception("poll loop")
                time.sleep(poll_interval)

        threading.Thread(target=loop, daemon=True).start()

        # Start guard polling if we have neighbors
        self._guard_poll_interval = max(0.25, float(poll_interval))
        if self._guard_blocks and not self._guard_thread_running:
            self._guard_thread_running = True
            threading.Thread(target=self._guard_loop, daemon=True).start()
            logger.info("Guard-block polling started for %s; guards=%s", self.line_name, self._guard_blocks)

    def stop_live_link(self) -> None:
        self._guard_thread_running = False
        self._live_thread_running = False
        logger.info("Live link stopped for %s", self.line_name)

    def _poll_track_model(self) -> None:
        """Mirror occupancy & signals from the track model, notify UI on change."""
        for b, seg in self.track_model.segments.items():
            # Occupancy
            occ = bool(getattr(seg, "occupied", False))
            if self._known_occupancy.get(b) != occ:
                self._known_occupancy[b] = occ
                # emit an 'update' without needing attribute type here
                self._notify_listeners()

            # Signals
            sig = getattr(seg, "signal_state", "N/A")
            if sig != "N/A" and self._known_signal.get(b) != sig:
                self._known_signal[b] = sig
                self._notify_listeners()

    def _guard_loop(self) -> None:
        while self._guard_thread_running:
            try:
                for gb in list(self._guard_blocks):
                    seg = self.track_model.segments.get(gb)
                    if not seg:
                        continue
                    occ = bool(getattr(seg, "occupied", False))
                    if self._known_occupancy.get(gb) != occ:
                        self._known_occupancy[gb] = occ
                        self._notify_listeners()
                    sig = getattr(seg, "signal_state", "N/A")
                    if sig != "N/A" and self._known_signal.get(gb) != sig:
                        self._known_signal[gb] = sig
                        self._notify_listeners()
            except Exception:
                logger.exception("Guard-block polling error")
            time.sleep(self._guard_poll_interval)

    # ---------- Public API used by the UI ----------
    def set_maintenance_mode(self, enabled: bool) -> None:
        self.maintenance_mode = bool(enabled)

    def safe_set_switch(self, switch_id: int, position: str) -> None:
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change switches")
        pos = position.title()
        if pos not in ("Normal", "Alternate"):
            raise ValueError("Invalid switch position")
        self.switches[switch_id] = pos
        self._notify_listeners()

    def safe_set_crossing(self, crossing_id: int, status: str) -> None:
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change crossings")
        stat = status.title()
        if stat not in ("Active", "Inactive"):
            raise ValueError("Invalid crossing status")
        self.crossings[crossing_id] = stat
        self._notify_listeners()

    def set_block_occupancy(self, block: int, status: bool) -> None:
        seg = self.track_model.segments.get(block)
        if seg:
            seg.set_occupancy(bool(status))
            self._known_occupancy[block] = bool(status)
            self._notify_listeners()

    def set_signal(self, block: int, color: str | SignalState) -> None:
        seg = self.track_model.segments.get(block)
        if not seg:
            return
        if isinstance(color, SignalState):
            state = color
        else:
            key = str(color).replace(" ", "").upper()
            if key not in ("RED", "YELLOW", "GREEN"):
                return  # silently ignore invalid text
            state = SignalState[key]
        seg.set_signal_state(state)
        self._known_signal[block] = state
        self._notify_listeners()

    def set_commanded_speed(self, block: int, speed_mph: int) -> None:
        self._commanded_speed_mph[block] = int(speed_mph)
        self._notify_listeners()

    def set_commanded_authority(self, block: int, auth_yd: int) -> None:
        self._commanded_auth_yd[block] = int(auth_yd)
        self._notify_listeners()

    def upload_plc(self, path: str) -> None:
        """Standalone no-op so the UI 'Upload PLC' never crashes."""
        logger.info("upload_plc: accepted %s (no-op in unified HW backend)", path)

    # ---------- Data exposure for UI ----------
    def get_line_block_ids(self) -> List[int]:
        # Always reflect HW ownership
        return list(HW_LINE_BLOCK_MAP.get(self.line_name, []))

    @property
    def blocks(self) -> Dict[int, Dict[str, object]]:
        """
        Structure the UI expects for each owned block:
          occupied: bool | "N/A"
          suggested_speed: int
          suggested_auth: int
          commanded_speed: int | "N/A"
          commanded_auth: int | "N/A"
          signal: SignalState | "N/A"
        """
        d: Dict[int, Dict[str, object]] = {}
        for b in self.get_line_block_ids():
            if b not in self.track_model.segments:
                continue
            cmd_spd  = int(self._commanded_speed_mph.get(b, 0)) or "N/A"
            cmd_auth = int(self._commanded_auth_yd.get(b, 0)) or "N/A"
            d[b] = {
                "occupied": self._known_occupancy.get(b, "N/A"),
                "suggested_speed": int(self._suggested_speed_mph.get(b, 50)),
                "suggested_auth": int(self._suggested_auth_yd.get(b, 50)),
                "commanded_speed": cmd_spd,
                "commanded_auth": cmd_auth,
                "signal": self._known_signal.get(b, "N/A"),
            }
        return d

    # ---------- Convenience test helper ----------
    def run_line_test(self, plc_path: str) -> Dict[str, Any]:
        self.set_maintenance_mode(True)
        self.upload_plc(plc_path)
        blocks = self.blocks
        return {
            "line": self.line_name,
            "switches": self.switches.copy(),
            "crossings": self.crossings.copy(),
            "signals_set": {
                b: (d["signal"].name.title() if hasattr(d["signal"], "name") else d["signal"])
                for b, d in blocks.items() if d.get("signal") not in (None, "N/A")
            },
            "commanded": {
                b: {"speed_mph": d["commanded_speed"], "auth_yd": d["commanded_auth"]}
                for b, d in blocks.items()
                if d.get("commanded_speed") != "N/A" or d.get("commanded_auth") != "N/A"
            },
        }

# Convenience for tests (same signature your code already uses)
def build_backend_for_sim(track_model: TrackModelAdapter, line_name: str = "Blue Line") -> HardwareTrackControllerBackend:
    return HardwareTrackControllerBackend(track_model, line_name=line_name)
