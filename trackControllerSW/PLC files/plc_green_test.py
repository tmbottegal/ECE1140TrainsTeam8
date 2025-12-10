# green line plc file

# stuff in territory of control:
# - switch at block 13
# - railway crossing at block 19
# - switch at block 29
# - switch at block 62

# speed limit of areas:
# - A to C = 45 km/h
# - D = 70 km/h
# - E = 60 km/h
# - F = 70 km/h (blocks 27-28 = 30 km/h)
# - G  = 30 km/h
# - H = 30 km/h
# - I = 30 km/h (underground)
# - J = 30 km/h
# - W = 20 km/h (underground)
# - X = 20 km/h
# - Y = 20 km/h
# - Z = 20 km/h

def plc_logic(block_occupancies, switch_positions, light_signals, crossing_signals, previous_occupancies, stop):
    territory_main_line = list(range(1, 63))
    territory_underground = list(range(122, 151))
    train_in_underground = any(block_occupancies[122:151])
    train_in_yard_area = any(block_occupancies[0:13])
    train_in_early_main = any(block_occupancies[13:29])
    switch_positions[0] = train_in_yard_area and not train_in_early_main
    light_signals[0] = True
    if switch_positions[0] == 0:
        light_signals[1] = True
        light_signals[2] = False
    else:
        light_signals[1] = False
        light_signals[2] = True
    train_in_stations = any(block_occupancies[29:63])
    switch_positions[1] = train_in_stations and not train_in_early_main
    light_signals[3] = True
    if switch_positions[1] == 0:
        light_signals[4] = True
        light_signals[5] = False
    else:
        light_signals[4] = False
        light_signals[5] = True
    train_near_end = any(block_occupancies[60:63])
    train_in_underground = any(block_occupancies[122:151])
    switch_positions[2] = train_near_end or train_in_underground
    light_signals[6] = True
    if switch_positions[2] == 0:
        light_signals[7] = True
        light_signals[8] = False
    else:
        light_signals[7] = False
        light_signals[8] = True
    train_near_crossing_19 = any(block_occupancies[16:22])
    crossing_signals[0] = train_near_crossing_19
    for i, block_idx in enumerate(territory_main_line):
        if block_occupancies[block_idx]:
            distance_to_end = len(territory_main_line) - i
            if distance_to_end > 2 and block_idx + 2 < len(block_occupancies):
                prev_idx = max(0, block_idx - 1)
                if block_idx > 0 and block_occupancies[block_idx] and previous_occupancies[prev_idx]:
                    if block_occupancies[block_idx + 2]: stop[block_idx] = True
                elif block_occupancies[block_idx] and previous_occupancies[block_idx]:
                    if block_occupancies[block_idx + 2]: stop[block_idx] = True
                if stop[block_idx]:
                    if not block_occupancies[block_idx + 2]: stop[block_idx] = False
    for i, block_idx in enumerate(territory_underground):
        if block_occupancies[block_idx]:
            distance_to_end = len(territory_underground) - i
            if distance_to_end > 2 and block_idx + 2 < len(block_occupancies):
                if block_idx > 0 and block_occupancies[block_idx] and previous_occupancies[prev_idx]:
                    if block_occupancies[block_idx + 2]: stop[block_idx] = True
                elif block_occupancies[block_idx] and previous_occupancies[block_idx]:
                    if block_occupancies[block_idx + 2]: stop[block_idx] = True
                if stop[block_idx]:
                    if not block_occupancies[block_idx + 2]: stop[block_idx] = False
    if not switch_positions[0] and train_in_yard_area: stop[0:3] = [True, True, True]
    else: stop[0:3] = [False] * 3
    if not switch_positions[1] and train_in_stations: stop[27:30] = [True] * 3
    else: stop[27:30] = [False] * 3
    return switch_positions, light_signals, crossing_signals, stop