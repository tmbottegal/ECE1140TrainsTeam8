from CTC_backend import TrackState

def test_ctc_sends_suggestion():
    print("\n=== TEST: CTC Sends Suggested Speed & Authority ===")

    # Create the CTC backend (Green Line)
    ctc = TrackState("Green Line")

    # Send a dispatch with known values
    train_id = "T1"
    start_block = 4
    suggested_speed_mph = 20   # should become 8.94 m/s
    suggested_auth_yd = 200    # should become 182.88 m

    ctc.dispatch_train(train_id, start_block, suggested_speed_mph, suggested_auth_yd)

    print("\n--- After dispatch, suggestions stored: ---")
    suggestions = ctc._train_suggestions.get(train_id)
    print(suggestions)

    print("\n--- Running tick to see resend ---")
    ctc.tick_all_modules()

    print("\n=== END TEST ===\n")


if __name__ == "__main__":
    test_ctc_sends_suggestion()
