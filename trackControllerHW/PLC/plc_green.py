"""Green Line PLC Logic Module - Hardware Wayside.

This module implements the Programmable Logic Controller (PLC) logic for the
Green Line railway system (Hardware Wayside), controlling switches, signals,
and crossings.

Territory of Control (Hardware):
    - Blocks 63-121 (main territory)
    - Switch at block 77 (77-78; 77-101)
    - Switch at block 85 (85-86; 100-85)
    - Railway crossing at block 108

Signal Convention:
    - True = GREEN (safe to proceed)
    - False = RED (stop/danger)
"""

from typing import List, Tuple

# Territory definition
TERRITORY = list(range(63, 122))  # Blocks 63-121 inclusive

# Initialize static variables for legacy PLC support
switch_77 = False   # False = Straight, True = Diverging
switch_85 = False
crossing_1 = False  # False = Inactive (gates up), True = Active (gates down)

# Initialize signals for all blocks in territory (True = GREEN, False = RED)
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
    """Execute PLC logic for Green Line Hardware Wayside.

    Args:
        block_occupancies: Current occupancy status of all blocks.
        switch_positions: Current positions of switches [switch_76, switch_85].
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

    # --- Initialize: clear stop flags in territory ---
    for b in TERRITORY:
        if 0 <= b < len(stop):
            stop[b] = False

    # --- COLLISION PREVENTION ---
    for b in TERRITORY:
        if 0 <= b < len(stop):
            next_block = b + 1
            if next_block <= 121 and occ(next_block):
                stop[b] = True

    # --- SIGNAL CONTROL (Boolean: True=GREEN, False=RED) ---
    for b in TERRITORY:
        if 0 <= b < len(light_signals):
            next_block = b + 1
            if next_block <= 121 and occ(next_block):
                light_signals[b] = False  # RED
            else:
                light_signals[b] = True   # GREEN

    # --- SWITCH CONTROL (Boolean: False=Straight, True=Diverging) ---
    def switch_clear(blocks: List[int]) -> bool:
        return not any(occ(b) for b in blocks if b < n)

    # Switch 77: (77, 78, 101)
    blocks_77 = [77, 78, 101]
    train_approaching_77 = any(occ(b) for b in range(74, 77) if b < n)
    train_on_diverging_77 = occ(101) or occ(100)

    if switch_clear(blocks_77) and len(switch_positions) > 0:
        if train_on_diverging_77 and not train_approaching_77:
            switch_positions[0] = True   # Diverging
        elif train_approaching_77 and not train_on_diverging_77:
            switch_positions[0] = False  # Straight

    # Switch 85: (85, 86, 100)
    blocks_85 = [85, 86, 100]
    train_approaching_85 = any(occ(b) for b in range(82, 85) if b < n)
    train_on_diverging_85 = occ(100) or occ(99)

    if switch_clear(blocks_85) and len(switch_positions) > 1:
        if train_on_diverging_85 and not train_approaching_85:
            switch_positions[1] = True   # Diverging
        elif train_approaching_85 and not train_on_diverging_85:
            switch_positions[1] = False  # Straight

    # --- SWITCH INTERLOCKING ---
    if len(switch_positions) > 0:
        if occ(76) and switch_positions[0]:  # Diverging when should be straight
            for b in [75, 76]:
                if 0 <= b < len(stop):
                    stop[b] = True
        if occ(101) and not switch_positions[0]:  # Straight when should be diverging
            for b in [100, 101]:
                if 0 <= b < len(stop):
                    stop[b] = True

    if len(switch_positions) > 1:
        if occ(84) and switch_positions[1]:
            for b in [83, 84]:
                if 0 <= b < len(stop):
                    stop[b] = True
        if occ(100) and not switch_positions[1]:
            for b in [99, 100]:
                if 0 <= b < len(stop):
                    stop[b] = True

    # --- CROSSING CONTROL (Block 108) ---
    crossing_range = range(105, 112)
    train_near_crossing = any(occ(b) for b in crossing_range if b < n)

    if len(crossing_signals) > 0:
        crossing_signals[0] = train_near_crossing

    # Set signals to RED near active crossing
    if train_near_crossing:
        for b in range(106, 111):
            if 0 <= b < len(light_signals):
                light_signals[b] = False  # RED

    # --- BOUNDARY HANDLING ---
    if occ(63) and occ(64):
        if 0 <= 63 < len(stop):
            stop[63] = True

    if occ(120) and occ(121):
        if 0 <= 120 < len(stop):
            stop[120] = True

    return switch_positions, light_signals, crossing_signals, stop