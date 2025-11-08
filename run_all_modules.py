import subprocess
import sys
import os
import time

# Define the modules to run(edit file path here if names change)

#Comment out parts if you dont want to run it for testing

modules = {
    "CTC": "CTC/CTC_frontend.py",
    "Track Model": "trackModel/track_model_frontend.py",
    "Track Controller SW": "trackControllerSW/track_controller_run.py",
    #"Track Controller HW": "trackControllerHW/track_controller_hw.py",      <---- Jay change when you push
    "Train Model": "trainModel/train_model_ui.py",
    "Train Controller SW": "trainControllerSW/TrainControllerRun.py"
}

processes = []

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        for name, script in modules.items():
            script_path = os.path.join(base_dir, script)
            if not os.path.exists(script_path):
                print(f"{name} ({script}) not found — skipping.")
                continue

            print(f"Launching {name}...")
            p = subprocess.Popen([sys.executable, script_path])
            processes.append(p)
            time.sleep(1)  # delay so modules don't all open simultaneously(could fuck with some systems)

        print("Close this window to stop them\n")
        for p in processes:
            p.wait()

    except KeyboardInterrupt:
        print("Shutting down modules")
        for p in processes:
            p.terminate()

if __name__ == "__main__":
    main()
