# MVU + EJS 智能代码检查工具 — 技术方案 v2（实施基准）

> **版本**: v2.1
> **日期**: 2026-09-03
> **状态**: 已锁定，Phase 0 完成验收，Phase 1 准备中

---

## 1. 已确认技术决策

| # | 决策 | 结论 |
|:-:|:-----|:-----|
| 1 | EJS 检查 | 纯 Python 自实现，弃 Node.js / ejs-lint |
| 2 | 向量数据库 | `sqlite-vec` 替代 `sqlite-vector` |
| 3 | LLM 模型 | 默认 `Qwen2.5-1.5B-Instruct`，3B 可选 |
| 4 | Schema 解析 | 主推 `schema.json`，`schema.ts` 降级文本扫描 |
| 5 | 安全定性 | Lv.4 改称"未转义 HTML 输出风险"，弃用 XSS |
| 6 | 打包体积 | 核心包 ≤ 200MB，模型外置 |

## 2. 底层设计决策（不可返工）

### 2.1 EJS 变量路径提取 — 静态子集边界

支持提取（`is_static=True`）:
- `<%= stat_data.X.Y %>`
- `<%= mvu.get('X.Y') %>`
- `<%= locals.X.Y %>`
- `<%- data.X[0].Y %>`（数字索引）

不支持提取（`is_static=False`，仅提示不报错）:
- 动态属性名 `vars[props.key]`
- 方法调用 `data.list.find(...)`
- 算术运算 `data.x + 1`
- `<% if/for %>` 块内变量

### 2.2 schema.json 双形态兼容

| 形态 | 识别 | 解析 |
|:-----|:-----|:-----|
| 标准 JSON Schema | 含 `$schema` 或 `properties` | 递归 properties → type |
| 纯数据形状 | 无上述键 | 递归叶子，type(value) 推断 |

数组元素用 `*` 占位：`主角.物品栏.*.名称`

### 2.3 模拟对话预期管理

- UI 文案为"技术验证对话"，不承诺角色扮演质量
- 系统提示词含 few-shot + 低温度
- 输出解析三级降级：标准格式 → 宽松正则 → LLM 重写（最多 1 次）

### 2.4 原生扩展降级路径

| 扩展 | 降级 | 触发 |
|:-----|:-----|:-----|
| sqlite-vec | NumPy 暴力余弦 | load_extension 失败 |
| llama-cpp | 跳过模拟 | 模型未下载 |

Phase 1 GUI 跑通后立即做空壳打包验证。

## 3. 用户工作流

### 3.1 标准操作流程

1. **导入项目**：拖拽或选择角色卡 ZIP 文件，系统自动解压到临时目录并建立 `file_index`。
2. **识别结构**：自动检测世界书、脚本、界面、Schema 等目录布局。
3. **Schema 加载**：尝试读取 `schema.json`，构建路径树写入 `schema_cache`。
4. **静态检查**：点击"开始检查"按钮，系统执行 F2 扫描。若未找到 `schema.json`，系统将启用降级模式（仅文本级扫描），并在报告中标注"⚠️ 部分 MVU 检查已降级，建议执行 `pnpm build` 生成 `schema.json`"。
5. **查看报告**：检查结果按 Lv.1–Lv.4 分级展示，支持过滤、排序、导出。
6. **自动修复**：对 `auto_fixable=1` 的错误提供一键修复预览。
7. **模拟对话**（Phase 3+）：启动技术验证对话，逐轮记录变量状态快照。
8. **动态定位**（Phase 4+）：结合模拟日志与快照，定位异常根因。
9. **AI 错误解释**（Phase 5+）：RAG 检索知识库，LLM 生成根因分析与修复建议。

### 3.2 决策门 — 补充说明

**模拟对话模式**：无论是否为自动漫步，每轮输出均经过输出格式解析器，解析失败自动重试一次。重试仍失败则记录为"命令解析错误"，继续执行下一轮（不中断流程）。

## 4. 技术架构

### 4.1 项目结构

