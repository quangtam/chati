"""CLI Provider package — pluggable drivers for AI coding CLIs.

To add a new provider:
1. Create a file in this folder, e.g. `cli_providers/my_cli.py`
2. Subclass `CliProvider` and set the class attribute `provider_id`
3. That's it — the registry auto-discovers it on import.

Example minimal driver (cli_providers/my_cli.py):

    from cli_providers.base import CliProvider

    class MyCLIProvider(CliProvider):
        provider_id = "mycli"
        name = "My CLI"
        default_cli_path = "mycli"
        response_marker = ""

        def build_args(self, prompt, *, model=None, resume=False):
            args = [self.config.cli_path, "--prompt", prompt]
            if model:
                args.extend(["--model", model])
            return args

        def build_env(self, base_env):
            env = base_env.copy()
            if self.config.api_key:
                env["MYCLI_API_KEY"] = self.config.api_key
            return env
"""

from cli_providers.base import CliProvider, CliProviderConfig
from cli_providers.registry import create_provider, get_available_providers

__all__ = [
    "CliProvider",
    "CliProviderConfig",
    "create_provider",
    "get_available_providers",
]
