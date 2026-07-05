"""Plugin system. DOCUMENT.md §F21, §10 (plugin commands), §17.

entry_points-based discovery of custom FeatureFn / strategy plugins under
the `cocoon.plugins` group, plus a local install/remove mechanism that
copies a plugin file into `<data_dir>/plugins/`. Every discovered object is
interface-checked (must be / produce a FeatureFn); a non-conforming plugin
raises PluginInterfaceError (exit 60) rather than being silently skipped.
"""

from __future__ import annotations

import importlib
import importlib.util
import shutil
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path

from cocoon.core.errors.exceptions import PluginInterfaceError
from cocoon.core.interfaces.feature_fn import FeatureFn
from cocoon.core.logging.setup import get_logger

_logger = get_logger(__name__)

ENTRY_POINT_GROUP = "cocoon.plugins"


@dataclass(frozen=True)
class PluginInfo:
    name: str
    source: str
    kind: str


def _coerce_feature_fns(name: str, obj) -> list[FeatureFn]:
    candidates = obj() if callable(obj) and not isinstance(obj, type) else obj
    if isinstance(candidates, FeatureFn):
        return [candidates]
    if isinstance(candidates, type) and issubclass(candidates, FeatureFn):
        return [candidates()]
    if isinstance(candidates, (list, tuple)):
        result: list[FeatureFn] = []
        for c in candidates:
            if isinstance(c, FeatureFn):
                result.append(c)
            elif isinstance(c, type) and issubclass(c, FeatureFn):
                result.append(c())
            else:
                raise PluginInterfaceError(
                    "Plugin produced a non-FeatureFn object",
                    context={"plugin": name, "type": type(c).__name__},
                )
        return result
    raise PluginInterfaceError(
        "Plugin entry point did not resolve to FeatureFn(s)",
        context={"plugin": name, "type": type(candidates).__name__},
    )


def discover_feature_plugins() -> list[FeatureFn]:
    features: list[FeatureFn] = []
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # pragma: no cover - older importlib API
        eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined]
    for ep in eps:
        try:
            obj = ep.load()
        except Exception as exc:
            raise PluginInterfaceError(
                "Plugin entry point failed to load",
                context={"plugin": ep.name, "error": str(exc)},
            ) from exc
        features.extend(_coerce_feature_fns(ep.name, obj))
    return features


class PluginLoader:
    def __init__(self, *, plugins_dir: str | Path) -> None:
        self._dir = Path(plugins_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_plugins(self) -> list[PluginInfo]:
        infos: list[PluginInfo] = []
        for ep_feature in self._safe_entry_points():
            infos.append(PluginInfo(name=ep_feature, source="entry_point", kind="feature"))
        for path in sorted(self._dir.glob("*.py")):
            infos.append(PluginInfo(name=path.stem, source=str(path), kind="local"))
        return infos

    def _safe_entry_points(self) -> list[str]:
        try:
            eps = entry_points(group=ENTRY_POINT_GROUP)
        except TypeError:  # pragma: no cover
            eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined]
        return [ep.name for ep in eps]

    def install(self, source_path: str | Path) -> PluginInfo:
        src = Path(source_path)
        if not src.exists() or src.suffix != ".py":
            raise PluginInterfaceError(
                "Plugin install source must be an existing .py file",
                context={"source": str(src)},
            )
        dest = self._dir / src.name
        shutil.copy2(src, dest)
        self._validate_local(dest)
        _logger.info("plugin_installed", name=dest.stem)
        return PluginInfo(name=dest.stem, source=str(dest), kind="local")

    def remove(self, name: str) -> bool:
        target = self._dir / f"{name}.py"
        if not target.exists():
            return False
        target.unlink()
        _logger.info("plugin_removed", name=name)
        return True

    def load_local(self, name: str) -> list[FeatureFn]:
        path = self._dir / f"{name}.py"
        if not path.exists():
            raise PluginInterfaceError(
                "Unknown local plugin", context={"name": name}
            )
        return self._validate_local(path)

    def load_all_local(self) -> list[FeatureFn]:
        out: list[FeatureFn] = []
        for path in sorted(self._dir.glob("*.py")):
            out.extend(self._validate_local(path))
        return out

    def _validate_local(self, path: Path) -> list[FeatureFn]:
        spec = importlib.util.spec_from_file_location(f"cocoon_plugin_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise PluginInterfaceError(
                "Could not import local plugin", context={"path": str(path)}
            )
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise PluginInterfaceError(
                "Local plugin raised on import",
                context={"path": str(path), "error": str(exc)},
            ) from exc
        factory = getattr(module, "build_features", None)
        if factory is None:
            raise PluginInterfaceError(
                "Local plugin missing required `build_features()` factory",
                context={"path": str(path)},
            )
        return _coerce_feature_fns(path.stem, factory)
