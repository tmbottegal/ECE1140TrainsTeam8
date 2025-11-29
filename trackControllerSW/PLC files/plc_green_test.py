# green plc logic 

SPEED_LIMIT = 70  #placeholder till i feel like adding the real speed limits
YELLOW_SPEED_FACTOR = 0.5
MIN_SAFE_AUTHORITY = 50  #placeholder till i feel like adding the real stuff
CROSSING_APPROACH_SPEED = 25  #placeholder for thing

# switch
switch_1 = 0
switch_2 = 0
switch_3 = 0

# cross
crossing_1 = True

def get_speed_for_signal(base_speed, signal_state):
    if signal_state == "RED":
        return 0
    elif signal_state == "YELLOW":
        return int(base_speed * YELLOW_SPEED_FACTOR)
    elif signal_state == "SUPERGREEN":
        return min(base_speed, SPEED_LIMIT)
    else:  # GREEN aka the default
        return base_speed


def get_authority_for_signal(base_authority, signal_state, block_occupied):
    if signal_state == "RED":
        return 0
    elif block_occupied:
        return max(int(base_authority * 0.5), MIN_SAFE_AUTHORITY)
    else:
        return base_authority


def adjust_for_crossing(speed, authority, crossing_active, blocks_to_crossing):
    if crossing_active and blocks_to_crossing <= 2:
        speed = min(speed, CROSSING_APPROACH_SPEED)
        authority = min(authority, 75)
    return speed, authority


def adjust_for_switch(speed, authority, switch_position, blocks_to_switch):
    if blocks_to_switch <= 1:
        if switch_position == 1:
            speed = int(speed * 0.7)
            authority = min(authority, 100)
    return speed, authority


def check_ahead_occupancy(current_block, next_blocks_occupied):
    if any(next_blocks_occupied):
        return YELLOW_SPEED_FACTOR
    return 1.0


def check_proximity_occupancy(block_id, all_occupancy):
    if not all_occupancy.get(block_id, False):
        return 1.0
    for distance in [1, 2]:
        prev_block = block_id - distance
        next_block = block_id + distance
        if all_occupancy.get(prev_block, False) or all_occupancy.get(next_block, False):
            return 0.5
    return 1.0


# lights
signal_12 = "GREEN"
signal_58 = "GREEN"
signal_62 = "GREEN"

# sped
commanded_speed_1  = 45
commanded_speed_2  = 45
commanded_speed_3  = 45
commanded_speed_4  = 45
commanded_speed_5  = 45
commanded_speed_6  = 45
commanded_speed_7  = 45
commanded_speed_8  = 45
commanded_speed_9  = 45
commanded_speed_10 = 45
commanded_speed_11 = 45
commanded_speed_12 = 45
commanded_speed_13 = 70
commanded_speed_14 = 70
commanded_speed_15 = 70
commanded_speed_16 = 70
commanded_speed_17 = 60
commanded_speed_18 = 60
commanded_speed_19 = 60
commanded_speed_20 = 60
commanded_speed_21 = 70
commanded_speed_22 = 70
commanded_speed_23 = 70
commanded_speed_24 = 70
commanded_speed_25 = 70
commanded_speed_26 = 70
commanded_speed_27 = 30
commanded_speed_28 = 30
commanded_speed_29 = 30
commanded_speed_30 = 30
commanded_speed_31 = 30
commanded_speed_32 = 30
commanded_speed_33 = 30
commanded_speed_34 = 30
commanded_speed_35 = 30
commanded_speed_36 = 30
commanded_speed_37 = 30
commanded_speed_38 = 30
commanded_speed_39 = 30
commanded_speed_40 = 30
commanded_speed_41 = 30
commanded_speed_42 = 30
commanded_speed_43 = 30
commanded_speed_44 = 30
commanded_speed_45 = 30
commanded_speed_46 = 30
commanded_speed_47 = 30
commanded_speed_48 = 30
commanded_speed_49 = 30
commanded_speed_50 = 30
commanded_speed_51 = 30
commanded_speed_52 = 30
commanded_speed_53 = 30
commanded_speed_54 = 30
commanded_speed_55 = 30
commanded_speed_56 = 30
commanded_speed_57 = 30
commanded_speed_58 = 30
commanded_speed_59 = 30
commanded_speed_60 = 30
commanded_speed_61 = 30
commanded_speed_62 = 30

