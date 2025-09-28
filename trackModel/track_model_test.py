"""
Track Model Interface - Access layer for the track model backend.

This module provides a higher-level interface for interacting with the 
track model backend, including network setup, command broadcasting,
and status monitoring.
"""

from track_model_backend import (
    TrackNetwork, 
    TrackSegment, 
    TrackSwitch, 
    Station,
    TrainCommand,
    FailureType,
    SignalState
)
from datetime import datetime
from typing import List, Dict, Optional

if __name__ == "__main__":
    print("Test") 