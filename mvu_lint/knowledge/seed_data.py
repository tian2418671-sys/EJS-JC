"""Default knowledge base seed data.

Provides:
  - Knowledge chunks (EJS syntax, MVU format, common errors)
  - Error patterns (for ExceptionClassifier in Phase 4)
"""
from __future__ import annotations

from typing import List


def get_default_chunks() -> List[dict]:
    """Return default knowledge chunks for the RAG knowledge base."""
    return [
        {
            "chunk_id": "KB-001",
            "source_type": "docs",
            "title": "EJS 标签类型与语法",
            "content": (
                "EJS 模板使用 <% %> 标签嵌入 JavaScript 代码。\n"
                "标签类型：\n"
                "- <% ... %>：脚本标签，执行代码但不输出\n"
                "- <%= ... %>：转义输出，自动 HTML 转义（安全）\n"
                "- <%- ... %>：未转义输出，保留原始 HTML（有风险）\n"
                "- <%# ... %>：注释标签\n"
                "- <%% 输出字面量 <%，%%> 输出字面量 %>\n"
                "所有标签必须正确闭合，否则世界书加载失败。"
            ),
        },
        {
            "chunk_id": "KB-002",
            "source_type": "docs",
            "title": "EJS 转义输出与未转义输出",
            "content": (
                "<%= expr %> 会对输出内容进行 HTML 转义，将 < > & 等字符"
                "转换为实体，防止注入。\n"
                "<%- expr %> 不做转义，直接输出原始内容。\n"
                "在酒馆角色卡中，<%- 可能导致渲染异常或意外脚本注入。\n"
                "建议：除非确需渲染 HTML 片段，否则始终使用 <%=。\n"
                "安全等级：Lv.4（未转义 HTML 输出风险）。"
            ),
        },
        {
            "chunk_id": "KB-003",
            "source_type": "docs",
            "title": "MVU 命令格式",
            "content": (
                "MVU（Model Variable Update）框架通过 HTML 注释命令更新变量。\n"
                "命令格式：\n"
                "  <!-- mvu: 变量路径 操作符 数值/字符串 -->\n"
                "支持的操作符：\n"
                "  =  赋值：<!-- mvu: 主角.好感度 = 50 -->\n"
                "  += 加法：<!-- mvu: 主角.好感度 += 5 -->\n"
                "  -= 减法：<!-- mvu: 主角.好感度 -= 3 -->\n"
                "字符串赋值需用引号：\n"
                "  <!-- mvu: 主角.状态 = \"高兴\" -->\n"
                "每轮对话至少输出一条更新指令。"
            ),
        },
        {
            "chunk_id": "KB-004",
            "source_type": "docs",
            "title": "MVU 变量框架概述",
            "content": (
                "MVU 框架通过 schema.json 或 schema.ts 定义角色变量结构。\n"
                "核心 API：\n"
                "- Mvu.getMvuData()：获取当前变量数据\n"
                "- Mvu.parseMessage()：解析 AI 回复中的更新命令\n"
                "- stat_data：EJS 模板中访问变量的全局对象\n"
                "变量路径使用点号分隔：主角.能力面板.力量\n"
                "数组元素路径使用通配符：主角.物品栏.*.名称\n"
                "initvar 块定义变量初始值，必须与 Schema 一致。"
            ),
        },
        {
            "chunk_id": "KB-005",
            "source_type": "error_pattern",
            "title": "常见 EJS 错误模式",
            "content": (
                "1. 标签未闭合：缺少 %> 结束标签（Lv.1 致命错误）\n"
                "   症状：世界书加载失败或内容截断\n"
                "   修复：检查每个 <% 是否有对应的 %>\n\n"
                "2. 孤立 %>：有多余的 %> 但无对应 <%（Lv.1）\n"
                "   修复：删除多余的 %>\n\n"
                "3. 未转义输出 <%-：（Lv.4 安全警告）\n"
                "   修复：改为 <%= 或确认需要 HTML 渲染\n\n"
                "4. 变量路径不存在：EJS 中引用的路径在 Schema 中未定义（Lv.2）\n"
                "   修复：检查路径拼写或更新 Schema"
            ),
        },
        {
            "chunk_id": "KB-006",
            "source_type": "error_pattern",
            "title": "常见 MVU 错误模式",
            "content": (
                "1. initvar 缺字段：初始值缺少 Schema 中定义的必填字段（Lv.2）\n"
                "   修复：补充缺失的初始值\n\n"
                "2. 类型不匹配：initvar 值类型与 Schema 定义不符（Lv.2）\n"
                "   例：Schema 定义 number 但 initvar 给了 string\n"
                "   修复：修正 initvar 值类型\n\n"
                "3. 更新规则路径不存在：MVU 命令中的路径在 Schema 中找不到（Lv.3）\n"
                "   修复：检查路径或更新 Schema\n\n"
                "4. 命令格式错误：缺少操作符或值（Lv.2）\n"
                "   修复：按标准格式重写命令"
            ),
        },
        {
            "chunk_id": "KB-007",
            "source_type": "docs",
            "title": "Schema.json 双形态说明",
            "content": (
                "角色卡的 Schema 有两种 JSON 形态：\n\n"
                "形态一：标准 JSON Schema\n"
                "  包含 $schema 或 properties 顶层键\n"
                "  通过 properties/type 递归解析\n\n"
                "形态二：纯数据形状（Zod 直出）\n"
                "  直接是对象，无 $schema\n"
                "  通过实际值推断类型：int/float→number, str→string, bool→boolean\n"
                "  数组元素用首元素推断，路径用 * 占位\n\n"
                "两种形态解析后统一为路径树，用于联动检查。"
            ),
        },
        {
            "chunk_id": "KB-008",
            "source_type": "docs",
            "title": "EJS 变量路径静态子集",
            "content": (
                "EJS 变量路径提取的静态子集边界：\n\n"
                "可静态解析（输出 path 字段）：\n"
                "- <%= stat_data.主角.好感度 %>\n"
                "- <%= mvu.get('主角.好感度') %>\n"
                "- <%= locals.user.name %>\n"
                "- <%= data.物品栏[0].名称 %>（数字索引）\n\n"
                "不可静态解析（仅提示，不报错）：\n"
                "- <%= vars[props.key] %>（动态属性名）\n"
                "- <%= data.list.find(x => x.id) %>（方法调用）\n"
                "- <%= data.x + 1 %>（算术运算）\n"
                "- <% if %> / <% for %> 块内变量不跨块追踪\n\n"
                "联动检查只消费可静态解析的条目。"
            ),
        },
    ]


