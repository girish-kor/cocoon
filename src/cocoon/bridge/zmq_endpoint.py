"""ZeroMQ endpoint. DOCUMENT.md §13.1.

REQ/REP (synchronous command/response, one outstanding request at a time)
and PUB/SUB (EA publishes bar-close/tick/heartbeat; Python subscribes,
unidirectional). This class is transport only — it frames/deframes msgpack
via bridge.protocol but holds no trading logic.
"""

from __future__ import annotations

import threading
from typing import Any

import zmq

from cocoon.bridge.protocol import MessageType, decode_message, encode_message
from cocoon.core.logging.setup import get_logger

_logger = get_logger(__name__)


class ZmqEndpoint:
    def __init__(
        self,
        *,
        req_port: int,
        pub_port: int,
        host: str = "127.0.0.1",
        session_id: str = "",
    ) -> None:
        self._req_port = req_port
        self._pub_port = pub_port
        self._host = host
        self._session_id = session_id
        self._ctx: zmq.Context | None = None
        self._req: zmq.Socket | None = None
        self._sub: zmq.Socket | None = None
        self._req_lock = threading.Lock()

    def connect(self, *, req_timeout_ms: int = 5000) -> None:
        self._ctx = zmq.Context.instance()
        self._req = self._ctx.socket(zmq.REQ)
        self._req.setsockopt(zmq.RCVTIMEO, req_timeout_ms)
        self._req.setsockopt(zmq.SNDTIMEO, req_timeout_ms)
        self._req.setsockopt(zmq.LINGER, 0)
        self._req.connect(f"tcp://{self._host}:{self._req_port}")

        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.setsockopt(zmq.LINGER, 0)
        self._sub.setsockopt_string(zmq.SUBSCRIBE, "")
        self._sub.connect(f"tcp://{self._host}:{self._pub_port}")
        _logger.info("zmq_connected", req=self._req_port, pub=self._pub_port)

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id

    def request(
        self,
        msg_type: MessageType,
        payload: dict[str, Any] | None = None,
        *,
        ts_unix_ms: int,
    ) -> dict[str, Any]:
        if self._req is None:
            raise RuntimeError("ZmqEndpoint.request before connect()")
        frame = encode_message(
            msg_type=msg_type,
            ts_unix_ms=ts_unix_ms,
            session_id=self._session_id,
            payload=payload,
        )
        with self._req_lock:  # single-flight (REQ socket constraint, §13.1)
            self._req.send(frame)
            reply = self._req.recv()
        return decode_message(reply)

    def poll_pub(self, timeout_ms: int = 0) -> dict[str, Any] | None:
        if self._sub is None:
            raise RuntimeError("ZmqEndpoint.poll_pub before connect()")
        events = self._sub.poll(timeout=timeout_ms)
        if not events:
            return None
        data = self._sub.recv()
        return decode_message(data)

    def drain_pub(self, max_messages: int = 100) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for _ in range(max_messages):
            msg = self.poll_pub(timeout_ms=0)
            if msg is None:
                break
            out.append(msg)
        return out

    def close(self) -> None:
        for sock in (self._req, self._sub):
            if sock is not None:
                sock.close(0)
        self._req = None
        self._sub = None
        _logger.info("zmq_closed")