commanded_speed_122 = 20
commanded_speed_123 = 20
commanded_speed_124 = 20
commanded_speed_125 = 20
commanded_speed_126 = 20
commanded_speed_127 = 20
commanded_speed_128 = 20
commanded_speed_129 = 20
commanded_speed_130 = 20
commanded_speed_131 = 20
commanded_speed_132 = 20
commanded_speed_133 = 20
commanded_speed_134 = 20
commanded_speed_135 = 20
commanded_speed_136 = 20
commanded_speed_137 = 20
commanded_speed_138 = 20
commanded_speed_139 = 20
commanded_speed_140 = 20
commanded_speed_141 = 20
commanded_speed_142 = 20
commanded_speed_143 = 20
commanded_speed_144 = 20
commanded_speed_145 = 20
commanded_speed_146 = 20
commanded_speed_147 = 20
commanded_speed_148 = 20
commanded_speed_149 = 20
commanded_speed_150 = 20

# authority
commanded_auth_1  = 100
commanded_auth_2  = 100
commanded_auth_3  = 100
commanded_auth_4  = 100
commanded_auth_5  = 100
commanded_auth_6  = 100
commanded_auth_7  = 100
commanded_auth_8  = 100
commanded_auth_9  = 100
commanded_auth_10 = 100
commanded_auth_11 = 100
commanded_auth_12 = 100
commanded_auth_13 = 150
commanded_auth_14 = 150
commanded_auth_15 = 150
commanded_auth_16 = 150
commanded_auth_17 = 150
commanded_auth_18 = 150
commanded_auth_19 = 150
commanded_auth_20 = 150
commanded_auth_21 = 300
commanded_auth_22 = 300
commanded_auth_23 = 300
commanded_auth_24 = 300
commanded_auth_25 = 200
commanded_auth_26 = 100
commanded_auth_27 = 50
commanded_auth_28 = 50
commanded_auth_29 = 50
commanded_auth_30 = 50
commanded_auth_31 = 50
commanded_auth_32 = 50
commanded_auth_33 = 50
commanded_auth_34 = 50
commanded_auth_35 = 50
commanded_auth_36 = 50
commanded_auth_37 = 50
commanded_auth_38 = 50
commanded_auth_39 = 50
commanded_auth_40 = 50
commanded_auth_41 = 50
commanded_auth_42 = 50
commanded_auth_43 = 50
commanded_auth_44 = 50
commanded_auth_45 = 50
commanded_auth_46 = 50
commanded_auth_47 = 50
commanded_auth_48 = 50
commanded_auth_49 = 50
commanded_auth_50 = 50
commanded_auth_51 = 50
commanded_auth_52 = 50
commanded_auth_53 = 50
commanded_auth_54 = 50
commanded_auth_55 = 50
commanded_auth_56 = 50
commanded_auth_57 = 50
commanded_auth_58 = 50
commanded_auth_59 = 50
commanded_auth_60 = 50
commanded_auth_61 = 50
commanded_auth_62 = 50
commanded_auth_122 = 50
commanded_auth_123 = 50
commanded_auth_124 = 50
commanded_auth_125 = 50
commanded_auth_126 = 50
commanded_auth_127 = 50
commanded_auth_128 = 50
commanded_auth_129 = 50
commanded_auth_130 = 50
commanded_auth_131 = 50
commanded_auth_132 = 50
commanded_auth_133 = 50
commanded_auth_134 = 50
commanded_auth_135 = 50
commanded_auth_136 = 50
commanded_auth_137 = 50
commanded_auth_138 = 50
commanded_auth_139 = 50
commanded_auth_140 = 50
commanded_auth_141 = 50
commanded_auth_142 = 50
commanded_auth_143 = 50
commanded_auth_144 = 50
commanded_auth_145 = 50
commanded_auth_146 = 50
commanded_auth_147 = 50
commanded_auth_148 = 184
commanded_auth_149 = 40
commanded_auth_150 = 35