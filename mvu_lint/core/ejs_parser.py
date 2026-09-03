"""Pure-Python EJS tag checker and variable reference extractor.

Static subset boundary (Decision 1):
  Supported (path extracted, is_static=True):
    - <%= stat_data.X.Y %>
    - <%= data.X.Y[0].Z %>      (numeric indices normalized to .N)
    - <%= mvu.get('X.Y') %>
    - <%= locals.X.Y %>
    - <%- ... %>                 (same patterns, but flagged Lv.4)

  Not supported (is_static=False, noted but not errored):
    - Dynamic property names: vars[props.key]
    - Method calls: data.list.find(...)
    - Arithmetic: data.x + 1
    - Variables inside <% if/for %> blocks (not tracked)

Known limitation: %> inside string literals within EJS tags may cause
false positives.  Acceptable for Phase 0; real tavern-card EJS rarely
contains %> inside strings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..models.check_result import CheckResult, ErrorCategory, ErrorLevel


@dataclass
class EJSVariableReference:
    """A variable reference extracted from an EJS output tag."""
    raw: str
    path: Optional[str]
    line: int
    is_safe: bool        # True for <%=, False for <%-
    is_static: bool
    note: Optional[str] = None


@dataclass
class EJSParseResult:
    """Aggregated result of parsing one file's EJS content."""
    check_results: List[CheckResult]
    variable_refs: List[EJSVariableReference]

    def to_dict(self) -> dict:
        return {
            "errors": [r.to_dict() for r in self.check_results],
            "variable_refs": [
                {
                    "raw": ref.raw,
                    "path": ref.path,
                    "line": ref.line,
                    "is_safe": ref.is_safe,
                    "is_static": ref.is_static,
                    "note": ref.note,
                }
                for ref in self.variable_refs
            ],
        }


# ── Regex patterns ──────────────────────────────────────────────────

# Find <%= ... %> or <%- ... %> output tags (non-greedy, DOTALL)
_OUTPUT_TAG_RE = re.compile(r"<%([=\-])\s*([\s\S]*?)\s*%>", re.DOTALL)

# Match mvu.get('X.Y') / Mvu.getMvuData('X.Y') / mvu.getData('X.Y')
_MVU_GET_RE = re.compile(
    r"^[Mm]vu\.get(?:MvuData|Data)?\(\s*['\"](.+?)['\"]\s*\)$"
)

# Match data.X.Y / stat_data.X.Y / locals.X.Y
_DOTTED_ACCESS_RE = re.compile(
    r"^(?:stat_data|data|locals)\.(.+)$"
)

# Valid static path segment: word chars (incl. Chinese) + optional [N]
_STATIC_PATH_RE = re.compile(
    r"^[\w\u4e00-\u9fff]+(?:\[\d+\])?(?:\.[\w\u4e00-\u9fff]+(?:\[\d+\])?)*$"
)

# Dynamic property name: [non-numeric content]
_DYNAMIC_INDEX_RE = re.compile(r"\[[^\d\]]+\]")

# Method call: .word(
_METHOD_CALL_RE = re.compile(r"\.\w+\(")

# Arithmetic / ternary operators (excluding leading minus in paths)
_ARITH_RE = re.compile(r"[\+\*/%?]")


