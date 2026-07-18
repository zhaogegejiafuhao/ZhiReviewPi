"""GroupAnalysisService 小组协同分析逻辑测试

测试目标：
- _find_common_weak_points：共性薄弱点判定（阈值50%）
- _build_group_radar / _build_comparison_radar：小组雷达图聚合
- _generate_template_exercises：模板题生成（每个薄弱点2道，最多5个）
- _generate_group_suggestion：小组建议生成
- analyze_groups：完整集成测试（不依赖LLM）
"""
from datetime import date

import pytest

from app.group_service import (
    GroupAnalysisService,
    GroupWeakness,
    GroupComparisonResult,
    COMMON_WEAKNESS_RATIO,
    WEAKNESS_THRESHOLD,
)
from app.attribution import ErrorEvent, WeaknessResult


def make_error_event(kid, weight=1.0, ts=None):
    """构造 ErrorEvent"""
    return ErrorEvent(
        knowledge_node_id=kid,
        error_weight=weight,
        timestamp=ts or date(2025, 7, 1),
        question_content="测试题目",
        error_cause="计算粗心",
    )


def make_weakness(kid, name, score):
    """构造 WeaknessResult"""
    return WeaknessResult(
        knowledge_id=kid,
        knowledge_name=name,
        weakness_score=score,
    )


# ======================================================================
# _find_common_weak_points 测试
# ======================================================================


class TestFindCommonWeakPoints:
    """共性薄弱点判定"""

    def test_find_common_weak_points_above_threshold(self):
        """超过50%成员薄弱的知识点是共性薄弱点"""
        service = GroupAnalysisService()
        # 3个学生中2个薄弱 = 66.7% >= 50%
        result = service._find_common_weak_points(
            student_ids=["s1", "s2", "s3"],
            student_weaknesses={
                "s1": [make_weakness("rational_concept", "有理数的概念", 0.8)],
                "s2": [make_weakness("rational_concept", "有理数的概念", 0.6)],
                "s3": [],
            },
        )
        assert len(result) >= 1
        assert result[0]["knowledge_id"] == "rational_concept"
        assert result[0]["weakness_ratio"] > COMMON_WEAKNESS_RATIO

    def test_find_common_weak_points_below_threshold(self):
        """低于50%的知识点不是共性薄弱点"""
        service = GroupAnalysisService()
        # 3个学生中1个薄弱 = 33.3% < 50%
        result = service._find_common_weak_points(
            student_ids=["s1", "s2", "s3"],
            student_weaknesses={
                "s1": [make_weakness("rational_concept", "有理数的概念", 0.8)],
                "s2": [],
                "s3": [],
            },
        )
        assert result == []

    def test_find_common_weak_points_empty(self):
        """空学生列表返回空"""
        service = GroupAnalysisService()
        result = service._find_common_weak_points([], {})
        assert result == []


# ======================================================================
# _build_group_radar 测试
# ======================================================================


class TestBuildGroupRadar:
    """小组雷达图聚合"""

    def test_build_group_radar_normal(self):
        """正常聚合学生雷达图"""
        service = GroupAnalysisService()
        student_radars = {
            "s1": {"数与代数": 0.8, "图形与几何": 0.9},
            "s2": {"数与代数": 0.6, "图形与几何": 0.7},
        }
        radar = service._build_group_radar(student_radars)

        assert radar["数与代数"] == round((0.8 + 0.6) / 2, 2)
        assert radar["图形与几何"] == round((0.9 + 0.7) / 2, 2)

    def test_build_group_radar_empty_students(self):
        """无学生数据时返回全满分"""
        service = GroupAnalysisService()
        radar = service._build_group_radar({})

        # 数学图谱有4个一级维度：数与代数、图形与几何、统计与概率、综合与实践
        assert len(radar) >= 1
        assert all(score == 1.0 for score in radar.values())


# ======================================================================
# _build_comparison_radar 测试
# ======================================================================


class TestBuildComparisonRadar:
    """多组对比雷达图"""

    def test_build_comparison_radar(self):
        """多组对比雷达图数据正确"""
        service = GroupAnalysisService()
        g1 = GroupWeakness(
            group_id="g1",
            group_name="第1组",
            common_weak_points=[],
            radar={"数与代数": 0.8, "图形与几何": 0.9},
            suggestion="",
        )
        g2 = GroupWeakness(
            group_id="g2",
            group_name="第2组",
            common_weak_points=[],
            radar={"数与代数": 0.6, "图形与几何": 0.7},
            suggestion="",
        )
        radar = service._build_comparison_radar([g1, g2])

        assert "数与代数" in radar
        assert "图形与几何" in radar
        assert radar["数与代数"]["g1"] == 0.8
        assert radar["数与代数"]["g2"] == 0.6
        assert radar["图形与几何"]["g1"] == 0.9
        assert radar["图形与几何"]["g2"] == 0.7


