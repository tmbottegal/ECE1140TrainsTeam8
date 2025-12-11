import sys
import os
import logging
logging.basicConfig(level=logging.INFO)

# Set up sys.path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CTC'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackControllerHW'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackControllerSW'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackModel'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trainModel'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trainControllerSW'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'universal'))


# CTC import
from CTC.CTC_backend import TrackState,Block 
from CTC.CTC_ui import CTCWindow 
from CTC.track_controller_hw_server import HardwareTrackControllerServer # comment if doesnt work

# Wayside Controller SW import
from trackControllerSW.track_controller_backend import TrackControllerBackend
from trackControllerSW.track_controller_ui import TrackControllerUI

# Wayside Controller HW import
from trackControllerHW.track_controller_hw_ui import TrackControllerHWUI, _build_networks
from trackControllerHW.track_controller_hw_backend import build_backend_for_sim, HardwareTrackControllerBackend

# Track Model import
from trackModel.track_model_backend import TrackNetwork
from trackModel.track_model_test_frontend import NetworkStatusUI

# Train Model import
from trainModel.train_model_backend import TrainModelBackend, Train
from trainModel.train_model_ui import TrainModelUI  
from trainModel.train_model_test_ui import TrainModelTestUI 


# Train Controller import
from trainControllerSW.TrainControllerBackend import TrainControllerBackend as TC_Backend
from trainControllerSW.TrainControllerFrontend import TrainControllerUI as TrainControllerWindow

# Universal import
from universal.universal import TrainCommand, SignalState, ConversionFunctions
from universal.global_clock import clock
# PyQt6 import
from PyQt6.QtWidgets import QApplication




if __name__ == "__main__":
    
    app = QApplication([])
    network1 = TrackNetwork()
    network1.load_track_layout('trackModel/green_line.csv')
    network1.line_name = "Green Line"
    network2 = TrackNetwork()
    network2.load_track_layout('trackModel/red_line.csv')
    network2.line_name = "Red Line"
    trains: dict[tuple[str, int | str], dict] = {}

    #------------------------------------------------------------------------------------------------
    # trackcontroller sw stuff that might be wrong or need to be changed, tell me to change if needed
    controllers = {
        "Green Line": TrackControllerBackend(network1, "Green Line"),
        "Red Line": TrackControllerBackend(network2, "Red Line")
        }
    for ctrl in controllers.values(): 
        ctrl.start_live_link(poll_interval=1.0)
    #------------------------------------------------------------------------------------------------
    # track controller hw
    # hw_controllers = {
    # "Green Line": HardwareTrackControllerBackend(network1, "Green Line"),
    # Add Red Line if needed:
    # "Red Line": HardwareTrackControllerBackend(network2, "Red Line"),
