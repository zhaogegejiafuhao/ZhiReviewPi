"""
希沃智教π 知识归因层 - DecayPropagate算法 + 错题映射 + 学情报告

核心算法：DecayPropagate — 基于知识依赖DAG的方向性衰减传播
  - 后向传播：前置知识薄弱向后传播（乘法不会→除法也弱）
  - 前向聚合：子节点全弱则父节点可能教得不好（弱信号）
  - 时间衰减：近期错题权重更高（Ebbinghaus遗忘曲线）
"""
import logging
import math
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from app.knowledge_graph import KnowledgeGraph


@dataclass
class ErrorEvent:
    """错题事件"""
    knowledge_node_id: str
    error_weight: float       # 1.0=完全错误, 0.5=部分错误
    timestamp: date           # 错误发生日期
    question_content: str = ""  # 题目内容（用于展示）
    error_cause: str = ""       # 错因标签（计算粗心|概念混淆|审题不清|辅助线缺失|逻辑跳步|知识缺失）


@dataclass
class WeaknessResult:
    """单个知识点的薄弱度结果"""
    knowledge_id: str
    knowledge_name: str
    weakness_score: float      # 归一化薄弱度 [0, 1]
    root_cause: Optional[dict] = None  # {root_node, path, propagation_type, contribution_ratio}
    error_count: int = 0
    recent_errors: list[dict] = field(default_factory=list)
    suggestion: str = ""
    error_cause_distribution: dict = field(default_factory=dict)  # 错因分布统计，如 {"计算粗心": 3, "概念混淆": 2}


@dataclass
class AnalysisReport:
    """学情分析报告"""
    student_id: str
    analysis_date: str
    radar: dict[str, float]          # 一级维度 → 归一化得分 (1-薄弱度)
    weak_points: list[WeaknessResult]
    correction_status: dict           # {total_errors, corrected, uncorrected, correction_rate}


