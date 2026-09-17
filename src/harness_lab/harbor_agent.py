"""Harbor adapter: runs the harness as an external agent against a task container.

    harbor run -p tasks/py-bugfix-lite \
      --agent harness_lab.harbor_agent:HarnessLabAgent \
      -m local/qwen3-8b --ak config=configs/full.yaml

The model string is `<provider>/<model id>`:
  local/...    llama.cpp or vLLM on this machine (HARNESS_LOCAL_BASE_URL)
  nvidia/...   NVIDIA API catalog (NVIDIA_API_KEY)
  openai/...   any other OpenAI-compatible endpoint (HARNESS_BASE_URL, HARNESS_API_KEY)
"""

import os
import shlex
import subprocess
from pathlib import Path
from typing import override

from pydantic import Field

from harbor.agents.base import BaseAgent
from harbor.agents.options import AgentOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from harness_lab import __version__
from harness_lab.config import HarnessConfig
from harness_lab.llm import LLMClient
from harness_lab.loop import run_agent
from harness_lab.tools import ExecOutput
from harness_lab.tracing import Tracer

PROVIDERS = {
    "local": ("HARNESS_LOCAL_BASE_URL", "http://127.0.0.1:8080/v1", None),
    "nvidia": ("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
    "openai": ("HARNESS_BASE_URL", None, "HARNESS_API_KEY"),
}


def _git_version() -> str | None:
    """Commit of the harness code, with a -dirty suffix for uncommitted changes."""
    try:
        out = subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


class HarnessLabOptions(AgentOptions):
    config: str | None = Field(default=None, description="Path to a harness YAML config.")
    variant: str | None = None
    context_strategy: str | None = None
    tool_set: str | None = None
    reasoning: str | None = None
    max_steps: str | None = None
    max_context_tokens: str | None = None
    compaction_threshold_tokens: str | None = None


class HarborExecutor:
    def __init__(self, environment: BaseEnvironment):
        self.environment = environment

    async def run(self, command: str, timeout_sec: int) -> ExecOutput:
        # Enforce the timeout inside the container too: killing `docker exec` on the
        # host does not stop the process it started.
        wrapped = f"timeout -k 5 {timeout_sec} bash -c {shlex.quote(command)}"
        try:
            result = await self.environment.exec(wrapped, timeout_sec=timeout_sec + 15)
        except (TimeoutError, RuntimeError) as exc:
            if "timed out" not in str(exc) and not isinstance(exc, TimeoutError):
                raise
            return ExecOutput(f"Error: command timed out after {timeout_sec}s", 124)
        output = (result.stdout or "") + (result.stderr or "")
        if result.return_code == 124:
            output += f"\nError: command timed out after {timeout_sec}s"
        return ExecOutput(output, result.return_code)


class HarnessLabAgent(BaseAgent):
    options_model = HarnessLabOptions

    @staticmethod
    @override
    def name() -> str:
        return "harness-lab"

    @override
    def version(self) -> str:
        return __version__

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        # External agent: nothing is installed in the container.
        pass

    def _harness_config(self) -> HarnessConfig:
        opts = self.options.model_dump() if self.options else {}
        path = opts.pop("config", None)
        return HarnessConfig.load(path, **opts)

    def _llm(self) -> LLMClient:
        if not self.model_name or "/" not in self.model_name:
            raise ValueError("Pass the model as <provider>/<model id>, e.g. -m local/qwen3-8b")
        provider, model = self.model_name.split("/", 1)
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}; choose from {sorted(PROVIDERS)}")
        url_var, default_url, key_var = PROVIDERS[provider]
        base_url = os.environ.get(url_var, default_url)
        if not base_url:
            raise ValueError(f"Set {url_var} for provider {provider!r}")
        api_key = os.environ.get(key_var) if key_var else None
        if key_var and not api_key:
            raise ValueError(f"Set {key_var} (e.g. in .env, then pass --env-file .env)")
        return LLMClient(base_url, model, api_key)

    @override
    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        cfg = self._harness_config()
        llm = self._llm()
        tracer = Tracer(
            Path(self.logs_dir) / "harness_trace.jsonl",
            {
                "harness_version": __version__,
                "git": _git_version(),
                "model": self.model_name,
                "endpoint": llm.url,
                "config": cfg.to_dict(),
            },
        )
        result = await run_agent(instruction, HarborExecutor(environment), llm, cfg, tracer)

        t = result.totals
        context.n_input_tokens = t.prompt_tokens
        context.n_cache_tokens = t.cached_tokens
        context.n_output_tokens = t.completion_tokens
        context.metadata = {
            "variant": cfg.variant,
            "stop_reason": result.stop_reason,
            "steps": result.steps,
            "error": result.error,
            **{k: v for k, v in vars(t).items() if k not in ("prompt_tokens", "cached_tokens", "completion_tokens")},
        }
