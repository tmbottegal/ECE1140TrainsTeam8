from __future__ import annotations
""" 
 This is the Train Controller Run Program

 Launch the demo UI
"""
""" 

This is the main entry point for running the Train Controller application.

It performs the following tasks:
1. Initialize PyQt6 application
2. Optionally import Train Model (if available in the Python path)
3. Create Train Controller Frontend with optional Train Model attachment
4. Create and show Train Controller UI
5. Optionally create and show Train Model UI (if available)
6. Start the Qt event loop

INTEGRATION WITH TRAIN MODEL:
If the Train Model backend is available in the Python path, it will be
automatically imported and connected to the Train Controller. Otherwise,
the Train Controller runs in demo mode with simulated physics.

To run with Train Model integration:
- Ensure train_model_backend.py and train_model_ui.py are in Python path
- Run this script

To run in demo mode (testing only):
- Just run this script without Train Model files available  
"""

import sys
from PyQt6.QtWidgets import QApplication

# Import Train Controller modules
try:
    from .TrainControllerFrontend import TrainControllerFrontend
    from .TrainControllerUI import TrainControllerUI
except Exception:
    from TrainControllerFrontend import TrainControllerFrontend  # type: ignore
    from TrainControllerUI import TrainControllerUI  # type: ignore

# ======================================================================
# OPTIONAL TRAIN MODEL IMPORT
# ======================================================================
# Try to import Train Model if it's available in the Python path.
# If not available, the Train Controller will run in demo mode.

TM_BACKEND = None  # Train Model Backend class (if available)
TM_UI_CLS = None   # Train Model UI class (if available)

try:
    # Attempt to import Train Model backend and UI
    from train_model_backend import TrainModelBackend as _TMBackend  # type: ignore
    from train_model_ui import TrainModelUI as _TMUI  # type: ignore
    
    # If successful, store the classes
    TM_BACKEND = _TMBackend
    TM_UI_CLS = _TMUI
    
    print("✓ Train Model found - running in INTEGRATED mode")
    print("  Train Controller will receive inputs from Train Model")
    print("  and send outputs to Train Model")
    
except Exception as e:
    # Train Model not available - will run in demo mode
    print("⚠ Train Model not found - running in DEMO mode")
    print("  Train Controller will use simulated physics")
    print(f"  (Import error: {e})")


def main() -> None:
    """
    Main entry point for the Train Controller application
    
    This function:
    1. Creates the QApplication
    2. Creates optional Train Model instance (if available)
    3. Creates Train Controller Frontend (connected to TM if available)
    4. Creates and shows Train Controller UI
    5. Creates and shows Train Model UI (if available)
    6. Starts the Qt event loop
    """
    
    # Create the Qt application
    app = QApplication(sys.argv)
    
    # ======================================================================
    # CREATE TRAIN MODEL (if available)
    # ======================================================================
    # If Train Model backend was successfully imported, create an instance
    # Otherwise, set to None (demo mode)
    
    if TM_BACKEND:
        print("\nCreating Train Model instance...")
        tm = TM_BACKEND()
        print(f"  Train Model created: {type(tm).__name__}")
    else:
        tm = None
        print("\nNo Train Model - using demo mode")
    
    # ======================================================================
    # CREATE TRAIN CONTROLLER
    # ======================================================================
    # Create the Frontend with optional Train Model attachment
    # The train_id identifies this specific train
    
    print("\nCreating Train Controller...")
    frontend = TrainControllerFrontend(train_id="Blue-01", train_model=tm)
    print(f"  Train ID: Blue-01")
    print(f"  Mode: {'INTEGRATED' if tm else 'DEMO'}")
    
    # Create the UI connected to the Frontend
    ui = TrainControllerUI(frontend)
    ui.resize(1200, 750)  # Set window size
    ui.show()
    print(f"  Train Controller UI shown")
    
    # ======================================================================
    # CREATE TRAIN MODEL UI (if available)
    # ======================================================================
    # If both Train Model and its UI are available, create and show the UI
    # Position it next to the Train Controller UI for convenience
    
    if tm and TM_UI_CLS:
        print("\nCreating Train Model UI...")
        tm_ui = TM_UI_CLS(tm)  # type: ignore
        
        # Position Train Model UI to the right of Train Controller UI
        tm_ui.move(ui.x() + ui.width() + 10, ui.y())
        tm_ui.show()
        print(f"  Train Model UI shown (positioned next to Train Controller)")
    
    # ======================================================================
    # START APPLICATION
    # ======================================================================
    print("\n" + "="*60)
    print("TRAIN CONTROLLER STARTED")
    print("="*60)
    if tm:
        print("Mode: INTEGRATED with Train Model")
        print("Data Flow: Train Model → Train Controller → Train Model")
    else:
        print("Mode: DEMO (no Train Model)")
        print("Use the demo controls to simulate Train Model inputs")
    print("="*60 + "\n")
    
    # Start the Qt event loop (blocks until application closes)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()