class DecayPropagate:
    """DecayPropagate算法实现"""

    def __init__(
        self,
        kg: KnowledgeGraph,
        alpha: float = 0.6,    # 后向传播衰减因子
        beta: float = 0.3,     # 前向聚合弱传播因子
        lambda_decay: float = 0.1,  # Ebbinghaus时间衰减系数
        gamma: float = 0.4,    # 订正完成度奖励权重
    ):
        self.kg = kg
        self.alpha = alpha
        self.beta = beta
        self.lambda_decay = lambda_decay
        self.gamma = gamma

    def _time_decay(self, error_date: date, reference_date: date) -> float:
        """Ebbinghaus遗忘曲线衰减"""
        days_since = (reference_date - error_date).days
        if days_since < 0:
            days_since = 0
        return math.exp(-self.lambda_decay * days_since)

    def _backward_propagation(self, node_id: str, decayed_weights: dict[str, float]) -> float:
        """后向传播：前置知识薄弱向后传播"""
        ancestors = self.kg.get_ancestors(node_id)
        backward_score = 0.0

        for ancestor_id in ancestors:
            if ancestor_id not in decayed_weights:
                continue
            depth = self.kg.get_depth(ancestor_id, node_id)
            if depth == float("inf"):
                continue
            # 衰减传播：距离越远影响越小
            contribution = decayed_weights[ancestor_id] * (self.alpha ** depth)
            backward_score += contribution

        return backward_score

    def _forward_aggregation(self, node_id: str, raw_scores: dict[str, float]) -> float:
        """前向聚合：子节点全弱则父节点可能教得不好"""
        children = self.kg.get_children(node_id)
        if not children:
            return 0.0

        child_scores = [raw_scores.get(cid, 0.0) for cid in children]
        # 取子节点中的最大薄弱度（弱传播）
        return max(child_scores) * self.beta if child_scores else 0.0

    def analyze(
        self,
        errors: list[ErrorEvent],
        reference_date: date | None = None,
        top_k: int = 5,
        correction_records: list[dict] | None = None,
    ) -> list[WeaknessResult]:
        """
        执行DecayPropagate分析

        Args:
            errors: 错题事件列表
            reference_date: 参考日期（默认今天）
            top_k: 返回Top-K薄弱节点
            correction_records: 订正记录列表

        Returns:
            薄弱知识点列表，按薄弱度降序排列
        """
        if reference_date is None:
            reference_date = date.today()

        # Step 1: 计算每个节点的直接错误权重（含时间衰减）
        decayed_weights: dict[str, float] = {}
        error_counts: dict[str, int] = {}
        recent_errors: dict[str, list[dict]] = {}

        for error in errors:
            decay = self._time_decay(error.timestamp, reference_date)
            weighted = error.error_weight * decay

            kid = error.knowledge_node_id
            decayed_weights[kid] = decayed_weights.get(kid, 0.0) + weighted
            error_counts[kid] = error_counts.get(kid, 0) + 1

            if kid not in recent_errors:
                recent_errors[kid] = []
            recent_errors[kid].append({
                "date": error.timestamp.isoformat(),
                "question": error.question_content,
                "error_cause": error.error_cause,
            })

        # Step 1.5: 计算每个知识点的错因分布
        cause_counts: dict[str, dict[str, int]] = {}
        for error in errors:
            kid = error.knowledge_node_id
            if kid not in cause_counts:
                cause_counts[kid] = {}
            cause = error.error_cause or "未分类"
            cause_counts[kid][cause] = cause_counts[kid].get(cause, 0) + 1

        # Step 2: 对每个节点计算综合薄弱度
        raw_scores: dict[str, float] = {}
        for node_id in self.kg.get_all_nodes():
            direct = decayed_weights.get(node_id, 0.0)
            backward = self._backward_propagation(node_id, decayed_weights)
            forward = self._forward_aggregation(node_id, raw_scores if raw_scores else {})

            # 先用 direct + backward 计算，forward在第二轮更新
            raw_scores[node_id] = direct + backward

        # Step 3: 加入前向聚合（需要第二轮计算，因为forward依赖子节点的raw_scores）
        for node_id in list(raw_scores.keys()):
            forward = self._forward_aggregation(node_id, raw_scores)
            raw_scores[node_id] = raw_scores[node_id] + forward

        # Step 3.5: 订正完成度奖励（γ × correction_bonus）
        correction_bonus = {}
        if correction_records:
            for record in correction_records:
                kid = record["knowledge_node_id"]
                corrected = record.get("corrected", False)
                correction_score = record.get("correction_score", 0.0)

                if corrected:
                    # 订正满分→薄弱度快速下降（×0.3）
                    bonus = self.gamma * correction_score
                else:
                    # 长期不订正→薄弱度持续上浮（×1.2/周，简化为固定惩罚）
                    days_since = (reference_date - record.get("timestamp", reference_date)).days if record.get("timestamp") else 7
                    penalty = self.gamma * 0.05 * min(days_since / 7, 4)  # 最多4周累积
                    bonus = -penalty

                correction_bonus[kid] = correction_bonus.get(kid, 0.0) + bonus

        # Apply correction bonus to raw_scores
        for node_id in raw_scores:
            raw_scores[node_id] = max(0, raw_scores[node_id] - correction_bonus.get(node_id, 0.0))

        # Step 4: 归一化到 [0, 1]
        max_score = max(raw_scores.values()) if raw_scores else 1.0
        if max_score == 0:
            max_score = 1.0

        normalized = {nid: score / max_score for nid, score in raw_scores.items()}

        # Step 5: 找出薄弱节点（有错误记录的 + 受传播影响的）
        results = []
        for node_id, weakness in normalized.items():
            if weakness < 0.01:  # 忽略极小值
                continue

            node = self.kg.get_node(node_id)
            if not node:
                continue

            # 找薄弱根源
            root_cause = self._find_root_cause(node_id, decayed_weights, normalized)

            result = WeaknessResult(
                knowledge_id=node_id,
                knowledge_name=node["name"],
                weakness_score=round(weakness, 4),
                root_cause=root_cause,
                error_count=error_counts.get(node_id, 0),
                recent_errors=recent_errors.get(node_id, [])[:3],  # 最多展示3条
                suggestion=self._generate_suggestion(node_id, root_cause, node["name"], cause_counts.get(node_id, {})),
                error_cause_distribution=cause_counts.get(node_id, {}),
            )
            results.append(result)

        # 按薄弱度降序排列，取Top-K
        results.sort(key=lambda r: r.weakness_score, reverse=True)
        return results[:top_k]

    def _find_root_cause(
        self,
        node_id: str,
        decayed_weights: dict[str, float],
        normalized: dict[str, float],
    ) -> Optional[dict]:
        """找出薄弱根源节点和传播路径"""
        ancestors = self.kg.get_ancestors(node_id)
        if not ancestors:
            return None

        # 找祖先中权重最大的节点作为根源
        best_ancestor = None
        best_weight = 0.0

        for ancestor_id in ancestors:
            weight = decayed_weights.get(ancestor_id, 0.0)
            if weight > best_weight:
                best_weight = weight
                best_ancestor = ancestor_id

        if best_ancestor is None or best_ancestor == node_id:
            return None

        # 构建传播路径
        path = self._build_path(best_ancestor, node_id)

        # 计算根源贡献占比
        total_weakness = normalized.get(node_id, 0.0)
        root_weakness = normalized.get(best_ancestor, 0.0)
        contribution_ratio = round(root_weakness / total_weakness, 2) if total_weakness > 0 else 0.0

        root_node = self.kg.get_node(best_ancestor)
        return {
            "root_node": best_ancestor,
            "root_name": root_node["name"] if root_node else best_ancestor,
            "path": path,
            "propagation_type": "backward",
            "contribution_ratio": contribution_ratio,
        }

    def _build_path(self, from_id: str, to_id: str) -> list[str]:
        """构建从根源到当前节点的传播路径"""
        path = [from_id]
        current = from_id

        # 简化路径构建：通过prerequisites和parent关系
        visited = {from_id}
        max_depth = 10

        while current != to_id and len(path) < max_depth:
            node = self.kg.get_node(current)
            if not node:
                break

            # 优先查找prerequisites中指向to_id方向的节点
            children = self.kg.get_children(current)
            next_node = None

            for child_id in children:
                if child_id == to_id:
                    next_node = child_id
                    break
                # 检查child的子树是否包含to_id
                if self._is_ancestor_of(child_id, to_id) and child_id not in visited:
                    next_node = child_id
                    break

            # 也检查prerequisites指向的节点
            if next_node is None:
                target_node = self.kg.get_node(to_id)
                if target_node:
                    for prereq_id in target_node.get("prerequisites", []):
                        if prereq_id == current or self._is_ancestor_of(prereq_id, current):
                            # 找到路径中需要经过的中间节点
                            pass

            if next_node is None:
                # 直接跳到目标
                break

            path.append(next_node)
            visited.add(next_node)
            current = next_node

        if current != to_id and to_id not in path:
            path.append(to_id)

        # 将ID转为名称
        return [
            self.kg.get_node(nid)["name"] if self.kg.get_node(nid) else nid
            for nid in path
        ]

    def _is_ancestor_of(self, ancestor_id: str, descendant_id: str) -> bool:
        """检查ancestor_id是否是descendant_id的祖先"""
        descendants = self.kg.get_ancestors(descendant_id)
        return ancestor_id in descendants

    @staticmethod
    def _generate_suggestion(node_id: str, root_cause: Optional[dict], node_name: str, error_cause_distribution: dict = None) -> str:
        """生成改进建议"""
        if error_cause_distribution:
            top_cause = max(error_cause_distribution, key=error_cause_distribution.get)
            total_errors = sum(error_cause_distribution.values())
            top_ratio = error_cause_distribution[top_cause] / total_errors if total_errors > 0 else 0
            if top_ratio > 0.5:
                cause_advice = {
                    "计算粗心": f"建议进行计算专项训练，提高运算准确性",
                    "概念混淆": f"建议重新理解{node_name}的核心概念，梳理易混淆点",
                    "审题不清": f"建议培养审题习惯，标注题目关键条件",
                    "辅助线缺失": f"建议加强几何作图训练，掌握常见辅助线构造方法",
                    "逻辑跳步": f"建议养成逐步书写的习惯，每步都要有理有据",
                    "知识缺失": f"建议从基础开始系统复习{node_name}",
                }
                specific = cause_advice.get(top_cause, "")
                if specific:
                    return f"{node_name}薄弱（{top_cause}占比{top_ratio:.0%}），{specific}"
        if root_cause and root_cause.get("contribution_ratio", 0) > 0.3:
            root_name = root_cause.get("root_name", "")
            return f"根源在于{root_name}基础不牢，建议先巩固{root_name}再突破{node_name}"
        return f"建议重点复习{node_name}相关知识，多做针对性练习"


