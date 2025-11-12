import sys
import os

# Set up sys.path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CTC'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackControllerHW'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackControllerSW'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackModel'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trainModel'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trainControllerSW'))


# CTC import
from CTC.CTC_backend import Block 
from CTC.CTC_backend import TrackState 

# Wayside Controller SW import
from trackControllerSW.track_controller_backend import TrackControllerBackend
from trackControllerSW.track_controller_ui import TrackControllerUI
# Wayside Controller HW import

# Track Model import
from trackModel.track_model_backend import TrackNetwork
from trackModel.track_model_frontend import NetworkStatusUI
# Train Model import

# Train Controller import

# Universal import
from universal.universal import TrainCommand, SignalState, ConversionFunctions
from universal.global_clock import GlobalClock
# PyQt6 import
from PyQt6.QtWidgets import QApplication


if __name__ == "__main__":
    app = QApplication([])
    network = TrackNetwork()
    network.load_track_layout('trackModel/green_line.csv')
    #------------------------------------------------------------------------------------------------
    #trackcontroller sw stuff that might be wrong or need to be changed, tell me to change if needed
    controllers = {
        "Green Line": TrackControllerBackend(network, "Green Line"),
        "Red Line": TrackControllerBackend(network, "Red Line"),
        "Blue Line": TrackControllerBackend(network, "Blue Line"),
        }
    for ctrl in controllers.values(): 
        ctrl.start_live_link(poll_interval=1.0)
    #------------------------------------------------------------------------------------------------
    TrackModelUI = NetworkStatusUI(network)
    TrackControllerUi = TrackControllerUI(controllers)
    TrackModelUI.show()
    TrackControllerUi.setWindowTitle("Wayside SW Module")
    TrackControllerUi.show()
    app.exec()