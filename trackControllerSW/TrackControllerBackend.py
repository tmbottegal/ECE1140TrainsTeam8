"""Track controller backend.

Provides a simulated track controller backend for multiple lines.
Implements safety rules, PLC upload support, and an observer API.

This module is refactored to follow Google Python style: docstrings,
type hints, and use of the logging module.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from typing import Callable, Dict, List, Optional, Tuple

# Module-level logger.
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Valid signal string constants.
_VALID_SIGNALS = ("Red", "Yellow", "Green", "Super Green")


class SafetyException(Exception):
    """Raised when a requested operation would violate safety rules."""


class TrackControllerBackend:
    """Backend simulation for a single track line.

    The backend holds the state of blocks, switches, and crossings and
    enforces a set of conservative safety rules.
    """

    def __init__(self, line_name: str, num_blocks: int) -> None:
        """Initialize backend.

        Args:
            line_name: Human-readable name of the line (e.g. "Blue Line").
            num_blocks: Number of contiguous blocks on the line.
        """
        self.line_name: str = line_name
        self.num_blocks: int = int(num_blocks)

        # Blocks are keyed by block id (1..num_blocks). Each block state is a dict.
        self.blocks: Dict[int, Dict[str, object]] = {
            i: {
                "occupied": False,
                "broken": False,
                "suggested_speed": 50,
                "commanded_speed": 0,
                "suggested_auth": False,
                "commanded_auth": False,
                "signal": "Green",
            }
            for i in range(1, self.num_blocks + 1)
        }

        # Switch bookkeeping.
        self.switches: Dict[int, str] = {}  # switch_id -> position
        self.switch_map: Dict[int, Tuple[int, ...]] = {}  # switch_id -> (block_a,...)

        # Crossing bookkeeping.
        self.crossings: Dict[int, str] = {}  # crossing_id -> status
        self.crossing_blocks: Dict[int, int] = {}  # crossing_id -> block number

        # Observers/listeners are callables without args invoked on change.
        self._listeners: List[Callable[[], None]] = []

    # ---- Listener API ----
    def add_listener(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when backend state changes.

        Duplicate callbacks are ignored.

        Args:
            callback: Callable with no arguments.
        """
        if callback not in self._listeners:
            self._listeners.append(callback)
            logger.debug("Added listener %r for %s", callback, self.line_name)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        """Remove a previously registered listener.

        Args:
            callback: The callback to remove. Missing callbacks are ignored.
        """
        try:
            self._listeners.remove(callback)
            logger.debug("Removed listener %r for %s", callback, self.line_name)
        except ValueError:
            logger.debug("Listener %r not registered for %s", callback, self.line_name)

    def _notify_listeners(self) -> None:
        """Call all registered listeners, isolating exceptions per listener."""
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                logger.exception("Listener %r raised while notifying", cb)

    # ---- State mutation methods with safety checks ----
    def set_block_occupancy(self, block: int, status: bool) -> None:
        """Set occupancy for a block.

        Enforces:
            * If a block becomes occupied, commanded authority is revoked.
            * Activates any crossing on that block.

        Args:
            block: Block id (1-based).
            status: True if occupied, False otherwise.
        """
        if not (1 <= block <= self.num_blocks):
            logger.error("Invalid block %d for occupancy change", block)
            return

        self.blocks[block]["occupied"] = bool(status)
        logger.info("%s: block %d occupancy -> %s", self.line_name,
                    block, status)

        if status:
            # Activate crossings on the occupied block.
            for cid, b in self.crossing_blocks.items():
                if b == block:
                    try:
                        self.safe_set_crossing(cid, "Active")
                    except SafetyException:
                        logger.warning(
                            "Could not set crossing %d Active for occupied "
                            "block %d", cid, block
                        )

            # Revoke commanded authority if present.
            if self.blocks[block]["commanded_auth"]:
                logger.warning(
                    "Revoking commanded authority on block %d because it "
                    "became occupied", block
                )
                self.blocks[block]["commanded_auth"] = False

        self._notify_listeners()

    def break_rail(self, block: int) -> None:
        """Mark a block as having a broken rail.

        Safety actions:
            * Revoke any commanded authority.
            * Force the signal to Red.

        Args:
            block: Block id to mark broken.
        """
        if not (1 <= block <= self.num_blocks):
            logger.error("Invalid block %d for break_rail", block)
            return

        self.blocks[block]["broken"] = True
        if self.blocks[block]["commanded_auth"]:
            logger.warning("Revoking commanded authority on broken block %d",
                           block)
            self.blocks[block]["commanded_auth"] = False

        self.blocks[block]["signal"] = "Red"
        logger.info("%s: block %d marked BROKEN", self.line_name, block)
        self._notify_listeners()

    def repair_rail(self, block: int) -> None:
        """Repair a previously broken rail.

        Args:
            block: Block id to repair.
        """
        if not (1 <= block <= self.num_blocks):
            logger.error("Invalid block %d for repair_rail", block)
            return

        self.blocks[block]["broken"] = False
        logger.info("%s: block %d repaired", self.line_name, block)
        self._notify_listeners()

    def set_signal(self, block: int, color: str) -> None:
        """Set the signal color for a block.

        Safety: cannot set non-Red colors on a broken block.

        Args:
            block: Block id to set signal for.
            color: One of 'Red', 'Yellow', 'Green', 'Super Green'.
        """
        if not (1 <= block <= self.num_blocks):
            logger.error("Invalid block %d for signal", block)
            return

        if color not in _VALID_SIGNALS:
            logger.error("Invalid signal color '%s' for block %d", color,
                         block)
            return

        if color != "Red" and self.blocks[block]["broken"]:
            logger.warning(
                "Cannot set signal %s on broken block %d; forcing Red",
                color, block
            )
            self.blocks[block]["signal"] = "Red"
        else:
            self.blocks[block]["signal"] = color

        logger.info("%s: block %d signal -> %s", self.line_name, block,
                    self.blocks[block]["signal"])
        self._notify_listeners()

    def safe_set_switch(self, switch_id: int, position: str) -> None:
        """Set a switch position with conservative safety checks.

        Rules:
            * Position must be 'Normal' or 'Alternate' (case-insensitive).
            * All blocks involved must not be occupied when changing.

        Args:
            switch_id: Identifier for the switch.
            position: 'Normal' or 'Alternate'.

        Raises:
            ValueError: For invalid arguments.
            SafetyException: If safety rule prevents change.
        """
        pos = position.title()
        if pos not in ("Normal", "Alternate"):
            raise ValueError("Invalid switch position; expected 'Normal' or "
                             "'Alternate'")

        blocks = self.switch_map.get(switch_id)
        if not blocks:
            raise ValueError("Unknown switch id %d" % switch_id)

        # Do not change if any involved block is occupied.
        for b in blocks:
            if 1 <= b <= self.num_blocks and self.blocks[b]["occupied"]:
                raise SafetyException(
                    "Cannot change switch %d: block %d is occupied" % (
                        switch_id, b))

        self.switches[switch_id] = pos
        logger.info("%s: switch %d -> %s", self.line_name, switch_id, pos)
        self._notify_listeners()

    def safe_set_crossing(self, crossing_id: int, status: str) -> None:
        """Set crossing state with safety rule enforcement.

        Rules:
            * Status must be 'Active' or 'Inactive' (case-insensitive).
            * Cannot set 'Inactive' if the associated block is occupied.

        Args:
            crossing_id: Identifier for the crossing.
            status: 'Active' or 'Inactive'.

        Raises:
            ValueError: For invalid arguments.
            SafetyException: If safety rule prevents change.
        """
        stat = status.title()
        if stat not in ("Active", "Inactive"):
            raise ValueError("Invalid crossing status; expected 'Active' or "
                             "'Inactive'")

        block = self.crossing_blocks.get(crossing_id)
        if block and self.blocks.get(block, {}).get("occupied", False) and \
           stat == "Inactive":
            raise SafetyException(
                "Cannot set crossing %d Inactive: block %d is occupied" % (
                    crossing_id, block))

        self.crossings[crossing_id] = stat
        logger.info("%s: crossing %d -> %s", self.line_name, crossing_id,
                    stat)
        self._notify_listeners()

    # ---- CTC suggestion / Train relay ----
    def receive_ctc_suggestion(self,
                               block: int,
                               suggested_speed: int,
                               suggested_auth: bool) -> None:
        """Receive a suggestion from the CTC office for a block.

        Args:
            block: Block id the suggestion applies to.
            suggested_speed: Suggested speed in km/h (or arbitrary unit).
            suggested_auth: Suggested authority (True/False).
        """
        if 1 <= block <= self.num_blocks:
            self.blocks[block]["suggested_speed"] = int(suggested_speed)
            self.blocks[block]["suggested_auth"] = bool(suggested_auth)
            logger.debug("CTC suggestion for block %d: speed=%s auth=%s",
                         block, suggested_speed, suggested_auth)
            self._notify_listeners()
        else:
            logger.error("Invalid block %d in CTC suggestion", block)

    def set_commanded_speed(self, block: int, speed: int) -> None:
        """Set commanded speed for a block.

        Safety: cannot command speed > 0 on a broken block.

        Args:
            block: Block id.
            speed: Speed value to command.

        Raises:
            ValueError: If block id is invalid.
            SafetyException: If safety rule prevents speed change.
        """
        if not (1 <= block <= self.num_blocks):
            raise ValueError("Invalid block")

        if self.blocks[block]["broken"] and speed > 0:
            raise SafetyException(
                "Cannot command speed >0 on broken block %d" % block)

        self.blocks[block]["commanded_speed"] = int(speed)
        logger.info("%s: block %d commanded_speed -> %d", self.line_name,
                    block, speed)
        self._notify_listeners()

    def set_commanded_authority(self, block: int, auth: bool) -> None:
        """Grant or revoke commanded authority for a block.

        Safety rules:
            * No authority to broken blocks.
            * No authority to occupied blocks.
            * Do not allow adjacent blocks to both have commanded
              authority (conservative overlapping rule).

        Args:
            block: Block id.
            auth: True to grant, False to revoke.

        Raises:
            ValueError: If block id invalid.
            SafetyException: If safety rule prevents authority grant.
        """
        if not (1 <= block <= self.num_blocks):
            raise ValueError("Invalid block")

        if auth:
            if self.blocks[block]["broken"]:
                raise SafetyException("Cannot grant authority on broken block "
                                      "%d" % block)
            if self.blocks[block]["occupied"]:
                raise SafetyException("Cannot grant authority on occupied block "
                                      "%d" % block)

            neighbors = (block - 1, block + 1)
            for nb in neighbors:
                if 1 <= nb <= self.num_blocks and \
                   self.blocks[nb]["commanded_auth"]:
                    raise SafetyException(
                        "Granting authority on %d would overlap with "
                        "adjacent block %d" % (block, nb))

        self.blocks[block]["commanded_auth"] = bool(auth)
        logger.info("%s: block %d commanded_auth -> %s", self.line_name,
                    block, auth)
        self._notify_listeners()

    def relay_to_train_model(self, block: int) -> Dict[str, object]:
        """Return the commanded settings for a block.

        This simulates the relay process that would inform the train model.

        Args:
            block: Block id to query.

        Returns:
            A dict containing block, commanded_speed, commanded_auth, and
            signal.
        """
        if not (1 <= block <= self.num_blocks):
            raise ValueError("Invalid block")

        data = {
            "block": block,
            "commanded_speed": self.blocks[block]["commanded_speed"],
            "commanded_auth": self.blocks[block]["commanded_auth"],
            "signal": self.blocks[block]["signal"],
        }
        logger.debug("Relaying to train model for block %d: %s", block, data)
        return data

    # ---- PLC upload / interpreter (boolean-only) ----
    def upload_plc(self, filepath: str) -> None:
        """Execute a PLC file.

        Supported formats:
            * .py: Execute the module and inspect boolean global
              variables. Naming conventions recognized:
              - block_{id}_occupied (occupancy)
              - block_{id}_broken (broken)
              - switch_{id} (True -> Normal, False -> Alternate)
              - crossing_{id} (True -> Active, False -> Inactive)
            * .txt or .plc: Simple text commands, e.g.
              "SWITCH 1 Alternate" or "CROSSING 1 Active".

        Args:
            filepath: Path to PLC file.
        """
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".py":
            spec = importlib.util.spec_from_file_location("plc_module", filepath)
            if spec is None or spec.loader is None:
                logger.error("Failed to load PLC module from %s", filepath)
                return

            plc_module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(plc_module)  # type: ignore[attr-defined]
            except Exception:
                logger.exception("Failed to execute PLC Python file %s", filepath)
                return

            plc_vars = {
                k: v for k, v in vars(plc_module).items()
                if isinstance(v, bool)
            }

            for name, value in plc_vars.items():
                lname = name.lower()

                # Block occupancy: block_{id}_occupied
                if lname.startswith("block_") and "_occupied" in lname:
                    parts = lname.split("_")
                    if len(parts) >= 3:
                        try:
                            block_id = int(parts[1])
                            self.set_block_occupancy(block_id, value)
                        except ValueError:
                            logger.error("Could not parse block id from %s", name)
                    continue

                # Broken rail: block_{id}_broken
                if lname.startswith("block_") and "_broken" in lname:
                    parts = lname.split("_")
                    if len(parts) >= 3:
                        try:
                            block_id = int(parts[1])
                            if value:
                                self.break_rail(block_id)
                            else:
                                self.repair_rail(block_id)
                        except ValueError:
                            logger.error("Could not parse block id from %s", name)
                    continue

                # Switch boolean: switch_{id}
                if lname.startswith("switch_"):
                    parts = lname.split("_")
                    if len(parts) >= 2:
                        try:
                            switch_id = int(parts[1])
                            pos = "Normal" if value else "Alternate"
                            try:
                                self.safe_set_switch(switch_id, pos)
                            except SafetyException as se:
                                logger.warning(
                                    "PLC attempted unsafe switch %d change: %s",
                                    switch_id, se
                                )
                        except ValueError:
                            logger.error("Could not parse switch id from %s", name)
                    continue

                # Crossing boolean: crossing_{id}
                if lname.startswith("crossing_"):
                    parts = lname.split("_")
                    if len(parts) >= 2:
                        try:
                            crossing_id = int(parts[1])
                            status = "Active" if value else "Inactive"
                            try:
                                self.safe_set_crossing(crossing_id, status)
                            except SafetyException as se:
                                logger.warning(
                                    "PLC attempted unsafe crossing %d change: %s",
                                    crossing_id, se
                                )
                        except ValueError:
                            logger.error(
                                "Could not parse crossing id from %s", name)
                    continue

            logger.info("Boolean PLC Python executed for %s", self.line_name)

        else:
            # Simple text-based PLC format (.txt or .plc)
            try:
                with open(filepath, "r") as f:
                    lines = f.read().splitlines()
            except FileNotFoundError:
                logger.error("File %s not found.", filepath)
                return

            for line in lines:
                parts = line.split()
                if not parts:
                    continue
                cmd = parts[0].upper()
                if cmd == "SWITCH" and len(parts) >= 3:
                    _, sid, pos = parts
                    try:
                        try:
                            self.safe_set_switch(int(sid), pos)
                        except SafetyException as se:
                            logger.warning(
                                "PLC text attempted unsafe switch %s change: %s",
                                sid, se
                            )
                    except ValueError:
                        logger.error("Invalid switch line: %s", line)
                elif cmd == "CROSSING" and len(parts) >= 3:
                    _, cid, status = parts
                    try:
                        try:
                            self.safe_set_crossing(int(cid), status)
                        except SafetyException as se:
                            logger.warning(
                                "PLC text attempted unsafe crossing %s change: %s",
                                cid, se
                            )
                    except ValueError:
                        logger.error("Invalid crossing line: %s", line)

            logger.info("PLC text executed for %s", self.line_name)

        # Final notification to listeners.
        self._notify_listeners()

    # ---- Reporting (to CTC office / Dispatcher) ----
    def report_state(self) -> Dict[str, object]:
        """Return a snapshot of the current track state.

        The returned dict is suitable for display by a CTC/Dispatcher UI.

        Returns:
            A dictionary with line, blocks, switches, switch_map, and crossings.
        """
        state = {
            "line": self.line_name,
            "blocks": {
                b: {
                    "occupied": d["occupied"],
                    "broken": d["broken"],
                    "suggested_speed": d["suggested_speed"],
                    "commanded_speed": d["commanded_speed"],
                    "suggested_auth": d["suggested_auth"],
                    "commanded_auth": d["commanded_auth"],
                    "signal": d.get("signal", "Green"),
                } for b, d in self.blocks.items()
            },
            "switches": self.switches.copy(),
            "switch_map": self.switch_map.copy(),
            "crossings": {
                cid: {"block": self.crossing_blocks.get(cid), "status": status}
                for cid, status in self.crossings.items()
            },
        }
        logger.info(
            "Report for %s: %d blocks, %d switches, %d crossings",
            self.line_name, len(state["blocks"]),
            len(self.switches), len(self.crossings),
        )
        return state


