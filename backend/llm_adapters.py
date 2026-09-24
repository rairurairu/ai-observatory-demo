"""Provider adapters for paid APIs and locally authenticated subscription CLIs."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AdapterResult:
    provider: str
    model_id: str
    response_text: str
    token_usage: dict
    latency_ms: float


class BaseLLMAdapter:
    provider = "base"

    def generate(self, prompt: str, model_id: str) -> AdapterResult:
        raise NotImplementedError


class OpenAIAdapter(BaseLLMAdapter):
    provider = "openai"

    def generate(self, prompt, model_id):
        from openai import OpenAI
        started = time.perf_counter()
        response = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=90, max_retries=2).chat.completions.create(
            model=model_id, messages=[{"role": "user", "content": prompt}], max_tokens=900,
        )
        usage = response.usage
        tokens = {"input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens} if usage else {}
        return AdapterResult(self.provider, model_id, response.choices[0].message.content or "", tokens, (time.perf_counter()-started)*1000)


class AnthropicAdapter(BaseLLMAdapter):
    provider = "anthropic"

    def generate(self, prompt, model_id):
        from anthropic import Anthropic
        started = time.perf_counter()
        response = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=90, max_retries=2).messages.create(
            model=model_id, max_tokens=900, messages=[{"role": "user", "content": prompt}],
        )
        content = "\n".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        tokens = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return AdapterResult(self.provider, model_id, content, tokens, (time.perf_counter()-started)*1000)


class GeminiAdapter(BaseLLMAdapter):
    provider = "google"

    def generate(self, prompt, model_id):
        from google import genai
        started = time.perf_counter()
        response = genai.Client(api_key=os.environ["GOOGLE_API_KEY"]).models.generate_content(model=model_id, contents=prompt)
        usage = getattr(response, "usage_metadata", None)
        tokens = {}
        if usage:
            if getattr(usage, "prompt_token_count", None) is not None: tokens["input_tokens"] = usage.prompt_token_count
            if getattr(usage, "candidates_token_count", None) is not None: tokens["output_tokens"] = usage.candidates_token_count
        return AdapterResult(self.provider, model_id, response.text or "", tokens, (time.perf_counter()-started)*1000)


class OpenAICompatibleAdapter(BaseLLMAdapter):
    """MiniMax and DeepSeek expose OpenAI-compatible Chat Completions endpoints."""

    def __init__(self, provider, key_name, base_url, max_tokens=4096):
        self.provider, self.key_name, self.base_url, self.max_tokens = provider, key_name, base_url, max_tokens

    def generate(self, prompt, model_id):
        from openai import OpenAI
        started = time.perf_counter()
        response = OpenAI(api_key=os.environ[self.key_name], base_url=self.base_url, timeout=120, max_retries=2).chat.completions.create(
            model=model_id, messages=[{"role": "user", "content": prompt}], max_tokens=self.max_tokens,
        )
        usage = response.usage
        tokens = {"input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens} if usage else {}
        choice = response.choices[0]
        content = choice.message.content or ""
        # Some reasoning models include private scratchpad text in content.
        # Keep only the final answer, and never store an unterminated think block.
        if "<think>" in content.lower():
            start = content.lower().find("<think>")
            end = content.lower().find("</think>", start)
            content = content[:start] + (content[end + len("</think>"):] if end >= 0 else "")
        content = re.sub(r"</?think>", "", content, flags=re.IGNORECASE).strip()
        if not content:
            reason = getattr(choice, "finish_reason", None) or "unknown"
            raise RuntimeError(f"Provider returned no final response text (finish_reason={reason})")
        return AdapterResult(self.provider, model_id, content, tokens, (time.perf_counter()-started)*1000)


def _run_cli(command, timeout=180):
    started = time.perf_counter()
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"CLI timed out after {timeout} seconds") from exc
    if result.returncode:
        error = (result.stderr or result.stdout or "CLI request failed").strip()
        raise RuntimeError(error[-1500:])
    return result.stdout.strip(), (time.perf_counter()-started)*1000


class ClaudeCodeAdapter(BaseLLMAdapter):
    provider = "claude_code"

    def generate(self, prompt, model_id):
        executable = shutil.which("claude")
        if not executable: raise RuntimeError("Claude Code CLI is not installed")
        output, elapsed = _run_cli([executable, "-p", prompt, "--model", model_id, "--output-format", "json", "--tools", ""], 180)
        text = output
        tokens = {}
        try:
            payload = json.loads(output)
            text = payload.get("result", output)
            usage = payload.get("usage") or payload.get("modelUsage") or {}
            if isinstance(usage, dict):
                tokens = {
                    "input_tokens": usage.get("input_tokens", usage.get("inputTokens", 0)),
                    "output_tokens": usage.get("output_tokens", usage.get("outputTokens", 0)),
                }
                tokens = {k: int(v) for k, v in tokens.items() if v}
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return AdapterResult(self.provider, model_id, str(text).strip(), tokens, elapsed)


class CodexCLIAdapter(BaseLLMAdapter):
    provider = "codex_cli"

    def generate(self, prompt, model_id):
        executable = shutil.which("codex")
        if not executable: raise RuntimeError("Codex CLI is not installed")
        with tempfile.TemporaryDirectory(prefix="ai-observatory-codex-") as temp_dir:
            output_path = str(Path(temp_dir) / "last-message.txt")
            command = [executable, "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--model", model_id, "--output-last-message", output_path, "-C", temp_dir, prompt]
            _, elapsed = _run_cli(command, 240)
            text = Path(output_path).read_text(encoding="utf-8").strip() if Path(output_path).exists() else ""
            if not text: raise RuntimeError("Codex CLI completed without a final response")
        return AdapterResult(self.provider, model_id, text, {}, elapsed)


class CopilotCLIAdapter(BaseLLMAdapter):
    provider = "copilot_cli"

    def generate(self, prompt, model_id):
        executable = shutil.which("copilot")
        if not executable: raise RuntimeError("GitHub Copilot CLI is not installed")
        output, elapsed = _run_cli([executable, "-p", prompt, "--model", model_id, "--silent", "--disable-builtin-mcps"], 180)
        return AdapterResult(self.provider, model_id, output.strip(), {}, elapsed)


def configured_codex_model():
    explicit = os.getenv("CODEX_CLI_MODEL_ID", "").strip()
    if explicit: return explicit
    # Codex app model configuration can include models the standalone CLI
    # does not support for ChatGPT-account sign-ins. Keep a known CLI default
    # and let operators override it explicitly in .env.
    return "gpt-5.5"


def configured_providers():
    copilot_models = configured_copilot_models()
    return {
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "google": bool(os.getenv("GOOGLE_API_KEY")),
        "minimax": bool(os.getenv("MINIMAX_API_KEY")),
        "deepseek": bool(os.getenv("DEEPSEEK_API_KEY")),
        "claude_code": bool(shutil.which("claude")),
        "codex_cli": bool(shutil.which("codex")),
        # Never expose Copilot Auto as a research model because its resolved
        # backend model is not part of the persisted response metadata.
        "copilot_cli": bool(shutil.which("copilot") and copilot_models),
    }


def configured_copilot_models():
    """Return only explicitly pinned Copilot model IDs; Auto is not research data."""
    values = os.getenv("COPILOT_CLI_MODEL_IDS", "").split(",")
    single = os.getenv("COPILOT_CLI_MODEL_ID", "").strip()
    if single: values.append(single)
    models=[]
    for value in values:
        model_id=value.strip()
        if model_id and model_id.lower()!="auto" and model_id not in models:
            models.append(model_id)
    return models


def available_live_models():
    providers = configured_providers()
    copilot_names = {
        "gpt-5.6-luna": "GPT-5.6 Luna",
        "gpt-5.6-sol": "GPT-5.6 Sol",
        "gpt-5.6-terra": "GPT-5.6 Terra",
        "gemini-3.7-flash": "Gemini 3.7 Flash",
        "claude-sonnet-5": "Claude Sonnet 5",
    }
    catalog = {
        "openai": [(os.getenv("OPENAI_MODEL_ID", "gpt-4.1-mini"), "OpenAI API · " + os.getenv("OPENAI_MODEL_ID", "gpt-4.1-mini"))],
        "anthropic": [(os.getenv("ANTHROPIC_MODEL_ID", "claude-haiku-4-5-20251001"), "Anthropic API · " + os.getenv("ANTHROPIC_MODEL_ID", "claude-haiku-4-5-20251001"))],
        "google": [(os.getenv("GOOGLE_MODEL_ID", "gemini-3.7-flash"), "Google API · " + os.getenv("GOOGLE_MODEL_ID", "gemini-3.7-flash"))],
        "minimax": [(os.getenv("MINIMAX_MODEL_ID", "MiniMax-M3"), "MiniMax API · " + os.getenv("MINIMAX_MODEL_ID", "MiniMax-M3"))],
        "deepseek": [(os.getenv("DEEPSEEK_MODEL_ID", "deepseek-flash"), "DeepSeek API · " + os.getenv("DEEPSEEK_MODEL_ID", "deepseek-flash"))],
        "claude_code": [(os.getenv("CLAUDE_CODE_MODEL_ID", "sonnet"), "Claude Code · Sonnet (subscription CLI)")],
        "codex_cli": [(configured_codex_model(), "Codex CLI · " + configured_codex_model())],
        "copilot_cli": [
            (model_id, f"GitHub Copilot · {copilot_names.get(model_id, model_id)}")
            for model_id in configured_copilot_models()
        ] if providers["copilot_cli"] else [],
    }
    return [(provider, model_id, label) for provider, items in catalog.items() if providers[provider] for model_id, label in items]


ADAPTERS = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "google": GeminiAdapter,
    "minimax": lambda: OpenAICompatibleAdapter("minimax", "MINIMAX_API_KEY", os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")),
    "deepseek": lambda: OpenAICompatibleAdapter("deepseek", "DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")),
    "claude_code": ClaudeCodeAdapter,
    "codex_cli": CodexCLIAdapter,
    "copilot_cli": CopilotCLIAdapter,
}
