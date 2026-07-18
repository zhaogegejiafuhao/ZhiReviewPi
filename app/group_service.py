"""
希沃智教π 小组学情协同分析 (Phase 2 - 7.2.2)

按飞书班级群分组聚合薄弱数据：
1. 按小组聚合每个学生的薄弱知识点
2. 计算小组共性薄弱点（组内超过50%成员都薄弱的知识点）
3. 生成小组对比雷达图（一级维度 → 平均掌握度）
4. 自动生成小组专项练习卷（LLM出题，API不可用时返回模板题）
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

from app.attribution import DecayPropagate, ErrorEvent, WeaknessResult
from app.knowledge_graph import KnowledgeGraph
from app.config import settings


# ===== 共性薄弱判定阈值 =====
# 组内薄弱学生占比 >= 此值，判定为"小组共性薄弱点"
COMMON_WEAKNESS_RATIO = 0.5

# 薄弱度阈值：薄弱度 >= 此值视为"薄弱"
WEAKNESS_THRESHOLD = 0.4


@dataclass
class GroupWeakness:
    """单个小组的薄弱分析结果"""
    group_id: str
    group_name: str
    common_weak_points: list[dict]    # [{knowledge_id, knowledge_name, weakness_ratio, affected_members}]
    radar: dict[str, float]           # 一级维度 → 平均掌握度
    suggestion: str


@dataclass
class GroupComparisonResult:
    """小组对比分析结果"""
    groups: list[GroupWeakness]
    comparison_radar: dict[str, dict[str, float]]   # {dimension: {group_id: score}}
    group_exercises: list[dict]                     # [{group_id, group_name, exercises: [{question, answer, knowledge_id}]}]


class GroupAnalysisService:
    """
    小组学情协同分析服务

    对每个小组执行 DecayPropagate 分析，计算共性薄弱点，
    生成小组对比雷达图和专项练习题。
    """

    def __init__(self, kg: KnowledgeGraph | None = None):
        self.kg = kg or KnowledgeGraph()
        self.decay_propagate = DecayPropagate(self.kg)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def analyze_groups(
        self,
        group_errors_map: dict[str, dict[str, list[ErrorEvent]]],
        group_info: dict[str, dict],
        reference_date: Optional[date] = None,
    ) -> GroupComparisonResult:
        """
        小组学情协同分析主入口

        Args:
            group_errors_map: {group_id: {student_id: [ErrorEvent, ...]}}
                每个小组内每个学生的错题事件列表
            group_info: {group_id: {"group_name": "第1组", "student_ids": ["s1", "s2"]}}
                小组基本信息
            reference_date: 参考日期，默认今天

        Returns:
            GroupComparisonResult: 小组对比分析结果
        """
        if reference_date is None:
            reference_date = date.today()

        # Step 1: 对每个小组执行分析
        group_results: list[GroupWeakness] = []
        for group_id, students_errors in group_errors_map.items():
            info = group_info.get(group_id, {})
            group_name = info.get("group_name", group_id)
            student_ids = info.get("student_ids", list(students_errors.keys()))

            group_weakness = self._analyze_single_group(
                group_id=group_id,
                group_name=group_name,
                student_ids=student_ids,
                students_errors=students_errors,
                reference_date=reference_date,
            )
            group_results.append(group_weakness)

        # Step 2: 生成小组对比雷达图
        comparison_radar = self._build_comparison_radar(group_results)

        # Step 3: 为每个小组生成专项练习题
        group_exercises = []
        for gw in group_results:
            if not gw.common_weak_points:
                group_exercises.append({
                    "group_id": gw.group_id,
                    "group_name": gw.group_name,
                    "exercises": [],
                    "message": "该小组暂无共性薄弱点，无需专项练习",
                })
                continue

            exercises = self._generate_group_exercises_sync(
                group_id=gw.group_id,
                group_name=gw.group_name,
                weak_points=gw.common_weak_points,
            )
            group_exercises.append({
                "group_id": gw.group_id,
                "group_name": gw.group_name,
                "exercises": exercises,
            })

        return GroupComparisonResult(
            groups=group_results,
            comparison_radar=comparison_radar,
            group_exercises=group_exercises,
        )

    async def generate_group_exercises(
        self,
        group_id: str,
        group_name: str,
        weak_points: list[dict],
    ) -> list[dict]:
        """
        LLM生成小组专项练习题（异步版本）

        优先使用硅基流动API生成针对性练习题，API不可用时降级为模板题。

        Args:
            group_id: 小组ID
            group_name: 小组名称
            weak_points: 共性薄弱点列表 [{knowledge_id, knowledge_name, weakness_ratio, affected_members}]

        Returns:
            练习题列表 [{question, answer, knowledge_id, knowledge_name, difficulty}]
        """
        if not weak_points:
            return []

        # 尝试LLM生成
        llm_exercises = await self._generate_exercises_by_llm(group_name, weak_points)
        if llm_exercises:
            return llm_exercises

        # 降级为模板题
        return self._generate_template_exercises(weak_points)

    # ------------------------------------------------------------------
    # 内部方法 — 单组分析
    # ------------------------------------------------------------------

    def _analyze_single_group(
        self,
        group_id: str,
        group_name: str,
        student_ids: list[str],
        students_errors: dict[str, list[ErrorEvent]],
        reference_date: date,
    ) -> GroupWeakness:
        """
        分析单个小组的学情

        对组内每个学生执行 DecayPropagate 分析，然后计算共性薄弱点和小组雷达图。
        """
        # Step 1: 对每个学生执行 DecayPropagate 分析
        student_weaknesses: dict[str, list[WeaknessResult]] = {}
        student_radars: dict[str, dict[str, float]] = {}

        for student_id, errors in students_errors.items():
            if not errors:
                continue

            weak_points = self.decay_propagate.analyze(
                errors=errors,
                reference_date=reference_date,
                top_k=20,
            )
            student_weaknesses[student_id] = weak_points

            # 生成该学生的雷达图数据
            radar = self._build_student_radar(weak_points)
            student_radars[student_id] = radar

        # Step 2: 计算小组共性薄弱点
        common_weak_points = self._find_common_weak_points(
            student_ids=student_ids,
            student_weaknesses=student_weaknesses,
        )

        # Step 3: 生成小组雷达图（一级维度 → 平均掌握度）
        group_radar = self._build_group_radar(student_radars)

        # Step 4: 生成小组建议
        suggestion = self._generate_group_suggestion(group_name, common_weak_points, group_radar)

        return GroupWeakness(
            group_id=group_id,
            group_name=group_name,
            common_weak_points=common_weak_points,
            radar=group_radar,
            suggestion=suggestion,
        )

    def _build_student_radar(self, weak_points: list[WeaknessResult]) -> dict[str, float]:
        """
        根据学生的薄弱点构建雷达图数据

        Returns:
            {dimension_name: mastery_score}  一级维度 → 掌握度 (1 - 薄弱度)
        """
        radar = {}
        radar_dims = self.kg.get_radar_dimensions()

        for dim in radar_dims:
            dim_id = dim["id"]
            dim_name = dim["name"]

            # 计算该维度下所有薄弱节点的最大薄弱度
            max_weakness = 0.0
            for wp in weak_points:
                node = self.kg.get_node(wp.knowledge_id)
                if node and self._is_under_dimension(wp.knowledge_id, dim_id):
                    max_weakness = max(max_weakness, wp.weakness_score)

            # 雷达图展示"掌握度"而非"薄弱度"
            radar[dim_name] = round(1.0 - max_weakness, 2)

        return radar

    def _build_group_radar(self, student_radars: dict[str, dict[str, float]]) -> dict[str, float]:
        """
        聚合组内所有学生的雷达图，生成小组平均雷达图

        Args:
            student_radars: {student_id: {dimension_name: mastery_score}}

        Returns:
            {dimension_name: avg_mastery_score}  一级维度 → 平均掌握度
        """
        if not student_radars:
            # 无数据时返回全满分
            radar_dims = self.kg.get_radar_dimensions()
            return {dim["name"]: 1.0 for dim in radar_dims}

        # 收集所有维度名称
        all_dims = set()
        for radar in student_radars.values():
            all_dims.update(radar.keys())

        group_radar = {}
        for dim_name in all_dims:
            scores = [radar.get(dim_name, 1.0) for radar in student_radars.values()]
            avg_score = sum(scores) / len(scores) if scores else 1.0
            group_radar[dim_name] = round(avg_score, 2)

        return group_radar

    def _find_common_weak_points(
        self,
        student_ids: list[str],
        student_weaknesses: dict[str, list[WeaknessResult]],
    ) -> list[dict]:
        """
        计算小组共性薄弱点

        共性薄弱点定义：组内超过50%成员的薄弱度 >= WEAKNESS_THRESHOLD 的知识点。

        Returns:
            [{knowledge_id, knowledge_name, weakness_ratio, affected_members, avg_weakness_score}]
        """
        total_students = len(student_ids)
        if total_students == 0:
            return []

        # 统计每个知识点被哪些学生判定为薄弱
        # knowledge_id -> {student_id: weakness_score}
        knowledge_weak_students: dict[str, dict[str, float]] = {}

        for student_id, weak_points in student_weaknesses.items():
            for wp in weak_points:
                if wp.weakness_score >= WEAKNESS_THRESHOLD:
                    if wp.knowledge_id not in knowledge_weak_students:
                        knowledge_weak_students[wp.knowledge_id] = {}
                    knowledge_weak_students[wp.knowledge_id][student_id] = wp.weakness_score

        # 计算共性薄弱点
        common_points = []
        for kid, weak_students in knowledge_weak_students.items():
            weak_ratio = len(weak_students) / total_students

            if weak_ratio >= COMMON_WEAKNESS_RATIO:
                node = self.kg.get_node(kid)
                knowledge_name = node["name"] if node else kid

                avg_weakness = sum(weak_students.values()) / len(weak_students) if weak_students else 0.0

                common_points.append({
                    "knowledge_id": kid,
                    "knowledge_name": knowledge_name,
                    "weakness_ratio": round(weak_ratio, 4),
                    "affected_members": sorted(list(weak_students.keys())),
                    "avg_weakness_score": round(avg_weakness, 4),
                })

        # 按薄弱占比降序排列
        common_points.sort(key=lambda p: p["weakness_ratio"], reverse=True)
        return common_points

    def _is_under_dimension(self, node_id: str, dimension_id: str) -> bool:
        """检查node_id是否属于dimension_id的子树"""
        if node_id == dimension_id:
            return True
        ancestors = self.kg.get_ancestors(node_id)
        return dimension_id in ancestors

    # ------------------------------------------------------------------
    # 内部方法 — 对比雷达图
    # ------------------------------------------------------------------

    def _build_comparison_radar(self, group_results: list[GroupWeakness]) -> dict[str, dict[str, float]]:
        """
        构建小组对比雷达图数据

        Returns:
            {dimension_name: {group_id: mastery_score}}
        """
        comparison_radar: dict[str, dict[str, float]] = {}

        for gw in group_results:
            for dim_name, score in gw.radar.items():
                if dim_name not in comparison_radar:
                    comparison_radar[dim_name] = {}
                comparison_radar[dim_name][gw.group_id] = score

        return comparison_radar

    # ------------------------------------------------------------------
    # 内部方法 — 练习题生成
    # ------------------------------------------------------------------

    def _generate_group_exercises_sync(
        self,
        group_id: str,
        group_name: str,
        weak_points: list[dict],
    ) -> list[dict]:
        """
        同步生成小组专项练习题（降级为模板题）

        异步LLM生成通过 generate_group_exercises 方法提供。
        """
        return self._generate_template_exercises(weak_points)

    def _generate_template_exercises(self, weak_points: list[dict]) -> list[dict]:
        """
        生成模板练习题（LLM不可用时的降级方案）

        为每个共性薄弱点生成一道模板填空题和一道计算题。
        """
        exercises = []

        for wp in weak_points[:5]:  # 最多5个薄弱点
            kid = wp["knowledge_id"]
            kname = wp["knowledge_name"]

            # 根据知识点名称生成模板题
            exercise_1 = {
                "question": f"关于{ kname}，请写出其核心定义并举例说明。",
                "answer": f"{kname}的定义及示例（参考教材）",
                "knowledge_id": kid,
                "knowledge_name": kname,
                "difficulty": "基础",
                "type": "概念理解",
            }

            exercise_2 = {
                "question": f"请完成以下关于{kname}的练习题：已知条件如教材P{hash(kid) % 50 + 10}例题，求结果。",
                "answer": f"{kname}计算步骤及结果（参考教材解析）",
                "knowledge_id": kid,
                "knowledge_name": kname,
                "difficulty": "应用",
                "type": "计算应用",
            }

            exercises.extend([exercise_1, exercise_2])

        return exercises

    async def _generate_exercises_by_llm(
        self,
        group_name: str,
        weak_points: list[dict],
    ) -> list[dict]:
        """
        通过LLM生成针对性练习题

        使用硅基流动API，如果不可用返回空列表，由调用方降级为模板题。
        """
        if not settings.SILICONFLOW_API_KEY:
            return []

        from app.llm_utils import parse_llm_json, get_siliconflow_client

        client = get_siliconflow_client()

        # 构造薄弱点描述
        weak_descriptions = []
        for wp in weak_points[:5]:
            weak_descriptions.append(
                f"- {wp['knowledge_name']}（薄弱学生占比{wp['weakness_ratio']:.0%}，"
                f"平均薄弱度{wp.get('avg_weakness_score', 0):.2f}）"
            )

        prompt = f"""你是一位资深的数学教师，请为"{group_name}"生成针对性练习题。