class EJSParser:
    """EJS tag checker and variable reference extractor."""

    def __init__(self):
        self._file_path: str = ""
        self._error_counter: int = 0

    # ── Public API ──────────────────────────────────────────────────

    def parse(self, content: str, file_path: str = "") -> EJSParseResult:
        """Parse EJS content and return check results + variable refs."""
        self._file_path = file_path
        self._error_counter = 0

        check_results: List[CheckResult] = []
        var_refs: List[EJSVariableReference] = []

        # 1. Tag pairing check
        check_results.extend(self._check_tag_pairing(content))

        # 2. Extract variable references from output tags
        var_refs = self._extract_variable_references(content)

        # 3. Dangerous output check (<%-)
        check_results.extend(self._check_dangerous_output(var_refs))

        return EJSParseResult(check_results=check_results, variable_refs=var_refs)

    # ── Tag pairing ─────────────────────────────────────────────────

    def _check_tag_pairing(self, content: str) -> List[CheckResult]:
        """Check for unclosed <% and stray %> tags via state machine."""
        results: List[CheckResult] = []
        i = 0
        n = len(content)
        in_tag = False
        tag_start_line = 0

        while i < n:
            if not in_tag:
                # Escaped <%%
                if content[i:i + 3] == "<%%":
                    i += 3
                    continue
                # Escaped %%>
                if content[i:i + 3] == "%%>":
                    i += 3
                    continue
                # Opening <%
                if content[i:i + 2] == "<%":
                    in_tag = True
                    tag_start_line = content[:i].count("\n") + 1
                    i += 2
                    continue
                # Stray %>
                if content[i:i + 2] == "%>":
                    line = content[:i].count("\n") + 1
                    results.append(self._make_result(
                        level=ErrorLevel.LV1,
                        message=f"第 {line} 行：存在孤立的 %> 闭合标签，没有对应的 <% 开启标签",
                        line=line,
                        suggestion="删除多余的 %> 或补充对应的 <% 标签",
                        auto_fixable=False,
                    ))
                    i += 2
                    continue
            else:
                # Inside tag — look for closing %>
                if content[i:i + 2] == "%>":
                    in_tag = False
                    i += 2
                    continue
            i += 1

        # Unclosed tag at EOF
        if in_tag:
            results.append(self._make_result(
                level=ErrorLevel.LV1,
                message=f"第 {tag_start_line} 行：EJS 标签未闭合，缺少 %> 结束标签",
                line=tag_start_line,
                suggestion="在标签内容结束后添加 %> 闭合标签",
                auto_fixable=True,
            ))

        return results

    # ── Variable extraction ─────────────────────────────────────────

    def _extract_variable_references(self, content: str) -> List[EJSVariableReference]:
        """Extract variable references from <%= ... %> and <%- ... %> tags."""
        refs: List[EJSVariableReference] = []
        for match in _OUTPUT_TAG_RE.finditer(content):
            output_type = match.group(1)  # "=" or "-"
            expr = match.group(2).strip()
            line = content[:match.start()].count("\n") + 1
            is_safe = (output_type == "=")

            path, is_static, note = self._try_extract_path(expr)
            refs.append(EJSVariableReference(
                raw=match.group(0),
                path=path,
                line=line,
                is_safe=is_safe,
                is_static=is_static,
                note=note,
            ))
        return refs

    def _try_extract_path(self, expr: str) -> Tuple[Optional[str], bool, Optional[str]]:
        """Try to extract a static variable path from an expression.

        Returns (path, is_static, note).
        """
        expr = expr.strip()
        if not expr:
            return (None, False, "空表达式")

        # Pattern 1: mvu.get('X.Y') / Mvu.getMvuData('X.Y')
        m = _MVU_GET_RE.match(expr)
        if m:
            return (m.group(1), True, None)

        # Pattern 2: stat_data.X.Y / data.X.Y / locals.X.Y
        m = _DOTTED_ACCESS_RE.match(expr)
        if m:
            rest = m.group(1)
            # Check for dynamic patterns
            if _DYNAMIC_INDEX_RE.search(rest):
                return (None, False, "动态属性名 [key]，无法静态解析")
            if _METHOD_CALL_RE.search(rest):
                return (None, False, "包含方法调用，无法静态解析")
            if _ARITH_RE.search(rest):
                return (None, False, "包含算术/三元运算，无法静态解析")
            # Check if remaining "-" is part of arithmetic (not path)
            # A bare "-" between word chars is likely subtraction
            if re.search(r"\w\s*-\s*\w", rest):
                return (None, False, "包含算术运算，无法静态解析")
            # Validate static path format
            if _STATIC_PATH_RE.match(rest):
                # Normalize [N] → .N
                path = re.sub(r"\[(\d+)\]", r".\1", rest)
                return (path, True, None)
            else:
                return (None, False, "路径格式不符合静态子集")

        # Pattern 3: Recognized but non-static patterns (not in known prefix)
        if _DYNAMIC_INDEX_RE.search(expr):
            return (None, False, "动态属性名 [key]，无法静态解析")
        if _METHOD_CALL_RE.search(expr):
            return (None, False, "包含方法调用，无法静态解析")
        if _ARITH_RE.search(expr):
            return (None, False, "包含算术/三元运算，无法静态解析")

        # Pattern 4: unrecognized
        return (None, False, "无法识别的变量引用模式")

    # ── Dangerous output ────────────────────────────────────────────

    def _check_dangerous_output(self, var_refs: List[EJSVariableReference]) -> List[CheckResult]:
        """Flag <%- (unescaped output) as Lv.4 security warning."""
        results: List[CheckResult] = []
        for i, ref in enumerate(var_refs):
            if not ref.is_safe:
                results.append(self._make_result(
                    level=ErrorLevel.LV4,
                    message=(
                        f"第 {ref.line} 行：检测到 <%- 未转义输出，"
                        f"可能导致渲染异常或意外脚本注入"
                    ),
                    line=ref.line,
                    path=ref.path,
                    suggestion="改为 <%= 进行转义输出，除非确需 HTML 渲染",
                    auto_fixable=False,
                    is_static=ref.is_static,
                ))
        return results

    # ── Helpers ─────────────────────────────────────────────────────

    def _make_result(
        self,
        level: ErrorLevel,
        message: str,
        line: Optional[int] = None,
        path: Optional[str] = None,
        suggestion: Optional[str] = None,
        auto_fixable: bool = False,
        is_static: bool = False,
    ) -> CheckResult:
        self._error_counter += 1
        return CheckResult(
            error_id=f"EJS-{self._error_counter:04d}",
            level=level,
            category=ErrorCategory.EJS,
            file_path=self._file_path,
            message=message,
            line_number=line,
            path=path,
            suggestion=suggestion,
            auto_fixable=auto_fixable,
            status="pending",
            is_static=is_static,
        )
