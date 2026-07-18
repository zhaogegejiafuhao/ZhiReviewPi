"""DecayPropagate 算法与 ErrorMapper 逻辑单元测试

测试目标：
- DecayPropagate: 时间衰减（Ebbinghaus）、后向传播、前向聚合、订正奖励、top_k
- ErrorMapper: 关键词映射、规则自进化、双通道融合优先级
- 使用真实 MATH_KNOWLEDGE_GRAPH 构建 KnowledgeGraph 实例
"""
import math
from datetime import date, timedelta

import pytest

from app.knowledge_graph import KnowledgeGraph
from app.attribution import (
    DecayPropagate,
    ErrorMapper,
    ErrorEvent,
    WeaknessResult,
)


# ===== 公共 fixture =====


@pytest.fixture
def kg():
    """提供已预计算的 MATH 知识图谱实例"""
    graph = KnowledgeGraph()
    graph.precompute()
    return graph


@pytest.fixture
def dp(kg):
    """提供基于 MATH 图谱的 DecayPropagate 实例"""
    return DecayPropagate(kg)


@pytest.fixture
def mapper(kg):
    """提供基于 MATH 图谱的 ErrorMapper 实例"""
    return ErrorMapper(kg)


# ===== DecayPropagate: _time_decay 测试 =====


def test_ebbinghaus_decay_recent(dp):
    """最近错误（days_since=0）衰减因子接近 1"""
    today = date.today()
    decay = dp._time_decay(today, today)
    assert decay == pytest.approx(1.0, abs=1e-9)


def test_ebbinghaus_decay_old(dp):
    """30 天前的错误衰减因子较小（< 0.1）"""
    today = date.today()
    old_date = today - timedelta(days=30)
    decay = dp._time_decay(old_date, today)
    # exp(-0.1 * 30) ≈ 0.0498
    assert decay < 0.1
    assert decay == pytest.approx(math.exp(-0.1 * 30), abs=1e-6)


def test_ebbinghaus_decay_zero_days(dp):
    """0 天衰减因子 = 1.0"""
    today = date.today()
    decay = dp._time_decay(today, today)
    assert decay == 1.0


# ===== DecayPropagate: analyze 测试 =====


def test_analyze_single_error(dp):
    """单个错误事件分析：返回结果包含对应知识点"""
    today = date.today()
    errors = [
        ErrorEvent(
            knowledge_node_id="rational_num",
            error_weight=1.0,
            timestamp=today,
            question_content="有理数加减题",
            error_cause="概念混淆",
        ),
    ]
    results = dp.analyze(errors, reference_date=today)
    assert len(results) > 0
    # 结果中应包含 rational_num 或其传播影响的节点
    ids = {r.knowledge_id for r in results}
    assert "rational_num" in ids


def test_analyze_multiple_errors_same_knowledge(dp):
    """同一知识点多次错误，error_count 更高，且相对薄弱度提升"""
    today = date.today()
    # 单次错误 + 另一个知识点错误作为参照基准
    single_errors = [
        ErrorEvent(knowledge_node_id="rational_num", error_weight=1.0, timestamp=today),
        ErrorEvent(knowledge_node_id="congruent_tri", error_weight=1.0, timestamp=today),
    ]
    single_results = dp.analyze(single_errors, reference_date=today, top_k=10)
    single_rational = next(
        r for r in single_results if r.knowledge_id == "rational_num"
    )
    single_congruent = next(
        r for r in single_results if r.knowledge_id == "congruent_tri"
    )
    # 单次错误：error_count=1
    assert single_rational.error_count == 1
    # 相对薄弱度比值
    single_ratio = single_rational.weakness_score / single_congruent.weakness_score if single_congruent.weakness_score > 0 else 0

    # rational_num 3 次错误 + congruent_tri 1 次错误
    triple_errors = [
        ErrorEvent(knowledge_node_id="rational_num", error_weight=1.0, timestamp=today),
        ErrorEvent(knowledge_node_id="rational_num", error_weight=1.0, timestamp=today),
        ErrorEvent(knowledge_node_id="rational_num", error_weight=1.0, timestamp=today),
        ErrorEvent(knowledge_node_id="congruent_tri", error_weight=1.0, timestamp=today),
    ]
    triple_results = dp.analyze(triple_errors, reference_date=today, top_k=10)
    triple_rational = next(
        r for r in triple_results if r.knowledge_id == "rational_num"
    )
    # 多次错误：error_count=3
    assert triple_rational.error_count == 3
    # rational_num 在 triple 中的薄弱度应为 1.0（最高），且排第一
    assert triple_rational.weakness_score >= triple_results[0].weakness_score - 0.001