```
方案1/
├── SPEC_v2.md
├── pyproject.toml
├── mvu_lint/
│   ├── __init__.py
│   ├── __main__.py               # CLI: python -m mvu_lint scan
│   ├── app.py                    # GUI 主入口
│   ├── models/
│   │   └── check_result.py       # ErrorLevel / ErrorCategory / CheckResult
│   ├── core/
│   │   ├── ejs_parser.py         # 纯 Python EJS 检查（静态子集边界已定义）
│   │   ├── schema_loader.py      # 双形态 schema.json 读取器
│   │   ├── project_scanner.py    # ZIP 解压 + 目录识别 + file_index 写入
│   │   ├── static_checker.py     # 静态检查总控
│   │   ├── simulation_engine.py  # 模拟对话引擎（含降级解析器）
│   │   └── debugger.py           # 动态定位器
│   ├── db/
│   │   ├── database.py           # SQLite 连接管理
│   │   └── vector_db.py          # sqlite-vec + NumPy 降级路径
│   ├── knowledge/
│   │   └── seed_data.py          # 默认知识库种子数据
│   ├── controllers/              # 应用控制器
│   ├── views/                    # PySide6 界面
│   └── utils/
│       ├── logger.py
│       └── exceptions.py
├── tests/
│   ├── conftest.py
│   ├── test_ejs_parser.py
│   ├── test_schema_loader.py
│   ├── test_project_scanner.py
│   └── test_vector_db.py
├── resources/                    # 图标、样式
├── build.spec                    # PyInstaller 配置
└── requirements.txt
```

### 4.2 关键模块边界

**EJS 解析器（EJSParser）**
- 输入：世界书原始文本
- 输出：结构化 `EJSVariableReference` 列表（含 `is_static` 标记）
- 不依赖任何外部工具

**Schema 加载器（SchemaLoader）**
- 输入：`schema.json` 路径
- 输出：扁平化路径树 `[{path, type, is_leaf}]`
- 双形态兼容：标准 JSON Schema / 纯数据形状

**模拟引擎（SimulationEngine）**
- 系统提示词内嵌 2–3 个 few-shot 命令样例
- 输出解析器支持重试（最多 2 次）
- UI 文案统一为"技术验证对话"

**向量库（VectorDB）**
- 启动时尝试加载 `vec0` 扩展，失败则静默降级到 NumPy
- 降级模式下暴力检索仍可用

## 5. 技术选型

| 模块 | 选型 | 版本/规格 | 核心理由 |
|:-----|:-----|:----------|:---------|
| 编程语言 | Python | 3.10+ | AI 及数据科学生态最成熟，打包工具链完善 |
| GUI 框架 | PySide6 | 6.6+ | Qt 官方 Python 绑定，功能强大，LGPL 许可证友好 |
| AI 推理引擎 | llama-cpp-python | 0.2.77+ | 直接内嵌 GGUF 模型，无外部服务依赖 |
| 默认语言模型 | Qwen2.5-1.5B-Instruct-GGUF（Q4_K_M） | ~0.9 GB | 通用指令微调，兼顾角色扮演对话与代码解释（F4 模拟 + F7 解释） |
| 可选升级模型 | Qwen2.5-3B-Instruct-GGUF（Q4_K_M） | ~1.8 GB | 用户可选下载，提升错误解释质量 |
| 向量数据库 | sqlite-vec | 0.1.0+ | SQLite 原生向量扩展，社区活跃，零配置（Alex Garcia 维护） |
| 向量检索降级 | NumPy（暴力余弦） | — | sqlite-vec 加载失败时自动降级，确保 RAG 不失效 |
| 数据库驱动 | Python sqlite3（内置） | — | 标准库，无额外二进制依赖 |
| YAML 解析 | PyYAML | 6.0+ | Python 生态标准库 |
| EJS 检查 | 纯 Python 自实现（`ejs_parser.py`） | — | 彻底消除 Node.js 依赖；定义静态子集边界（固定写法可提取，动态表达式仅提示） |
| MVU 命令检查 | 纯 Python 自实现（`static_checker.py`） | — | 支持 `<!-- mvu: -->` 注释与 `<UpdateVariable>` + JSON Patch（RFC 6902）两种真实卡格式；JSON Pointer 路径映射到 schema 路径树做联动校验 |
| Schema 解析 | 主推 schema.json（双形态兼容：标准 JSON Schema / 纯数据形状）；schema.ts 仅降级文本扫描 | — | 避免引入 TS AST 解析器（tree-sitter/tsc），保持轻量 |
| ZIP 处理 | zipfile（内置） | — | 标准库 |
| 打包工具 | PyInstaller | 6.0+ | 快速打包为单 EXE，核心包目标 ≤ 200MB（模型外置） |
| 日志 | logging（内置） | — | 标准库 |

