"""Science plugin discovery and execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from importlib.metadata import entry_points
import json
import re
from typing import Any, Protocol


PROTOCOL_VERSION = "1"
ENTRY_POINT_GROUP = "llmwho.science.plugins"
_PLUGIN_ID = re.compile(r"^[a-z][a-z0-9_.-]*$")


class SciencePlugin(Protocol):
    """Runtime contract implemented by science plugins."""

    id: str
    version: str
    summary: str
    required_inputs: tuple[str, ...]
    limitations: tuple[str, ...]

    def analyze(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class PluginDescriptor:
    id: str
    version: str
    summary: str
    required_inputs: tuple[str, ...]
    source: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["required_inputs"] = list(self.required_inputs)
        return result


class PluginRegistry:
    """Discover installed plugins and return versioned analysis reports."""

    def __init__(self, *, include_external: bool = True) -> None:
        from .output_affinity import OutputAffinityPlugin

        self._plugins: dict[str, tuple[SciencePlugin, PluginDescriptor]] = {}
        self._register(OutputAffinityPlugin(), source="builtin")
        if include_external:
            self._discover_external()

    def _discover_external(self) -> None:
        for point in sorted(
            entry_points(group=ENTRY_POINT_GROUP), key=lambda item: item.name
        ):
            loaded = point.load()
            plugin = loaded() if isinstance(loaded, type) else loaded
            source = point.dist.name if point.dist is not None else point.name
            self._register(plugin, source=source)

    def _register(self, plugin: SciencePlugin, *, source: str) -> None:
        plugin_id = getattr(plugin, "id", None)
        version = getattr(plugin, "version", None)
        summary = getattr(plugin, "summary", None)
        required_inputs = getattr(plugin, "required_inputs", None)
        limitations = getattr(plugin, "limitations", None)
        analyze = getattr(plugin, "analyze", None)
        if not isinstance(plugin_id, str) or not _PLUGIN_ID.fullmatch(plugin_id):
            raise ValueError(f"invalid science plugin id from {source}")
        if not isinstance(version, str) or not version:
            raise ValueError(f"science plugin {plugin_id!r} has no version")
        if not isinstance(summary, str) or not summary:
            raise ValueError(f"science plugin {plugin_id!r} has no summary")
        if not isinstance(required_inputs, tuple) or not all(
            isinstance(item, str) and item for item in required_inputs
        ):
            raise ValueError(f"science plugin {plugin_id!r} has invalid required_inputs")
        if not isinstance(limitations, tuple) or not all(
            isinstance(item, str) and item for item in limitations
        ):
            raise ValueError(f"science plugin {plugin_id!r} has invalid limitations")
        if not callable(analyze):
            raise ValueError(f"science plugin {plugin_id!r} has no analyze method")
        if plugin_id in self._plugins:
            raise ValueError(f"duplicate science plugin id {plugin_id!r}")
        descriptor = PluginDescriptor(
            id=plugin_id,
            version=version,
            summary=summary,
            required_inputs=required_inputs,
            source=source,
        )
        self._plugins[plugin_id] = (plugin, descriptor)

    def descriptors(self) -> list[dict[str, Any]]:
        return [
            descriptor.to_dict()
            for _, descriptor in sorted(
                self._plugins.values(), key=lambda item: item[1].id
            )
        ]

    def run(self, plugin_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(plugin_id, str) or plugin_id not in self._plugins:
            raise ValueError("unknown science plugin")
        if not isinstance(payload, Mapping):
            raise TypeError("science payload must be a mapping")
        plugin, descriptor = self._plugins[plugin_id]
        missing = [key for key in plugin.required_inputs if key not in payload]
        if missing:
            raise ValueError("science payload is missing required inputs")
        evidence = plugin.analyze(payload)
        if not isinstance(evidence, Mapping):
            raise TypeError("science plugin evidence must be a mapping")
        report = {
            "schema_version": "1",
            "protocol_version": PROTOCOL_VERSION,
            "plugin": descriptor.to_dict(),
            "evidence": dict(evidence),
            "limitations": list(plugin.limitations),
        }
        try:
            json.dumps(report, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise TypeError("science plugin report must be JSON-safe") from error
        return report
