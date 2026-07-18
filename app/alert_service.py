"""
希沃智教π 学情干预预警机制 (Phase 2 - 7.2.1)

基于DecayPropagate薄弱度设置双阈值：
1. 单学生预警：连续3次同一知识点错题 → 推送"个别辅导预警"卡片
2. 班级级预警：超60%学生同一模块薄弱 → 推送"班级教学盲区"卡片，提醒老师重新授课
"""
from dataclasses import dataclass, field
from typing import Optional

from app.knowledge_graph import KnowledgeGraph


@dataclass
class StudentAlert:
    """个别辅导预警"""
    alert_type: str                          # "individual"
    student_id: str
    knowledge_id: str
    knowledge_name: str
    consecutive_errors: int
    message: str


@dataclass
class ClassAlert:
    """班级教学盲区预警"""
    alert_type: str                          # "class"
    class_id: str
    module_id: str
    module_name: str
    weak_ratio: float                        # 薄弱学生占比
    weak_students: list[str]
    total_students: int
    message: str


# 薄弱度阈值：薄弱度 >= 此值视为"薄弱"
WEAKNESS_THRESHOLD = 0.6

# 连续错题阈值：同一知识点连续错题 >= 此值触发个别辅导预警
CONSECUTIVE_ERROR_THRESHOLD = 3

# 班级薄弱占比阈值：薄弱学生占比 > 此值触发班级教学盲区预警
CLASS_WEAK_RATIO_THRESHOLD = 0.6