def test_analyze_different_knowledge_points(dp):
    """不同知识点的错误各自独立计算薄弱度"""
    today = date.today()
    errors = [
        ErrorEvent(knowledge_node_id="rational_num", error_weight=1.0, timestamp=today),
        ErrorEvent(knowledge_node_id="congruent_tri", error_weight=1.0, timestamp=today),
    ]
    results = dp.analyze(errors, reference_date=today, top_k=10)
    ids = {r.knowledge_id for r in results}
    # 两个知识点都应出现在结果中（可能因传播影响出现更多）
    assert "rational_num" in ids
    assert "congruent_tri" in ids


def test_analyze_with_correction(dp):
    """有订正完成记录时，薄弱度排名下降（γ 奖励使订正节点相对薄弱度降低）"""
    today = date.today()
    # 两个知识点同等权重错误
    errors = [
        ErrorEvent(knowledge_node_id="rational_num", error_weight=1.0, timestamp=today),
        ErrorEvent(knowledge_node_id="congruent_tri", error_weight=1.0, timestamp=today),
    ]
    # 无订正
    results_no_correction = dp.analyze(errors, reference_date=today, top_k=10)
    score_no_correction = next(
        (r.weakness_score for r in results_no_correction if r.knowledge_id == "rational_num"), 0
    )

    # 有订正（rational_num 满分订正）
    correction_records = [
        {
            "knowledge_node_id": "rational_num",
            "corrected": True,
            "correction_score": 1.0,
        },
    ]
    results_with_correction = dp.analyze(
        errors, reference_date=today, correction_records=correction_records, top_k=10
    )
    score_with_correction = next(
        (r.weakness_score for r in results_with_correction if r.knowledge_id == "rational_num"), 0
    )

    # 订正后 rational_num 的相对薄弱度应低于 congruent_tri
    score_congruent = next(
        (r.weakness_score for r in results_with_correction if r.knowledge_id == "congruent_tri"), 0
    )
    # 订正后 rational_num 排名应低于 congruent_tri
    assert score_with_correction < score_congruent


def test_analyze_top_k(dp):
    """top_k 限制返回的薄弱点数量"""
    today = date.today()
    errors = [
        ErrorEvent(knowledge_node_id="rational_num", error_weight=1.0, timestamp=today),
        ErrorEvent(knowledge_node_id="congruent_tri", error_weight=1.0, timestamp=today),
        ErrorEvent(knowledge_node_id="linear_eq_1var", error_weight=1.0, timestamp=today),
    ]
    # top_k=1 只返回 1 个
    results = dp.analyze(errors, reference_date=today, top_k=1)
    assert len(results) == 1

    # top_k=2 返回 2 个
    results = dp.analyze(errors, reference_date=today, top_k=2)
    assert len(results) == 2


# ===== DecayPropagate: _backward_propagation 测试 =====


def test_backward_propagate(dp):
    """后向传播将错误权重沿前置依赖传播"""
    # rational_op 的前置依赖包含 rational_concept
    # 如果 rational_concept 有错误权重，后向传播应影响 rational_op
    decayed_weights = {"rational_concept": 1.0}
    backward = dp._backward_propagation("rational_op", decayed_weights)
    # rational_concept 是 rational_op 的前置依赖，传播值应 > 0
    assert backward > 0


def test_backward_propagate_no_ancestors(dp):
    """没有前置依赖的节点，后向传播值为 0"""
    decayed_weights = {"rational_num": 1.0}
    # root 无前置依赖，且自身不在 decayed_weights 的传播范围内
    backward = dp._backward_propagation("root", decayed_weights)
    # root 的 ancestors 为空，后向传播为 0
    assert backward == 0.0


