"""
Minimal sanity check:
CTC TrackState sends suggested speed & authority to TrackControllerBackend
"""

from trackModel.track_model_backend import TrackNetwork
from trackControllerSW.track_controller_backend import TrackControllerBackend
from CTC.CTC_backend import TrackState
import datetime, time


def main():
    print("[TEST] Setting up fake Green Line integration...")

    # --- create TrackModel and backend ---
    track_model = TrackNetwork()
    track_model.segments[12] = object()   # fake block so it passes existence check

    controller = TrackControllerBackend(track_model, "Green Line")

    # --- create CTC and attach controller ---
    state = TrackState("Green Line", [])
    state.track_controller = controller

    # --- choose example data ---
    block_id = 12          # any valid integer
    suggested_speed = 25   # mph
    suggested_auth = 200   # yards

    print(f"[CTC] Sending test suggestion: block {block_id}, {suggested_speed} mph, {suggested_auth} yd")
    state.track_controller.receive_ctc_suggestion(block_id, suggested_speed, suggested_auth)

    print("\n[VERIFY] Backend received:")
    # Adapt to real backend's variable names
    if hasattr(controller, "_suggested_speed_mps"):
        print("  Speeds (m/s):", controller._suggested_speed_mps)
    elif hasattr(controller, "_suggested_speed_mph"):
        print("  Speeds (mph):", controller._suggested_speed_mph)
    else:
        print("  Speeds: (no attribute found)")

    if hasattr(controller, "_suggested_auth_yd"):
        print("  Authorities (yd):", controller._suggested_auth_yd)
    elif hasattr(controller, "_suggested_auth_m"):
        print("  Authorities (m):", controller._suggested_auth_m)
    else:
        print("  Authorities: (no attribute found)")

def test_dynamic_suggestions():
    print("[TEST] Starting dynamic CTC→TC loop demo...\n")

    # 1️⃣ Setup
    from trackModel.track_model_backend import TrackNetwork
    from trackControllerSW.track_controller_backend import TrackControllerBackend
    from CTC.CTC_backend import TrackState

    track_model = TrackNetwork()
    controller = TrackControllerBackend(track_model, "Green Line")
    ctc = TrackState("Green Line", [])

    ctc.track_controller = controller

    # 2️⃣ Initial suggestion
    block_id = 12
    speed_mph = 25
    authority_yd = 200

    print(f"[CTC] Dispatching initial suggestion → Block {block_id}: {speed_mph} mph, {authority_yd} yd")
    controller.receive_ctc_suggestion(block_id, speed_mph, authority_yd)

    # 3️⃣ Time loop: simulate movement and updates
    for tick in range(5):
        time.sleep(1.0)  # wait 1 second between updates

        # Decrease authority (simulate approaching destination)
        authority_yd = max(0, authority_yd - 40)
        # Decrease speed slightly each tick
        speed_mph = max(0, speed_mph - 3)

        print(f"\n[CTC→TC] Tick {tick+1}: sending update → Block {block_id}: {speed_mph} mph, {authority_yd} yd")
        controller.receive_ctc_suggestion(block_id, speed_mph, authority_yd)

        # Optional: print TC’s internal state after each update
        if hasattr(controller, "_suggested_speed_mps"):
            print("  TC Speeds (m/s):", controller._suggested_speed_mps)
        elif hasattr(controller, "_suggested_speed_mph"):
            print("  TC Speeds (mph):", controller._suggested_speed_mph)
        if hasattr(controller, "_suggested_auth_yd"):
            print("  TC Authorities (yd):", controller._suggested_auth_yd)
        elif hasattr(controller, "_suggested_auth_m"):
            print("  TC Authorities (m):", controller._suggested_auth_m)

    print("\n[TEST COMPLETE] Dynamic suggestion test finished.")



if __name__ == "__main__":
    main()