class ErrorMapper:
    """错题映射双通道：关键词规则 + LLM语义匹配"""

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg

    def map_by_keywords(self, error_text: str) -> list[str]:
        """通道1：关键词规则匹配"""
        matched = self.kg.search_by_keywords(error_text)
        if matched:
            logger.debug(f"[ErrorMapper] 关键词规则命中: {error_text[:30]}... → {[self.kg.get_node(m)['name'] for m in matched if self.kg.get_node(m)]}")
        return matched

    def auto_expand_rules(self, error_text: str, original_match: str, corrected_match: str) -> bool:
        """
        规则库自进化：当教师将LLM匹配的知识点修正为另一知识点时，
        自动提取错题中的关键词加入修正后知识点的规则集

        Args:
            error_text: 错题原文
            original_match: LLM原始匹配的知识点ID
            corrected_match: 教师修正后的知识点ID

        Returns:
            是否成功扩展了规则
        """
        if original_match == corrected_match:
            return False

        # 从错题文本中提取关键词（简单的分词策略）
        import re
        # 提取2-4字的中文词组
        chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,4}', error_text)

        # 获取修正后知识点的现有关键词
        corrected_node = self.kg.get_node(corrected_match)
        if not corrected_node:
            return False

        existing_keywords = set(corrected_node.get("keywords", []))

        # 找出与原始匹配知识点关键词的交集（即可能导致误匹配的关键词）
        original_node = self.kg.get_node(original_match)
        original_keywords = set(original_node.get("keywords", [])) if original_node else set()

        # 从错题中提取的关键词中，排除原始匹配的关键词
        new_keywords = []
        for word in chinese_words:
            if word not in existing_keywords and word not in original_keywords:
                # 检查这个词是否在错题中有意义（不是常见停用词）
                stop_words = {"已知", "求", "设", "则", "因为", "所以", "且", "或", "若", "则"}
                if word not in stop_words:
                    new_keywords.append(word)

        # 添加最有意义的1-2个关键词
        added = []
        for kw in new_keywords[:2]:
            existing_keywords.add(kw)
            added.append(kw)

        if added:
            # 更新知识图谱中的关键词
            self.kg._nodes[corrected_match]["keywords"] = list(existing_keywords)
            logger.info(f"[ErrorMapper] 规则自进化: 知识点'{corrected_node['name']}'新增关键词: {added}")
            return True

        return False

    async def map_by_llm(self, error_text: str, subject: str = "math") -> list[str]:
        """通道2：LLM语义匹配"""
        from app.llm_utils import parse_llm_json, get_siliconflow_client

        if not settings.SILICONFLOW_API_KEY:
            return []

        client = get_siliconflow_client()

        # 获取所有知识点名称供LLM选择
        all_nodes = self.kg.get_all_nodes()
        node_names = {nid: node["name"] for nid, node in all_nodes.items() if node["level"] >= 2}
        node_list = "\n".join([f"- {nid}: {name}" for nid, name in node_names.items()])

        prompt = f"""以下是一道数学错题，请判断它涉及的知识点。

## 错题内容
{error_text}

## 可选知识点列表
{node_list}

请从上述列表中选择最相关的1-3个知识点ID，输出JSON格式：
{{"matched": ["知识点ID1", "知识点ID2"]}}

只输出JSON，不要输出其他内容。"""

        try:
            response = await client.chat.completions.create(
                model="Qwen/Qwen2.5-7B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=256,
            )
            content = response.choices[0].message.content
            # 解析JSON
            data = parse_llm_json(content)
            return [mid for mid in data.get("matched", []) if mid in all_nodes]
        except Exception:
            pass

        return []

    async def map_error(self, error_text: str) -> list[str]:
        """双通道融合映射：关键词命中→直接采用；未命中→LLM兜底"""
        keyword_matches = self.map_by_keywords(error_text)
        if keyword_matches:
            return keyword_matches

        llm_matches = await self.map_by_llm(error_text)
        return llm_matches


