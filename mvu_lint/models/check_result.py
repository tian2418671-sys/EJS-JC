"""Data models for check results."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorLevel(Enum):
    """Error severity levels."""
    LV1 = "Lv.1"  # 致命：阻止世界书加载
    LV2 = "Lv.2"  # 严重：运行时崩溃
    LV3 = "Lv.3"  # 警告：逻辑问题
    LV4 = "Lv.4"  # 安全：未转义输出风险


class ErrorCategory(Enum):
    """Error categories."""
    EJS = "EJS"
    MVU = "MVU"
    LINKAGE = "联动"


@dataclass
class CheckResult:
    """A single check result / error finding."""
    error_id: str
    level: ErrorLevel
    category: ErrorCategory
    file_path: str
    message: str
    line_number: Optional[int] = None
    path: Optional[str] = None
    suggestion: Optional[str] = None
    auto_fixable: bool = False
    fix_preview: Optional[str] = None
    ai_explanation: Optional[str] = None
    status: str = "pending"
    is_static: bool = False

    def to_dict(self) -> dict:
        return {
            "error_id": self.error_id,
            "level": self.level.value,
            "category": self.category.value,
            "file_path": self.file_path,
            "message": self.message,
            "line_number": self.line_number,
            "path": self.path,
            "suggestion": self.suggestion,
            "auto_fixable": self.auto_fixable,
            "fix_preview": self.fix_preview,
            "status": self.status,
            "is_static": int(self.is_static),
        }
