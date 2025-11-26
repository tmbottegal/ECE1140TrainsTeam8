"""
Track Model Sandbox
"""
import sys
import os
from typing import TYPE_CHECKING
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universal.universal import (
    SignalState,
    TrainCommand,
    ConversionFunctions
)

from track_model_test_frontend import NetworkStatusUI
from PyQt6.QtWidgets import QApplication

from trainModel.train_model_backend import Train

from track_model_backend import (
    TrackNetwork, 
    TrackSegment, 
    TrackSwitch, 
    LevelCrossing,
    Station,
    StationSide,
    TrackFailureType,
)
from typing import List, Dict, Optional

if __name__ == "__main__":
    #app = QApplication([])
    network = TrackNetwork()
    network.load_track_layout('trackModel/green_line.csv')
    train = Train(1)
    network.add_train(train)
    network.connect_train(1, 12, 0.0)
    network.broadcast_train_command(12, 100, 100)
    
    #window = NetworkStatusUI(network)
    #window.show()
    #app.exec()