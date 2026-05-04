"""Kiro CLI driver.

Headless: kiro-cli chat --no-interactive --trust-all-tools "prompt"
Models:   kiro-cli chat --list-models --format json
Resume:   --resume
Auth:     KIRO_API_KEY env var
"""

import json

from cli_providers.base import CliProvider


class KiroProvider(CliProvider):
    provider_id = "kiro"
    name = "Kiro CLI"
    default_cli_path = "kiro-cli"
    response_marker = "> "

    def build_args(self, prompt, *, model=None, resume=False):
        args = [self.config.cli_path, "chat", "--no-interactive"]
        if self.config.trust_all_tools:
            args.append("--trust-all-tools")
        if model:
            args.extend(["--model", model])
        if resume:
            args.append("--resume")
        if self.config.extra_args:
            args.extend(self.config.extra_args)
        args.append(prompt)
        return args

    def build_env(self, base_env):
        env = self._base_env(base_env)
        env["KIRO_API_KEY"] = self.config.api_key
        env["KIRO_LOG_NO_COLOR"] = "1"
        env["CI"] = "1"
        return env

    def supports_resume(self):
        return True

    def list_models_args(self):
        return [self.config.cli_path, "chat", "--list-models", "--format", "json"]

    def parse_models_output(self, stdout):
        try:
            data = json.loads(stdout)
            return data.get("models", [])
        except (json.JSONDecodeError, KeyError):
            return []

    def status_check_args(self):
        return [self.config.cli_path, "whoami"]
