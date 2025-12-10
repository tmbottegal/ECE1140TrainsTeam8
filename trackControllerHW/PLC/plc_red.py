#RED LINE
TERRITORY = list(range(35, 72))  # Blocks 35–71 inclusive

switch_38 = 0     # Switch at block 38
switch_43 = 0     # Switch at block 43
switch_52 = 0     # Switch at block 52

crossing_47 = False   # False = gates up ; True = gates down

for blk in TERRITORY:
    globals()[f"signal_{blk}"] = True

for blk in TERRITORY:
    globals()[f"commanded_speed_{blk}"] = 40
    globals()[f"commanded_auth_{blk}"] = 200

def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    
    n = len(block_occupancies)

    def occ(b: int) -> bool:
        return 0 <= b < n and bool(block_occupancies[b])

    for b in TERRITORY:
        if 0 <= b < len(stop):
            stop[b] = False


    for b in TERRITORY:
        nxt = b + 1
        if nxt in TERRITORY and occ(nxt):
            stop[b] = True

    for b in TERRITORY:
        if 0 <= b < len(light_signals):
            nxt = b + 1
            if nxt in TERRITORY and occ(nxt):
                light_signals[b] = False  # RED
            else:
                light_signals[b] = True   # GREEN

    # CROSSING CONTROL – Block 47
    # Gates down if train on or near block 47
    crossing_block = 47
    if 0 <= crossing_block < n and 0 <= crossing_block < len(crossing_signals):
        near = any(
            occ(x)
            for x in range(crossing_block - 1, crossing_block + 2)
            if 0 <= x < n
        )
        crossing_signals[crossing_block] = near

    return switch_positions, light_signals, crossing_signals, stop