# ======================================================================
# _generate_template_exercises 测试
# ======================================================================


class TestGenerateTemplateExercises:
    """模板练习题生成"""

    def test_generate_template_exercises(self):
        """为每个薄弱点生成2道模板题"""
        service = GroupAnalysisService()
        weak_points = [
            {
                "knowledge_id": "rational_concept",
                "knowledge_name": "有理数的概念",
                "weakness_ratio": 1.0,
                "affected_members": ["s1"],
                "avg_weakness_score": 0.8,
            },
        ]
        exercises = service._generate_template_exercises(weak_points)

        assert len(exercises) == 2
        assert all("question" in e for e in exercises)
        assert all("answer" in e for e in exercises)
        assert all(e["knowledge_id"] == "rational_concept" for e in exercises)
        # 一道概念理解，一道计算应用
        types = {e["type"] for e in exercises}
        assert "概念理解" in types
        assert "计算应用" in types

    def test_generate_template_exercises_max_5(self):
        """最多生成5个薄弱点的练习"""
        service = GroupAnalysisService()
        weak_points = [
            {
                "knowledge_id": f"kid_{i}",
                "knowledge_name": f"知识点{i}",
                "weakness_ratio": 0.6,
                "affected_members": ["s1"],
                "avg_weakness_score": 0.5,
            }
            for i in range(10)
        ]
        exercises = service._generate_template_exercises(weak_points)

        # 5个薄弱点 × 2道 = 10道
        assert len(exercises) == 10


# ======================================================================
# _generate_group_suggestion 测试
# ======================================================================


class TestGenerateGroupSuggestion:
    """小组建议生成"""

    def test_generate_group_suggestion_with_weaknesses(self):
        """有共性薄弱点时生成建议"""
        service = GroupAnalysisService()
        weak_points = [
            {
                "knowledge_name": "有理数的概念",
                "weakness_ratio": 0.8,
            },
        ]
        suggestion = service._generate_group_suggestion(
            "第1组", weak_points, {"数与代数": 0.3, "图形与几何": 0.9}
        )

        assert "第1组" in suggestion
        assert "有理数的概念" in suggestion

    def test_generate_group_suggestion_no_weaknesses(self):
        """无薄弱点时返回正面建议"""
        service = GroupAnalysisService()
        suggestion = service._generate_group_suggestion(
            "第1组", [], {"数与代数": 1.0, "图形与几何": 1.0}
        )

        assert "第1组" in suggestion
        assert "良好" in suggestion or "保持" in suggestion


# ======================================================================
# analyze_groups 集成测试
# ======================================================================


class TestAnalyzeGroupsIntegration:
    """完整集成测试（不依赖LLM）"""

    def test_analyze_groups_integration(self):
        """构造简单 ErrorEvent 数据，调用 analyze_groups 后断言返回结构"""
        service = GroupAnalysisService()
        group_errors_map = {
            "g1": {
                "s1": [make_error_event("rational_concept")],
                "s2": [make_error_event("rational_concept")],
            },
        }
        group_info = {
            "g1": {"group_name": "第1组", "student_ids": ["s1", "s2"]},
        }

        result = service.analyze_groups(
            group_errors_map=group_errors_map,
            group_info=group_info,
            reference_date=date(2025, 7, 1),
        )

        # 返回类型正确
        assert isinstance(result, GroupComparisonResult)

        # 有1个小组
        assert len(result.groups) == 1
        gw = result.groups[0]
        assert gw.group_id == "g1"
        assert gw.group_name == "第1组"

        # 2/2 = 100% 薄弱，应触发共性薄弱点
        assert len(gw.common_weak_points) >= 1

        # 雷达图存在且维度有效
        assert isinstance(gw.radar, dict)
        assert len(gw.radar) >= 1

        # 建议不为空
        assert isinstance(gw.suggestion, str)
        assert len(gw.suggestion) > 0

        # 对比雷达图结构正确
        assert isinstance(result.comparison_radar, dict)
        for dim_name, group_scores in result.comparison_radar.items():
            assert isinstance(group_scores, dict)
            assert "g1" in group_scores

        # 练习题结构正确（模板题降级路径，不依赖LLM）
        assert len(result.group_exercises) == 1
        exercise_entry = result.group_exercises[0]
        assert exercise_entry["group_id"] == "g1"
        assert "exercises" in exercise_entry
        assert isinstance(exercise_entry["exercises"], list)
        # 有共性薄弱点，应有练习题
        if gw.common_weak_points:
            assert len(exercise_entry["exercises"]) > 0
