# GREEN LINE
TERRITORY = list(range(63, 122))  # 63–121

switch_76 = 0
switch_85 = 0

for blk in TERRITORY:
    globals()[f"signal_{blk}"] = True   # default everything green

signal_64 = False  # RED
signal_67 = False  # RED

for blk in TERRITORY:
    globals()[f"commanded_speed_{blk}"] = 1   
    globals()[f"commanded_auth_{blk}"] = 1    

def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):

    total_blocks = len(block_occupancies)

    def occ(b):
        return 0 <= b < total_blocks and bool(block_occupancies[b])

    for b in TERRITORY:
        if 0 <= b < len(stop):
            stop[b] = False  # allow movement by default

    # If a block is occupied, the block BEHIND it must be STOP.
    # If the next block ahead is occupied, current block gets RED.
    for b in TERRITORY:
        # SAFETY STOP: if the next block is occupied, stop this one
        nxt = b + 1
        if occ(nxt):
            if 0 <= b < len(stop):
                stop[b] = True

    # True  = GREEN (safe)
    # False = RED   (danger)
    for b in TERRITORY:
        if 0 <= b < len(light_signals):
            nxt = b + 1
            if nxt in TERRITORY and occ(nxt):
                light_signals[b] = False   # RED
            else:
                light_signals[b] = True    # GREEN

    return switch_positions, light_signals, crossing_signals, stop