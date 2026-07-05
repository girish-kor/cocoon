"""Lifecycle state machine table. Authoritative source: DOCUMENT.md §7.2.

DOCUMENT.md is explicit: "the state machine implementation must be a
direct translation of this table, not a reinterpretation." One real
discrepancy exists between the §7.2 mermaid diagram and its own
transition table: the diagram only draws SHUTTING_DOWN edges out of
RUNNING and SAFE_HALT, but the transition-table row says the shutdown
event fires "from: any". Per the explicit instruction to treat the
*table* as authoritative over reinterpretation, this module follows the
table's "any" — every non-terminal state accepts SIGINT/shutdown_cmd —
because a diagram that only draws two of the edges does not override a
row that says "any", and a shutdown signal arriving during
MT5_CONNECTING or STATE_RECONCILING is a real scenario the diagram's
narrower drawing would otherwise leave unhandled.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable


class State(str, enum.Enum):
    INIT = "INIT"
    CONFIG_LOADED = "CONFIG_LOADED"
    MT5_CONNECTING = "MT5_CONNECTING"
    MT5_CONNECTED = "MT5_CONNECTED"
    STATE_RECONCILING = "STATE_RECONCILING"
    RUNNING = "RUNNING"
    SAFE_HALT = "SAFE_HALT"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    INIT_FAILED = "INIT_FAILED"
    RECONCILE_FAILED = "RECONCILE_FAILED"
    TERMINATED = "TERMINATED"


TERMINAL_STATES: frozenset[State] = frozenset(
    {State.TERMINATED, State.INIT_FAILED, State.RECONCILE_FAILED}
)


class Event(str, enum.Enum):
    CONFIG_VALIDATED = "config_validated"
    CONNECT_ATTEMPT = "connect_attempt"
    EA_ACK = "ea_ack"
    CONNECT_TIMEOUT = "connect_timeout"
    RECONCILE_START = "reconcile_start"
    DIFF_RESOLVED = "diff_resolved"
    DIFF_CONFLICT = "diff_conflict"
    HEARTBEAT_MISS_THRESHOLD = "heartbeat_miss_threshold"
    RISK_DAILY_LOSS_BREACH = "risk_daily_loss_breach"
    MANUAL_HALT = "manual_halt"
    HEARTBEAT_RESUMED = "heartbeat_resumed"
    SIGINT = "sigint"
    SHUTDOWN_CMD = "shutdown_cmd"
    SHUTDOWN_COMPLETE = "shutdown_complete"


@dataclass(frozen=True)
class Transition:
    from_state: State
    event: Event
    to_state: State
    guard_description: str
    action_description: str
    guard: Callable[[dict], bool] = field(default=lambda ctx: True, repr=False)


_ANY_SHUTDOWN_SOURCE_STATES: tuple[State, ...] = (
    State.INIT,
    State.CONFIG_LOADED,
    State.MT5_CONNECTING,
    State.MT5_CONNECTED,
    State.STATE_RECONCILING,
    State.RUNNING,
    State.SAFE_HALT,
)


def _build_transition_table() -> list[Transition]:
    table: list[Transition] = [
        Transition(
            State.INIT,
            Event.CONFIG_VALIDATED,
            State.CONFIG_LOADED,
            guard_description="schema valid",
            action_description="load profile, resolve precedence",
        ),
        Transition(
            State.CONFIG_LOADED,
            Event.CONNECT_ATTEMPT,
            State.MT5_CONNECTING,
            guard_description="-",
            action_description="open ZMQ REQ socket, send HELLO",
        ),
        Transition(
            State.MT5_CONNECTING,
            Event.EA_ACK,
            State.MT5_CONNECTED,
            guard_description="timeout not exceeded",
            action_description="store terminal session id",
        ),
        Transition(
            State.MT5_CONNECTING,
            Event.CONNECT_TIMEOUT,
            State.INIT_FAILED,
            guard_description="-",
            action_description="log, exit code 20",
        ),
        Transition(
            State.MT5_CONNECTED,
            Event.RECONCILE_START,
            State.STATE_RECONCILING,
            guard_description="-",
            action_description="fetch broker positions/orders, diff vs local SQLite",
        ),
        Transition(
            State.STATE_RECONCILING,
            Event.DIFF_RESOLVED,
            State.RUNNING,
            guard_description="no unresolved conflicts",
            action_description="start scheduler, subscribe PUB channel",
        ),
        Transition(
            State.STATE_RECONCILING,
            Event.DIFF_CONFLICT,
            State.RECONCILE_FAILED,
            guard_description="conflict requires manual resolution",
            action_description="log full diff, exit code 21",
        ),
        Transition(
            State.RUNNING,
            Event.HEARTBEAT_MISS_THRESHOLD,
            State.SAFE_HALT,
            guard_description="-",
            action_description="cancel pending orders (not positions), alert",
        ),
        Transition(
            State.RUNNING,
            Event.RISK_DAILY_LOSS_BREACH,
            State.SAFE_HALT,
            guard_description="-",
            action_description="block new orders, keep monitoring open positions",
        ),
        Transition(
            State.RUNNING,
            Event.MANUAL_HALT,
            State.SAFE_HALT,
            guard_description="-",
            action_description="block new orders, keep monitoring open positions",
        ),
        Transition(
            State.SAFE_HALT,
            Event.HEARTBEAT_RESUMED,
            State.STATE_RECONCILING,
            guard_description="-",
            action_description="re-diff before resuming",
        ),
    ]

    for source_state in _ANY_SHUTDOWN_SOURCE_STATES:
        for event in (Event.SIGINT, Event.SHUTDOWN_CMD):
            table.append(
                Transition(
                    source_state,
                    event,
                    State.SHUTTING_DOWN,
                    guard_description="-",
                    action_description=(
                        "drain in-flight orders (max shutdown_grace_ms), "
                        "close sockets, flush logs"
                    ),
                )
            )

    table.append(
        Transition(
            State.SHUTTING_DOWN,
            Event.SHUTDOWN_COMPLETE,
            State.TERMINATED,
            guard_description="-",
            action_description="process exit",
        )
    )

    return table


TRANSITION_TABLE: list[Transition] = _build_transition_table()
