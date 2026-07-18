"""pytest 共享 fixtures 与全局配置"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 确保项目根目录在 sys.path 中（让 from app.xxx import yyy 可用）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_knowledge_graph():
    """提供一个 mock 的 KnowledgeGraph 实例

    用于测试中需要 KnowledgeGraph 但不想依赖真实数据的场景。
    返回的 mock 对象预设了常用方法的返回值。
    """
    kg = MagicMock()
    kg.get_node.return_value = {"id": "test_node", "name": "测试节点", "level": 2}
    kg.get_radar_dimensions.return_value = [
        {"id": "dim1", "name": "维度1"},
        {"id": "dim2", "name": "维度2"},
    ]
    kg.get_all_nodes.return_value = {
        "test_node": {"id": "test_node", "name": "测试节点", "level": 2},
    }
    kg.get_children.return_value = []
    kg.get_ancestors.return_value = []
    return kg


@pytest.fixture
def clean_subject_cache():
    """确保 SubjectService 缓存在测试前后都是空的"""
    from app.subject_framework import SubjectService
    SubjectService.clear_cache()
    yield
    SubjectService.clear_cache()
