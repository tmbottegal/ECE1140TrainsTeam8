"""Green Line PLC Logic Module.

This module implements the Programmable Logic Controller (PLC) logic for the
Green Line railway system, controlling switches, signals, and crossings.

Territory of Control:
    - Switch at block 13
    - Railway crossing at block 19
    - Switch at block 29
    - Switch at block 62

Speed Limits by Section:
    - A to C: 45 km/h
    - D: 70 km/h
    - E: 60 km/h
    - F: 70 km/h (blocks 27-28: 30 km/h)
    - G: 30 km/h
    - H: 30 km/h
    - I: 30 km/h (underground)
    - J: 30 km/h
    - W: 20 km/h (underground)
    - X: 20 km/h
    - Y: 20 km/h
    - Z: 20 km/h
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
    """Execute PLC logic for Green Line train control.

    This function implements the core control logic for the Green Line,
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
    # Define territory boundaries
    territory_main_line = list(range(1, 63))
    territory_underground = list(range(122, 151))

    # Check for train presence in key areas
    train_in_underground = any(block_occupancies[122:151])
    train_in_yard_area = any(block_occupancies[0:13])
    train_in_early_main = any(block_occupancies[13:29])
    train_in_stations = any(block_occupancies[29:63])
    train_near_end = any(block_occupancies[60:63])
    train_near_crossing_19 = any(block_occupancies[16:22])

    # Control switch 0 (block 13)
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

    # Control switch 1 (block 29)
    switch_positions[1] = (
        1 if train_in_stations and not train_in_early_main else 0
    )
    light_signals[3] = True  # Previous signal

    if switch_positions[1] == 0:
        light_signals[4] = True  # Straight signal
        light_signals[5] = False  # Diverging signal
    else:
        light_signals[4] = False  # Straight signal
        light_signals[5] = True  # Diverging signal

    # Control switch 2 (block 58)
    switch_positions[2] = 1 if train_near_end or train_in_underground else 0
    light_signals[6] = True  # Previous signal

    if switch_positions[2] == 0:
        light_signals[7] = True  # Straight signal
        light_signals[8] = False  # Diverging signal
    else:
        light_signals[7] = False  # Straight signal
        light_signals[8] = True  # Diverging signal

    # Control switch 3 (block 62)
    switch_positions[3] = 1 if train_near_end or train_in_underground else 0
    light_signals[9] = True  # Previous signal

    if switch_positions[3] == 0:
        light_signals[10] = True  # Straight signal
        light_signals[11] = False  # Diverging signal
    else:
        light_signals[10] = False  # Straight signal
        light_signals[11] = True  # Diverging signal

    # Control crossing 0 (block 19)
    crossing_signals[0] = train_near_crossing_19

    # Process main line blocks for collision prevention
    for i, block_idx in enumerate(territory_main_line):
        if block_occupancies[block_idx]:
            distance_to_end = len(territory_main_line) - i

            if distance_to_end > 2 and block_idx + 2 < len(block_occupancies):
                prev_idx = max(0, block_idx - 1)

                # Check if train is moving forward
                if (
                    block_idx > 0
                    and block_occupancies[block_idx]
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

    # Process underground blocks for collision prevention
    for i, block_idx in enumerate(territory_underground):
        if block_occupancies[block_idx]:
            distance_to_end = len(territory_underground) - i

            if distance_to_end > 2 and block_idx + 2 < len(block_occupancies):
                prev_idx = max(0, block_idx - 1)

                # Check if train is moving forward
                if (
                    block_idx > 0
                    and block_occupancies[block_idx]
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
        stop[0:3] = [True, True, True]
    else:
        stop[0:3] = [False, False, False]

    # Switch 1 interlocking: stop trains near station if switch is in wrong position
    if not switch_positions[1] and train_in_stations:
        stop[27:30] = [True, True, True]
    else:
        stop[27:30] = [False, False, False]

    return switch_positions, light_signals, crossing_signals, stop