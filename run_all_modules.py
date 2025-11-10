import subprocess
import sys
import os
import time

# Add project root to path
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from trackModel.track_model_backend import TrackNetwork

# Define the modules to run
modules = {
    #"CTC": "CTC/CTC_frontend.py",
    #"Track Model": "trackModel/track_model_frontend.py",
    "Track Controller SW": "trackControllerSW/track_controller_run.py",
    #"Track Controller HW": "trackControllerHW/track_controller_hw.py",
    #"Train Model": "trainModel/train_model_ui.py",
    #"Train Controller SW": "trainControllerSW/TrainControllerRun.py"
}

# Global shared network that modules can access
shared_track_network = None

def initialize_shared_network(line_files=None):
    """
    Create and initialize shared TrackNetwork(s).
    
    Args:
        line_files: Optional list of track layout CSV files to preload.
                   If None, creates an empty network.
    
    Returns:
        TrackNetwork instance or dict of TrackNetwork instances by line name.
    """
    global shared_track_network
    
    if line_files is None:
        # Create a single empty network
        shared_track_network = TrackNetwork()
        print("Created empty shared TrackNetwork")
        return shared_track_network
    
    if isinstance(line_files, str):
        line_files = [line_files]
    
    if len(line_files) == 1:
        # Single network
        shared_track_network = TrackNetwork()
        try:
            shared_track_network.load_track_layout(line_files[0])
            print(f"Loaded {shared_track_network.line_name}: {len(shared_track_network.segments)} segments")
        except Exception as e:
            print(f"Warning: Failed to load {line_files[0]}: {e}")
        return shared_track_network
    else:
        # Multiple networks (one per line)
        networks = {}
        for line_file in line_files:
            try:
                net = TrackNetwork()
                net.load_track_layout(line_file)
                networks[net.line_name] = net
                print(f"Loaded {net.line_name}: {len(net.segments)} segments")
            except Exception as e:
                print(f"Warning: Failed to load {line_file}: {e}")
        shared_track_network = networks
        return networks

def main():
    """Main entry point - creates shared network and launches modules."""
    global shared_track_network
    
    print("=" * 60)
    print("Transit System - Launching All Modules")
    print("=" * 60)
    print()
    
    # Initialize shared TrackNetwork
    print("Initializing shared TrackNetwork...")
    
    # Option 1: Empty network (modules will load layouts as needed)
    shared_track_network = initialize_shared_network()
    
    # Option 2: Preload specific line(s)
    # Uncomment and modify paths as needed:
    # line_files = [
    #     os.path.join(base_dir, "trackModel", "Blue_Line.csv"),
    #     os.path.join(base_dir, "trackModel", "Red_Line.csv"),
    #     os.path.join(base_dir, "trackModel", "Green_Line.csv"),
    # ]
    # shared_track_network = initialize_shared_network(line_files)
    
    # Make network available as a module that can be imported
    import types
    network_module = types.ModuleType('shared_track_network')
    network_module.network = shared_track_network
    network_module.get_network = lambda: shared_track_network
    sys.modules['shared_track_network'] = network_module
    
    print(f"Shared TrackNetwork initialized")
    print(f"Network object ID: {id(shared_track_network)}")
    print()
    print("NOTE: Modules can access the shared network by importing:")
    print("  import shared_track_network")
    print("  network = shared_track_network.get_network()")
    print()
    
    processes = []

    try:
        for name, script in modules.items():
            script_path = os.path.join(base_dir, script)
            if not os.path.exists(script_path):
                print(f"⚠ {name} ({script}) not found – skipping.")
                continue

            print(f"Launching {name}...")
            
            # Use subprocess.Popen to launch as separate process
            # Set PYTHONPATH to include base directory
            env = os.environ.copy()
            env['PYTHONPATH'] = base_dir + os.pathsep + env.get('PYTHONPATH', '')
            
            p = subprocess.Popen(
                [sys.executable, script_path],
                env=env,
                cwd=base_dir
            )
            processes.append((name, p))
            time.sleep(1)  # Delay between launches

        print()
        print("=" * 60)
        print("All modules launched successfully!")
        print("Close this window or press Ctrl+C to stop all modules")
        print("=" * 60)
        print()
        
        # Keep main process running and monitor subprocesses
        try:
            while True:
                time.sleep(1)
                # Check if any process has died
                for name, p in processes:
                    if p.poll() is not None:
                        print(f"⚠ {name} has stopped (exit code: {p.poll()})")
        except KeyboardInterrupt:
            pass

    except KeyboardInterrupt:
        pass
    finally:
        print()
        print("=" * 60)
        print("Shutting down all modules...")
        print("=" * 60)
        
        for name, p in processes:
            if p.poll() is None:  # Process still running
                print(f"Stopping {name}...")
                p.terminate()
        
        # Give processes time to shut down gracefully
        time.sleep(2)
        
        # Force kill any remaining
        for name, p in processes:
            if p.poll() is None:
                print(f"Force stopping {name}...")
                p.kill()
        
        print("All modules stopped.")

if __name__ == "__main__":
    main()