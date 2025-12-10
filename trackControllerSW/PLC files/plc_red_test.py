# red line plc file - Wayside 1

# stuff in territory of control:
# - switch at block 9
# - crossing at block 11
# - switch at block 15
# - switch at block 27 (underground)
# - switch at block 32 (underground)

# speed limit of areas:
# - A to C = 40 km/h
# - D to G = 40-70 km/h
# - H = 70 km/h (underground)

def plc_logic(block_occupancies, switch_positions, light_signals, crossing_signals, previous_occupancies, stop):
    train_in_yard_area = any(block_occupancies[1:9])
    train_in_early_main = any(block_occupancies[9:16])
    train_in_surface = any(block_occupancies[9:24])
    switch_positions[0] = train_in_yard_area and not train_in_early_main
    light_signals[0] = True
    if switch_positions[0] == 0:
        light_signals[1] = True
        light_signals[2] = False
    else:
        light_signals[1] = False
        light_signals[2] = True
    train_before_switch_15 = any(block_occupancies[1:15])
    train_after_switch_15 = any(block_occupancies[16:25])
    switch_positions[1] = train_before_switch_15 and not train_after_switch_15
    light_signals[3] = True
    if switch_positions[1] == 0:
        light_signals[4] = True
        light_signals[5] = False
    else:
        light_signals[4] = False
        light_signals[5] = True
    train_approaching_27 = any(block_occupancies[24:27])
    train_past_27 = any(block_occupancies[28:34])
    switch_positions[2] = not (train_approaching_27 and train_past_27)
    light_signals[6] = True
    if switch_positions[2] == 0:
        light_signals[7] = True
        light_signals[8] = False
    else:
        light_signals[7] = False
        light_signals[8] = True
    train_past_32 = any(block_occupancies[33:34])
    switch_positions[3] = not train_past_32
    light_signals[9] = True
    if switch_positions[3] == 0:
        light_signals[10] = True
        light_signals[11] = False
    else:
        light_signals[10] = False
        light_signals[11] = True
    train_near_crossing_11 = any(block_occupancies[6:17])
    crossing_signals[0] = train_near_crossing_11
    for block_idx in range(1, 34):
        if block_occupancies[block_idx]:
            if block_idx + 2 <= 33:
                if block_occupancies[block_idx] and previous_occupancies[block_idx - 1 if block_idx > 1 else 1]:
                    if block_occupancies[block_idx + 2]:
                        stop[block_idx] = True
                elif block_occupancies[block_idx] and previous_occupancies[block_idx]:
                    if block_occupancies[block_idx + 2]:
                        stop[block_idx] = True
                if stop[block_idx]:
                    if not block_occupancies[block_idx + 2]:
                        stop[block_idx] = False
    if not switch_positions[0] and train_in_yard_area: stop[0:3] = [True] * len(stop[0:3])
    else: stop[0:3] = [False] * len(stop[0:3])
    if not switch_positions[1] and train_in_surface: stop[13:17] = [True] * len(stop[13:17])
    else: stop[13:17] = [False] * len(stop[13:17])
    if switch_positions[2]: stop[25:29] = [True] * len(stop[25:29])
    else: stop[25:29] = [False] * len(stop[25:29])
    if switch_positions[3]: stop[30:34] = [True] * len(stop[30:34])
    else: stop[30:34] = [False] * len(stop[30:34])
    return switch_positions, light_signals, crossing_signals, stop