## 小组共性薄弱知识点
{chr(10).join(weak_descriptions)}

## 要求
1. 为每个薄弱知识点生成1-2道练习题（共不超过8道）
2. 题目难度由浅入深（基础题 → 应用题）
3. 包含参考答案和简要解析
4. 题目要贴近初中数学教学实际

## 输出格式
严格输出以下JSON格式，不要输出其他内容：
{{"exercises": [{{"question": "题目内容", "answer": "参考答案及解析", "knowledge_id": "知识点ID", "knowledge_name": "知识点名称", "difficulty": "基础|应用|拓展", "type": "概念理解|计算应用|证明推理"}}]}}"""

        try:
            response = await client.chat.completions.create(
                model="Qwen/Qwen2.5-7B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
            content = response.choices[0].message.content

            # 解析JSON
            data = parse_llm_json(content)
            return data.get("exercises", [])
        except Exception as e:
            logger.warning(f"[GroupAnalysisService] LLM生成练习题失败: {type(e).__name__}: {e}")

        return []

    # ------------------------------------------------------------------
    # 内部方法 — 建议生成
    # ------------------------------------------------------------------

    def _generate_group_suggestion(
        self,
        group_name: str,
        common_weak_points: list[dict],
        group_radar: dict[str, float],
    ) -> str:
        """
        生成小组改进建议

        根据共性薄弱点和雷达图数据，给出针对性的教学建议。
        """
        if not common_weak_points:
            return f"{group_name}整体表现良好，暂无共性薄弱点，建议继续保持并适度拔高。"

        # 找出最薄弱的维度
        sorted_dims = sorted(group_radar.items(), key=lambda x: x[1])
        weakest_dim = sorted_dims[0] if sorted_dims else ("未知", 1.0)

        # 找出最严重的共性薄弱点
        top_weak = common_weak_points[0]
        top_name = top_weak["knowledge_name"]
        top_ratio = top_weak["weakness_ratio"]

        parts = [f"{group_name}分析结果："]

        # 共性薄弱点描述
        weak_names = [wp["knowledge_name"] for wp in common_weak_points[:3]]
        if len(common_weak_points) <= 3:
            parts.append(
                f"共性薄弱知识点为{ '、'.join(weak_names)}，"
                f"其中「{top_name}」薄弱学生占比最高（{top_ratio:.0%}）。"
            )
        else:
            parts.append(
                f"共有{len(common_weak_points)}个共性薄弱知识点，"
                f"最突出的是「{top_name}」（薄弱学生占比{top_ratio:.0%}），"
                f"其次为{'、'.join(weak_names[1:])}。"
            )

        # 雷达维度描述
        if weakest_dim[1] < 0.5:
            parts.append(
                f"雷达图显示「{weakest_dim[0]}」维度掌握度最低（{weakest_dim[1]:.0%}），需重点突破。"
            )
        elif weakest_dim[1] < 0.8:
            parts.append(
                f"雷达图显示「{weakest_dim[0]}」维度有提升空间（掌握度{weakest_dim[1]:.0%}），建议针对性练习。"
            )

        # 建议措施
        parts.append("建议：1) 针对共性薄弱点开展小组专项练习；2) 安排掌握较好的同学帮扶薄弱同学；3) 薄弱知识点重新讲解核心概念。")

        return "".join(parts)