class AlertService:
    """
    学情干预预警服务

    基于DecayPropagate薄弱度设置双阈值，实现个别辅导预警和班级教学盲区预警。
    """

    def __init__(self, kg: KnowledgeGraph | None = None):
        self.kg = kg or KnowledgeGraph()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def check_student_alert(
        self,
        student_id: str,
        errors: list[dict],
    ) -> list[dict]:
        """
        检查单学生预警：统计同一知识点连续错题次数，
        连续3次以上同一知识点 → 生成个别辅导预警

        Args:
            student_id: 学生ID
            errors: 错题事件列表，每个元素包含:
                - knowledge_node_id (str): 知识点ID
                - timestamp (date/str): 错误日期
                - error_weight (float): 错误权重
                - question_content (str): 题目内容（可选）
                - error_cause (str): 错因标签（可选）

        Returns:
            预警列表 [{"alert_type": "individual", "student_id": ..., ...}]
        """
        if not errors:
            return []

        # 按知识点分组，保持时间顺序
        knowledge_errors: dict[str, list[dict]] = {}
        for error in errors:
            kid = error.get("knowledge_node_id", "")
            if not kid:
                continue
            if kid not in knowledge_errors:
                knowledge_errors[kid] = []
            knowledge_errors[kid].append(error)

        alerts = []
        for kid, error_list in knowledge_errors.items():
            # 按时间排序（升序，最早的在前）
            sorted_errors = sorted(
                error_list,
                key=lambda e: str(e.get("timestamp", "")),
            )

            # 统计连续错题次数
            consecutive_count = self._count_consecutive_errors(sorted_errors)

            if consecutive_count >= CONSECUTIVE_ERROR_THRESHOLD:
                node = self.kg.get_node(kid)
                knowledge_name = node["name"] if node else kid

                alert = StudentAlert(
                    alert_type="individual",
                    student_id=student_id,
                    knowledge_id=kid,
                    knowledge_name=knowledge_name,
                    consecutive_errors=consecutive_count,
                    message=(
                        f"学生{student_id}在知识点「{knowledge_name}」上连续错题{consecutive_count}次，"
                        f"建议安排个别辅导，重点关注该知识点的理解与练习"
                    ),
                )
                alerts.append(self._student_alert_to_dict(alert))

        return alerts

    def check_class_alert(
        self,
        class_id: str,
        student_errors_map: dict[str, list[dict]],
    ) -> list[dict]:
        """
        检查班级级预警：统计班级内各模块薄弱学生占比，
        超过60%学生同一模块薄弱 → 生成班级教学盲区预警

        Args:
            class_id: 班级ID
            student_errors_map: {student_id: [error, ...]} 班级内每个学生的错题列表

        Returns:
            预警列表 [{"alert_type": "class", "module_id": ..., ...}]
        """
        if not student_errors_map:
            return []

        total_students = len(student_errors_map)

        # Step 1: 确定每个学生在哪些模块上薄弱
        # module_id -> set of weak student_ids
        module_weak_students: dict[str, set[str]] = {}

        for student_id, errors in student_errors_map.items():
            weak_modules = self._get_weak_modules(errors)
            for module_id in weak_modules:
                if module_id not in module_weak_students:
                    module_weak_students[module_id] = set()
                module_weak_students[module_id].add(student_id)

        # Step 2: 检查每个模块的薄弱学生占比
        alerts = []
        for module_id, weak_student_ids in module_weak_students.items():
            weak_ratio = len(weak_student_ids) / total_students if total_students > 0 else 0.0

            if weak_ratio > CLASS_WEAK_RATIO_THRESHOLD:
                node = self.kg.get_node(module_id)
                module_name = node["name"] if node else module_id

                alert = ClassAlert(
                    alert_type="class",
                    class_id=class_id,
                    module_id=module_id,
                    module_name=module_name,
                    weak_ratio=round(weak_ratio, 4),
                    weak_students=sorted(list(weak_student_ids)),
                    total_students=total_students,
                    message=(
                        f"班级{class_id}在模块「{module_name}」上薄弱学生占比{weak_ratio:.0%}"
                        f"（{len(weak_student_ids)}/{total_students}人），"
                        f"建议重新授课或开展集体复习，重点关注该模块教学效果"
                    ),
                )
                alerts.append(self._class_alert_to_dict(alert))

        # 按薄弱占比降序排列
        alerts.sort(key=lambda a: a.get("weak_ratio", 0), reverse=True)
        return alerts

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _count_consecutive_errors(self, sorted_errors: list[dict]) -> int:
        """
        统计同一知识点的连续错题次数

        连续错题定义：按时间顺序排列的错题序列中，从最近一次向前数，
        连续的error_weight > 0的事件数量（只要有一次得分满分则中断连续性）。

        对于仅含错题（无满分记录）的场景，直接统计错题总数。
        """
        if not sorted_errors:
            return 0

        # 从最近一次错误向前统计连续错题
        consecutive = 0
        for error in reversed(sorted_errors):
            weight = error.get("error_weight", 1.0)
            if weight > 0:
                consecutive += 1
            else:
                # 满分记录中断连续性
                break

        return consecutive

    def _get_weak_modules(self, errors: list[dict]) -> set[str]:
        """
        根据学生的错题列表，确定该学生在哪些模块上薄弱

        模块定义：知识图谱中 level=1（如"数与代数"、"图形与几何"）或
        level=2（如"有理数"、"三角形"）的节点。

        判断逻辑：学生某个知识点有错题 → 向上溯源到所属模块 → 该模块记为薄弱。

        Returns:
            薄弱模块ID集合
        """
        weak_modules = set()

        for error in errors:
            kid = error.get("knowledge_node_id", "")
            if not kid:
                continue

            # 只统计有实际错误权重的事件
            weight = error.get("error_weight", 1.0)
            if weight <= 0:
                continue

            # 向上溯源找到所属模块（level=2 的章节节点，或 level=1 的一级维度节点）
            module_id = self._find_parent_module(kid)
            if module_id:
                weak_modules.add(module_id)

        return weak_modules

    def _find_parent_module(self, knowledge_id: str) -> Optional[str]:
        """
        向上溯源找到知识点所属的模块节点（优先level=2，其次level=1）

        Args:
            knowledge_id: 知识点ID

        Returns:
            模块节点ID，找不到则返回None
        """
        node = self.kg.get_node(knowledge_id)
        if not node:
            return None

        level = node.get("level", 0)

        # 如果本身是模块级节点（level=1或level=2），直接返回
        if level in (1, 2):
            return knowledge_id

        # 向上查找最近的level=2节点
        parent_id = node.get("parent_id")
        while parent_id:
            parent_node = self.kg.get_node(parent_id)
            if not parent_node:
                break
            if parent_node.get("level") == 2:
                return parent_id
            if parent_node.get("level") == 1:
                # 如果直接是level=1，也返回（有些模块没有level=2的子节点）
                return parent_id
            parent_id = parent_node.get("parent_id")

        return None

    @staticmethod
    def _student_alert_to_dict(alert: StudentAlert) -> dict:
        """将StudentAlert转为字典"""
        return {
            "alert_type": alert.alert_type,
            "student_id": alert.student_id,
            "knowledge_id": alert.knowledge_id,
            "knowledge_name": alert.knowledge_name,
            "consecutive_errors": alert.consecutive_errors,
            "message": alert.message,
        }

    @staticmethod
    def _class_alert_to_dict(alert: ClassAlert) -> dict:
        """将ClassAlert转为字典"""
        return {
            "alert_type": alert.alert_type,
            "class_id": alert.class_id,
            "module_id": alert.module_id,
            "module_name": alert.module_name,
            "weak_ratio": alert.weak_ratio,
            "weak_students": alert.weak_students,
            "total_students": alert.total_students,
            "message": alert.message,
        }
