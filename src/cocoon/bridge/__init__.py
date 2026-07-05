"""L4: bridge. May import L0-L3 (DOCUMENT.md §6.1). Concrete BrokerAdapter
implementation wired at the CLI composition root only (§18)."""

from cocoon._layering import enforce_layering

enforce_layering(__name__)

from cocoon.bridge.broker_adapter import ZmqBrokerAdapter
from cocoon.bridge.heartbeat import HeartbeatMonitor
from cocoon.bridge.protocol import (
    PROTOCOL_VERSION,
    MessageType,
    decode_message,
    encode_message,
)
from cocoon.bridge.zmq_endpoint import ZmqEndpoint

__all__ = [
    "PROTOCOL_VERSION",
    "HeartbeatMonitor",
    "MessageType",
    "ZmqBrokerAdapter",
    "ZmqEndpoint",
    "decode_message",
    "encode_message",
]
