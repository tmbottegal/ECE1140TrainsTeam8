"""
Track Model Frontend
"""

from track_model_backend import (
    TrackNetwork, 
    TrackSegment, 
    TrackSwitch, 
    Station,
    TrainCommand,
    TrackFailureType,
    SignalState
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