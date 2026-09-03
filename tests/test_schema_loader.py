"""Unit tests for SchemaLoader."""
import pytest
from mvu_lint.core.schema_loader import SchemaLoader


def test_json_schema_form():
    """Standard JSON Schema format should be parsed correctly."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "主角": {
                "type": "object",
                "properties": {
                    "好感度": {"type": "number"},
                    "姓名": {"type": "string"},
                }
            }
        }
    }
    loader = SchemaLoader()
    info = loader.load_from_dict(schema, "test.json")
    assert info.form == "json_schema"
    paths = info.get_path_set()
    assert "主角" in paths
    assert "主角.好感度" in paths
    assert "主角.姓名" in paths
    leaf_paths = info.get_leaf_paths()
    assert "主角.好感度" in leaf_paths
    assert "主角" not in leaf_paths


def test_data_shape_form():
    """Pure data shape (Zod direct output) should be parsed correctly."""
    data = {
        "主角": {
            "好感度": 0,
            "姓名": "测试",
            "物品栏": [
                {"名称": "长剑", "数量": 1}
            ]
        }
    }
    loader = SchemaLoader()
    info = loader.load_from_dict(data, "init.json")
    assert info.form == "data_shape"
    paths = info.get_path_set()
    assert "主角.好感度" in paths
    assert "主角.姓名" in paths
    assert "主角.物品栏" in paths
    assert "主角.物品栏.*.名称" in paths
    assert "主角.物品栏.*.数量" in paths


def test_array_wildcard_json_schema():
    """Array elements in JSON Schema should use * placeholder."""
    schema = {
        "type": "object",
        "properties": {
            "列表": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "值": {"type": "number"}
                    }
                }
            }
        }
    }
    loader = SchemaLoader()
    info = loader.load_from_dict(schema, "test.json")
    paths = info.get_path_set()
    assert "列表" in paths
    assert "列表.*.值" in paths


def test_boolean_before_integer():
    """Boolean values should not be misclassified as numbers."""
    data = {
        "flag": True,
        "count": 42,
    }
    loader = SchemaLoader()
    info = loader.load_from_dict(data, "test.json")
    types = info.get_path_types()
    assert types["flag"] == "boolean"
    assert types["count"] == "number"
