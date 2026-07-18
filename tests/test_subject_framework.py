"""SubjectService 跨学科框架逻辑单元测试

测试目标：
- list_subjects 返回4个学科，包含数学/英语/物理/语文
- get_subject 获取学科配置，未知学科默认返回数学配置
- get_error_cause_labels 数学6个错因标签、英语4个错因标签
- get_question_types 数学4个题型、物理4个题型
- get_knowledge_graph 返回 KnowledgeGraph 实例
- get_knowledge_graph 缓存机制：连续调用返回同一实例
- clear_cache 清空缓存后重新创建
"""
import pytest

from app.subject_framework import SubjectService, SUBJECT_REGISTRY
from app.knowledge_graph import KnowledgeGraph


# ===== list_subjects 测试 =====


def test_list_subjects_count():
    """返回4个学科"""
    subjects = SubjectService.list_subjects()
    assert len(subjects) == 4


def test_list_subjects_contains_math():
    """包含数学"""
    subjects = SubjectService.list_subjects()
    names = [s["name"] for s in subjects]
    assert "数学" in names


def test_list_subjects_contains_english():
    """包含英语"""
    subjects = SubjectService.list_subjects()
    names = [s["name"] for s in subjects]
    assert "英语" in names


def test_list_subjects_contains_physics():
    """包含物理"""
    subjects = SubjectService.list_subjects()
    names = [s["name"] for s in subjects]
    assert "物理" in names


def test_list_subjects_contains_chinese():
    """包含语文"""
    subjects = SubjectService.list_subjects()
    names = [s["name"] for s in subjects]
    assert "语文" in names


# ===== get_subject 测试 =====


def test_get_subject_math():
    """获取数学配置"""
    config = SubjectService.get_subject("math")
    assert config["name"] == "数学"
    assert "knowledge_graph_class" in config
    assert "knowledge_graph_data" in config
    assert "question_types" in config
    assert "error_cause_labels" in config


def test_get_subject_english():
    """获取英语配置"""
    config = SubjectService.get_subject("english")
    assert config["name"] == "英语"
    assert config["knowledge_graph_class"] == KnowledgeGraph


def test_get_subject_unknown():
    """未知学科默认返回数学配置"""
    config = SubjectService.get_subject("nonexistent_subject")
    assert config["name"] == "数学"


# ===== get_error_cause_labels 测试 =====


def test_get_error_cause_labels_math():
    """数学错因标签6个"""
    labels = SubjectService.get_error_cause_labels("math")
    assert isinstance(labels, list)
    assert len(labels) == 6


def test_get_error_cause_labels_english():
    """英语错因标签4个"""
    labels = SubjectService.get_error_cause_labels("english")
    assert isinstance(labels, list)
    assert len(labels) == 4


# ===== get_question_types 测试 =====


def test_get_question_types_math():
    """数学题型4个"""
    qtypes = SubjectService.get_question_types("math")
    assert isinstance(qtypes, list)
    assert len(qtypes) == 4


def test_get_question_types_physics():
    """物理题型4个"""
    qtypes = SubjectService.get_question_types("physics")
    assert isinstance(qtypes, list)
    assert len(qtypes) == 4


# ===== get_knowledge_graph 测试 =====


def test_get_knowledge_graph_math(clean_subject_cache):
    """获取数学知识图谱（KnowledgeGraph实例）"""
    kg = SubjectService.get_knowledge_graph("math")
    assert isinstance(kg, KnowledgeGraph)
    nodes = kg.get_all_nodes()
    assert len(nodes) > 0


def test_get_knowledge_graph_english(clean_subject_cache):
    """获取英语知识图谱"""
    kg = SubjectService.get_knowledge_graph("english")
    assert isinstance(kg, KnowledgeGraph)
    nodes = kg.get_all_nodes()
    assert len(nodes) > 0


def test_get_knowledge_graph_cache(clean_subject_cache):
    """连续调用返回同一实例（缓存机制）"""
    kg1 = SubjectService.get_knowledge_graph("math")
    kg2 = SubjectService.get_knowledge_graph("math")
    assert kg1 is kg2


# ===== clear_cache 测试 =====


def test_clear_cache(clean_subject_cache):
    """清空缓存后重新创建"""
    kg1 = SubjectService.get_knowledge_graph("math")
    SubjectService.clear_cache()
    kg2 = SubjectService.get_knowledge_graph("math")
    assert kg1 is not kg2