class KnowledgeAttributionService:
    """知识归因服务 - 对外统一接口"""

    def __init__(self, kg: KnowledgeGraph | None = None, wkg: 'WritingKnowledgeGraph | None' = None):
        self.kg = kg or KnowledgeGraph()
        self.decay_propagate = DecayPropagate(self.kg)
        self.error_mapper = ErrorMapper(self.kg)
        self.wkg = wkg

    async def analyze(
        self,
        errors: list[ErrorEvent],
        reference_date: date | None = None,
        correction_records: list[dict] | None = None,
    ) -> AnalysisReport:
        """执行完整的知识归因分析"""

        # Step 1: DecayPropagate薄弱度计算
        weak_points = self.decay_propagate.analyze(errors, reference_date, correction_records=correction_records)

        # Step 2: 生成雷达图数据（一级维度）
        radar = {}
        radar_dims = self.kg.get_radar_dimensions()
        for dim in radar_dims:
            dim_id = dim["id"]
            dim_name = dim["name"]
            # 计算该维度下所有子节点的最大薄弱度
            max_weakness = 0.0
            for wp in weak_points:
                # 检查wp是否属于该维度
                node = self.kg.get_node(wp.knowledge_id)
                if node and self._is_under_dimension(wp.knowledge_id, dim_id):
                    max_weakness = max(max_weakness, wp.weakness_score)
            # 雷达图显示"掌握度"而非"薄弱度"，所以用1-薄弱度
            radar[dim_name] = round(1.0 - max_weakness, 2)

        # Step 3: 统计订正状态（PoC阶段简化）
        total_errors = len(errors)
        corrected = sum(1 for e in errors if e.error_weight < 1.0)

        return AnalysisReport(
            student_id="",
            analysis_date=(reference_date or date.today()).isoformat(),
            radar=radar,
            weak_points=weak_points,
            correction_status={
                "total_errors": total_errors,
                "corrected": corrected,
                "uncorrected": total_errors - corrected,
                "correction_rate": round(corrected / total_errors, 2) if total_errors > 0 else 0.0,
            },
        )

    def _is_under_dimension(self, node_id: str, dimension_id: str) -> bool:
        """检查node_id是否属于dimension_id的子树"""
        if node_id == dimension_id:
            return True
        ancestors = self.kg.get_ancestors(node_id)
        return dimension_id in ancestors


