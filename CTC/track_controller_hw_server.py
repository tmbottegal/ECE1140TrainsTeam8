from __future__ import annotations
import json
import logging
import socket
import threading
from typing import Any, Dict, List

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class HardwareTrackControllerServer:
    """
    TCP server that listens for wayside status messages from the hardware
    track controller running on the Raspberry Pi.

    We DON'T change CTC code. Instead, we call existing methods on the
    per-line TrackState objects (one for Green, one for Red).
    """

    def __init__(self, backends_by_line: Dict[str, Any],
                 host: str = "0.0.0.0", port: int = 6000) -> None:
        """
        backends_by_line: {"Green Line": TrackState(...), "Red Line": TrackState(...)}
        """
        self.backends_by_line = backends_by_line
        self.host = host
        self.port = port

    def start(self) -> None:
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
        logger.info("[HWTC-Server] Listening on %s:%d", self.host, self.port)

    # ------------- internal server loop -------------

    def _serve(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen()
            while True:
                conn, addr = s.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True,
                ).start()

    def _handle_client(self, conn: socket.socket, addr) -> None:
        logger.info("[HWTC-Server] Connection from %s", addr)
        with conn:
            buf = b""
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                        self._handle_message(msg)
                    except Exception:
                        logger.exception("[HWTC-Server] Bad message from Pi")

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        msg_type = msg.get("type")
        if msg_type == "wayside_status":
            self._handle_wayside_status(msg)
        else:
            logger.warning("[HWTC-Server] Unknown message type '%s'", msg_type)

    def _handle_wayside_status(self, msg: Dict[str, Any]) -> None:
        line_name: str = msg.get("line", "Unknown Line")
        updates: List[Dict[str, Any]] = msg.get("updates", [])

        ctc_backend = self.backends_by_line.get(line_name)
        if ctc_backend is None:
            logger.warning("[HWTC-Server] No CTC backend for line '%s'", line_name)
            return

        for u in updates:
            block_id = u.get("block_id")
            if block_id is None:
                continue
            block_id = int(block_id)

            # Block occupancy
            if "occupied" in u and hasattr(ctc_backend, "update_block_occupancy"):
                try:
                    # Most likely signature: update_block_occupancy(block_id, occupied)
                    ctc_backend.update_block_occupancy(block_id, bool(u["occupied"]))
                except Exception:
                    logger.exception("[HWTC-Server] update_block_occupancy failed")

            # Signal state string (e.g. "Red", "Yellow", "Green")
            if "signal_state" in u and hasattr(ctc_backend, "update_signal_state"):
                try:
                    ctc_backend.update_signal_state(block_id, u["signal_state"])
                except Exception:
                    logger.exception("[HWTC-Server] update_signal_state failed")

            # Switch position (we treat block_id as the switch's block id)
            if "switch_position" in u and u["switch_position"] is not None:
                if hasattr(ctc_backend, "update_switch_position"):
                    try:
                        ctc_backend.update_switch_position(block_id, int(u["switch_position"]))
                    except Exception:
                        logger.exception("[HWTC-Server] update_switch_position failed")

            # Crossing gate status (True/False)
            if "crossing_status" in u and u["crossing_status"] is not None:
                if hasattr(ctc_backend, "update_crossing_status"):
                    try:
                        ctc_backend.update_crossing_status(block_id, bool(u["crossing_status"]))
                    except Exception:
                        logger.exception("[HWTC-Server] update_crossing_status failed")