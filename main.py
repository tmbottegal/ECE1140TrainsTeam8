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


# Train Controller import
from trainControllerSW.TrainControllerBackend import TrainControllerBackend as TC_Backend
from trainControllerSW.TrainControllerUI import TrainControllerUI

# Universal import
from universal.universal import TrainCommand, SignalState, ConversionFunctions
from universal.global_clock import clock
# PyQt6 import
from PyQt6.QtWidgets import QApplication

LINE_DATA = {
  
   "Red Line":   [],
   "Green Line": [
       # ----- Section A -----
   ("A", 1, "free", "", "", "", "", "", 8.0, 45),
   ("A", 2, "free", "Pioneer", "Left", "", "", "", 8.0, 45),
   ("A", 3, "free", "", "", "", "", "", 8.0, 45),


   # ----- Section B -----
   ("B", 4, "free", "", "", "", "", "", 8.0, 45),
   ("B", 5, "free", "", "", "", "", "", 8.0, 45),
   ("B", 6, "free", "", "", "", "", "", 8.0, 45),


   # ----- Section C -----
   ("C", 7, "free", "", "", "", "", "", 8.0, 45),
   ("C", 8, "free", "", "", "", "", "", 8.0, 45),
   ("C", 9, "free", "Edgebrook", "Left", "", "", "", 8.0, 45),
   ("C", 10, "free", "", "", "", "", "", 8.0, 45),
   ("C", 11, "free", "", "", "", "", "", 8.0, 45),
   ("C", 12, "free", "", "", "SWITCH (12-13; 1-13)", "", "", 8.0, 45),


   # ----- Section D -----
   ("D", 13, "free", "", "", "", "", "", 7.7, 70),
   ("D", 14, "free", "", "", "", "", "", 7.7, 70),
   ("D", 15, "free", "", "", "", "", "", 7.7, 70),
   ("D", 16, "free", "Station", "Left/Right", "", "", "", 7.7, 70),


   # ----- Section E -----
   ("E", 17, "free", "", "", "", "", "", 9.0, 60),
   ("E", 18, "free", "", "", "", "", "", 9.0, 60),
   ("E", 19, "free", "", "", "", "", "RAILWAY CROSSING", 9.0, 60),
   ("E", 20, "free", "", "", "", "", "", 9.0, 60),


   # ----- Section F -----
   ("F", 21, "free", "", "", "", "", "", 15.4, 70),
   ("F", 22, "free", "Whited", "Left/Right", "", "", "", 15.4, 70),
   ("F", 23, "free", "", "", "", "", "", 15.4, 70),
   ("F", 24, "free", "", "", "", "", "", 15.4, 70),
   ("F", 25, "free", "", "", "", "", "", 10.3, 70),
   ("F", 26, "free", "", "", "", "", "", 5.1, 70),
   ("F", 27, "free", "", "", "", "", "", 6.0, 30),
   ("F", 28, "free", "", "", "SWITCH (28-29; 150-28)", "", "", 6.0, 30),
       # ----- Section G -----
   ("G", 29, "free", "", "", "", "", "", 6.0, 30),
   ("G", 30, "free", "", "", "", "", "", 6.0, 30),
   ("G", 31, "free", "South Bank", "Left", "", "", "", 6.0, 30),
   ("G", 32, "free", "", "", "", "", "", 6.0, 30),


   # ----- Section H -----
   ("H", 33, "free", "", "", "", "", "", 6.0, 30),
   ("H", 34, "free", "", "", "", "", "", 6.0, 30),
   ("H", 35, "free", "", "", "", "", "", 6.0, 30),


   # ----- Section I -----
   ("I", 36, "free", "", "", "", "", "", 6.0, 30),
   ("I", 37, "free", "", "", "", "", "", 6.0, 30),
   ("I", 38, "free", "", "", "", "", "", 6.0, 30),
   ("I", 39, "free", "Central", "Right", "", "", "", 6.0, 30),
   ("I", 40, "free", "", "", "", "", "", 6.0, 30),
   ("I", 41, "free", "", "", "", "", "", 6.0, 30),
   ("I", 42, "free", "", "", "", "", "", 6.0, 30),
   ("I", 43, "free", "", "", "", "", "", 6.0, 30),
   ("I", 44, "free", "", "", "", "", "", 6.0, 30),
   ("I", 45, "free", "", "", "", "", "", 6.0, 30),
   ("I", 46, "free", "", "", "", "", "", 6.0, 30),
   ("I", 47, "free", "", "", "", "", "", 6.0, 30),
   ("I", 48, "free", "Inglewood", "Right", "", "", "", 6.0, 30),
   ("I", 49, "free", "", "", "", "", "", 6.0, 30),
   ("I", 50, "free", "", "", "", "", "", 6.0, 30),
   ("I", 51, "free", "", "", "", "", "", 6.0, 30),
   ("I", 52, "free", "", "", "", "", "", 6.0, 30),
   ("I", 53, "free", "", "", "", "", "", 6.0, 30),
   ("I", 54, "free", "", "", "", "", "", 6.0, 30),
   ("I", 55, "free", "", "", "", "", "", 6.0, 30),
   ("I", 56, "free", "", "", "", "", "", 6.0, 30),
   ("I", 57, "free", "Overbrook", "Right", "", "", "", 6.0, 30),


   # ----- Section J -----
   ("J", 58, "free", "", "", "SWITCH TO YARD (57-yard)", "", "", 6.0, 30),
   ("J", 59, "free", "", "", "", "", "", 6.0, 30),
   ("J", 60, "free", "", "", "", "", "", 6.0, 30),
   ("J", 61, "free", "", "", "", "", "", 6.0, 30),
   ("J", 62, "free", "", "", "SWITCH FROM YARD (Yard-63)", "", "", 6.0, 30),


   # ----- Section K -----
   ("K", 63, "free", "", "", "", "", "", 5.1, 70),
   ("K", 64, "free", "", "", "", "", "", 5.1, 70),
   ("K", 65, "free", "Glenbury", "Right", "", "", "", 10.3, 70),
   ("K", 66, "free", "", "", "", "", "", 10.3, 70),
   ("K", 67, "free", "", "", "", "", "", 9.0, 40),
   ("K", 68, "free", "", "", "", "", "", 9.0, 40),


   # ----- Section L -----
   ("L", 69, "free", "", "", "", "", "", 9.0, 40),
   ("L", 70, "free", "", "", "", "", "", 9.0, 40),
   ("L", 71, "free", "", "", "", "", "", 9.0, 40),
   ("L", 72, "free", "", "", "", "", "", 9.0, 40),
   ("L", 73, "free", "Dormont", "Right", "", "", "", 9.0, 40),


       # ----- Section M -----
   ("M", 74, "free", "", "", "", "", "", 9.0, 40),
   ("M", 75, "free", "", "", "", "", "", 9.0, 40),
   ("M", 76, "free", "", "", "SWITCH (76-77;77-101)", "", "", 9.0, 40),


   # ----- Section N -----
   ("N", 77, "free", "Mt Lebanon", "Left/Right", "", "", "", 15.4, 70),
   ("N", 78, "free", "", "", "", "", "", 15.4, 70),
   ("N", 79, "free", "", "", "", "", "", 15.4, 70),
   ("N", 80, "free", "", "", "", "", "", 15.4, 70),
   ("N", 81, "free", "", "", "", "", "", 15.4, 70),
   ("N", 82, "free", "", "", "", "", "", 15.4, 70),
   ("N", 83, "free", "", "", "", "", "", 15.4, 70),
   ("N", 84, "free", "", "", "", "", "", 15.4, 70),
   ("N", 85, "free", "", "", "SWITCH (85-86; 100-85)", "", "", 15.4, 70),


   # ----- Section O -----
   ("O", 86, "free", "", "", "", "", "", 14.4, 25),
   ("O", 87, "free", "", "", "", "", "", 12.5, 25),
   ("O", 88, "free", "Poplar", "Left", "", "", "", 14.4, 25),


   # ----- Section P -----
   ("P", 89, "free", "", "", "", "", "", 10.8, 25),
   ("P", 90, "free", "", "", "", "", "", 10.8, 25),
   ("P", 91, "free", "", "", "", "", "", 10.8, 25),
   ("P", 92, "free", "", "", "", "", "", 10.8, 25),
   ("P", 93, "free", "", "", "", "", "", 10.8, 25),
   ("P", 94, "free", "", "", "", "", "", 10.8, 25),
   ("P", 95, "free", "", "", "", "", "", 10.8, 25),
   ("P", 96, "free", "Castle Shannon", "Left", "", "", "", 10.8, 25),
   ("P", 97, "free", "", "", "", "", "", 10.8, 25),


   # ----- Section Q -----
   ("Q", 98, "free", "", "", "", "", "", 10.8, 25),
   ("Q", 99, "free", "", "", "", "", "", 10.8, 25),
   ("Q", 100, "free", "", "", "", "", "", 10.8, 25),


   # ----- Section R -----
   ("R", 101, "free", "", "", "", "", "", 4.8, 26),


   # ----- Section S -----
   ("S", 102, "free", "", "", "", "", "", 12.9, 28),
   ("S", 103, "free", "", "", "", "", "", 12.9, 28),
   ("S", 104, "free", "", "", "", "", "", 10.3, 28),


       # ----- Section T -----
   ("T", 105, "free", "Dormont", "Right", "", "", "", 12.9, 28),
   ("T", 106, "free", "", "", "", "", "", 12.9, 28),
   ("T", 107, "free", "", "", "", "", "", 11.6, 28),
   ("T", 108, "free", "", "", "", "", "RAILWAY CROSSING", 12.9, 28),
   ("T", 109, "free", "", "", "", "", "", 12.9, 28),


   # ----- Section U -----
   ("U", 110, "free", "", "", "", "", "", 12.0, 30),
   ("U", 111, "free", "", "", "", "", "", 12.0, 30),
   ("U", 112, "free", "", "", "", "", "", 12.0, 30),
   ("U", 113, "free", "", "", "", "", "", 12.0, 30),
   ("U", 114, "free", "Glenbury", "Right", "", "", "", 19.4, 30),
   ("U", 115, "free", "", "", "", "", "", 12.0, 30),
   ("U", 116, "free", "", "", "", "", "", 12.0, 30),


   # ----- Section V -----
   ("V", 117, "free", "", "", "", "", "", 12.0, 15),
   ("V", 118, "free", "", "", "", "", "", 12.0, 15),
   ("V", 119, "free", "", "", "", "", "", 9.6, 15),
   ("V", 120, "free", "", "", "", "", "", 12.0, 15),
   ("V", 121, "free", "", "", "", "", "", 12.0, 15),


   # ----- Section W -----
   ("W", 122, "free", "", "", "", "", "", 9.0, 20),
   ("W", 123, "free", "Overbrook", "Right", "", "", "", 9.0, 20),
   ("W", 124, "free", "", "", "", "", "", 9.0, 20),
   ("W", 125, "free", "", "", "", "", "", 9.0, 20),
   ("W", 126, "free", "", "", "", "", "", 9.0, 20),
   ("W", 127, "free", "", "", "", "", "", 9.0, 20),
   ("W", 128, "free", "", "", "", "", "", 9.0, 20),
   ("W", 129, "free", "", "", "", "", "", 9.0, 20),
   ("W", 130, "free", "", "", "", "", "", 9.0, 20),
   ("W", 131, "free", "", "", "", "", "", 9.0, 20),
   ("W", 132, "free", "Inglewood", "Left", "", "", "", 9.0, 20),
   ("W", 133, "free", "", "", "", "", "", 9.0, 20),
   ("W", 134, "free", "", "", "", "", "", 9.0, 20),
   ("W", 135, "free", "", "", "", "", "", 9.0, 20),
   ("W", 136, "free", "", "", "", "", "", 9.0, 20),
   ("W", 137, "free", "", "", "", "", "", 9.0, 20),
   ("W", 138, "free", "", "", "", "", "", 9.0, 20),
   ("W", 139, "free", "", "", "", "", "", 9.0, 20),
   ("W", 140, "free", "", "", "", "", "", 9.0, 20),
   ("W", 141, "free", "Central", "Right", "", "", "", 9.0, 20),
   ("W", 142, "free", "", "", "", "", "", 9.0, 20),
   ("W", 143, "free", "", "", "", "", "", 9.0, 20),


   # ----- Section X -----
   ("X", 144, "free", "", "", "", "", "", 9.0, 20),
   ("X", 145, "free", "", "", "", "", "", 9.0, 20),
   ("X", 146, "free", "", "", "", "", "", 9.0, 20),


   # ----- Section Y -----
   ("Y", 147, "free", "", "", "", "", "", 9.0, 20),
   ("Y", 148, "free", "", "", "", "", "", 33.1, 20),
   ("Y", 149, "free", "", "", "", "", "", 7.2, 20),


   # ----- Section Z -----
   ("Z", 150, "free", "", "", "", "", "", 6.3, 20),








   ],
}

GREEN_LINE_DATA = LINE_DATA["Green Line"]


if __name__ == "__main__":
    
    app = QApplication([])
    network1 = TrackNetwork()
    network1.load_track_layout('trackModel/green_line.csv')
    network1.line_name = "GREEN LINE"
    network2 = TrackNetwork()
    network2.load_track_layout('trackModel/red_line.csv')
    network2.line_name = "RED LINE"


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
    # "Red Line": HardwareTrackControllerBackend(tm, "Red Line"),
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
    # === CTC Backend + UI ===
    ctc_state = TrackState("Green Line", GREEN_LINE_DATA, network1)
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
    train = Train(train_id=99, backend=train_backend) # train object wrapper so it can talk to TrackNetwork
    network1.add_train(train)
    network1.connect_train(99, block_id=1, displacement=0.0) 
    # choose a starting block for the train on Green Line (adjust block_id/displacement)
    train_ui = TrainModelUI(train_backend) # launch the Train Model UI window
    train_ui.setWindowTitle("Train Model – T1 (Green Line)")
    train_ui.show()

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
    app.exec()

    