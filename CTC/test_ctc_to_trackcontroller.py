"""
Minimal sanity check:
CTC TrackState sends suggested speed & authority to TrackControllerBackend
"""

from trackModel.track_model_backend import TrackNetwork
from trackControllerSW.track_controller_backend import TrackControllerBackend
from CTC.CTC_backend import TrackState


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



if __name__ == "__main__":
    main()
