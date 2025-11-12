import sys
import os

# Set up sys.path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CTC'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackControllerHW'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackControllerSW'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackModel'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trainModel'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trainControllerSW'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'universal'))


# CTC import

# Wayside Controller SW import
from trackControllerSW.track_controller_ui import TrackControllerUI
# Wayside Controller HW import

# Track Model import
from trackModel.track_model_backend import TrackNetwork
from trackModel.track_model_frontend import NetworkStatusUI
# Train Model import

# Train Controller import

# Universal import

# PyQt6 import
from PyQt6.QtWidgets import QApplication


if __name__ == "__main__":
    app = QApplication([])
    network = TrackNetwork()
    network.load_track_layout('trackModel/green_line.csv')
    TrackModelUI = NetworkStatusUI(network)
    TrackModelUI.show()
    app.exec()