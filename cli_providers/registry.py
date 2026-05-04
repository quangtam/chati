"""Auto-discovery registry for CLI providers.

Scans all .py files in the cli_providers/ package, imports them,
and registers any CliProvider subclass that has a non-empty provider_id.
"""

import importlib
import logging
import pkgutil
import shutil
from pathlib import Path

from cli_providers.base import CliProvider, CliProviderConfig

logger = logging.getLogger(__name__)

# provider_id → CliProvider subclass
_REGISTRY: dict[str, type[CliProvider]] = {}


def _discover_providers() -> None:
    """Import all modules in cli_providers/ and register providers."""
    package_dir = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name in ("base", "registry"):
            continue
        try:
            module = importlib.import_module(f"cli_providers.{module_info.name}")
        except Exception:
            logger.exception("Failed to import provider module: %s", module_info.name)
            continue

        # Find all CliProvider subclasses in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, CliProvider)
                and attr is not CliProvider
                and getattr(attr, "provider_id", "")
            ):
                pid = attr.provider_id
                if pid in _REGISTRY:
                    logger.warning(
                        "Duplicate provider_id '%s': %s vs %s",
                        pid, _REGISTRY[pid].__name__, attr.__name__,
                    )
                _REGISTRY[pid] = attr
                logger.debug("Registered CLI provider: %s → %s", pid, attr.__name__)


def get_available_providers() -> dict[str, type[CliProvider]]:
    """Return all registered providers. Triggers discovery on first call."""
    if not _REGISTRY:
        _discover_providers()
    return dict(_REGISTRY)


def create_provider(
    provider_name: str,
    cli_path: str | None = None,
    api_key: str = "",
    trust_all_tools: bool = True,
    extra_args: list[str] | None = None,
) -> CliProvider:
    """Create a CLI provider instance by name.

    Args:
        provider_name: Provider ID (e.g. 'kiro', 'claude', 'gemini').
        cli_path: Path to CLI binary. Uses provider default if None.
        api_key: API key for authentication.
        trust_all_tools: Skip tool confirmation prompts.
        extra_args: Additional CLI arguments.

    Returns:
        Configured CliProvider instance.

    Raises:
        ValueError: If provider_name is not recognized.
    """
    providers = get_available_providers()
    provider_name = provider_name.lower().strip()

    if provider_name not in providers:
        available = ", ".join(sorted(providers.keys()))
        raise ValueError(
            f"Unknown CLI provider: '{provider_name}'. "
            f"Available: {available}"
        )

    provider_cls = providers[provider_name]

    # Resolve CLI path
    if not cli_path:
        cli_path = provider_cls.default_cli_path or provider_name

    # Try to resolve from PATH if not absolute
    if not Path(cli_path).is_absolute():
        resolved = shutil.which(cli_path)
        if resolved:
            cli_path = resolved

    config = CliProviderConfig(
        cli_path=cli_path,
        api_key=api_key,
        trust_all_tools=trust_all_tools,
        extra_args=extra_args,
    )

    return provider_cls(config)
