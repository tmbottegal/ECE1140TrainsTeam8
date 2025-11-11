"""
Track Model Sandbox
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universal.universal import (
    SignalState,
    TrainCommand,
    ConversionFunctions
)

from track_model_frontend import NetworkStatusUI
from PyQt6.QtWidgets import QApplication

from track_model_backend import (
    TrackNetwork, 
    TrackSegment, 
    TrackSwitch, 
    LevelCrossing,
    Station,
    StationSide,
    TrackFailureType,
    Train
)
from typing import List, Dict, Optional

if __name__ == "__main__":
    app = QApplication([])
    network = TrackNetwork()
    network.load_track_layout('trackModel/green_line.csv')
    window = NetworkStatusUI(network)
    window.show()
    app.exec()