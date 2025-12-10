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
from CTC.CTC_backend import TrackState,Block 
from CTC.CTC_ui import CTCWindow 

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
from trainControllerSW.TrainControllerUI import TrainControllerUI

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
    hw_controllers = {
    "Green Line": HardwareTrackControllerBackend(network1, "Green Line"),
    # Add Red Line if needed:
    "Red Line": HardwareTrackControllerBackend(network2, "Red Line"),
}

    for ctrl in hw_controllers.values():
        ctrl.start_live_link(1.0)

    hw_ui = TrackControllerHWUI(hw_controllers)
    hw_ui.setWindowTitle("Wayside Controller – Hardware UI")
    hw_ui.show()
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

    ctc_ui = CTCWindow(backend_by_line)
    ctc_ui.show()


    ctc_ui.setWindowTitle("Centralized Traffic Controller")
    ctc_ui.show()
 #-----------------------------------------------------------------------------------------------
    '''
    # === TRAIN CONTROLLER INTEGRATION (WORKAROUND VERSION) ===
    print("\n" + "="*60)
    print("INTEGRATING TRAIN CONTROLLER...")
    print("="*60)
    print("NOTE: Using workaround method (clock listener)")
    print("      Ideal: Train Model calls controller in tick()")
    print("      Current: main.py listener calls controller manually")
    print("="*60)
    
    # Create Train Controller backend
    print("\n[1/4] Creating Train Controller backend...")
    train_controller = TC_Backend(train_id="T1")
    print(f"  ✓ Train Controller created")
    print(f"    Train ID: {train_controller.state.train_id}")
    print(f"    Kp: {train_controller.state.kp}, Ki: {train_controller.state.ki}")
    print(f"    Initial mode: {'AUTO' if train_controller.state.auto_mode else 'MANUAL'}")
    
    # Attach Train Controller to Train Model
    print("\n[2/4] Attaching Train Controller to Train Model...")
    train.attach_controller(train_controller)
    print(f"  ✓ Train Controller attached")
    
    # Workaround: Register clock listener
    print("\n[3/4] Setting up automatic integration (workaround)...")
    
    # Track last tick time for accurate dt calculation
    train_controller_last_tick = [None]  # Use list to allow modification in closure
    
    def train_controller_clock_listener(current_time):
        """
        Workaround: Manually call controller integration every clock tick.
        
        In ideal solution, Train.tick() would call step_controller() automatically.
        Since Train Model hasn't made that change yet, we register this listener
        with the global clock to call step_controller() manually.
        """
        try:
            # Calculate dt since last tick
            if train_controller_last_tick[0] is None:
                train_controller_last_tick[0] = current_time
                return
            
            dt_s = (current_time - train_controller_last_tick[0]).total_seconds()
            train_controller_last_tick[0] = current_time
            
            # Call the controller integration (same as Train.tick() would)
            if dt_s > 0.0:
                train.step_controller(dt_s)
                
        except Exception as e:
            import traceback
            print(f"\n[ERROR] Train Controller integration failed:")
            print(f"  {e}")
            traceback.print_exc()
    
    # Register with global clock
    clock.register_listener(train_controller_clock_listener)
    print(f"  ✓ Clock listener registered")
    print(f"  ✓ Controller will run every clock tick")
    
    # Create Train Controller UI
    print("\n[4/4] Creating Train Controller UI...")
    from trainControllerSW.TrainControllerFrontend import TrainControllerFrontend
    train_controller_frontend = TrainControllerFrontend(train_id="T1", train_model=None)
    train_controller_frontend.ctrl = train_controller
    
    train_controller_ui = TrainControllerUI(train_controller_frontend)
    train_controller_ui.setWindowTitle("Train Controller - T1 (Green Line)")
    train_controller_ui.resize(1200, 750)
    train_controller_ui.show()
    '''

    create_train(99, network1, 1)
    create_train(98, network1, 3)

    app.exec()

    