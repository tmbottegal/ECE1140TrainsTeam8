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
    track controller running on the Raspberry Pi and forwards them into the
    CTC backends (TrackState instances) running on the laptop.

    The Pi sends JSON lines that look like:

        {
            "type": "wayside_status",
            "line": "Green Line",
            "updates": [
                {
                    "block_id": 12,
                    "occupied": true,
                    "signal_state": "Green",
                    "switch_position": "Straight" | "Diverging" | null,
                    "crossing_status": "Active" | "Inactive" | true | false | null
                },
                ...
            ]
        }
    """

    def __init__(self,
                 backends_by_line: Dict[str, Any],
                 host: str = "0.0.0.0",
                 port: int = 6000) -> None:
        self.backends_by_line = backends_by_line
        self.host = host
        self.port = port
        self._server_socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Reuse port on restart
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)

        logger.info("[HWTC-Server] Listening on %s:%d", self.host, self.port)

        self._thread = threading.Thread(
            target=self._serve_forever,
            name="HardwareTrackControllerServer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None

    # ------------------------------------------------------------------ #
    # Internal server loop
    # ------------------------------------------------------------------ #

    def _serve_forever(self) -> None:
        assert self._server_socket is not None
        while self._running:
            try:
                client_sock, addr = self._server_socket.accept()
            except OSError:
                # Socket was closed during shutdown
                break

            logger.info("[HWTC-Server] Connection from %s:%d", *addr)
            t = threading.Thread(
                target=self._handle_client,
                args=(client_sock, addr),
                daemon=True,
            )
            t.start()

    def _handle_client(self, sock: socket.socket, addr: Any) -> None:
        with sock:
            buffer = b""
            while self._running:
                try:
                    data = sock.recv(4096)
                except OSError:
                    break
                if not data:
                    break
                buffer += data

                # Messages are newline-delimited JSON
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        logger.exception("[HWTC-Server] Failed to decode JSON from %s:%d", *addr)
                        continue
                    self._handle_message(msg)

        logger.info("[HWTC-Server] Connection closed from %s:%d", *addr)

    # ------------------------------------------------------------------ #
    # Message handling
    # ------------------------------------------------------------------ #

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        msg_type = msg.get("type")
        logger.info("[HWTC-Server] Received message type '%s': %s", msg_type, msg)
        if msg_type == "wayside_status":
            self._handle_wayside_status(msg)
        else:
            logger.warning("[HWTC-Server] Unknown message type '%s'", msg_type)

    def _handle_wayside_status(self, msg: Dict[str, Any]) -> None:
        """
        Apply wayside status updates coming from the Pi to the correct CTC backend.
        """
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

            # ----- Block occupancy -----
            if "occupied" in u and hasattr(ctc_backend, "update_block_occupancy"):
                try:
                    # TrackState signature: (line_name, block_id, occupied)
                    ctc_backend.update_block_occupancy(line_name, block_id, bool(u["occupied"]))
                except Exception:
                    logger.exception("[HWTC-Server] update_block_occupancy failed")

            # ----- Signal state (e.g. 'Red', 'Yellow', 'Green') -----
            if "signal_state" in u and hasattr(ctc_backend, "update_signal_state"):
                try:
                    ctc_backend.update_signal_state(line_name, block_id, u["signal_state"])
                except Exception:
                    logger.exception("[HWTC-Server] update_signal_state failed")

            # ----- Switch position -----
            if "switch_position" in u and u["switch_position"] is not None:
                if hasattr(ctc_backend, "update_switch_position"):
                    try:
                        ctc_backend.update_switch_position(line_name, block_id, u["switch_position"])
                    except Exception:
                        logger.exception("[HWTC-Server] update_switch_position failed")

            # ----- Crossing gate status -----
            if "crossing_status" in u and u["crossing_status"] is not None:
                if hasattr(ctc_backend, "update_crossing_status"):
                    try:
                        ctc_backend.update_crossing_status(line_name, block_id, bool(u["crossing_status"]))
                    except Exception:
                        logger.exception("[HWTC-Server] update_crossing_status failed") 

    # ------------------------------------------------------------------ #
    # Helper to handle different CTC method signatures
    # ------------------------------------------------------------------ #

    def _call_ctc_method(
        self,
        backend: Any,
        method_name: str,
        line_name: str,
        block_id: int,
        value: Any,
    ) -> None:
        func = getattr(backend, method_name, None)
        if func is None:
            return

        try:
            # Some backends are per-line and want (block_id, value)
            try:
                func(block_id, value)
            except TypeError:
                # Others implement a "global" interface and want (line_name, block_id, value)
                func(line_name, block_id, value)
        except Exception:
            logger.exception("[HWTC-Server] %s failed", method_name)
