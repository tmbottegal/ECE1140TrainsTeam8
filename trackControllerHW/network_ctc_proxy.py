"""Network CTC Proxy for Hardware Track Controller.

Forwards wayside status updates over TCP to the CTC running on the laptop.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Any

try:
    from trackControllerHW.track_controller_hw_backend import WaysideStatusUpdate
except ImportError:
    from track_controller_hw_backend import WaysideStatusUpdate

from universal.universal import SignalState

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class NetworkCTCProxy:
    """Proxy that forwards wayside status updates to CTC over TCP."""

    def __init__(self, host: str, port: int = 6000) -> None:
        """Initialize the proxy.

        Args:
            host: IP address of the laptop running main.py.
            port: TCP port where the laptop server listens.
        """
        self.host = host
        self.port = port
        self._lock = threading.Lock()

    def receive_wayside_status(
        self,
        line_name: str,
        status_updates: list[WaysideStatusUpdate],
    ) -> None:
        """Convert status updates to dicts and send them to laptop.

        Args:
            line_name: Name of the rail line.
            status_updates: List of status updates to send.
        """
        payload_updates: list[dict[str, Any]] = []
        for s in status_updates:
            if isinstance(s.signal_state, SignalState):
                signal_value = s.signal_state.value
            else:
                signal_value = str(s.signal_state)

            payload_updates.append({
                "block_id": int(s.block_id),
                "occupied": bool(s.occupied),
                "signal_state": signal_value,
                "switch_position": s.switch_position,
                "crossing_status": s.crossing_status,
            })

        payload = {
            "type": "wayside_status",
            "line": line_name,
            "updates": payload_updates,
        }
        self._send(payload)

    def _send(self, payload: dict[str, Any]) -> None:
        """Send payload to CTC server over TCP."""
        data = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            with self._lock:
                with socket.create_connection(
                    (self.host, self.port), timeout=2.0
                ) as sock:
                    sock.sendall(data)
            logger.debug(
                "Sent %d bytes to CTC server at %s:%d",
                len(data),
                self.host,
                self.port,
            )
        except OSError:
            logger.exception(
                "Failed to send payload to CTC server at %s:%d",
                self.host,
                self.port,
            )