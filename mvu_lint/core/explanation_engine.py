"""Error explanation engine (Phase 5 / F7) — RAG + LLM + template fallback.

Turns a single static-check error dict into a human-readable root-cause
explanation. Strategy:

  1. Retrieve related knowledge chunks via RAG (when a knowledge base is
     provided).
  2. If an LLM is available, build a structured prompt and ask the model.
  3. Otherwise (or if generation fails / times out), fall back to a
     deterministic template explanation assembled from the error fields and
     the retrieved knowledge.

Qt-free by design (see tests/test_explanation_engine.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .llm_service import LLMService

_LEVEL_HINTS = {
    "Lv.1": "致命错误：会导致世界书加载失败或内容截断。",
    "Lv.2": "严重错误：运行时可能崩溃或行为异常。",
    "Lv.3": "警告：逻辑问题或潜在不一致。",
    "Lv.4": "安全提示：未转义 HTML 输出风险。",
}

_SYSTEM_PROMPT = (
    "你是 MVU（Model Variable Update）+ EJS 角色卡脚本的资深调试专家。"
    "请用简洁的中文分析给定的静态检查错误，"
    "严格输出两部分内容：1) 根因分析 2) 具体修复步骤。"
)


@dataclass
class ExplanationResult:
    """One error explanation, with provenance for the UI/CLI to display."""
    error_id: str
    explanation: str
    source: str = "template"        # "llm" / "template"
    model: str = ""                 # model path when source == "llm"
    chunks: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "error_id": self.error_id,
            "explanation": self.explanation,
            "source": self.source,
            "model": self.model,
            "chunks": [
                {"chunk_id": c.get("chunk_id", ""), "title": c.get("title", "")}
                for c in self.chunks
            ],
        }


class ExplanationEngine:
    """Generate root-cause explanations for static-check errors."""

    def __init__(self, llm: Optional[LLMService] = None, rag=None):
        self.llm = llm or LLMService()
        self.rag = rag

    # ── main entry ──────────────────────────────────────────────────

    def explain(self, error: dict, use_llm: bool = True, top_k: int = 3,
                timeout: Optional[float] = None) -> ExplanationResult:
        """Explain a single error dict.

        ``use_llm=False`` forces the template path (useful for tests / when
        no model should ever be invoked).
        """
        chunks = self._retrieve(error, top_k)
        if use_llm and self.llm.available:
            prompt = self._build_prompt(error, chunks)
            text = self.llm.generate(
                prompt, max_tokens=512, temperature=0.3, timeout=timeout
            )
            if text:
                return ExplanationResult(
                    error_id=error.get("error_id", ""),
                    explanation=text,
                    source="llm",
                    model=self.llm.model_path or "local-model",
                    chunks=chunks,
                )
        return self._template_explain(error, chunks)

    # ── retrieval ───────────────────────────────────────────────────

    def _retrieve(self, error: dict, top_k: int) -> List[dict]:
        if self.rag is None:
            return []
        query = " ".join(filter(None, [
            error.get("category", ""),
            error.get("message", ""),
            error.get("path") or "",
        ]))
        if not query.strip():
            return []
        try:
            return self.rag.search(query, top_k=top_k)
        except Exception:  # noqa: BLE001 — RAG failure is non-fatal
            return []

    # ── prompt ──────────────────────────────────────────────────────

    def _build_prompt(self, error: dict, chunks: List[dict]) -> str:
        parts: List[str] = [_SYSTEM_PROMPT, "", "【错误信息】"]
        parts.append(f"级别: {error.get('level', '')}")
        hint = _LEVEL_HINTS.get(error.get("level", ""), "")
        if hint:
            parts.append(f"级别说明: {hint}")
        parts.append(f"类别: {error.get('category', '')}")
        if error.get("file_path"):
            parts.append(f"文件: {error['file_path']}")
        if error.get("line_number"):
            parts.append(f"行号: {error['line_number']}")
        if error.get("path"):
            parts.append(f"变量路径: {error['path']}")
        parts.append(f"错误消息: {error.get('message', '')}")
        if error.get("suggestion"):
            parts.append(f"工具建议: {error['suggestion']}")

        if chunks:
            parts.append("")
            parts.append("【相关知识库片段】")
            for c in chunks:
                parts.append(f"- {c.get('title', '')}: {c.get('content', '')[:400]}")
        parts.append("")
        parts.append("请输出：根因分析 + 修复步骤。")
        return "\n".join(parts)

    # ── template fallback ───────────────────────────────────────────

    def _template_explain(self, error: dict,
                          chunks: List[dict]) -> ExplanationResult:
        lines: List[str] = []
        lines.append("【根因分析】")
        hint = _LEVEL_HINTS.get(error.get("level", ""), "")
        if hint:
            lines.append(hint)
        if error.get("message"):
            lines.append(f"触发点：{error['message']}")
        if error.get("category"):
            lines.append(f"问题类别：{error['category']} 类检查发现。")

        if chunks:
            lines.append("")
            lines.append("【参考依据】")
            for c in chunks[:3]:
                lines.append(f"· {c.get('title', '')}")

        lines.append("")
        lines.append("【修复建议】")
        if error.get("suggestion"):
            lines.append(error["suggestion"])
        else:
            lines.append("请根据消息与级别定位到对应模板或脚本片段，核对语法后重新扫描。")

        return ExplanationResult(
            error_id=error.get("error_id", ""),
            explanation="\n".join(lines),
            source="template",
            chunks=chunks,
        )