## 6. 数据库设计

### 6.1 项目数据库（`:memory:` 或 `./cache/项目名.db`）

用于存储当前扫描/模拟会话的临时数据。

#### 表 `static_errors`（静态检查错误记录）

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER | 主键 |
| error_id | TEXT | 唯一标识，如 EJS-001 |
| level | TEXT | Lv.1 / Lv.2 / Lv.3 / Lv.4 |
| category | TEXT | EJS / MVU / 联动 |
| file_path | TEXT | 相对路径（如 `世界书/index.yaml`） |
| line_number | INTEGER | 行号（可空） |
| path | TEXT | 变量路径（仅当 `is_static=True` 时由 EJS 解析器提供） |
| message | TEXT | 错误描述 |
| suggestion | TEXT | 修复建议 |
| auto_fixable | INTEGER | 0 / 1 |
| fix_preview | TEXT | 修复预览文本 |
| ai_explanation | TEXT | LLM 生成的根因分析（可空） |
| status | TEXT | pending / fixed / ignored |
| is_static | INTEGER | 1 表示路径经过静态子集验证；0 表示仅为文本提示 |

#### 表 `simulation_rounds`（模拟对话轮次记录）

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER | 主键 |
| round_number | INTEGER | 轮次编号 |
| user_input | TEXT | 用户输入（或自动生成） |
| ai_raw_output | TEXT | AI 原始回复文本 |
| parsed_commands | TEXT | JSON 数组，解析出的 MVU 命令列表 |
| ejs_rendered | TEXT | 本轮渲染后的世界书文本 |
| errors | TEXT | JSON 数组，本轮异常记录 |
| warnings | TEXT | JSON 数组，本轮警告记录 |
| parse_attempts | INTEGER | 命令解析重试次数 |
| created_at | TIMESTAMP | 时间戳 |

#### 表 `state_snapshots`（变量状态快照 — 时间旅行用）

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER | 主键 |
| round_id | INTEGER | 关联 `simulation_rounds.id` |
| stat_data | TEXT | JSON 格式的完整变量快照 |
| changed_paths | TEXT | JSON 数组，本轮发生变化的路径列表 |

#### 表 `schema_cache`（Schema 路径树缓存）

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER | 主键 |
| path | TEXT | 唯一，如 `主角.能力面板.*`（`*` 表示动态键） |
| type | TEXT | string / number / boolean / object / array |
| is_leaf | INTEGER | 1 表示叶子节点（非嵌套对象） |
| parent_path | TEXT | 父路径（用于树形展现） |
| source | TEXT | 来源：json_schema / data_shape / text_fallback |

#### 表 `file_index`（文件索引 / 增量扫描）

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER | 主键 |
| file_path | TEXT | 唯一，相对路径 |
| file_type | TEXT | worldbook / script / interface / schema |
| content_hash | TEXT | SHA-256 哈希，用于增量变更检测 |
| last_scanned | TIMESTAMP | 最后扫描时间 |

#### 索引

```sql
CREATE INDEX idx_errors_level ON static_errors(level);
CREATE INDEX idx_errors_status ON static_errors(status);
CREATE INDEX idx_errors_path ON static_errors(path);
CREATE INDEX idx_snapshots_round ON state_snapshots(round_id);
CREATE INDEX idx_schema_parent ON schema_cache(parent_path);
```

