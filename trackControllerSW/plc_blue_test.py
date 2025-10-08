
"""Test PLC file for Blue Line.

Simulates all 15 Blue Line blocks, their occupancy, broken rails,
the single switch, and crossing. Used for testing upload_plc().
"""

# Block occupancy
block_1_occupied = False
block_2_occupied = True
block_3_occupied = False
block_4_occupied = False
block_5_occupied = False
block_6_occupied = False
block_7_occupied = False
block_8_occupied = False
block_9_occupied = False
block_10_occupied = False
block_11_occupied = False
block_12_occupied = False
block_13_occupied = False
block_14_occupied = False
block_15_occupied = False

# Broken rails
block_1_broken = False
block_2_broken = False
block_3_broken = False
block_4_broken = False
block_5_broken = False
block_6_broken = False
block_7_broken = False
block_8_broken = False
block_9_broken = False
block_10_broken = False
block_11_broken = False
block_12_broken = False
block_13_broken = False
block_14_broken = False
block_15_broken = False

# Switch positions
# True = Normal, False = Alternate
switch_1 = True

# Crossing states
# True = Active, False = Inactive
crossing_1 = True

# Signals

block_1_signal_red = True
block_2_signal_yellow = True
block_3_signal_green = True
block_4_signal_supergreen = True
block_5_signal_red = True
block_6_signal_yellow = True
block_7_signal_green = True
block_8_signal_supergreen = True
block_9_signal_green = True
block_10_signal_green = True
block_11_signal_green = True
block_12_signal_green = True
block_13_signal_green = True
block_14_signal_green = True
block_15_signal_green = True

