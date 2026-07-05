"""MT5 bridge wire protocol. DOCUMENT.md §13.

msgpack envelope for every message, mirroring
mql5/Include/Cocoon/Protocol.mqh. A protocol version is embedded so a
Python/EA schema mismatch fails fast (ProtocolVersionMismatchError, exit 50)
rather than silently misinterpreting binary payloads.
"""

from __future__ import annotations

import enum
from typing import Any

import msgpack

from cocoon.core.errors.exceptions import ProtocolVersionMismatchError

PROTOCOL_VERSION = 1


class MessageType(str, enum.Enum):
    HELLO = "HELLO"
    ACK = "ACK"
    HEARTBEAT = "HEARTBEAT"
    BAR_CLOSED = "BAR_CLOSED"
    TICK = "TICK"
    ORDER_SUBMIT = "ORDER_SUBMIT"
    ORDER_RESULT = "ORDER_RESULT"
    ORDER_CANCEL = "ORDER_CANCEL"
    ORDER_MODIFY = "ORDER_MODIFY"
    POSITIONS_QUERY = "POSITIONS_QUERY"
    POSITIONS_RESULT = "POSITIONS_RESULT"
    ORDERS_QUERY = "ORDERS_QUERY"
    ORDERS_RESULT = "ORDERS_RESULT"
    ERROR = "ERROR"


def encode_message(
    *,
    msg_type: MessageType | str,
    ts_unix_ms: int,
    session_id: str,
    payload: dict[str, Any] | None = None,
    protocol_version: int = PROTOCOL_VERSION,
) -> bytes:
    type_value = msg_type.value if isinstance(msg_type, MessageType) else msg_type
    envelope = {
        "v": protocol_version,
        "type": type_value,
        "ts": int(ts_unix_ms),
        "session_id": session_id,
        "payload": payload or {},
    }
    return msgpack.packb(envelope, use_bin_type=True) or b""


def decode_message(data: bytes, *, verify_version: bool = True) -> dict[str, Any]:
    envelope = msgpack.unpackb(data, raw=False)
    if verify_version:
        version = envelope.get("v")
        if version != PROTOCOL_VERSION:
            raise ProtocolVersionMismatchError(
                "Bridge protocol version mismatch between Python and EA",
                context={"python_version": PROTOCOL_VERSION, "received": version},
            )
    return envelope
