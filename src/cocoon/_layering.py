"""Import-time layering guard. Authoritative source: DOCUMENT.md §6.1.

§6.1: "a module in layer N may import from layers 0..N-1 only ... No
downward imports (L1 importing L3) under any circumstance ... enforced
at import-time via __init__.py guards, violation = build failure."

HONEST LIMITATION: a fully sound enforcement of this rule requires
either (a) a static import-graph linter run at build time (out of scope
per DOCUMENT.md §0 — CI/CD is explicitly excluded from this spec), or
(b) a `sys.meta_path` finder/loader that intercepts every import
statement and checks the full call graph, not just the immediate
caller. What is implemented here is (c): each layer's `__init__.py`
calls `enforce_layering(__name__)` on first import, which inspects the
immediate calling frame via `inspect.stack()` and rejects it if the
caller is a `cocoon.*` module belonging to a strictly lower layer. This
catches the common case (a low-layer module doing `import
cocoon.trading...` at its own module top level) but does NOT catch a
violation buried inside a function body that only executes conditionally
and is never invoked during the process that happens to trigger the
first import, nor does it catch a violation where the immediate caller
is itself already mislayered (transitive laundering). Treat this as a
best-effort runtime tripwire, not a substitute for a real static
analysis pass — which DOCUMENT.md §0 already tells you not to skip
before production deployment.
"""

from __future__ import annotations

import inspect

LAYER_OF: dict[str, int] = {
    "core": 0,
    "data": 1,
    "ml": 2,
    "trading": 3,
    "bridge": 4,
    "cli": 5,
}


class LayeringViolationError(ImportError):
    pass


def _layer_of_module_name(module_name: str) -> int | None:
    parts = module_name.split(".")
    if len(parts) < 2 or parts[0] != "cocoon":
        return None
    return LAYER_OF.get(parts[1])


def enforce_layering(current_module_name: str) -> None:
    current_layer = _layer_of_module_name(current_module_name)
    if current_layer is None:
        return

    for frame_info in inspect.stack()[1:]:
        caller_name = frame_info.frame.f_globals.get("__name__", "")
        if not caller_name.startswith("cocoon."):
            continue
        caller_layer = _layer_of_module_name(caller_name)
        if caller_layer is None:
            continue
        if caller_layer < current_layer:
            raise LayeringViolationError(
                f"Layering violation: '{caller_name}' (layer "
                f"{caller_layer}) imported '{current_module_name}' "
                f"(layer {current_layer}). A module may only import "
                f"from its own layer or below (DOCUMENT.md §6.1)."
            )
        break