### 6.2 知识库数据库（`%APPDATA%/MvuEjsLinter/knowledge.db`）

持久化存储 RAG 知识库，包含向量索引。

#### 表 `knowledge_chunks`（知识块 + 向量）

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER | 主键 |
| chunk_id | TEXT | 唯一标识，如 KB-001 |
| source_type | TEXT | docs / error_pattern / code_sample / api_ref |
| source_path | TEXT | 来源文件/URL（可空） |
| title | TEXT | 文档标题 |
| content | TEXT | 文档块原始文本 |
| embedding | BLOB | 向量数据（由 sqlite-vec 管理） |
| created_at | TIMESTAMP | 时间戳 |

#### 表 `error_patterns`（常见错误模式 — 快速匹配）

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER | 主键 |
| pattern_name | TEXT | 如 `ejs_unclosed_tag` |
| error_level | TEXT | Lv.1 ~ Lv.4 |
| regex_pattern | TEXT | 正则匹配表达式 |
| description | TEXT | 错误描述 |
| fix_suggestion | TEXT | 修复建议文本 |
| priority | INTEGER | 匹配优先级（越大越优先） |
| category | TEXT | EJS / MVU / 联动 |

#### 表 `knowledge_tags` & `knowledge_chunk_tags`（标签分类）

```sql
CREATE TABLE knowledge_tags (
    id INTEGER PRIMARY KEY,
    tag_name TEXT UNIQUE NOT NULL
);

CREATE TABLE knowledge_chunk_tags (
    chunk_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    FOREIGN KEY (chunk_id) REFERENCES knowledge_chunks(chunk_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES knowledge_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (chunk_id, tag_id)
);
```

#### 初始种子数据要求

`vector_db.py` 初始化后 `SELECT count(*) FROM knowledge_chunks > 0`（内置 EJS 语法摘要、MVU 命令格式、常见错误模式）。

## 7. 开发阶段

| 阶段 | 版本 | 内容 |
|:-----|:-----|:-----|
| **Phase 0** ✅ | 基础库 | 4 核心模块 + CLI + 单元测试（已完成验收） |
| Phase 1 | v0.1 | GUI + ZIP 导入 + EJS 检查 + 报告 |
| Phase 2 | v0.2 | 完整静态检查 + 自动修复 + 导出 |
| Phase 3 | v0.3 | 模拟对话 + 日志 + 快照 |
| Phase 4 | v0.4 | 动态定位 + 时间旅行 |
| Phase 5 | v1.0 | LLM + RAG + 错误解释 |
| Phase 6 | v1.1 | 打包发布 + 文档 |

## 8. 功能清单

| 功能 | 描述 | 阶段 |
|:-----|:-----|:-----|
| F1 | ZIP 导入与项目结构识别 | Phase 1 |
| F2 | 静态检查（EJS 标签 + MVU 路径 + 联动） | Phase 1–2 |
| F3 | 检查报告展示与导出 | Phase 1–2 |
| F4 | 模拟对话引擎（技术验证） | Phase 3 |
| F5 | 日志追踪与变量快照（时间旅行） | Phase 3–4 |
| F6 | 动态定位器 | Phase 4 |
| F7 | AI 错误解释 + RAG 知识库 | Phase 5 |
| F8 | 打包发布 | Phase 6 |

## 9. 风险与应对措施

| 风险 | 影响 | 概率 | 缓解措施 |
|:-----|:-----|:-----|:---------|
| sqlite-vec 扩展打包失败 | RAG 不可用 | 中 | 内置 NumPy 降级路径；Phase 1 中期即做打包验证，不拖到后期 |
| 1.5B 模型模拟对话质量低 | F4 体验差 | 中 | 预期管理（UI 写"技术验证"）；系统提示词强约束 + few-shot；提供 3B 可选升级 |
| schema.json 双形态解析误判 | 路径树不准 | 低 | 对无法识别的形态输出警告并走降级模式，报告中标注"未完全解析" |
| EJS 静态子集边界漏报 | 部分变量路径未检查 | 中 | 只对 `is_static=True` 做联动报错，其余仅统计并提示"无法静态分析，请人工确认" |
| PyInstaller 打包体积超 200MB | 分发不便 | 低 | 模型外置；核心库剥离不必要的依赖（如跳过 matplotlib/scipy）；接受 200MB 基线 |

