from __future__ import annotations
import json
import logging
import socket
import threading
from typing import Any, Dict, List

# Try both import styles so it works whether we run from repo root
# or inside trackControllerHW.
try:
    from trackControllerHW.track_controller_hw_backend import WaysideStatusUpdate
except ImportError:
    from track_controller_hw_backend import WaysideStatusUpdate

from universal.universal import SignalState

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class NetworkCTCProxy:
    """
    Acts like a CTC backend to HardwareTrackControllerBackend,
    but forwards wayside status updates over TCP to the real CTC
    running on the laptop.
    """

    def __init__(self, host: str, port: int = 6000) -> None:
        """
        :param host: IP address of the laptop running main.py
        :param port: TCP port where the laptop server listens
        """
        self.host = host
        self.port = port
        self._lock = threading.Lock()

    # -------- API used by HardwareTrackControllerBackend --------

    def receive_wayside_status(
        self,
        line_name: str,
        status_updates: List[WaysideStatusUpdate],
    ) -> None:
        """
        Called by _send_status_to_ctc() in your HW backend.
        Convert dataclasses to plain dicts and send them to laptop.
        """
        payload_updates: List[Dict[str, Any]] = []
        for s in status_updates:
            # SignalState -> string ("Red", "Yellow", "Green")
            if isinstance(s.signal_state, SignalState):
                signal_value = s.signal_state.value
            else:
                signal_value = str(s.signal_state)

            payload_updates.append(
                {
                    "block_id": int(s.block_id),
                    "occupied": bool(s.occupied),
                    "signal_state": signal_value,
                    "switch_position": s.switch_position,
                    "crossing_status": s.crossing_status,
                }
            )

        payload = {
            "type": "wayside_status",
            "line": line_name,
            "updates": payload_updates,
        }
        self._send(payload)

    # -------- internal TCP helper --------

    def _send(self, payload: Dict[str, Any]) -> None:
        data = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            with self._lock:
                with socket.create_connection((self.host, self.port), timeout=2.0) as sock:
                    sock.sendall(data)
            logger.debug(
                "Sent %d bytes to CTC server at %s:%d",
                len(data), self.host, self.port,
            )
        except OSError:
            logger.exception(
                "Failed to send payload to CTC server at %s:%d",
                self.host, self.port,
            )