def get_default_error_patterns() -> List[dict]:
    """Return default error patterns for exception classification."""
    return [
        {
            "pattern_name": "ejs_unclosed_tag",
            "error_level": "Lv.1",
            "regex_pattern": r"<%(?!%)[^%]*$",
            "description": "EJS 标签未闭合，缺少 %> 结束标签",
            "fix_suggestion": "在标签内容结束后添加 %> 闭合标签",
            "priority": 10,
        },
        {
            "pattern_name": "ejs_stray_close",
            "error_level": "Lv.1",
            "regex_pattern": r"(?<!%)%>(?!%)",
            "description": "存在孤立的 %> 闭合标签，没有对应的 <% 开启标签",
            "fix_suggestion": "删除多余的 %> 或补充对应的 <% 标签",
            "priority": 10,
        },
        {
            "pattern_name": "ejs_unsafe_output",
            "error_level": "Lv.4",
            "regex_pattern": r"<%-",
            "description": "检测到 <%- 未转义输出，可能导致渲染异常或意外脚本注入",
            "fix_suggestion": "改为 <%= 进行转义输出，除非确需 HTML 渲染",
            "priority": 5,
        },
        {
            "pattern_name": "mvu_invalid_command",
            "error_level": "Lv.2",
            "regex_pattern": r"<!--\s*mvu\s*:[^>]*-->",
            "description": "MVU 命令格式可能不正确，需检查路径、操作符和值",
            "fix_suggestion": "按标准格式重写：<!-- mvu: 路径 操作符 值 -->",
            "priority": 8,
        },
        {
            "pattern_name": "mvu_path_not_found",
            "error_level": "Lv.3",
            "regex_pattern": r"",
            "description": "MVU 更新规则中的变量路径在 Schema 中不存在",
            "fix_suggestion": "检查路径拼写或在 Schema 中添加该路径",
            "priority": 6,
        },
        {
            "pattern_name": "mvu_initvar_missing",
            "error_level": "Lv.2",
            "regex_pattern": r"",
            "description": "initvar 初始值缺少 Schema 中定义的必填字段",
            "fix_suggestion": "补充缺失的初始值字段",
            "priority": 7,
        },
    ]