# ===== 写作归因服务 =====

from app.writing_graph import (
    WritingKnowledgeGraph,
    WRITING_ERROR_CAUSE_MAPPING,
    WRITING_ERROR_CAUSE_FINE_MAPPING,
    WRITING_ERROR_SUGGESTIONS,
)


@dataclass
class WritingErrorEvent:
    """写作错因事件"""
    error_cause: str         # 错因标签：素材匮乏|逻辑断层|修辞单一|偏题跑题|书写潦草
    error_weight: float      # 错误严重度 1.0=严重, 0.5=轻微
    timestamp: date          # 错误发生日期
    essay_title: str = ""    # 作文题目（用于展示）


@dataclass
class WritingWeaknessResult:
    """写作单项薄弱度结果"""
    dimension_id: str        # 一级维度ID（theme/structure/expression/writing_norm）
    dimension_name: str      # 维度名称
    weakness_score: float    # 归一化薄弱度 [0, 1]
    sub_weaknesses: list[dict] = field(default_factory=list)  # 子能力薄弱详情
    error_causes: list[str] = field(default_factory=list)     # 涉及的错因标签
    suggestion: str = ""


@dataclass
class WritingAnalysisReport:
    """写作学情分析报告"""
    student_id: str
    analysis_date: str
    radar: dict[str, float]                  # 一级维度 → 掌握度 (1 - 薄弱度)
    weak_dimensions: list[WritingWeaknessResult]
    error_cause_distribution: dict[str, int] # 错因标签出现次数统计
    overall_suggestion: str = ""


