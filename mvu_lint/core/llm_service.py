"""LLM service (Phase 5 / F7) — optional llama-cpp-python integration.

Wraps a local GGUF model behind a small, Qt-free interface with a graceful
fallback story: when ``llama-cpp-python`` is missing or no model file exists,
:attr:`LLMService.available` is ``False`` and :meth:`LLMService.generate`
returns ``None`` so callers can degrade to template explanations.

Models are expected to live under ``%APPDATA%/MvuEjsLinter/models/`` on
Windows (or ``$XDG_DATA_HOME/MvuEjsLinter/models/`` elsewhere) and are never
bundled with the application.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

_DEFAULT_N_CTX = 2048
_DEFAULT_MAX_TOKENS = 512
_DEFAULT_TEMPERATURE = 0.3
_STOP_SEQUENCES = ["<|im_end|>", "<|endoftext|>", "###"]


def default_models_dir() -> Path:
    """Return the platform model directory (created on demand)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(
            Path.home() / ".local" / "share"
        )
    return Path(base) / "MvuEjsLinter" / "models"


def find_default_model(models_dir: Optional[Path] = None) -> Optional[Path]:
    """Return the first ``*.gguf`` file found, preferring Qwen-named ones."""
    directory = models_dir or default_models_dir()
    if not directory.exists():
        return None
    ggufs = sorted(directory.glob("*.gguf"))
    if not ggufs:
        return None
    for prefer in ("qwen", "Qwen"):
        for path in ggufs:
            if prefer in path.name:
                return path
    return ggufs[0]


class LLMService:
    """Lazy local-LLM wrapper with graceful fallback.

    The model is only loaded on :meth:`load`; constructing the service is
    cheap and side-effect free, which keeps the GUI and unit tests fast.
    """

    def __init__(self, model_path: Optional[str] = None,
                 n_ctx: int = _DEFAULT_N_CTX):
        self._model_path: Optional[str] = model_path
        self._n_ctx = n_ctx
        self._llm = None
        self._load_error: str = ""
        self._cancel = threading.Event()

    # ── state ──────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """Whether a model is currently loaded and ready to generate."""
        return self._llm is not None

    @property
    def model_path(self) -> Optional[str]:
        return self._model_path

    @property
    def load_error(self) -> str:
        return self._load_error

    @property
    def status(self) -> str:
        if self.available:
            return "loaded"
        if self._load_error:
            return "error"
        return "idle"

    # ── lifecycle ──────────────────────────────────────────────────

    def load(self) -> bool:
        """Load the configured (or first discovered) model. Idempotent.

        Returns ``True`` on success; on failure :attr:`load_error` explains
        why and :attr:`available` stays ``False``.
        """
        if self._llm is not None:
            return True

        path = self._model_path
        if not path:
            found = find_default_model()
            if found is None:
                self._load_error = "未找到模型文件（请将 .gguf 放入模型目录）"
                return False
            path = str(found)
            self._model_path = path

        if not Path(path).exists():
            self._load_error = f"模型文件不存在: {path}"
            return False

        try:
            from llama_cpp import Llama  # optional dependency
        except ImportError:
            self._load_error = "未安装 llama-cpp-python（可选依赖，可降级为模板解释）"
            return False

        try:
            self._llm = Llama(model_path=path, n_ctx=self._n_ctx, verbose=False)
            return True
        except Exception as exc:  # noqa: BLE001 — surface any load failure
            self._load_error = f"模型加载失败: {exc}"
            return False

    def unload(self):
        """Release the model and reset error state."""
        self._llm = None
        self._load_error = ""

    def cancel(self):
        """Request cancellation of any in-flight generation."""
        self._cancel.set()

    # ── generation ─────────────────────────────────────────────────

    def generate(self, prompt: str,
                 max_tokens: int = _DEFAULT_MAX_TOKENS,
                 temperature: float = _DEFAULT_TEMPERATURE,
                 timeout: Optional[float] = None) -> Optional[str]:
        """Generate text, or return ``None`` if unavailable / timed out.

        ``timeout`` (seconds) performs a soft timeout: the blocking llama-cpp
        call runs in a daemon thread and ``None`` is returned early if it
        does not finish in time. The background thread still completes, but
        the caller never blocks past the deadline.
        """
        if not self.available:
            return None
        self._cancel.clear()
        if timeout and timeout > 0:
            return self._generate_with_timeout(
                prompt, max_tokens, temperature, timeout
            )
        return self._generate_now(prompt, max_tokens, temperature)

    def _generate_now(self, prompt: str, max_tokens: int,
                      temperature: float) -> Optional[str]:
        try:
            out = self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=_STOP_SEQUENCES,
            )
            return out["choices"][0]["text"].strip()
        except Exception:  # noqa: BLE001 — generation failure → fallback
            return None

    def _generate_with_timeout(self, prompt: str, max_tokens: int,
                               temperature: float, timeout: float) -> Optional[str]:
        box: dict = {}

        def _run() -> None:
            box["text"] = self._generate_now(prompt, max_tokens, temperature)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self._cancel.set()
            return None
        return box.get("text")
