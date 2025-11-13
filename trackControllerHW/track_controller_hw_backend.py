from __future__ import annotations
import time, threading, logging
from typing import Dict, Tuple, Any, Callable, List, Optional
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# -------------------- Public enums & adapters (UI imports these) --------------------
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
        self.current_position = 0  # 0 = Normal, 1 = Alternate

    def set_switch_position(self, pos: int) -> None:
        self.current_position = int(pos)


class LevelCrossing(TrackSegment):
    def __init__(self, block_id: int) -> None:
        super().__init__(block_id)
        self.gate_status = False  # False = open/inactive, True = closed/active

    def set_gate_status(self, closed: bool) -> None:
        self.gate_status = bool(closed)


class TrackModelAdapter:
    """
    Minimal local track-model so the backend can run standalone.

    If you pass in the *real* track model backend instead, this class is ignored
    and we just duck-type against whatever object you give us (must expose
    .segments and, ideally, the same set_* methods).
    """
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

    def set_switch_position(self, switch_id: int, pos: int) -> None:
        # Standalone stub: switch state is not separately modeled here.
        logger.info("TrackModelAdapter.set_switch_position(%s, %s) [stub]", switch_id, pos)

    def set_gate_status(self, block_id: int, closed: bool) -> None:
        seg = self.segments.get(block_id)
        if isinstance(seg, LevelCrossing):
            seg.set_gate_status(closed)
        else:
            logger.info("TrackModelAdapter.set_gate_status(%s, %s) [stub]", block_id, closed)

    def broadcast_train_command(self, block_id: int, speed_mph: int, auth_yd: int) -> None:
        # Standalone stub: in a real system this would push to train/track model.
        logger.info(
            "TrackModelAdapter.broadcast_train_command(block=%s, speed_mph=%s, auth_yd=%s) [stub]",
            block_id, speed_mph, auth_yd
        )


# -------------------- Line partition (your HW ownership) --------------------
HW_LINE_BLOCK_MAP: Dict[str, range] = {
    "Blue Line":  range(1, 16),     # 1..15
    "Red Line":   range(74, 151),   # 74..150
    "Green Line": range(1, 151),    # 1..150
}


# -------------------- CTC interoperability types --------------------
@dataclass
class WaysideStatusUpdate:
    block_id: int
    occupied: bool | str
    signal_state: SignalState | str
    switch_position: Optional[str]
    crossing_status: Optional[str]


