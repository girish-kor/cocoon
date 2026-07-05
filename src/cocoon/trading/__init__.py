"""L3: trading. May import L0-L2 (DOCUMENT.md §6.1). Depends on the broker
only through core/interfaces/broker_adapter.py — never on bridge (L4)."""

from cocoon._layering import enforce_layering

enforce_layering(__name__)
