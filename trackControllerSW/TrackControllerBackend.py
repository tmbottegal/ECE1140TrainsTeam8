from typing import Dict, Callable, List, Optional
import importlib.util
import os


class SafetyException(Exception):
    pass


class TrackControllerBackend:
    def __init__(self, line_name: str, num_blocks: int):
        self.line_name = line_name
        self.num_blocks = num_blocks
        self.blocks: Dict[int, Dict] = {
            i: {
                "occupied": False,
                "broken": False,
                "suggested_speed": 50,
                "commanded_speed": 0,
                "suggested_auth": False,
                "commanded_auth": False,
                "signal": "Green",
            }
            for i in range(1, num_blocks + 1)}
        self.switches: Dict[int, str] = {}       # switch_id -> position
        self.switch_map: Dict[int, tuple] = {}   # switch_id -> (block_a, block_b, block_c)
        self.crossings: Dict[int, str] = {}      # crossing_id -> status
        self.crossing_blocks: Dict[int, int] = {}# crossing_id -> block number

        # Observer/listener support
        self._listeners: List[Callable[[], None]] = []

    # ---- Listener API ----
    def add_listener(self, cb: Callable[[], None]):
        """Register a callable that will be called (without args) whenever backend changes."""
        if cb not in self._listeners:
            self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[], None]):
        try:
            self._listeners.remove(cb)
        except ValueError:
            pass

    def _notify_listeners(self):
        """Call all registered listeners. Exceptions are caught and printed."""
        for cb in list(self._listeners):
            try:
                cb()
            except Exception as e:
                print(f"[DEBUG] listener callback raised: {e}")

    # ---- State mutation methods with safety checks ----
    def set_block_occupancy(self, block: int, status: bool):
        if 1 <= block <= self.num_blocks:
            # Track circuits detection simulation: set occupancy
            self.blocks[block]["occupied"] = status
            print(f"[BACKEND] {self.line_name}: block {block} occupancy -> {status}")
            # If a block becomes occupied, make sure crossing is active and no authority conflicts
            if status:
                # Force crossing active if exists on that block
                for cid, b in self.crossing_blocks.items():
                    if b == block:
                        try:
                            self.safe_set_crossing(cid, "Active")
                        except SafetyException:
                            # Crossing must be active; if we can't set it for some reason, log it.
                            print(f"[WARN] Could not set crossing {cid} Active for occupied block {block}")
                # If block is occupied, commanded_auth must be False (can't grant to an occupied block)
                if self.blocks[block]["commanded_auth"]:
                    print(f"[SAFETY] Revoking commanded authority on block {block} because it became occupied")
                    self.blocks[block]["commanded_auth"] = False
            self._notify_listeners()

    def break_rail(self, block: int):
        if 1 <= block <= self.num_blocks:
            self.blocks[block]["broken"] = True
            # Safety: revoke any commanded authority on a broken rail
            if self.blocks[block]["commanded_auth"]:
                print(f"[SAFETY] Revoking commanded authority on broken block {block}")
                self.blocks[block]["commanded_auth"] = False
            # Safety: force signal red
            self.blocks[block]["signal"] = "Red"
            print(f"[BACKEND] {self.line_name}: block {block} marked BROKEN")
            self._notify_listeners()

    def repair_rail(self, block: int):
        if 1 <= block <= self.num_blocks:
            self.blocks[block]["broken"] = False
            print(f"[BACKEND] {self.line_name}: block {block} repaired")
            self._notify_listeners()

    def set_signal(self, block: int, color: str):
        valid_colors = ["Red", "Yellow", "Green", "Super Green"]
        if not (1 <= block <= self.num_blocks):
            print(f"[ERROR] Invalid block {block} for signal")
            return
        if color not in valid_colors:
            print(f"[ERROR] Invalid signal color '{color}' for block {block}")
            return
        # Safety: cannot set Green (permit movement) on a broken block
        if color != "Red" and self.blocks[block]["broken"]:
            print(f"[SAFETY] Cannot set signal {color} on broken block {block}; forcing Red")
            self.blocks[block]["signal"] = "Red"
        else:
            self.blocks[block]["signal"] = color
        print(f"[BACKEND] {self.line_name}: block {block} signal -> {self.blocks[block]['signal']}")
        self._notify_listeners()

    def safe_set_switch(self, switch_id: int, position: str):
        """Set a switch position with conservative safety checks:
           - Block IDs involved in the switch must not be occupied when changing the switch.
           - Position must be 'Normal' or 'Alternate' (case-insensitive match allowed).
        """
        pos = position.title()
        if pos not in ("Normal", "Alternate"):
            raise ValueError("Invalid switch position; expected 'Normal' or 'Alternate'")

        blocks = self.switch_map.get(switch_id)
        if not blocks:
            raise ValueError(f"Unknown switch id {switch_id}")
        # Conservative safety rule: do not change a switch if any of the three involved blocks are occupied.
        for b in blocks:
            if 1 <= b <= self.num_blocks and self.blocks[b]["occupied"]:
                raise SafetyException(f"Cannot change switch {switch_id}: block {b} is occupied")

        # commit change
        self.switches[switch_id] = pos
        print(f"[BACKEND] {self.line_name}: switch {switch_id} -> {pos}")
        self._notify_listeners()

    def safe_set_crossing(self, crossing_id: int, status: str):
        """Set crossing state. Status could be 'Active' or 'Inactive'.
           Safety rule: cannot set Inactive if the associated block is occupied.
        """
        stat = status.title()
        if stat not in ("Active", "Inactive"):
            raise ValueError("Invalid crossing status; expected 'Active' or 'Inactive'")

        block = self.crossing_blocks.get(crossing_id)
        if block and self.blocks.get(block, {}).get("occupied", False) and stat == "Inactive":
            raise SafetyException(f"Cannot set crossing {crossing_id} Inactive: block {block} is occupied")

        self.crossings[crossing_id] = stat
        print(f"[BACKEND] {self.line_name}: crossing {crossing_id} -> {stat}")
        self._notify_listeners()

    # ---- CTC suggestion / Train relay ----
    def receive_ctc_suggestion(self, block: int, suggested_speed: int, suggested_auth: bool):
        """Called by the CTC Office to suggest speed and authority for a block."""
        if 1 <= block <= self.num_blocks:
            self.blocks[block]["suggested_speed"] = int(suggested_speed)
            self.blocks[block]["suggested_auth"] = bool(suggested_auth)
            print(f"[CTC] Received suggestion for block {block}: speed={suggested_speed}, auth={suggested_auth}")
            self._notify_listeners()
        else:
            print(f"[CTC] Invalid block {block} in suggestion")

    def set_commanded_speed(self, block: int, speed: int):
        """Set commanded speed that Track Controller will instruct Train Model to use.
           Basic safety check: cannot command speed > 0 onto a broken block.
        """
        if not (1 <= block <= self.num_blocks):
            raise ValueError("Invalid block")
        if self.blocks[block]["broken"] and speed > 0:
            raise SafetyException(f"Cannot command speed >0 on broken block {block}")
        self.blocks[block]["commanded_speed"] = int(speed)
        print(f"[BACKEND] {self.line_name}: block {block} commanded_speed -> {speed}")
        self._notify_listeners()

    def set_commanded_authority(self, block: int, auth: bool):
        """Set commanded authority for a block with safety checks:
           - No authority to broken blocks
           - No authority to occupied blocks
           - No overlapping / adjacent authority allowed (conservative enforcement)
        """
        if not (1 <= block <= self.num_blocks):
            raise ValueError("Invalid block")
        if auth:
            if self.blocks[block]["broken"]:
                raise SafetyException(f"Cannot grant authority on broken block {block}")
            if self.blocks[block]["occupied"]:
                raise SafetyException(f"Cannot grant authority on occupied block {block}")
            # Conservative overlapping rule: do not allow adjacent blocks to both have commanded authority
            neighbors = [block - 1, block + 1]
            for nb in neighbors:
                if 1 <= nb <= self.num_blocks and self.blocks[nb]["commanded_auth"]:
                    raise SafetyException(f"Granting authority on {block} would overlap with authority on adjacent block {nb}")
        # commit
        self.blocks[block]["commanded_auth"] = bool(auth)
        print(f"[BACKEND] {self.line_name}: block {block} commanded_auth -> {auth}")
        self._notify_listeners()

    def relay_to_train_model(self, block: int) -> Dict[str, object]:
        """Return the commanded settings for a block (what would be relayed to the Train Model).
           This is a simulation placeholder for "relay".
        """
        if not (1 <= block <= self.num_blocks):
            raise ValueError("Invalid block")
        data = {
            "block": block,
            "commanded_speed": self.blocks[block]["commanded_speed"],
            "commanded_auth": self.blocks[block]["commanded_auth"],
            "signal": self.blocks[block]["signal"],
        }
        print(f"[RELAY] Relaying to train model for block {block}: {data}")
        return data

    # ---- PLC upload / interpreter (boolean-only) ----
    def upload_plc(self, filepath: str):
        """
        Execute a PLC file.
        - For .py: execute module but only react to boolean variables in the module.
        - For .txt/.plc: simple text commands (SWITCH / CROSSING).
        """
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".py":
            spec = importlib.util.spec_from_file_location("plc_module", filepath)
            plc_module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(plc_module)
                # Only boolean variables are considered part of the PLC language
                plc_vars = {k: v for k, v in vars(plc_module).items() if isinstance(v, bool)}

                # Apply booleans to backend
                for name, value in plc_vars.items():
                    name = name.lower()

                    # Block occupancy
                    if name.startswith("block_") and "_occupied" in name:
                        parts = name.split("_")
                        if len(parts) >= 3:
                            try:
                                block_id = int(parts[1])
                                self.set_block_occupancy(block_id, value)
                            except ValueError:
                                print(f"[ERROR] could not parse block id from {name}")

                    # Broken rail
                    elif name.startswith("block_") and "_broken" in name:
                        parts = name.split("_")
                        if len(parts) >= 3:
                            try:
                                block_id = int(parts[1])
                                if value:
                                    self.break_rail(block_id)
                                else:
                                    self.repair_rail(block_id)
                            except ValueError:
                                print(f"[ERROR] could not parse block id from {name}")

                    # Switch positions boolean: switch_{id} True -> Normal, False -> Alternate
                    elif name.startswith("switch_"):
                        parts = name.split("_")
                        if len(parts) >= 2:
                            try:
                                switch_id = int(parts[1])
                                pos = "Normal" if value else "Alternate"
                                try:
                                    self.safe_set_switch(switch_id, pos)
                                except SafetyException as se:
                                    print(f"[SAFETY] PLC attempted unsafe switch {switch_id} change: {se}")
                            except ValueError:
                                print(f"[ERROR] could not parse switch id from {name}")

                    # Crossing active/inactive
                    elif name.startswith("crossing_"):
                        parts = name.split("_")
                        if len(parts) >= 2:
                            try:
                                crossing_id = int(parts[1])
                                status = "Active" if value else "Inactive"
                                try:
                                    self.safe_set_crossing(crossing_id, status)
                                except SafetyException as se:
                                    print(f"[SAFETY] PLC attempted unsafe crossing {crossing_id} change: {se}")
                            except ValueError:
                                print(f"[ERROR] could not parse crossing id from {name}")

                print(f"[INFO] Boolean PLC Python executed for {self.line_name}")
            except Exception as e:
                print(f"[ERROR] Failed to execute {filepath}: {e}")

        else:
            # Handle .txt or .plc formats (simple text commands)
            try:
                with open(filepath, "r") as f:
                    code = f.read().splitlines()
            except FileNotFoundError:
                print(f"[ERROR] File {filepath} not found.")
                return
            for line in code:
                parts = line.split()
                if not parts:
                    continue
                if parts[0].upper() == "SWITCH" and len(parts) >= 3:
                    _, sid, pos = parts
                    try:
                        try:
                            self.safe_set_switch(int(sid), pos)
                        except SafetyException as se:
                            print(f"[SAFETY] PLC text attempted unsafe switch {sid} change: {se}")
                    except ValueError:
                        print(f"[ERROR] invalid switch line: {line}")
                elif parts[0].upper() == "CROSSING" and len(parts) >= 3:
                    _, cid, status = parts
                    try:
                        try:
                            self.safe_set_crossing(int(cid), status)
                        except SafetyException as se:
                            print(f"[SAFETY] PLC text attempted unsafe crossing {cid} change: {se}")
                    except ValueError:
                        print(f"[ERROR] invalid crossing line: {line}")
            print(f"[INFO] PLC text executed for {self.line_name}")

        # Final notification
        self._notify_listeners()

    # ---- Reporting (to CTC office / Dispatcher) ----
    def report_state(self) -> Dict[str, object]:
        """Return a snapshot of the current track state suitable for the CTC Office display."""
        state = {
            "line": self.line_name,
            "blocks": {b: {
                "occupied": d["occupied"],
                "broken": d["broken"],
                "suggested_speed": d["suggested_speed"],
                "commanded_speed": d["commanded_speed"],
                "suggested_auth": d["suggested_auth"],
                "commanded_auth": d["commanded_auth"],
                "signal": d.get("signal", "Green"),
            } for b, d in self.blocks.items()},
            "switches": self.switches.copy(),
            "switch_map": self.switch_map.copy(),
            "crossings": {cid: {"block": self.crossing_blocks.get(cid), "status": status} for cid, status in self.crossings.items()}
        }
        # Print brief log for traceability
        print(f"[REPORT] Report for {self.line_name}: {len(state['blocks'])} blocks, {len(self.switches)} switches, {len(self.crossings)} crossings")
        return state