class TrackNetwork:
    """Container for all track lines."""

    def __init__(self) -> None:
        """Initialize a network containing Blue, Red, and Green lines."""
        self.lines: Dict[str, TrackControllerBackend] = {
            "Blue Line": TrackControllerBackend("Blue Line", 15),
            "Red Line": TrackControllerBackend("Red Line", 76),
            "Green Line": TrackControllerBackend("Green Line", 150),
        }

        self._init_blue_line()
        self._init_red_line()
        self._init_green_line()

    def get_line(self, name: str) -> TrackControllerBackend:
        """Return the backend for a given line name."""
        return self.lines[name]

    def _init_blue_line(self) -> None:
        """Initialize switches and crossings for Blue Line."""
        line = self.lines["Blue Line"]
        line.switch_map[1] = (5, 6, 11)
        line.switches[1] = "Normal"
        line.crossing_blocks[1] = 3
        line.crossings[1] = "Inactive"

    def _init_red_line(self) -> None:
        """Initialize switches and crossings for Red Line."""
        line = self.lines["Red Line"]
        line.switch_map[1] = (15, 16, 1)
        line.switch_map[2] = (27, 28, 76)
        line.switch_map[3] = (32, 33, 72)
        line.switch_map[4] = (38, 39, 71)
        line.switch_map[5] = (43, 44, 67)
        line.switch_map[6] = (52, 53, 66)
        for sid in line.switch_map:
            line.switches[sid] = "Normal"
        line.crossing_blocks[1] = 11
        line.crossings[1] = "Inactive"
        line.crossing_blocks[2] = 47
        line.crossings[2] = "Inactive"

    def _init_green_line(self) -> None:
        """Initialize switches and crossings for Green Line."""
        line = self.lines["Green Line"]
        line.switch_map[1] = (12, 13, 1)
        line.switch_map[2] = (28, 29, 150)
        line.switch_map[3] = (76, 77, 101)
        line.switch_map[4] = (85, 86, 100)
        for sid in line.switch_map:
            line.switches[sid] = "Normal"
        line.crossing_blocks[1] = 19
        line.crossings[1] = "Inactive"
        line.crossing_blocks[2] = 108
        line.crossings[2] = "Inactive"
