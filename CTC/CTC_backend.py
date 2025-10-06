# CTC_backend.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import itertools

@dataclass
class Block:
    line: str
    block_id: int
    status: str          # "free" | "occupied" | "closed"  (your UI calls this "Occupancy")
    station: str
    signal: str          # "Open" | "Closed" (track status column in your table)
    switch: str          # e.g., "SW1" or ""
    light: str           # "RED" | "YELLOW" | "GREEN" | ""
    crossing: str        # "True" or ""
    maintenance: str     # "Beacon" or ""

class TrackState:
    """
    Minimal backend stub to drive your UI. Treats the Blue Line list as a loop.
    Provides:
      - set_line(name, tuples)
      - get_blocks() -> List[Block]
      - set_status("A5", "closed"/"free"/"occupied")
      - _advance_one_step() : simulate TC telemetry each tick
    """
    def __init__(self, line_name: str, line_tuples: List[Tuple]):
        self.line_name = line_name
        self._lines: Dict[str, List[Block]] = {}
        self._train_positions: Dict[str, str] = {}  # train_id -> "A2" (bid)
        self._tick_count = 0
        self.set_line(line_name, line_tuples)

        # Seed a couple of fake trains for the demo
        # They’ll advance one block per tick if the next block isn’t closed/occupied
        self._train_positions = {"T1": "A2", "T2": "A5"}

    # ---------- public API used by your UI ----------
    def set_line(self, name: str, tuples: List[Tuple]):
        self.line_name = name
        # convert tuples -> Block list
        self._lines[name] = [
            Block(*t) for t in tuples
        ]

    def get_blocks(self) -> List[Block]:
        return self._lines.get(self.line_name, [])

    def set_status(self, bid: str, new_status: str):
        # bid like "A5" -> (section='A', id=5)
        sec, num = bid[0], int(bid[1:])
        for b in self.get_blocks():
            if b.line == sec and b.block_id == num:
                # If user closes a block, clear any train in it
                if new_status == "closed":
                    for tid, pos in list(self._train_positions.items()):
                        if pos == bid:
                            # eject train backwards one block for safety
                            self._train_positions[tid] = self._prev_block_id(pos)
                b.status = new_status
                return

    # ---------- simulation ----------
    def _advance_one_step(self):
        """
        Simulates Track Controller inputs to CTC:
          - Moves trains forward if the next block is free and not closed
          - Updates occupancy on blocks
          - Sets light aspects and one crossing
        Called every second by your QTimer.
        """
        self._tick_count += 1
        blocks = self.get_blocks()
        if not blocks:
            return

        # 1) Clear all occupancies to "free" unless "closed"
        for b in blocks:
            if b.status != "closed":
                b.status = "free"

        # 2) Move trains along a simple path (sorted by (section, id))
        order = [f"{b.line}{b.block_id}" for b in sorted(blocks, key=lambda x: (x.line, x.block_id))]

        # helper: next/prev block in order (wrap around)
        def next_block_id(bid: str) -> str:
            i = order.index(bid)
            return order[(i + 1) % len(order)]

        # move each train if the next block is available
        for tid in sorted(self._train_positions.keys()):
            cur = self._train_positions[tid]
            nxt = next_block_id(cur)
            # find next block object
            nb = self._find_block(nxt)
            if nb and nb.status == "free" and nb.signal != "Closed":
                # occupy it
                self._train_positions[tid] = nxt

        # 3) Mark occupancy on the blocks
        occupied_bids = set(self._train_positions.values())
        for b in blocks:
            bid = f"{b.line}{b.block_id}"
            if bid in occupied_bids:
                if b.status != "closed":
                    b.status = "occupied"

        # 4) Simple signal logic: RED behind a train, GREEN ahead, YELLOW near crossing
        for b in blocks:
            bid = f"{b.line}{b.block_id}"
            if b.status == "closed":
                b.light = ""    # lights off if closed track
                continue
            if bid in occupied_bids:
                b.light = "RED"
            else:
                # make the next block after any occupied block show YELLOW; others GREEN
                if any(self._is_next_of(bid, occ, order) for occ in occupied_bids):
                    b.light = "YELLOW"
                else:
                    b.light = "GREEN"

        # 5) Crossing behavior near A3: toggle true when adjacent block occupied
        for b in blocks:
            if b.line == "A" and b.block_id == 3:
                b.crossing = "True" if any(
                    f"A{n}" in occupied_bids for n in (2, 3, 4)
                ) else ""

    # ---------- helpers ----------
    def _find_block(self, bid: str) -> Optional[Block]:
        sec, num = bid[0], int(bid[1:])
        for b in self.get_blocks():
            if b.line == sec and b.block_id == num:
                return b
        return None

    def _prev_block_id(self, bid: str) -> str:
        blocks = self.get_blocks()
        order = [f"{b.line}{b.block_id}" for b in sorted(blocks, key=lambda x: (x.line, x.block_id))]
        i = order.index(bid)
        return order[(i - 1) % len(order)]

    @staticmethod
    def _is_next_of(candidate_bid: str, occupied_bid: str, order: List[str]) -> bool:
        i = order.index(occupied_bid)
        nxt = order[(i + 1) % len(order)]
        return candidate_bid == nxt
