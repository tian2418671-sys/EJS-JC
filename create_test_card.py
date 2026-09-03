"""Create a test character card ZIP for CLI end-to-end validation."""
import json
import zipfile
from pathlib import Path

zip_path = Path(__file__).parent / "test_card.zip"

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    # schema.json (pure data shape form)
    zf.writestr("schema.json", json.dumps({
        "主角": {
            "好感度": 0,
            "姓名": "测试",
            "状态": "正常",
            "物品栏": [
                {"名称": "长剑", "数量": 1}
            ]
        }
    }, ensure_ascii=False))

    # Worldbook entry with clean EJS
    zf.writestr("世界书/entry_clean.json", json.dumps({
        "content": "<%= stat_data.主角.好感度 %> 点好感度"
    }, ensure_ascii=False))

    # Worldbook entry with unescaped output (Lv.4)
    zf.writestr("世界书/entry_unsafe.json", json.dumps({
        "content": "<%- data.主角.状态 %>"
    }, ensure_ascii=False))

    # Worldbook entry with unclosed tag (Lv.1)
    zf.writestr("世界书/entry_broken.json", json.dumps({
        "content": "<%= stat_data.主角.姓名\n"
    }, ensure_ascii=False))

    # Worldbook entry with mvu.get pattern
    zf.writestr("世界书/entry_mvu.json", json.dumps({
        "content": "当前好感：<%= mvu.get('主角.好感度') %>"
    }, ensure_ascii=False))

    # Script file
    zf.writestr("脚本/helper.js", "function updateStat() { return true; }")

    # Interface file
    zf.writestr("界面/ui.html", "<div>界面</div>")

print(f"Test card created: {zip_path} ({zip_path.stat().st_size} bytes)")
