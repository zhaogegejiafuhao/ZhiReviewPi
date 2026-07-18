"""WritingKnowledgeGraph 作文分层归因逻辑单元测试

测试目标：
- map_error_cause_to_nodes: 写作错因标签 → DAG二级节点ID列表
- map_error_cause_to_dimension: 写作错因标签 → 一级维度
- get_error_cause_suggestion: 写作错因标签 → 改进建议
- 写作知识图谱节点数量与雷达维度
- WritingKnowledgeGraph 继承关系
"""
from app.writing_graph import (
    WritingKnowledgeGraph,
    WRITING_ERROR_CAUSE_MAPPING,
)
from app.knowledge_graph import KnowledgeGraph


# ===== map_error_cause_to_nodes 测试 =====


def test_map_error_cause_to_nodes_sucai():
    """'素材匮乏' → ['topic_understanding', 'theme_depth']"""
    nodes = WritingKnowledgeGraph.map_error_cause_to_nodes("素材匮乏")
    assert nodes == ["topic_understanding", "theme_depth"]


def test_map_error_cause_to_nodes_luoji():
    """'逻辑断层' → ['opening', 'paragraph_transition', 'ending']"""
    nodes = WritingKnowledgeGraph.map_error_cause_to_nodes("逻辑断层")
    assert nodes == ["opening", "paragraph_transition", "ending"]


def test_map_error_cause_to_nodes_xiuci():
    """'修辞单一' → ['vocabulary', 'rhetoric', 'sentence_variety']"""
    nodes = WritingKnowledgeGraph.map_error_cause_to_nodes("修辞单一")
    assert nodes == ["vocabulary", "rhetoric", "sentence_variety"]


def test_map_error_cause_to_nodes_pianti():
    """'偏题跑题' → ['topic_understanding', 'thesis_extraction']"""
    nodes = WritingKnowledgeGraph.map_error_cause_to_nodes("偏题跑题")
    assert nodes == ["topic_understanding", "thesis_extraction"]


def test_map_error_cause_to_nodes_shuxie():
    """'书写潦草' → ['handwriting', 'page_neatness']"""
    nodes = WritingKnowledgeGraph.map_error_cause_to_nodes("书写潦草")
    assert nodes == ["handwriting", "page_neatness"]


def test_map_error_cause_to_nodes_unknown():
    """未知错因 → []"""
    nodes = WritingKnowledgeGraph.map_error_cause_to_nodes("不存在的错因")
    assert nodes == []


# ===== map_error_cause_to_dimension 测试 =====


def test_map_error_cause_to_dimension_all():
    """所有5个错因映射到正确维度"""
    assert WritingKnowledgeGraph.map_error_cause_to_dimension("素材匮乏") == "theme"
    assert WritingKnowledgeGraph.map_error_cause_to_dimension("逻辑断层") == "structure"
    assert WritingKnowledgeGraph.map_error_cause_to_dimension("修辞单一") == "expression"
    assert WritingKnowledgeGraph.map_error_cause_to_dimension("偏题跑题") == "theme"
    assert WritingKnowledgeGraph.map_error_cause_to_dimension("书写潦草") == "writing_norm"


def test_map_error_cause_to_dimension_unknown():
    """未知错因 → None"""
    result = WritingKnowledgeGraph.map_error_cause_to_dimension("不存在的错因")
    assert result is None


# ===== get_error_cause_suggestion 测试 =====


def test_get_error_cause_suggestion_sucai():
    """'素材匮乏'有建议且包含'素材积累'"""
    suggestion = WritingKnowledgeGraph.get_error_cause_suggestion("素材匮乏")
    assert isinstance(suggestion, str)
    assert "素材积累" in suggestion


def test_get_error_cause_suggestion_unknown():
    """未知错因 → 默认建议"""
    suggestion = WritingKnowledgeGraph.get_error_cause_suggestion("不存在的错因")
    assert isinstance(suggestion, str)
    assert len(suggestion) > 0


# ===== 写作知识图谱结构测试 =====


def test_writing_knowledge_graph_nodes():
    """图谱有合理数量的节点"""
    wkg = WritingKnowledgeGraph()
    nodes = wkg.get_all_nodes()
    # root + 4个维度 + 11个子能力 = 16
    assert len(nodes) == 16


def test_writing_knowledge_graph_radar_dimensions():
    """雷达维度有4个（审题立意、结构组织、语言表达、书写规范）"""
    wkg = WritingKnowledgeGraph()
    dims = wkg.get_writing_radar_dimensions()
    assert len(dims) == 4
    dim_names = {d["name"] for d in dims}
    assert dim_names == {"审题立意", "结构组织", "语言表达", "书写规范"}


def test_writing_knowledge_graph_inherits_kg():
    """WritingKnowledgeGraph 是 KnowledgeGraph 的子类"""
    wkg = WritingKnowledgeGraph()
    assert isinstance(wkg, KnowledgeGraph)
    assert issubclass(WritingKnowledgeGraph, KnowledgeGraph)
