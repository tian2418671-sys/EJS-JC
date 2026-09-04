"""Scan all real cards in 数据库/ to survey real-world syntax patterns.

Output is a JSON-ish text summary used to drive algorithm optimization.
"""
import sys
import re
import json
from collections import Counter
from pathlib import Path

sys.path.insert(0, r"E:\AI\酒馆工具\JSK管理APP\方案1")
from mvu_lint.core.card_loader import load_card, extract_schema_dict
from mvu_lint.core.schema_loader import SchemaLoader

DB = Path(r"E:\AI\酒馆工具\JSK管理APP\方案1\数据库")

# ── patterns ──────────────────────────────────────────────────────
GETVAR_RE = re.compile(r"\bgetvar\s*\(\s*['\"]([^'\"]+)['\"]")
SETVAR_RE = re.compile(r"\bsetvar\s*\(")
INCVAR_RE = re.compile(r"\bincvar\s*\(")
DECVAR_RE = re.compile(r"\bdecvar\s*\(")
GETWI_RE = re.compile(r"\bgetwi\s*\(")
ACTIVEWI_RE = re.compile(r"\bactivewi\s*\(")
TAG_RE = re.compile(r"<%(=|[-_#]?)")
DECOR_RE = re.compile(r"^@@[a-z_]+", re.M)
INJECT_RE = re.compile(r"@INJECT\b", re.M)
MVU_COMMENT_RE = re.compile(r"<!--\s*[Mm][Vv][Uu]\s*:")
UPDVAR_RE = re.compile(r"<UpdateVariable\b")
INITVAR_TITLE_RE = re.compile(r"#\s*变量初始值")
INITVAR_TAG_RE = re.compile(r"\[InitialVariables\]|\[initvar\]|@@initial_variables")

tag_names = {"": "script", "_": "script_", "=": "output", "-": "output_raw", "#": "comment"}

for png in sorted(DB.glob("*.png")):
    print("=" * 78)
    print("CARD:", png.name)
    try:
        card = load_card(str(png))
    except Exception as exc:
        print("  LOAD ERROR:", exc)
        continue
    print(f"  blocks={len(card.blocks)}  spec={card.spec}")

    # schema
    sd = extract_schema_dict(card)
    if sd is not None:
        si = SchemaLoader().load_from_dict(sd)
        print(f"  schema: {si.form} paths={len(si.paths)} leaves={len(si.get_leaf_paths())}")
    else:
        print("  schema: NONE (no # 变量初始值 block)")

    # aggregate over blocks
    getvar_paths = Counter()
    getvar_forms = Counter()   # stat_data / [0] / plain
    tag_usage = Counter()
    decor_usage = Counter()
    func_usage = Counter()
    mvu_formats = Counter()
    initvar_marks = Counter()
    for b in card.blocks:
        c = b.content
        for m in GETVAR_RE.finditer(c):
            p = m.group(1)
            getvar_paths[p] += 1
            if p.startswith("stat_data."):
                getvar_forms["stat_data."] += 1
                if re.search(r"\[\d+\]$", p):
                    getvar_forms["stat_data.[0]"] += 1
                else:
                    getvar_forms["stat_data.(无[0])"] += 1
            elif re.search(r"\[\d+\]", p):
                getvar_forms["非stat_data带[数字]"] += 1
            else:
                getvar_forms["纯路径(无前缀)"] += 1
        for m in TAG_RE.finditer(c):
            tag_usage[tag_names.get(m.group(1), m.group(1))] += 1
        for m in DECOR_RE.finditer(c):
            decor_usage[m.group(0)] += 1
        if INJECT_RE.search(c):
            func_usage["@INJECT"] += 1
        if MVU_COMMENT_RE.search(c):
            mvu_formats["<!-- mvu: -->"] += 1
        if UPDVAR_RE.search(c):
            mvu_formats["<UpdateVariable>"] += 1
        if "[mvu_update]" in c:
            mvu_formats["[mvu_update]块"] += 1
        if INITVAR_TITLE_RE.search(c):
            initvar_marks["# 变量初始值"] += 1
        if INITVAR_TAG_RE.search(c):
            initvar_marks["[InitialVariables]/@@initial"] += 1
        for fn, name in [(SETVAR_RE, "setvar"), (INCVAR_RE, "incvar"),
                         (DECVAR_RE, "decvar"), (GETWI_RE, "getwi"),
                         (ACTIVEWI_RE, "activewi")]:
            if fn.search(c):
                func_usage[name] += 1

    print(f"  getvar总数={sum(getvar_paths.values())} 唯一路径={len(getvar_paths)}")
    print("  getvar形态:", dict(getvar_forms))
    print("  标签:", dict(tag_usage))
    print("  装饰器:", dict(decor_usage) if decor_usage else "(无)")
    print("  函数:", dict(func_usage) if func_usage else "(无)")
    print("  MVU格式:", dict(mvu_formats) if mvu_formats else "(无)")
    print("  initvar标记:", dict(initvar_marks) if initvar_marks else "(无)")
    if getvar_paths:
        print("  示例路径:")
        for p, n in getvar_paths.most_common(8):
            print(f"    {n:3d}  {p}")
