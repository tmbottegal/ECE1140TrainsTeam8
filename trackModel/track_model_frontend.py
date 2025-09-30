"""
Track Model Frontend
"""
import sys
sys.path.append('../')

from universal.universal import (
    SignalState,
    TrainCommand,
    ConversionFunctions
)

from track_model_backend import (
    TrackNetwork, 
    TrackSegment, 
    TrackSwitch, 
    LevelCrossing,
    Station,
    TrackFailureType
)
from typing import List, Dict, Optional
import sys
from PyQt6.QtWidgets import QApplication, QWidget
from sys import argv

if __name__ == "__main__":
    app = QApplication([])
    window = QWidget()
    window.show()
    app.exec()