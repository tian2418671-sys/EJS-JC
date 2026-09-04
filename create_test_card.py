"""Create a test NPC role card (JSON, chara_card_v2) for CLI e2e validation."""
import json
from pathlib import Path

json_path = Path(__file__).parent / "test_card.json"

card = {
    "spec": "chara_card_v2",
    "spec_version": "2.0",
    "name": "测试角色卡",
    "data": {
        "name": "测试角色卡",
        "description": "用于 CLI 端到端验证的测试角色卡",
        "first_mes": "你好，我是测试角色。",
        "character_version": "1.0",
        "extensions": {},
        "character_book": {
            "name": "测试世界书",
            "entries": [
                {
                    "id": "entry_clean",
                    "keys": ["测试"],
                    "comment": "干净条目",
                    "content": "<%= stat_data.主角.好感度 %> 点好感度",
                    "constant": False,
                    "enabled": True,
                },
                {
                    "id": "entry_unsafe",
                    "keys": ["风险"],
                    "comment": "未转义输出",
                    "content": "<%- data.主角.状态 %>",
                    "constant": False,
                    "enabled": True,
                },
                {
                    "id": "entry_broken",
                    "keys": ["损坏"],
                    "comment": "未闭合标签",
                    "content": "<%= stat_data.主角.姓名\n",
                    "constant": False,
                    "enabled": True,
                },
                {
                    "id": "entry_mvu",
                    "keys": ["好感"],
                    "comment": "MVU 命令",
                    "content": "当前好感：<%= mvu.get('主角.好感度') %>",
                    "constant": False,
                    "enabled": True,
                },
                {
                    "id": "entry_initvar",
                    "keys": ["初始值"],
                    "comment": "变量初始值（Schema 来源）",
                    "content": (
                        "# 变量初始值（由 mvu 在开始时读取）\n"
                        "主角:\n"
                        "  好感度: 0\n"
                        "  姓名: 测试\n"
                        "  状态: 正常\n"
                        "  物品栏:\n"
                        "    - 名称: 长剑\n"
                        "      数量: 1\n"
                    ),
                    "constant": False,
                    "enabled": True,
                },
            ],
        },
    },
}

json_path.write_text(
    json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"Test card created: {json_path} ({json_path.stat().st_size} bytes)")
