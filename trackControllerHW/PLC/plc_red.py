"""Red Line PLC Logic Module for Hardware Wayside.

Controls switches, signals, and crossings for Red Line blocks 35-71.

Switches:
    - Block 38: 38-39 (straight), 38-71 (diverging)
    - Block 43: 43-44 (straight), 44-67 (diverging)
    - Block 52: 52-53 (straight), 52-66 (diverging)

Crossings:
    - Block 47

Signal Convention:
    - True = GREEN (safe to proceed)
    - False = RED (stop/danger)
"""
from typing import List, Tuple

TERRITORY = list(range(35, 72))

switch_38 = False
switch_43 = False
switch_52 = False
crossing_1 = False

for blk in TERRITORY:
    globals()[f"signal_{blk}"] = True


def plc_logic(
    block_occupancies: List[bool],
    switch_positions: List[int],
    light_signals: List[bool],
    crossing_signals: List[bool],
    previous_occupancies: List[bool],
    stop: List[bool],
) -> Tuple[List[int], List[bool], List[bool], List[bool]]:
    """Execute PLC logic for Red Line Hardware Wayside.

    Args:
        block_occupancies: Current occupancy status of all blocks.
        switch_positions: Positions of switches [switch_38, switch_43, switch_52].
        light_signals: Signal states (True=GREEN, False=RED).
        crossing_signals: Crossing gate states.
        previous_occupancies: Previous tick occupancy status.
        stop: Stop flags for blocks.

    Returns:
        Tuple of (switch_positions, light_signals, crossing_signals, stop).
    """
    n = len(block_occupancies)

    def occ(block: int) -> bool:
        return 0 <= block < n and bool(block_occupancies[block])

    for b in TERRITORY:
        if 0 <= b < len(stop):
            stop[b] = False

    # Collision prevention
    for b in TERRITORY:
        if 0 <= b < len(stop):
            next_block = b + 1
            if next_block <= 71 and occ(next_block):
                stop[b] = True

    # Signal control
    for b in TERRITORY:
        if 0 <= b < len(light_signals):
            next_block = b + 1
            if next_block <= 71 and occ(next_block):
                light_signals[b] = False
            else:
                light_signals[b] = True

    def switch_clear(blocks: List[int]) -> bool:
        return not any(occ(b) for b in blocks if b < n)

    # Switch 38 control
    blocks_38 = [38, 39, 71]
    train_approaching_38 = any(occ(b) for b in range(35, 38) if b < n)
    train_on_loop_71 = occ(71) or occ(70)

    if switch_clear(blocks_38) and len(switch_positions) > 0:
        if train_on_loop_71 and not train_approaching_38:
            switch_positions[0] = True
        elif train_approaching_38 and not train_on_loop_71:
            switch_positions[0] = False

    # Switch 43 control
    blocks_43 = [43, 44, 67]
    train_approaching_43 = any(occ(b) for b in range(40, 43) if b < n)
    train_on_67 = occ(67) or occ(66)

    if switch_clear(blocks_43) and len(switch_positions) > 1:
        if train_on_67 and not train_approaching_43:
            switch_positions[1] = True
        elif train_approaching_43 and not train_on_67:
            switch_positions[1] = False

    # Switch 52 control
    blocks_52 = [52, 53, 66]
    train_approaching_52 = any(occ(b) for b in range(49, 52) if b < n)
    train_on_66 = occ(66) or occ(65)

    if switch_clear(blocks_52) and len(switch_positions) > 2:
        if train_on_66 and not train_approaching_52:
            switch_positions[2] = True
        elif train_approaching_52 and not train_on_66:
            switch_positions[2] = False

    # Switch interlocking
    if len(switch_positions) > 0:
        if occ(37) and switch_positions[0]:
            for b in [36, 37]:
                if 0 <= b < len(stop):
                    stop[b] = True
        if occ(71) and not switch_positions[0]:
            for b in [70, 71]:
                if 0 <= b < len(stop):
                    stop[b] = True

    if len(switch_positions) > 1:
        if occ(42) and switch_positions[1]:
            for b in [41, 42]:
                if 0 <= b < len(stop):
                    stop[b] = True
        if occ(67) and not switch_positions[1]:
            for b in [66, 67]:
                if 0 <= b < len(stop):
                    stop[b] = True

    if len(switch_positions) > 2:
        if occ(51) and switch_positions[2]:
            for b in [50, 51]:
                if 0 <= b < len(stop):
                    stop[b] = True
        if occ(66) and not switch_positions[2]:
            for b in [65, 66]:
                if 0 <= b < len(stop):
                    stop[b] = True

    # Crossing control (Block 47)
    crossing_range = range(44, 51)
    train_near_crossing = any(occ(b) for b in crossing_range if b < n)

    if len(crossing_signals) > 0:
        crossing_signals[0] = train_near_crossing

    if train_near_crossing:
        for b in range(45, 50):
            if 0 <= b < len(light_signals):
                light_signals[b] = False

    # Boundary and loop handling
    if occ(35) and occ(36):
        if 0 <= 35 < len(stop):
            stop[35] = True

    loop_blocks = [66, 67, 68, 69, 70, 71]
    loop_congested = sum(1 for b in loop_blocks if occ(b)) >= 3

    if loop_congested:
        if len(switch_positions) > 2 and switch_positions[2]:
            if 0 <= 51 < len(stop):
                stop[51] = True
        if len(switch_positions) > 1 and switch_positions[1]:
            if 0 <= 42 < len(stop):
                stop[42] = True

    return switch_positions, light_signals, crossing_signals, stop