# }

    # for ctrl in hw_controllers.values():
    #     ctrl.start_live_link(1.0)

    # hw_ui = TrackControllerHWUI(hw_controllers)
    # hw_ui.setWindowTitle("Wayside Controller – Hardware UI")
    # hw_ui.show()
    #-----------------------------------------------------------------------------------------------
    TrackModelUI = NetworkStatusUI(network1, network2)
    TrackModelUI.show()
    TrackModelUI.refresh_status()
    clock.register_listener(network1.set_time)
    clock.register_listener(network2.set_time)
    #-----------------------------------------------------------------------------------------------
    TrackControllerUi = TrackControllerUI(controllers)
    TrackControllerUi.setWindowTitle("Wayside SW Module")
    TrackControllerUi.show()
    TrackControllerUi.refresh_tables()
    #-----------------------------------------------------------------------------------------------
    '''
    # train model backend + train wrapper + ui
    train_backend = TrainModelBackend() #backend
    train = Train(train_id=99, backend=train_backend) # train object wrapper so it can talk to TrackNetwork
    network1.add_train(train)
    network1.connect_train(99, block_id=1, displacement=0.0) 
    # choose a starting block for the train on Green Line (adjust block_id/displacement)
    train_ui = TrainModelUI(train_backend) # launch the Train Model UI window
    train_ui.setWindowTitle("Train Model – T1")
    train_ui.show()
    #-----------------------------------------------------------------------------------------------
    # train controller testbench
    testbench = TrainModelTestUI(train_backend)
    testbench.setWindowTitle("Train Testbench (Acting as Train Controller)")
    testbench.show()
    '''

    # keep track of all trains by (line_name, train_id)
    def create_train(train_id: int, network: TrackNetwork, start_block_id: int) -> None:
        """
        creates TrainModelBackend + Train wrapper, attaches it to the right TrackNetwork, opens TrainModel UI + Test UI for that specific train
        """
        # pick correct network based on line name label
        line_name = network.line_name
        # normalize ints or string ids
        train_id_str = int(train_id)

        # create backend and train
        backend = TrainModelBackend(line_name=line_name)
        backend.train_id = train_id_str  

        train = Train(train_id=train_id_str, backend=backend)
        network.add_train(train)

        network.connect_train(train_id_str, block_id=start_block_id, displacement=0.0)

        # create main Train Model UI
        tm_ui = TrainModelUI(backend)
        tm_ui.setWindowTitle(f"Train Model – {line_name} – Train {train_id_str}")
        tm_ui.show()

        # create the Test UI (acting as controller)
        test_ui = TrainModelTestUI(backend)
        test_ui.setWindowTitle(f"Train Controller Testbench – {line_name} – Train {train_id_str}")
        test_ui.show()

        # store in registry for later
        trains[(line_name, train_id_str)] = {
            "backend": backend, "train": train, "tm_ui": tm_ui,"test_ui": test_ui,
        }

        print(f"[MAIN] Created train {train_id_str} on {line_name}, block {start_block_id}")
    #-----------------------------------------------------------------------------------------------
    # === CTC Backend + UI ===
    '''
    ctc_state = TrackState("Green Line", network1)
    # Replace its internal controller with the already-created one
    ctc_state.track_controller = controllers["Green Line"]
    controllers["Green Line"].set_ctc_backend(ctc_state)
    controllers["Green Line"].start_live_link(poll_interval=1.0)

    #ctc_ui = CTCWindow()
    #ctc_ui.state = ctc_state  # ensure UI uses this backend
    '''

    # Create both real CTC backends
    ctc_green = TrackState("Green Line", network1)
    ctc_red = TrackState("Red Line", network2)

    # Replace internal controllers so both use REAL modules
    ctc_green.track_controller = controllers["Green Line"]
    controllers["Green Line"].set_ctc_backend(ctc_green)

    ctc_red.track_controller = controllers["Red Line"]
    controllers["Red Line"].set_ctc_backend(ctc_red)

    ctc_green.on_train_created = create_train
    ctc_red.on_train_created  = create_train

    # Give both to the UI
    backend_by_line = {
        "Green Line": ctc_green,
        "Red Line": ctc_red
    }

    hw_server = HardwareTrackControllerServer(backend_by_line, host="0.0.0.0", port=6000) # comment if doesnt work
    hw_server.start() # comment if doesnt work
    
    ctc_ui = CTCWindow(backend_by_line)
    ctc_ui.show()


    ctc_ui.setWindowTitle("Centralized Traffic Controller")
    ctc_ui.show()
 #-----------------------------------------------------------------------------------------------
    # === TRAIN CONTROLLER INTEGRATION ===
    print("\n" + "="*60)
    print("SETTING UP TRAIN CONTROLLER INTEGRATION")
    print("="*60)
    
    # Dictionary to store train controllers by train_id
    train_controllers = {}
    
    def create_train_with_controller(train_id: int, network: TrackNetwork, start_block_id: int) -> None:
        """
        Enhanced create_train that also creates and attaches a Train Controller
        """
        # Create train using existing function
        create_train(train_id, network, start_block_id)
        
        line_name = network.line_name
        train_id_str = int(train_id)
        
        # Get the backend from trains registry
        train_data = trains[(line_name, train_id_str)]
        backend = train_data["backend"]
        train_obj = train_data["train"]
        
        print(f"\n[Creating Train Controller for Train {train_id_str}]")
        
        # Create Train Controller Backend
        train_controller = TC_Backend(train_id=train_id_str)
        print(f"  ✓ Train Controller backend created")
        print(f"    Kp: {train_controller.kp}, Ki: {train_controller.ki}")
        print(f"    Mode: {'AUTO' if train_controller.automatic_mode else 'MANUAL'}")
        
        # Create integration between Train Controller and Train Model
        # We need to modify the Train's _auto_tick to call the controller
        
        # Store original _auto_tick
        original_auto_tick = train_obj._auto_tick
        
        # Create new _auto_tick that includes controller
        def enhanced_auto_tick(current_time):
            """Enhanced tick that integrates Train Controller"""
            # First run the original train model tick
            original_auto_tick(current_time)
            
            # Now update Train Controller with current state
            train_controller.update_from_train_model(
                current_speed_mph=backend.velocity * backend.MPS_TO_MPH,
                engine_fail=backend.engine_failure,
                brake_fail=backend.brake_failure,
                signal_fail=backend.signal_pickup_failure
            )
            
            # Update from Track Controller (commanded speed and authority)
            # Convert from m/s to MPH for controller
            train_controller.update_from_track_controller(
                commanded_speed_mph=backend.commanded_speed * backend.MPS_TO_MPH,
                authority_ft=backend.authority_m * 3.28084,  # meters to feet
                speed_limit_mph=backend.MAX_SPEED * backend.MPS_TO_MPH
            )
            
            # Calculate power using PI controller
            train_controller.calculate_power()
            
            # Apply controller outputs to train model
            backend.power_kw = train_controller.power_kw
            backend.service_brake = train_controller.service_brake
            backend.emergency_brake = train_controller.emergency_brake
            backend.left_doors = train_controller.left_doors_open
            backend.right_doors = train_controller.right_doors_open
            backend.cabin_lights = train_controller.interior_lights_on
            backend.headlights = train_controller.headlights_on
            backend.temperature_setpoint = (train_controller.cabin_temp_f - 32) * 5/9  # F to C
        
        # Replace the _auto_tick with our enhanced version
        train_obj._auto_tick = enhanced_auto_tick
        
        print(f"  ✓ Train Controller integrated with Train Model tick")
        
        # Create Train Controller UI using the TrainControllerUI class from TrainControllerFrontend
        train_controller_ui = TrainControllerWindow()
        train_controller_ui.backend = train_controller  # Replace backend with our integrated one
        train_controller_ui.setWindowTitle(f"Train Controller - Train {train_id_str} ({line_name})")
        train_controller_ui.resize(1200, 750)
        train_controller_ui.show()
        
        print(f"  ✓ Train Controller UI created and shown")
        
        # Store controller reference
        train_controllers[(line_name, train_id_str)] = {
            "backend": train_controller,
            "ui": train_controller_ui
        }
        
        print(f"[Train Controller for Train {train_id_str} ready!]")
        print(f"  - Automatic mode: {train_controller.automatic_mode}")
        print(f"  - Safety systems active")
        print(f"  - UI displayed")
        print()
    
    print("Train Controller integration ready!")
    print("Use create_train_with_controller() to create trains with controllers")
    print("="*60)
    print()

    create_train_with_controller(99, network1, 1)
    create_train_with_controller(98, network1, 3)


    app.exec()

    