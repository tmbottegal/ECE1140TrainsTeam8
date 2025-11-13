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
from CTC.CTC_backend import TrackState,Block 
from CTC.CTC_ui import CTCWindow 

# Wayside Controller SW import
from trackControllerSW.track_controller_backend import TrackControllerBackend
from trackControllerSW.track_controller_ui import TrackControllerUI

# Wayside Controller HW import
from trackControllerHW.track_controller_hw_ui import TrackControllerHWUI, _build_networks
from trackControllerHW.track_controller_hw_backend import build_backend_for_sim

# Track Model import
from trackModel.track_model_backend import TrackNetwork
from trackModel.track_model_frontend import NetworkStatusUI

# Train Model import
from trainModel.train_model_backend import TrainModelBackend, Train
from trainModel.train_model_ui import TrainModelUI  


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
    #wayside hw
    nets_hw = _build_networks()
    hw_controllers = {
        "Blue Line": build_backend_for_sim(nets_hw["Blue Line"], "Blue Line"),
        "Red Line":  build_backend_for_sim(nets_hw["Red Line"],  "Red Line"),
        "Green Line": build_backend_for_sim(nets_hw["Green Line"], "Green Line"),
    }

    for ctrl in hw_controllers.values():
        ctrl.start_live_link(1.0)

    hw_ui = TrackControllerHWUI(hw_controllers)
    hw_ui.setWindowTitle("Wayside Controller – Hardware UI")
    hw_ui.show()
    #-----------------------------------------------------------------------------------------------
    TrackModelUI = NetworkStatusUI(network)
    TrackControllerUi = TrackControllerUI(controllers)
    TrackModelUI.show()
    TrackControllerUi.setWindowTitle("Wayside SW Module")
    TrackControllerUi.show()
    TrackControllerUi.refresh_tables()
    #-----------------------------------------------------------------------------------------------
    # === CTC Backend + UI ===
    ctc_state = TrackState("Green Line")
    # Replace its internal controller with the already-created one
    ctc_state.track_controller = controllers["Green Line"]
    controllers["Green Line"].set_ctc_backend(ctc_state)
    controllers["Green Line"].start_live_link(poll_interval=1.0)

    ctc_ui = CTCWindow()
    ctc_ui.state = ctc_state  # ensure UI uses this backend
    ctc_ui.setWindowTitle("Centralized Traffic Controller")
    ctc_ui.show()
    #-----------------------------------------------------------------------------------------------
    # train model backend + train wrapper + ui
    train_backend = TrainModelBackend() #backend
    train = Train(train_id="T1", backend=train_backend) # train object wrapper so it can talk to TrackNetwork
    train.attach_to_network(network)
    # choose a starting block for the train on Green Line (adjust block_id/displacement)
    train.connect_to_track(block_id=1, displacement_m=0.0)
    train_ui = TrainModelUI(train_backend) # launch the Train Model UI window
    train_ui.setWindowTitle("Train Model – T1 (Green Line)")
    train_ui.show()

    app.exec()