class TrackNetwork:
    def __init__(self):
        self.lines: Dict[str, TrackControllerBackend] = {
            "Blue Line": TrackControllerBackend("Blue Line", 15),
            "Red Line": TrackControllerBackend("Red Line", 76),
            "Green Line": TrackControllerBackend("Green Line", 150),
        }

        # Initialize infra for each line
        self._init_blue_line()
        self._init_red_line()
        self._init_green_line()

    def get_line(self, name: str) -> TrackControllerBackend:
        return self.lines[name]

    def _init_blue_line(self):
        line = self.lines["Blue Line"]
        # Switch IDs we assign ourselves (arbitrary but unique)
        line.switch_map[1] = (5, 6, 11)   # block 5 can go to 6 or 11
        line.switches[1] = "Normal"       # default
        # Crossings
        line.crossing_blocks[1] = 3
        line.crossings[1] = "Inactive"

    def _init_red_line(self):
        line = self.lines["Red Line"]
        # Switches
        line.switch_map[1] = (15, 16, 1)
        line.switch_map[2] = (27, 28, 76)
        line.switch_map[3] = (32, 33, 72)
        line.switch_map[4] = (38, 39, 71)
        line.switch_map[5] = (43, 44, 67)
        line.switch_map[6] = (52, 53, 66)
        for sid in line.switch_map:
            line.switches[sid] = "Normal"
        # Crossings
        line.crossing_blocks[1] = 11
        line.crossings[1] = "Inactive"
        line.crossing_blocks[2] = 47
        line.crossings[2] = "Inactive"

    def _init_green_line(self):
        line = self.lines["Green Line"]
        # Switches
        line.switch_map[1] = (12, 13, 1)
        line.switch_map[2] = (28, 29, 150)
        line.switch_map[3] = (76, 77, 101)
        line.switch_map[4] = (85, 86, 100)
        for sid in line.switch_map:
            line.switches[sid] = "Normal"
        # Crossings
        line.crossing_blocks[1] = 19
        line.crossings[1] = "Inactive"
        line.crossing_blocks[2] = 108
        line.crossings[2] = "Inactive"
