# MVU + EJS 智能代码检查工具

一个纯 Python 的酒馆角色卡（SillyTavern 角色卡）**静态检查 + 动态定位 + AI 解释**工具。

针对使用 **MVU（Model Variable Update）变量框架** 与 **EJS 模板语法** 的角色卡，提供导入、检查、修复、模拟、定位、AI 解释的一站式工作流。无需 Node.js，无需外部推理服务。

> 仓库：https://github.com/tian2418671-sys/EJS-JC

---

## ✨ 功能特性

| 功能 | 说明 | 阶段 |
|:-----|:-----|:-----|
| **F1 导入与结构识别** | 拖拽导入角色卡（`.png` / `.json`），自动识别世界书、开场白、变量初始值等检查块 | Phase 1 |
| **F2 静态检查** | EJS 标签闭合、`<%-` 未转义输出、MVU 命令格式、JSON Patch 路径、EJS↔Schema 联动、initvar 完整性，按 Lv.1–Lv.4 分级 | Phase 1–2 |
| **F3 报告展示与导出** | 分级过滤、双击详情、右键标记状态；导出 HTML / CSV / Markdown | Phase 1–2 |
| **F4 模拟对话引擎** | 规则驱动的变量推演（技术验证），逐轮记录命令与快照 | Phase 3 |
| **F5 日志追踪与时间旅行** | 滑块回放任意步骤的变量快照，变更行高亮 + diff 视图 | Phase 3–4 |
| **F6 动态定位器** | 基于日志 + 快照 diff，定位命令失败 / 变量消失 / 类型漂移 / 未追踪变更 | Phase 4 |
| **F7 AI 错误解释 + RAG** | 本地 LLM + 知识库检索生成根因分析与修复步骤（无模型时降级为模板解释） | Phase 5 |

## 🏗️ 技术栈

- **语言**：Python 3.10+
- **GUI**：PySide6（Qt6）
- **AI 推理**：llama-cpp-python（可选依赖，模型外置）
- **默认模型**：Qwen2.5-1.5B-Instruct-GGUF（Q4_K_M）
- **向量检索**：sqlite-vec，内置 NumPy 暴力余弦降级路径
- **存储**：SQLite（标准库 `sqlite3`）
- **打包**：PyInstaller（单文件 EXE）

## 📦 安装

```bash
# 基础运行
pip install -r requirements.txt

# 启用 AI 解释（可选，需本地模型）
pip install llama-cpp-python
```

### 模型下载（可选）

将 GGUF 模型放入模型目录（首次运行 AI 解释时自动探测）：

- Windows：`%APPDATA%\MvuEjsLinter\models\`
- Linux/macOS：`$XDG_DATA_HOME/MvuEjsLinter/models/`（默认 `~/.local/share/MvuEjsLinter/models/`）

推荐模型（HuggingFace / ModelScope 下载）：

| 模型 | 参数量 | 量化 | 用途 |
|:-----|:-------|:-----|:-----|
| Qwen2.5-1.5B-Instruct | 15 亿 | Q4_K_M | 默认，模拟对话 + 错误解释 |
| Qwen2.5-3B-Instruct | 30 亿 | Q4_K_M | 可选升级，更高质量解释 |

> **未安装模型也能正常使用**：AI 解释会自动降级为「模板规则 + 知识库摘要」，不阻塞核心检查流程。

## 🚀 使用方法

### GUI

```bash
python -m mvu_lint gui
```

打包后直接双击 `MvuEjsLinter.exe`。

工作流：拖入角色卡 → 「开始静态检查」→ 右键错误行 →「🤖 AI 解释」→（可选）「运行模拟」→「时间旅行」→「动态定位」。

### 命令行

```bash
# 静态检查
python -m mvu_lint scan <角色卡.png|json>

# 模拟对话
python -m mvu_lint simulate <角色卡.png|json> [--input 文本 ...]

# 动态定位
python -m mvu_lint debug <角色卡.png|json> [--input 文本 ...]

# AI 解释（列出错误后指定 ID 解释）
python -m mvu_lint explain <角色卡.png|json>
python -m mvu_lint explain <角色卡.png|json> EJS-0001
python -m mvu_lint explain <角色卡.png|json> --all
```

## 📐 架构

```
mvu_lint/
├── core/                 # 纯逻辑，Qt-free，可无头单测
│   ├── ejs_parser.py         # 纯 Python EJS 检查（静态子集边界）
│   ├── schema_loader.py      # schema.json 双形态解析
│   ├── static_checker.py     # MVU / JSON Patch / 联动 / initvar 检查
│   ├── simulation_engine.py  # 规则驱动模拟引擎
│   ├── debugger.py           # 动态定位器（F6）
│   ├── llm_service.py        # 本地 LLM 封装（可选依赖，Phase 5）
│   ├── rag_service.py        # RAG 知识库门面（Phase 5）
│   └── explanation_engine.py # 错误解释引擎（RAG + LLM + 模板降级，Phase 5）
├── db/
│   ├── database.py           # SQLite 连接与表管理
│   └── vector_db.py          # sqlite-vec + NumPy 降级
├── knowledge/                # 默认知识库种子数据
├── controllers/              # 应用控制器（GUI-agnostic）
├── views/                    # PySide6 界面
└── utils/                    # 报告导出等
```

## 🗺️ 开发阶段

| 阶段 | 版本 | 内容 | 状态 |
|:-----|:-----|:-----|:-----|
| Phase 0 | — | 基础库 + CLI + 单元测试 | ✅ |
| Phase 1 | v0.1 | GUI + 导入 + EJS 检查 + 报告 | ✅ |
| Phase 2 | v0.2 | 完整静态检查 + 自动修复 + 导出 | ✅ |
| Phase 3 | v0.3 | 模拟对话 + 日志 + 快照 | ✅ |
| Phase 4 | v0.4 | 动态定位 + 时间旅行 | ✅ |
| Phase 5 | v1.0 | LLM + RAG + 错误解释 | ✅ |
| Phase 6 | v1.1 | 打包发布 + 文档 | ⬜ |

## 🧪 测试

```bash
python -m pytest
```

测试覆盖：EJS 解析、Schema 加载、静态检查、模拟引擎、动态定位、自动修复、报告导出、向量库、LLM 服务、解释引擎、RAG、控制器。

## ⚠️ 免责声明

- 「模拟对话」为**技术验证**用途，不承诺角色扮演质量。
- AI 错误解释依赖本地模型，质量随模型规模与量化格式而异；无模型时自动降级为模板解释。
