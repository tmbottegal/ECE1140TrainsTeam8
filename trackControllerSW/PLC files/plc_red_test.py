"""Red Line PLC Logic Module - Wayside 1.

This module implements the Programmable Logic Controller (PLC) logic for the
Red Line railway system (Wayside 1), controlling switches, signals, and crossings.

Territory of Control:
    - Switch at block 9
    - Crossing at block 11
    - Switch at block 15
    - Switch at block 27 (underground)
    - Switch at block 32 (underground)

Speed Limits by Section:
    - A to C: 40 km/h
    - D to G: 40-70 km/h
    - H: 70 km/h (underground)
"""

from typing import List


def plc_logic(
    block_occupancies: List[bool],
    switch_positions: List[int],
    light_signals: List[bool],
    crossing_signals: List[bool],
    previous_occupancies: List[bool],
    stop: List[bool],
) -> tuple[List[int], List[bool], List[bool], List[bool]]:
    """Execute PLC logic for Red Line train control.

    This function implements the core control logic for Red Line Wayside 1,
    managing switch positions, signal states, crossing gates, and train
    stop commands based on current and previous block occupancies.

    Args:
        block_occupancies: Current occupancy status of all blocks.
        switch_positions: Current positions of all switches (0=straight, 1=diverging).
        light_signals: Current state of all light signals.
        crossing_signals: Current state of all crossing gates.
        previous_occupancies: Previous occupancy status of all blocks.
        stop: Current stop commands for all blocks.

    Returns:
        Tuple containing:
            - Updated switch positions
            - Updated light signals
            - Updated crossing signals
            - Updated stop commands
    """
    # Check for train presence in key areas
    train_in_yard_area = any(block_occupancies[1:9])
    train_in_early_main = any(block_occupancies[9:16])
    train_in_surface = any(block_occupancies[9:24])
    train_before_switch_15 = any(block_occupancies[1:15])
    train_after_switch_15 = any(block_occupancies[16:25])
    train_approaching_27 = any(block_occupancies[24:27])
    train_past_27 = any(block_occupancies[28:34])
    train_past_32 = any(block_occupancies[33:34])
    train_near_crossing_11 = any(block_occupancies[6:17])

    # Control switch 0 (block 9)
    switch_positions[0] = (
        1 if train_in_yard_area and not train_in_early_main else 0
    )
    light_signals[0] = True  # Previous signal

    if switch_positions[0] == 0:
        light_signals[1] = True  # Straight signal
        light_signals[2] = False  # Diverging signal
    else:
        light_signals[1] = False  # Straight signal
        light_signals[2] = True  # Diverging signal

    # Control switch 1 (block 15)
    switch_positions[1] = (
        1 if train_before_switch_15 and not train_after_switch_15 else 0
    )
    light_signals[3] = True  # Previous signal

    if switch_positions[1] == 0:
        light_signals[4] = True  # Straight signal
        light_signals[5] = False  # Diverging signal
    else:
        light_signals[4] = False  # Straight signal
        light_signals[5] = True  # Diverging signal

    # Control switch 2 (block 27)
    switch_positions[2] = 0 if train_approaching_27 and train_past_27 else 1
    light_signals[6] = True  # Previous signal

    if switch_positions[2] == 0:
        light_signals[7] = True  # Straight signal
        light_signals[8] = False  # Diverging signal
    else:
        light_signals[7] = False  # Straight signal
        light_signals[8] = True  # Diverging signal

    # Control switch 3 (block 32)
    switch_positions[3] = 0 if train_past_32 else 1
    light_signals[9] = True  # Previous signal

    if switch_positions[3] == 0:
        light_signals[10] = True  # Straight signal
        light_signals[11] = False  # Diverging signal
    else:
        light_signals[10] = False  # Straight signal
        light_signals[11] = True  # Diverging signal

    # Control crossing 0 (block 11)
    crossing_signals[0] = train_near_crossing_11

    # Process all blocks for collision prevention
    for block_idx in range(1, 34):
        if block_occupancies[block_idx]:
            # Check if there's room to look ahead
            if block_idx + 2 <= 33:
                prev_idx = block_idx - 1 if block_idx > 1 else 1

                # Check if train is moving forward
                if (
                    block_occupancies[block_idx]
                    and previous_occupancies[prev_idx]
                ):
                    if block_occupancies[block_idx + 2]:
                        stop[block_idx] = True
                # Check if train is stationary
                elif (
                    block_occupancies[block_idx]
                    and previous_occupancies[block_idx]
                ):
                    if block_occupancies[block_idx + 2]:
                        stop[block_idx] = True

                # Clear stop if path ahead is clear
                if stop[block_idx]:
                    if not block_occupancies[block_idx + 2]:
                        stop[block_idx] = False

    # Switch 0 interlocking: stop trains in yard if switch is in wrong position
    if not switch_positions[0] and train_in_yard_area:
        stop[0:3] = [True] * len(stop[0:3])
    else:
        stop[0:3] = [False] * len(stop[0:3])

    # Switch 1 interlocking: stop trains on surface if switch is in wrong position
    if not switch_positions[1] and train_in_surface:
        stop[13:17] = [True] * len(stop[13:17])
    else:
        stop[13:17] = [False] * len(stop[13:17])

    # Switch 2 interlocking: stop trains approaching block 27 if switch is diverging
    if switch_positions[2]:
        stop[25:29] = [True] * len(stop[25:29])
    else:
        stop[25:29] = [False] * len(stop[25:29])

    # Switch 3 interlocking: stop trains approaching block 32 if switch is diverging
    if switch_positions[3]:
        stop[30:34] = [True] * len(stop[30:34])
    else:
        stop[30:34] = [False] * len(stop[30:34])

    return switch_positions, light_signals, crossing_signals, stop