---

## 附录 A：模型下载源与推荐

| 模型 | 参数量 | 量化格式 | 下载源 | 用途 |
|:-----|:-------|:---------|:-------|:-----|
| Qwen2.5-1.5B-Instruct（默认） | 15亿 | Q4_K_M | HuggingFace / ModelScope | F4 模拟对话 + F7 错误解释 |
| Qwen2.5-3B-Instruct（可选升级） | 30亿 | Q4_K_M | HuggingFace | 高质量错误解释（用户手动下载切换） |

**首次启动行为：**

1. 应用自动检测 `%APPDATA%/MvuEjsLinter/models/` 目录。
2. 若无模型文件，弹出下载窗口（默认勾选 1.5B），支持后台下载 + 断点续传。
3. 下载完成后自动加载。

## 附录 B：原生扩展打包验证（关键）

以下二进制文件需在 Phase 1 中期（GUI 空壳打包验证）确认收集：

| 扩展 | 文件（Windows） | 文件（Linux/macOS） | PyInstaller 处理方式 |
|:-----|:----------------|:--------------------|:---------------------|
| sqlite-vec | `vec0.dll` | `vec0.so` | `--add-binary` 或 datas 收集，确保与 sqlite3 同目录 |
| llama-cpp-python | `llama.dll` | `libllama.so` | 由 llama-cpp-python wheel 自带，需设置 `--hidden-import=llama_cpp`，并确保 `_ctypes` 能找到 |

**验证脚本（打包后运行）：**

```python
# 测试 sqlite-vec 加载
import sqlite3
conn = sqlite3.connect(":memory:")
conn.enable_load_extension(True)
conn.load_extension("vec0")  # 不抛异常即为成功

# 测试 llama-cpp 加载
from llama_cpp import Llama
llm = Llama(model_path="dummy.gguf", n_ctx=128)  # 仅测试库加载，不实际跑
```

若加载失败，`vector_db.py` 自动降级到 NumPy 暴力检索（知识库 ≤ 500 条时完全可用）。

## 附录 C：开发环境配置

```bash
# 基础依赖（移除 node / ejs-lint）
pip install PySide6 llama-cpp-python PyYAML numpy

# 向量库（sqlite-vec 预编译包）
pip install sqlite-vec

# 打包工具
pip install pyinstaller

# 测试框架
pip install pytest pytest-cov
```

## 附录 D：目录结构规范

```
MVU_Lint/
├── src/
│   ├── __main__.py              # CLI 入口 (python -m mvu_lint scan)
│   ├── app.py                   # GUI 主入口
│   ├── controllers/             # 应用控制器
│   ├── views/                   # PySide6 界面
│   ├── core/
│   │   ├── ejs_parser.py        # 纯 Python EJS 检查（静态子集边界已定义）
│   │   ├── schema_loader.py     # 双形态 schema.json 读取器
│   │   ├── project_scanner.py   # ZIP 解压 + 目录识别 + file_index 写入
│   │   ├── static_checker.py    # 静态检查总控
│   │   ├── simulation_engine.py # 模拟对话引擎（含降级解析器）
│   │   └── debugger.py          # 动态定位器
│   ├── db/
│   │   ├── database.py          # SQLite 连接管理
│   │   └── vector_db.py         # sqlite-vec + NumPy 降级路径
│   ├── knowledge/
│   │   └── seed_data.py         # 默认知识库种子数据
│   └── utils/
│       ├── logger.py
│       └── exceptions.py
├── tests/
│   ├── test_ejs_parser.py
│   ├── test_schema_loader.py
│   ├── test_project_scanner.py
│   └── test_vector_db.py
├── resources/                   # 图标、样式
├── build.spec                   # PyInstaller 配置
└── requirements.txt
```