# -------------------- Unified Backend (standalone; no external imports) --------------------
class HardwareTrackControllerBackend:
    """
    Single, original backend that includes:
      - data/state for blocks, switches, crossings
      - suggested/commanded speed & authority (mph / yards)
      - maintenance-mode protections
      - live polling loop and guard-block polling
      - real PLC upload (Python + text) with simple conventions
      - optional CTC + track-model integration via duck-typing
    """
    def __init__(self, track_model: TrackModelAdapter, line_name: str = "Blue Line") -> None:
        self.track_model = track_model
        self.line_name = line_name

        self._listeners: List[Callable[[], None]] = []

        # Logical infrastructure (owned by this wayside)
        self.switches: Dict[int, str] = {}                 # switch_id -> "Normal"/"Alternate"
        self.switch_map: Dict[int, Tuple[int, ...]] = {}   # switch_id -> (root, straight, diverging)
        self.crossings: Dict[int, str] = {}                # crossing_id -> "Active"/"Inactive"
        self.crossing_blocks: Dict[int, int] = {}          # crossing_id -> block_id

        # Internal caches
        self._known_occupancy: Dict[int, bool] = {}
        self._known_signal: Dict[int, SignalState] = {}
        self._suggested_speed_mph: Dict[int, int] = {}
        self._suggested_auth_yd: Dict[int, int] = {}
        self._commanded_speed_mph: Dict[int, int] = {}
        self._commanded_auth_yd: Dict[int, int] = {}

        self.maintenance_mode: bool = False
        self._live_thread_running = False

        # CTC integration
        self.ctc_backend: Any | None = None
        self._ctc_update_enabled: bool = True

        # Our block range
        self._line_blocks = list(HW_LINE_BLOCK_MAP.get(self.line_name, []))

        # Guard blocks just outside our ownership (blind-spot mitigation)
        self._guard_blocks: List[int] = []
        rng = HW_LINE_BLOCK_MAP.get(self.line_name)
        if isinstance(rng, range):
            first, last = rng.start, rng.stop - 1
            before, after = first - 1, last + 1
            if before in getattr(self.track_model, "segments", {}):
                self._guard_blocks.append(before)
            if after in getattr(self.track_model, "segments", {}):
                self._guard_blocks.append(after)
        self._guard_thread_running = False
        self._guard_poll_interval = 1.0

        # If we're using the local adapter, make sure our blocks exist
        if hasattr(self.track_model, "ensure_blocks"):
            try:
                self.track_model.ensure_blocks(self._line_blocks)
            except Exception:
                logger.exception("ensure_blocks failed")

        # Initial read-back from the track model if possible
        self._initial_sync()

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

    # ---------- CTC integration ----------
    def set_ctc_backend(self, ctc_backend: Any) -> None:
        """Attach a CTC backend (any object with the expected methods)."""
        self.ctc_backend = ctc_backend

    def enable_ctc_updates(self, enabled: bool = True) -> None:
        """Globally enable/disable pushing status to CTC."""
        self._ctc_update_enabled = bool(enabled)

    def receive_ctc_suggestion(
        self,
        block: int,
        suggested_speed_mph: Optional[int] = None,
        suggested_auth_yd: Optional[int] = None,
    ) -> None:
        """
        Called by CTC to tell the wayside what it *wants* for speed/authority.
        We keep these separate from commanded values; UI can decide what to do.
        """
        b = int(block)
        if suggested_speed_mph is not None:
            self._suggested_speed_mph[b] = int(suggested_speed_mph)
        if suggested_auth_yd is not None:
            self._suggested_auth_yd[b] = int(suggested_auth_yd)
        self._notify_listeners()

    def _send_status_to_ctc(self) -> None:
        if not self.ctc_backend or not self._ctc_update_enabled:
            return

        updates: List[WaysideStatusUpdate] = []
        blocks = self.get_line_block_ids()

        for b in blocks:
            occ = self._known_occupancy.get(b, "N/A")
            sig = self._known_signal.get(b, "N/A")

            # Attach switch & crossing status if this block participates
            switch_pos: Optional[str] = None
            for switch_id, mapping in self.switch_map.items():
                if b in mapping:
                    switch_pos = self.switches.get(switch_id)
                    break

            crossing_status: Optional[str] = None
            for crossing_id, blk in self.crossing_blocks.items():
                if blk == b:
                    crossing_status = self.crossings.get(crossing_id)
                    break

            updates.append(
                WaysideStatusUpdate(
                    block_id=b,
                    occupied=occ,
                    signal_state=sig,
                    switch_position=switch_pos,
                    crossing_status=crossing_status,
                )
            )

        backend = self.ctc_backend
        try:
            if hasattr(backend, "receive_wayside_status"):
                backend.receive_wayside_status(self.line_name, updates)
            else:
                for u in updates:
                    self._send_single_status_to_ctc(u)
        except Exception:
            logger.exception("Error sending status to CTC")

    def _send_single_status_to_ctc(self, u: WaysideStatusUpdate) -> None:
        backend = self.ctc_backend
        if not backend:
            return

        try:
            if hasattr(backend, "update_block_occupancy"):
                backend.update_block_occupancy(self.line_name, u.block_id, u.occupied)
            if hasattr(backend, "update_signal_state"):
                backend.update_signal_state(self.line_name, u.block_id, u.signal_state)
            if u.switch_position is not None and hasattr(backend, "update_switch_position"):
                backend.update_switch_position(self.line_name, u.block_id, u.switch_position)
            if u.crossing_status is not None and hasattr(backend, "update_crossing_status"):
                backend.update_crossing_status(self.line_name, u.block_id, u.crossing_status)
        except Exception:
            logger.exception("CTC single-status update failed")

    # ---------- Track model sync helpers ----------
    def _initial_sync(self) -> None:
        """
        Seed occupancy and signals from the track model (if it has segments).
        """
        segments = getattr(self.track_model, "segments", {})
        if not isinstance(segments, dict):
            return

        changed = False
        for b in self._line_blocks:
            seg = segments.get(b)
            if not seg:
                continue

            occ = bool(getattr(seg, "occupied", False))
            if self._known_occupancy.get(b) != occ:
                self._known_occupancy[b] = occ
                changed = True

            sig = getattr(seg, "signal_state", "N/A")
            if sig != "N/A" and self._known_signal.get(b) != sig:
                self._known_signal[b] = sig
                changed = True

        if changed:
            self._notify_listeners()
            self._send_status_to_ctc()

    def _on_occupancy_change(self, block_id: int, occupied: bool) -> None:
        """
        Central handler when a block's occupancy changes.
        We enforce some safety rules here.
        """
        self._known_occupancy[block_id] = occupied

        # If this block has a crossing, auto-control the gate
        for crossing_id, blk in self.crossing_blocks.items():
            if blk == block_id:
                if occupied:
                    self.crossings[crossing_id] = "Active"
                    # Try to tell the track model too
                    try:
                        if hasattr(self.track_model, "set_gate_status"):
                            self.track_model.set_gate_status(blk, True)
                    except Exception:
                        logger.exception("Failed to set gate in track model for crossing %s", crossing_id)
                else:
                    # Only automatically inactivate if we had set it active before
                    if self.crossings.get(crossing_id) == "Active":
                        self.crossings[crossing_id] = "Inactive"
                        try:
                            if hasattr(self.track_model, "set_gate_status"):
                                self.track_model.set_gate_status(blk, False)
                        except Exception:
                            logger.exception("Failed to clear gate in track model for crossing %s", crossing_id)

        # Safety: drop authority on newly-occupied block
        if occupied:
            if block_id in self._commanded_auth_yd:
                self._commanded_auth_yd[block_id] = 0

    # ---------- Live link & polling ----------
    def start_live_link(self, poll_interval: float = 1.0) -> None:
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
        segments = getattr(self.track_model, "segments", {})
        if not isinstance(segments, dict):
            return

        changed_ctc = False

        # Poll all segments we know about (including guard blocks)
        for b, seg in segments.items():
            occ = bool(getattr(seg, "occupied", False))
            if self._known_occupancy.get(b) != occ:
                self._on_occupancy_change(b, occ)
                self._notify_listeners()
                changed_ctc = True

            sig = getattr(seg, "signal_state", "N/A")
            if sig != "N/A" and self._known_signal.get(b) != sig:
                self._known_signal[b] = sig
                self._notify_listeners()
                changed_ctc = True

        if changed_ctc:
            self._send_status_to_ctc()

    def _guard_loop(self) -> None:
        while self._guard_thread_running:
            try:
                segments = getattr(self.track_model, "segments", {})
                for gb in list(self._guard_blocks):
                    seg = segments.get(gb)
                    if not seg:
                        continue
                    occ = bool(getattr(seg, "occupied", False))
                    if self._known_occupancy.get(gb) != occ:
                        self._known_occupancy[gb] = occ
                        self._notify_listeners()
                        # Guard-block occupancy typically isn't sent to CTC, but we could if desired
            except Exception:
                logger.exception("Guard-block polling error")
            time.sleep(self._guard_poll_interval)

    # ---------- Public API used by the UI ----------
    def set_maintenance_mode(self, enabled: bool) -> None:
        self.maintenance_mode = bool(enabled)

    def _check_switch_clear_for_move(self, switch_id: int) -> None:
        """
        Safety: don't allow moving a switch if any of its connected blocks are occupied.
        """
        blocks = self.switch_map.get(switch_id, ())
        for b in blocks:
            if self._known_occupancy.get(b, False):
                raise PermissionError(f"Cannot move switch {switch_id}; block {b} is occupied")

    def safe_set_switch(self, switch_id: int, position: str) -> None:
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change switches")

        self._check_switch_clear_for_move(switch_id)

        pos = position.title()
        if pos not in ("Normal", "Alternate"):
            raise ValueError("Invalid switch position")

        # Update local state
        self.switches[switch_id] = pos

        # Try to tell the track model (if it supports it)
        try:
            if hasattr(self.track_model, "set_switch_position"):
                self.track_model.set_switch_position(switch_id, 0 if pos == "Normal" else 1)
        except Exception:
            logger.exception("Failed to set switch in track model")

        self._notify_listeners()
        self._send_status_to_ctc()

    def safe_set_crossing(self, crossing_id: int, status: str) -> None:
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change crossings")

        stat = status.title()
        if stat not in ("Active", "Inactive"):
            raise ValueError("Invalid crossing status")

        # Safety: don't inactivate crossing if its block is occupied
        block_id = self.crossing_blocks.get(crossing_id)
        if block_id is not None and stat == "Inactive":
            if self._known_occupancy.get(block_id, False):
                raise PermissionError(
                    f"Cannot inactivate crossing {crossing_id}; block {block_id} is occupied"
                )

        self.crossings[crossing_id] = stat

        try:
            if block_id is not None and hasattr(self.track_model, "set_gate_status"):
                self.track_model.set_gate_status(block_id, stat == "Active")
        except Exception:
            logger.exception("Failed to set crossing gate in track model")

        self._notify_listeners()
        self._send_status_to_ctc()

    def set_block_occupancy(self, block: int, status: bool) -> None:
        seg = getattr(self.track_model, "segments", {}).get(block)
        if seg:
            try:
                seg.set_occupancy(bool(status))
            except Exception:
                logger.exception("TrackSegment.set_occupancy failed for block %s", block)

        self._on_occupancy_change(block, bool(status))
        self._notify_listeners()
        self._send_status_to_ctc()

    def set_signal(self, block: int, color: str | SignalState) -> None:
        seg = getattr(self.track_model, "segments", {}).get(block)
        if not seg:
            return

        if isinstance(color, SignalState):
            state = color
        else:
            key = str(color).replace(" ", "").upper()
            if key not in ("RED", "YELLOW", "GREEN"):
                return  # silently ignore invalid text
            state = SignalState[key]

        try:
            if hasattr(seg, "set_signal_state"):
                seg.set_signal_state(state)
            elif hasattr(self.track_model, "set_signal_state"):
                self.track_model.set_signal_state(block, state)
        except Exception:
            logger.exception("Failed to set signal")

        self._known_signal[block] = state
        self._notify_listeners()
        self._send_status_to_ctc()

    def set_commanded_speed(self, block: int, speed_mph: int) -> None:
        self._commanded_speed_mph[block] = int(speed_mph)

        # Try to propagate to track model if it supports broadcast
        try:
            if hasattr(self.track_model, "broadcast_train_command"):
                auth = self._commanded_auth_yd.get(block, 0)
                self.track_model.broadcast_train_command(block, int(speed_mph), int(auth))
        except Exception:
            logger.exception("broadcast_train_command failed for speed")

        self._notify_listeners()

    def set_commanded_authority(self, block: int, auth_yd: int) -> None:
        self._commanded_auth_yd[block] = int(auth_yd)

        try:
            if hasattr(self.track_model, "broadcast_train_command"):
                spd = self._commanded_speed_mph.get(block, 0)
                self.track_model.broadcast_train_command(block, int(spd), int(auth_yd))
        except Exception:
            logger.exception("broadcast_train_command failed for authority")

        self._notify_listeners()

    # ---------- PLC upload ----------
    def upload_plc(self, path: str) -> None:
        """
        Upload and apply a PLC file.

        Supports:
          - Python PLC (.py): looks for simple globals:
              block_<id>_occupied     -> bool
              switch_<id>             -> "Normal"/"Alternate"/0/1
              crossing_<id>           -> "Active"/"Inactive"/True/False
              commanded_speed_<id>    or cmd_speed_<id> -> mph
              commanded_auth_<id>     or cmd_auth_<id>  -> yards
              signal_<id>             -> "Red"/"Yellow"/"Green"
          - Text PLC (other): each non-comment line is:
              SWITCH <id> <Normal|Alternate|0|1>
              CROSSING <id> <Active|Inactive|true|false>
              SIGNAL <block> <Red|Yellow|Green>
              CMD_SPEED <block> <mph>
              CMD_AUTH  <block> <yards>
        """
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to upload PLC")

        logger.info("upload_plc: %s", path)
        try:
            if path.lower().endswith(".py"):
                self._upload_plc_python(path)
            else:
                self._upload_plc_text(path)
        except FileNotFoundError:
            logger.error("PLC file not found: %s", path)
        except Exception:
            logger.exception("PLC upload failed for %s", path)

        # After PLC, notify UI + CTC
        self._notify_listeners()
        self._send_status_to_ctc()

    def _upload_plc_python(self, path: str) -> None:
        ns: Dict[str, Any] = {}
        with open(path, "r") as f:
            code = f.read()
        exec(code, ns, ns)  # PLC is trusted in this project

        for name, value in list(ns.items()):
            if name.startswith("__"):
                continue

            # block_XX_occupied
            if name.startswith("block_") and name.endswith("_occupied"):
                try:
                    block_id = int(name[len("block_") : -len("_occupied")])
                    self.set_block_occupancy(block_id, bool(value))
                except Exception:
                    logger.exception("Failed to apply PLC occupancy for %s", name)
                continue

            # switch_XX
            if name.startswith("switch_"):
                try:
                    switch_id = int(name[len("switch_") :])
                    pos_str = str(value).title()
                    if pos_str in ("0", "1"):
                        pos_str = "Normal" if pos_str == "0" else "Alternate"
                    self.safe_set_switch(switch_id, pos_str)
                except Exception:
                    logger.exception("Failed to apply PLC switch for %s", name)
                continue

            # crossing_XX
            if name.startswith("crossing_"):
                try:
                    crossing_id = int(name[len("crossing_") :])
                    val_str = str(value).title()
                    if val_str in ("True", "False"):
                        val_str = "Active" if value else "Inactive"
                    self.safe_set_crossing(crossing_id, val_str)
                except Exception:
                    logger.exception("Failed to apply PLC crossing for %s", name)
                continue

            # commanded_speed_XX or cmd_speed_XX
            if name.startswith("commanded_speed_") or name.startswith("cmd_speed_"):
                key = "commanded_speed_" if name.startswith("commanded_speed_") else "cmd_speed_"
                try:
                    block_id = int(name[len(key) :])
                    self.set_commanded_speed(block_id, int(value))
                except Exception:
                    logger.exception("Failed to apply PLC speed for %s", name)
                continue

            # commanded_auth_XX or cmd_auth_XX
            if name.startswith("commanded_auth_") or name.startswith("cmd_auth_"):
                key = "commanded_auth_" if name.startswith("commanded_auth_") else "cmd_auth_"
                try:
                    block_id = int(name[len(key) :])
                    self.set_commanded_authority(block_id, int(value))
                except Exception:
                    logger.exception("Failed to apply PLC authority for %s", name)
                continue

            # signal_XX
            if name.startswith("signal_"):
                try:
                    block_id = int(name[len("signal_") :])
                    self.set_signal(block_id, str(value))
                except Exception:
                    logger.exception("Failed to apply PLC signal for %s", name)
                continue

    def _upload_plc_text(self, path: str) -> None:
        with open(path, "r") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                cmd = parts[0].upper()
                try:
                    if cmd == "SWITCH" and len(parts) >= 3:
                        switch_id = int(parts[1])
                        pos = parts[2]
                        if pos in ("0", "1"):
                            pos = "Normal" if pos == "0" else "Alternate"
                        self.safe_set_switch(switch_id, pos)

                    elif cmd == "CROSSING" and len(parts) >= 3:
                        crossing_id = int(parts[1])
                        stat = parts[2]
                        if stat.lower() in ("true", "false"):
                            stat = "Active" if stat.lower() == "true" else "Inactive"
                        self.safe_set_crossing(crossing_id, stat)

                    elif cmd == "SIGNAL" and len(parts) >= 3:
                        block_id = int(parts[1])
                        color = parts[2]
                        self.set_signal(block_id, color)

                    elif cmd == "CMD_SPEED" and len(parts) >= 3:
                        block_id = int(parts[1])
                        speed_mph = int(parts[2])
                        self.set_commanded_speed(block_id, speed_mph)

                    elif cmd == "CMD_AUTH" and len(parts) >= 3:
                        block_id = int(parts[1])
                        auth_yd = int(parts[2])
                        self.set_commanded_authority(block_id, auth_yd)

                    else:
                        logger.warning("Unknown PLC command line: %s", raw_line.rstrip())
                except Exception:
                    logger.exception("Failed to parse PLC line: %r", raw_line)

    # ---------- Data exposure for UI ----------
    def get_line_block_ids(self) -> List[int]:
        return list(HW_LINE_BLOCK_MAP.get(self.line_name, []))

    @property
    def blocks(self) -> Dict[int, Dict[str, object]]:
        d: Dict[int, Dict[str, object]] = {}
        for b in self.get_line_block_ids():
            if b not in getattr(self.track_model, "segments", {}):
                continue
            cmd_spd = int(self._commanded_speed_mph.get(b, 0)) or "N/A"
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

    def report_state(self) -> Dict[str, Any]:
        """
        Compact snapshot used by UI/CTC debugging.
        """
        return {
            "line": self.line_name,
            "maintenance_mode": self.maintenance_mode,
            "blocks": self.blocks,
            "switches": self.switches.copy(),
            "switch_map": self.switch_map.copy(),
            "crossings": self.crossings.copy(),
            "crossing_blocks": self.crossing_blocks.copy(),
        }

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
                for b, d in blocks.items()
                if d.get("signal") not in (None, "N/A")
            },
            "commanded": {
                b: {"speed_mph": d["commanded_speed"], "auth_yd": d["commanded_auth"]}
                for b, d in blocks.items()
                if d.get("commanded_speed") != "N/A" or d.get("commanded_auth") != "N/A"
            },
        }


def build_backend_for_sim(
    track_model: TrackModelAdapter,
    line_name: str = "Blue Line",
) -> HardwareTrackControllerBackend:
    return HardwareTrackControllerBackend(track_model, line_name=line_name)
