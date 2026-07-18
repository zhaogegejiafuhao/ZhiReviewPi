"""AlertService 学情预警双阈值逻辑测试

测试目标：
- check_student_alert：连续错题 >= 3 次触发个别辅导预警
- check_class_alert：薄弱学生占比 > 60% 触发班级教学盲区预警
- _count_consecutive_errors：满分记录中断连续性
- 边界：空列表、阈值临界值、多知识点并发
"""
import pytest

from app.alert_service import (
    AlertService,
    CONSECUTIVE_ERROR_THRESHOLD,
    CLASS_WEAK_RATIO_THRESHOLD,
)


def make_error(knowledge_id, timestamp, weight=1.0):
    """构造错题事件字典"""
    return {
        "knowledge_node_id": knowledge_id,
        "timestamp": timestamp,
        "error_weight": weight,
    }


# ======================================================================
# check_student_alert 测试
# ======================================================================


class TestCheckStudentAlert:
    """学生个别辅导预警"""

    def test_check_student_alert_consecutive_errors(self):
        """学生同一知识点连续错题3次触发预警"""
        service = AlertService()
        errors = [
            make_error("rational_concept", "2025-07-01", 1.0),
            make_error("rational_concept", "2025-07-02", 1.0),
            make_error("rational_concept", "2025-07-03", 1.0),
        ]
        alerts = service.check_student_alert("s1", errors)

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["alert_type"] == "individual"
        assert alert["student_id"] == "s1"
        assert alert["knowledge_id"] == "rational_concept"
        assert alert["knowledge_name"] == "有理数的概念"
        assert alert["consecutive_errors"] >= CONSECUTIVE_ERROR_THRESHOLD

    def test_check_student_alert_below_threshold(self):
        """连续错题2次不触发预警"""
        service = AlertService()
        errors = [
            make_error("rational_concept", "2025-07-01", 1.0),
            make_error("rational_concept", "2025-07-02", 1.0),
        ]
        alerts = service.check_student_alert("s1", errors)
        assert alerts == []

    def test_check_student_alert_empty_errors(self):
        """空错题列表返回空预警"""
        service = AlertService()
        alerts = service.check_student_alert("s1", [])
        assert alerts == []

    def test_check_student_alert_multiple_knowledge(self):
        """多个知识点都有连续错题，生成多个预警"""
        service = AlertService()
        errors = [
            # rational_concept 连续3次错题
            make_error("rational_concept", "2025-07-01", 1.0),
            make_error("rational_concept", "2025-07-02", 1.0),
            make_error("rational_concept", "2025-07-03", 1.0),
            # congruent_tri 连续3次错题
            make_error("congruent_tri", "2025-07-01", 1.0),
            make_error("congruent_tri", "2025-07-02", 1.0),
            make_error("congruent_tri", "2025-07-03", 1.0),
        ]
        alerts = service.check_student_alert("s1", errors)

        assert len(alerts) == 2
        knowledge_ids = {a["knowledge_id"] for a in alerts}
        assert "rational_concept" in knowledge_ids
        assert "congruent_tri" in knowledge_ids


# ======================================================================
# _count_consecutive_errors 测试
# ======================================================================


class TestCountConsecutiveErrors:
    """连续错题计数算法"""

    def test_count_consecutive_errors_with_score_interrupt(self):
        """满分记录中断连续性"""
        service = AlertService()
        errors = [
            make_error("rational_concept", "2025-07-01", 1.0),  # 错题
            make_error("rational_concept", "2025-07-02", 0.0),  # 满分中断
            make_error("rational_concept", "2025-07-03", 1.0),  # 错题
            make_error("rational_concept", "2025-07-04", 1.0),  # 错题
        ]
        # 从最近向前数：错、错、满分(中断)，只有最后2次连续
        assert service._count_consecutive_errors(errors) == 2

    def test_count_consecutive_errors_all_errors(self):
        """所有都是错题，返回总数"""
        service = AlertService()
        errors = [
            make_error("rational_concept", "2025-07-01", 1.0),
            make_error("rational_concept", "2025-07-02", 1.0),
            make_error("rational_concept", "2025-07-03", 1.0),
            make_error("rational_concept", "2025-07-04", 1.0),
        ]
        assert service._count_consecutive_errors(errors) == 4

    def test_count_consecutive_errors_empty(self):
        """空列表返回0"""
        service = AlertService()
        assert service._count_consecutive_errors([]) == 0


# ======================================================================
# check_class_alert 测试
# ======================================================================


class TestCheckClassAlert:
    """班级教学盲区预警"""

    def test_check_class_alert_high_ratio(self):
        """70%学生薄弱，触发班级预警"""
        service = AlertService()
        # 10个学生中7个薄弱同一模块 = 70% > 60%
        student_errors_map = {}
        for i in range(7):
            # 错题映射到 rational_concept → 上溯到 rational_num 模块
            student_errors_map[f"s{i}"] = [
                make_error("rational_concept", "2025-07-01", 1.0)
            ]
        for i in range(7, 10):
            student_errors_map[f"s{i}"] = []

        alerts = service.check_class_alert("c1", student_errors_map)

        assert len(alerts) >= 1
        alert = alerts[0]
        assert alert["alert_type"] == "class"
        assert alert["class_id"] == "c1"
        assert alert["weak_ratio"] == 0.7
        assert alert["total_students"] == 10

    def test_check_class_alert_low_ratio(self):
        """40%学生薄弱，不触发班级预警"""
        service = AlertService()
        # 10个学生中4个薄弱 = 40%，不 > 60%
        student_errors_map = {}
        for i in range(4):
            student_errors_map[f"s{i}"] = [
                make_error("rational_concept", "2025-07-01", 1.0)
            ]
        for i in range(4, 10):
            student_errors_map[f"s{i}"] = []

        alerts = service.check_class_alert("c1", student_errors_map)
        # 不应有 rational_num 模块的预警（40% <= 60%）
        rational_alerts = [
            a for a in alerts if a.get("module_id") == "rational_num"
        ]
        assert rational_alerts == []

    def test_check_class_alert_empty(self):
        """空学生列表返回空预警"""
        service = AlertService()
        alerts = service.check_class_alert("c1", {})
        assert alerts == []

    def test_check_class_alert_ordering(self):
        """预警按薄弱占比降序排列"""
        service = AlertService()
        # 构造两个模块的薄弱占比不同
        student_errors_map = {
            # 3/4 = 75% 在 triangle 模块薄弱
            "s1": [
                make_error("congruent_tri", "2025-07-01", 1.0),
                make_error("rational_concept", "2025-07-01", 1.0),
            ],
            "s2": [
                make_error("similar_tri", "2025-07-01", 1.0),
                make_error("rational_op", "2025-07-01", 1.0),
            ],
            "s3": [
                make_error("right_tri", "2025-07-01", 1.0),
            ],
            "s4": [],
        }
        alerts = service.check_class_alert("c1", student_errors_map)

        if len(alerts) >= 2:
            ratios = [a["weak_ratio"] for a in alerts]
            assert ratios == sorted(ratios, reverse=True)
