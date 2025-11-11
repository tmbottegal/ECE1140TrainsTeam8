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
    print("  Speeds:", controller._suggested_speed_mph)
    print("  Authorities:", controller._suggested_auth_yd)


if __name__ == "__main__":
    main()