class WritingAttributionService:
    """
    写作归因服务 - 复用 DecayPropagate 算法但使用 WritingKnowledgeGraph

    将写作错因标签（素材匮乏、逻辑断层等）映射到 DAG 节点后，
    调用 DecayPropagate 进行后向传播与前向聚合分析，
    最终生成"写作能力雷达"维度的学情报告。
    """

    def __init__(self, wkg: WritingKnowledgeGraph | None = None):
        self.wkg = wkg or WritingKnowledgeGraph()
        self.decay_propagate = DecayPropagate(self.wkg)

    async def analyze(
        self,
        writing_errors: list[WritingErrorEvent],
        student_id: str = "",
        reference_date: date | None = None,
    ) -> WritingAnalysisReport:
        """
        执行写作归因分析

        Args:
            writing_errors: 写作错因事件列表
            student_id: 学生ID
            reference_date: 参考日期（默认今天）

        Returns:
            WritingAnalysisReport 写作学情分析报告
        """
        if reference_date is None:
            reference_date = date.today()

        # Step 1: 将写作错因标签映射为 DAG 节点的 ErrorEvent 列表
        mapped_errors: list[ErrorEvent] = []
        error_cause_counts: dict[str, int] = {}

        for we in writing_errors:
            cause = we.error_cause
            error_cause_counts[cause] = error_cause_counts.get(cause, 0) + 1

            # 细粒度映射：一个错因可能对应多个DAG节点
            node_ids = WritingKnowledgeGraph.map_error_cause_to_nodes(cause)
            if not node_ids:
                # 回退到一级维度映射
                dim_id = WritingKnowledgeGraph.map_error_cause_to_dimension(cause)
                if dim_id:
                    node_ids = [dim_id]

            for node_id in node_ids:
                mapped_errors.append(ErrorEvent(
                    knowledge_node_id=node_id,
                    error_weight=we.error_weight / len(node_ids),  # 分摊权重
                    timestamp=we.timestamp,
                    question_content=we.essay_title[:50],
                    error_cause=cause,
                ))

        if not mapped_errors:
            # 没有可映射的错因，返回空报告
            radar_dims = self.wkg.get_radar_dimensions()
            empty_radar = {dim["name"]: 1.0 for dim in radar_dims}
            return WritingAnalysisReport(
                student_id=student_id,
                analysis_date=reference_date.isoformat(),
                radar=empty_radar,
                weak_dimensions=[],
                error_cause_distribution=error_cause_counts,
                overall_suggestion="暂无写作错因数据，继续保持良好的写作习惯",
            )

        # Step 2: 调用 DecayPropagate 进行薄弱度分析
        weak_points = self.decay_propagate.analyze(
            errors=mapped_errors,
            reference_date=reference_date,
            top_k=20,  # 写作图谱节点少，取全部
        )

        # Step 3: 生成写作能力雷达（一级维度）
        radar = {}
        radar_dims = self.wkg.get_radar_dimensions()
        for dim in radar_dims:
            dim_id = dim["id"]
            dim_name = dim["name"]
            # 该维度下所有子节点的最大薄弱度
            max_weakness = 0.0
            for wp in weak_points:
                if self._is_under_dimension(wp.knowledge_id, dim_id):
                    max_weakness = max(max_weakness, wp.weakness_score)
            # 雷达图展示"掌握度"而非"薄弱度"
            radar[dim_name] = round(1.0 - max_weakness, 2)

        # Step 4: 按一级维度聚合薄弱结果
        weak_dimensions = self._aggregate_by_dimension(
            weak_points, error_cause_counts
        )

        # Step 5: 生成综合建议
        overall_suggestion = self._generate_overall_suggestion(
            radar, error_cause_counts
        )

        return WritingAnalysisReport(
            student_id=student_id,
            analysis_date=reference_date.isoformat(),
            radar=radar,
            weak_dimensions=weak_dimensions,
            error_cause_distribution=error_cause_counts,
            overall_suggestion=overall_suggestion,
        )

    def _is_under_dimension(self, node_id: str, dimension_id: str) -> bool:
        """检查node_id是否属于dimension_id的子树"""
        if node_id == dimension_id:
            return True
        ancestors = self.wkg.get_ancestors(node_id)
        return dimension_id in ancestors

    def _aggregate_by_dimension(
        self,
        weak_points: list[WeaknessResult],
        error_cause_counts: dict[str, int],
    ) -> list[WritingWeaknessResult]:
        """按一级维度聚合薄弱结果"""
        dim_data: dict[str, dict] = {}

        for wp in weak_points:
            # 找到该节点所属的一级维度
            node = self.wkg.get_node(wp.knowledge_id)
            if not node:
                continue

            # 向上追溯到一级维度
            dim_id = wp.knowledge_id
            current = node
            while current.get("parent_id") and current.get("parent_id") != "root":
                dim_id = current["parent_id"]
                current = self.wkg.get_node(dim_id)

            if current.get("parent_id") != "root":
                # 本身就是一级维度
                if node.get("parent_id") == "root":
                    dim_id = wp.knowledge_id
                else:
                    continue

            if dim_id not in dim_data:
                dim_node = self.wkg.get_node(dim_id)
                dim_data[dim_id] = {
                    "dimension_name": dim_node["name"] if dim_node else dim_id,
                    "weakness_score": 0.0,
                    "sub_weaknesses": [],
                    "error_causes": set(),
                }

            # 更新维度薄弱度（取最大值）
            dim_data[dim_id]["weakness_score"] = max(
                dim_data[dim_id]["weakness_score"], wp.weakness_score
            )

            # 收集子能力薄弱详情
            dim_data[dim_id]["sub_weaknesses"].append({
                "node_id": wp.knowledge_id,
                "node_name": wp.knowledge_name,
                "weakness_score": wp.weakness_score,
                "error_count": wp.error_count,
                "error_cause_distribution": wp.error_cause_distribution,
                "root_cause": wp.root_cause,
            })

            # 收集该维度涉及的错因标签
            for cause in wp.error_cause_distribution:
                dim_data[dim_id]["error_causes"].add(cause)

        # 构建结果列表
        results = []
        for dim_id, data in dim_data.items():
            # 生成该维度的建议
            suggestion = self._generate_dimension_suggestion(
                dim_id, data["error_causes"], data["weakness_score"]
            )

            results.append(WritingWeaknessResult(
                dimension_id=dim_id,
                dimension_name=data["dimension_name"],
                weakness_score=round(data["weakness_score"], 4),
                sub_weaknesses=sorted(
                    data["sub_weaknesses"],
                    key=lambda x: x["weakness_score"],
                    reverse=True,
                ),
                error_causes=sorted(data["error_causes"]),
                suggestion=suggestion,
            ))

        # 按薄弱度降序排列
        results.sort(key=lambda r: r.weakness_score, reverse=True)
        return results

    @staticmethod
    def _generate_dimension_suggestion(
        dimension_id: str,
        error_causes: set[str],
        weakness_score: float,
    ) -> str:
        """生成单个维度的改进建议"""
        if not error_causes:
            return ""

        # 取最主要的错因标签
        main_cause = sorted(error_causes)[0]
        base_suggestion = WRITING_ERROR_SUGGESTIONS.get(main_cause, "")

        dim_names = {
            "theme": "审题立意",
            "structure": "结构组织",
            "expression": "语言表达",
            "writing_norm": "书写规范",
        }
        dim_name = dim_names.get(dimension_id, dimension_id)

        if weakness_score > 0.7:
            prefix = f"{dim_name}方面存在明显薄弱（{','.join(error_causes)}），需重点突破。"
        elif weakness_score > 0.4:
            prefix = f"{dim_name}方面有提升空间（{','.join(error_causes)}），建议针对性练习。"
        else:
            prefix = f"{dim_name}方面表现尚可，但仍需注意{','.join(error_causes)}问题。"

        return f"{prefix}{base_suggestion}" if base_suggestion else prefix

    @staticmethod
    def _generate_overall_suggestion(
        radar: dict[str, float],
        error_cause_counts: dict[str, int],
    ) -> str:
        """生成综合建议"""
        if not radar:
            return "暂无数据"

        # 找出最薄弱的维度
        sorted_dims = sorted(radar.items(), key=lambda x: x[1])
        weakest_dim = sorted_dims[0]

        # 找出出现最多的错因
        if error_cause_counts:
            top_cause = max(error_cause_counts, key=error_cause_counts.get)
            top_suggestion = WRITING_ERROR_SUGGESTIONS.get(top_cause, "")
        else:
            top_cause = ""
            top_suggestion = ""

        if weakest_dim[1] < 0.5:
            overall = (
                f"写作能力整体有待加强，最薄弱维度为'{weakest_dim[0]}'"
                f"（掌握度{weakest_dim[1]:.0%}），"
            )
        elif weakest_dim[1] < 0.8:
            overall = (
                f"写作能力总体中等，'{weakest_dim[0]}'维度需提升"
                f"（掌握度{weakest_dim[1]:.0%}），"
            )
        else:
            overall = "写作能力整体良好，各维度掌握度较高，"

        if top_cause:
            overall += f"最突出的问题是'{top_cause}'（出现{error_cause_counts[top_cause]}次）。"
        else:
            overall += "继续巩固提升。"

        if top_suggestion:
            overall += f"\n{top_suggestion}"

        return overall
