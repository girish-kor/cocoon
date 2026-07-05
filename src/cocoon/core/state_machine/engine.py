"""State machine engine. Authoritative source: DOCUMENT.md §7.2, §12.

Module responsibility matrix (§12) is explicit: `core/state_machine`
owns "transition table enforcement, current-state authority" and must
NOT contain "business logic (risk/order decisions)". This engine
therefore never itself opens a ZMQ socket, queries MT5, or decides risk
outcomes — it only (a) validates that a requested transition is legal
for the current state, (b) evaluates the transition's guard against a
caller-supplied context dict, (c) invokes a caller-registered action
callback keyed by the transition's action description, and (d) records
the transition to the audit log. All real work lives in the action
callbacks, which are wired by higher layers (trading/bridge/cli) at the
composition root — never inside this module.
"""

from __future__ import annotations

import threading
from typing import Callable

from cocoon.core.errors.exceptions import ConfigValidationError
from cocoon.core.logging.audit import AuditLogger
from cocoon.core.logging.setup import get_logger
from cocoon.core.state_machine.states import (
    TERMINAL_STATES,
    TRANSITION_TABLE,
    Event,
    State,
    Transition,
)

ActionHandler = Callable[[dict], None]

_logger = get_logger(__name__)


class InvalidTransitionError(ConfigValidationError):
    """Raised when an event is fired that has no legal transition from
    the current state. Reuses ConfigValidationError's structured-context
    contract rather than inventing a parallel exception without an
    exit-code mapping in §16 — an invalid transition request is a
    programming/config-precondition defect, not a distinct runtime
    failure class the catalogue enumerates separately."""


class StateMachine:
    def __init__(
        self,
        *,
        audit_logger: AuditLogger | None = None,
        initial_state: State = State.INIT,
    ) -> None:
        self._state = initial_state
        self._audit_logger = audit_logger
        self._lock = threading.RLock()
        self._action_handlers: dict[str, ActionHandler] = {}
        self._table_index: dict[tuple[State, Event], list[Transition]] = {}
        for transition in TRANSITION_TABLE:
            key = (transition.from_state, transition.event)
            self._table_index.setdefault(key, []).append(transition)

    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    @property
    def is_terminal(self) -> bool:
        with self._lock:
            return self._state in TERMINAL_STATES

    def register_action(self, action_description: str, handler: ActionHandler) -> None:
        """Higher layers wire concrete behavior here, keyed by the exact
        action_description string from the §7.2 table, e.g.
        `sm.register_action("open ZMQ REQ socket, send HELLO", bridge.connect)`.
        """
        self._action_handlers[action_description] = handler

    def legal_events(self) -> list[Event]:
        with self._lock:
            return [
                event
                for (from_state, event) in self._table_index
                if from_state == self._state
            ]

    def fire(self, event: Event, context: dict | None = None) -> State:
        context = context or {}
        with self._lock:
            candidates = self._table_index.get((self._state, event), [])
            if not candidates:
                raise InvalidTransitionError(
                    f"No legal transition for event '{event.value}' from "
                    f"state '{self._state.value}'",
                    context={
                        "current_state": self._state.value,
                        "event": event.value,
                    },
                )

            selected: Transition | None = None
            for transition in candidates:
                if transition.guard(context):
                    selected = transition
                    break

            if selected is None:
                raise InvalidTransitionError(
                    f"Event '{event.value}' fired from state "
                    f"'{self._state.value}' but no candidate transition's "
                    f"guard passed",
                    context={
                        "current_state": self._state.value,
                        "event": event.value,
                        "guard_descriptions": [c.guard_description for c in candidates],
                    },
                )

            from_state = self._state
            handler = self._action_handlers.get(selected.action_description)
            if handler is not None:
                handler(context)

            self._state = selected.to_state

            _logger.info(
                "state_transition",
                from_state=from_state.value,
                to_state=selected.to_state.value,
                # NOTE: cannot use the kwarg name `event` here — structlog's
                # BoundLogger.info(event, **kwargs) treats `event` as its own
                # reserved first positional parameter (the log message key),
                # so passing event=... collides and raises TypeError at
                # runtime. Caught by testing this module, not by inspection.
                sm_event=event.value,
                action=selected.action_description,
            )
            if self._audit_logger is not None:
                self._audit_logger.record_state_transition(
                    from_state=from_state.value,
                    to_state=selected.to_state.value,
                    event=event.value,
                    action=selected.action_description,
                )

            return self._state