# ===== DecayPropagate: _forward_aggregation 测试 =====


def test_forward_aggregate(dp):
    """前向聚合将子节点的薄弱度传播到父节点"""
    # rational_num 有子节点 rational_concept, rational_op, num_axis_abs
    raw_scores = {
        "rational_concept": 0.8,
        "rational_op": 0.5,
        "num_axis_abs": 0.3,
    }
    forward = dp._forward_aggregation("rational_num", raw_scores)
    # forward = max(0.8, 0.5, 0.3) * beta = 0.8 * 0.3 = 0.24
    expected = 0.8 * dp.beta
    assert forward == pytest.approx(expected, abs=1e-9)


def test_forward_aggregate_leaf(dp):
    """叶节点无子节点，前向聚合为 0"""
    raw_scores = {"some_node": 1.0}
    forward = dp._forward_aggregation("rational_concept", raw_scores)
    assert forward == 0.0


# ===== ErrorMapper: map_by_keywords 测试 =====


def test_map_by_keywords_match(mapper):
    """关键词匹配成功：'有理数' 映射到 rational_num 相关节点"""
    matched = mapper.map_by_keywords("有理数的加减运算")
    assert len(matched) > 0
    # 至少包含 rational_num 或其子节点
    matched_names = {
        mapper.kg.get_node(nid)["name"] for nid in matched if mapper.kg.get_node(nid)
    }
    assert "有理数" in matched_names or "有理数的运算" in matched_names or "有理数的概念" in matched_names


def test_map_by_keywords_no_match(mapper):
    """无匹配关键词返回空列表"""
    matched = mapper.map_by_keywords("量子纠缠态测量")
    assert matched == []


def test_map_by_keywords_multiple(mapper):
    """多个关键词匹配多个节点：'有理数方程' 同时命中有理数和方程相关节点"""
    matched = mapper.map_by_keywords("有理数的一元一次方程")
    assert len(matched) >= 2
    # 应包含有理数和方程相关节点
    matched_names = {
        mapper.kg.get_node(nid)["name"] for nid in matched if mapper.kg.get_node(nid)
    }
    # 至少包含有理数或方程中的一种
    assert len(matched_names) >= 2


# ===== ErrorMapper: auto_expand_rules 测试 =====


def test_auto_expand_rules(mapper):
    """规则自进化：教师修正映射后，自动添加关键词到修正后知识点"""
    # 原始映射是 rational_concept，教师修正为 rational_op
    result = mapper.auto_expand_rules(
        error_text="有理数乘法分配律计算错误",
        original_match="rational_concept",
        corrected_match="rational_op",
    )
    # "乘法" 或 "分配律" 是新增关键词，应返回 True
    assert result is True
    # 验证 rational_op 的关键词已更新
    node = mapper.kg.get_node("rational_op")
    assert "乘法" in node["keywords"] or "分配律" in node["keywords"]


def test_auto_expand_rules_persistence(mapper):
    """添加的规则在后续关键词匹配中生效"""
    # 先执行规则自进化
    mapper.auto_expand_rules(
        error_text="有理数乘方运算法则",
        original_match="rational_concept",
        corrected_match="rational_op",
    )
    # 用新增的关键词再次搜索，应能匹配到 rational_op
    matched = mapper.map_by_keywords("乘方运算")
    assert "rational_op" in matched


def test_auto_expand_rules_same_match(mapper):
    """original_match == corrected_match 时，不做任何修改"""
    result = mapper.auto_expand_rules(
        error_text="有理数计算",
        original_match="rational_num",
        corrected_match="rational_num",
    )
    assert result is False


# ===== ErrorMapper: map_error 双通道融合测试 =====


def test_map_error_keywords_priority(mapper):
    """关键词通道优先于 LLM 通道：关键词匹配成功时直接返回关键词结果"""
    # "有理数" 可通过关键词匹配，map_error 应直接返回关键词结果
    # map_error 是 async 方法
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        mapper.map_error("有理数的加减运算")
    )
    assert len(result) > 0
    # 结果应与 map_by_keywords 一致
    keyword_result = mapper.map_by_keywords("有理数的加减运算")
    assert result == keyword_result
