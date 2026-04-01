"""
ConnectorRegistry: discovers, validates, and instantiates ERP connector plugins.

Built-in connectors live in backend/connectors/<system_name>/connector.py.
External plugins are dropped into the plugins/ directory at the repo root
or any path listed in NEXUS_PLUGIN_DIRS env var.

No central list is maintained—subclasses of ERPConnector with a valid
Meta.system_name are auto-registered on module import.
"""
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Type

from .base import ERPConnector, ConnectorConfig

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    _registry: dict[str, Type[ERPConnector]] = {}

    @classmethod
    def register(cls, connector_class: Type[ERPConnector]) -> None:
        """Explicitly register a connector class."""
        system_name = getattr(connector_class.Meta, "system_name", "")
        if not system_name:
            raise ValueError(f"{connector_class.__name__} must define Meta.system_name")
        cls._registry[system_name] = connector_class
        logger.info(
            "Registered connector: %s v%s",
            system_name,
            getattr(connector_class.Meta, "version", "?"),
        )

    @classmethod
    def get(cls, system_name: str) -> Type[ERPConnector]:
        if system_name not in cls._registry:
            raise KeyError(f"No connector registered for '{system_name}'")
        return cls._registry[system_name]

    @classmethod
    def create(cls, config: ConnectorConfig) -> ERPConnector:
        """Instantiate a connector from a ConnectorConfig."""
        connector_class = cls.get(config.system_name)
        return connector_class(config)

    @classmethod
    def list_registered(cls) -> list[dict]:
        return [
            {
                "system_name": klass.Meta.system_name,
                "display_name": getattr(klass.Meta, "display_name", klass.Meta.system_name),
                "version": getattr(klass.Meta, "version", "1.0.0"),
                "capabilities": [c.value for c in getattr(klass.Meta, "capabilities", [])],
                "supported_entities": getattr(klass.Meta, "supported_entities", []),
            }
            for klass in cls._registry.values()
        ]

    @classmethod
    def discover(cls, extra_plugin_dirs: list[Path] | None = None) -> None:
        """
        Auto-discover connectors. Called once at application startup.

        Scans:
          1. backend/connectors/<name>/connector.py  (built-ins)
          2. plugins/<name>/connector.py             (user plugins, repo root)
          3. Any paths in NEXUS_PLUGIN_DIRS env var  (colon-separated)
        """
        built_in_base = Path(__file__).parent
        repo_root = built_in_base.parent.parent

        dirs_to_scan: list[Path] = [built_in_base]

        plugins_dir = repo_root / "plugins"
        if plugins_dir.exists():
            dirs_to_scan.append(plugins_dir)

        env_dirs = os.environ.get("NEXUS_PLUGIN_DIRS", "")
        for path_str in env_dirs.split(":"):
            p = Path(path_str.strip())
            if p.exists():
                dirs_to_scan.append(p)

        if extra_plugin_dirs:
            dirs_to_scan.extend(extra_plugin_dirs)

        for base_dir in dirs_to_scan:
            for connector_file in base_dir.rglob("connector.py"):
                cls._load_module(connector_file)

    @classmethod
    def _load_module(cls, path: Path) -> None:
        module_name = f"_nexus_connector_{path.parent.name}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.warning("Failed to load connector plugin %s: %s", path, exc)
            return

        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, ERPConnector)
                and obj is not ERPConnector
                and hasattr(obj, "Meta")
                and getattr(obj.Meta, "system_name", "")
            ):
                cls.register(obj)
