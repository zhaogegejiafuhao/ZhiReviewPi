"""
希沃智教π 订正闭环 + 可解释性模块

订正闭环：学生提交订正 → 二次批改 → 前后对比 → 学情更新
可解释性：OCR区域高亮 + 推理步骤标注 + rubric条目引用 + reasoning_trace
"""
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.attribution import ErrorEvent, KnowledgeAttributionService
from app.grader import GradingService
from app.ocr import OCRService


@dataclass
class CorrectionComparison:
    """订正前后对比"""
    question_id: str
    original_score: float
    correction_score: float
    max_score: float
    improved: bool
    remaining_errors: list[str]          # 仍存在的错误步骤ID
    new_comment: str


@dataclass
class CorrectionResult:
    """订正二次批改结果"""
    correction_id: str
    original_task_id: str
    student_id: str
    status: str                          # processing | completed
    comparisons: list[CorrectionComparison]
    knowledge_update: dict               # {weakened, strengthened, still_weak}


@dataclass
class ExplainAnnotation:
    """可解释性标注"""
    type: str                            # ocr_region | error_highlight | rubric_ref
    bbox: list[float]                    # [x1, y1, x2, y2]
    label: str
    confidence: Optional[float] = None
    color: str = "green"                 # green=高置信, yellow=中, red=低
    step_id: Optional[str] = None
    rubric_text: Optional[str] = None
    matched: Optional[bool] = None


@dataclass
class ReasoningStep:
    """推理步骤可解释性"""
    step: int
    observation: str                     # AI观察到什么
    judgment: str                        # AI判定结果
    rubric_ref: Optional[str] = None     # 引用的rubric条目


@dataclass
class ExplainResult:
    """可解释性完整结果"""
    task_id: str
    image_url: str
    annotations: list[ExplainAnnotation]
    reasoning_trace: list[ReasoningStep]


class CorrectionService:
    """订正闭环服务"""

    def __init__(self):
        self.grading_service = GradingService()
        self.ocr_service = OCRService()
        self.attribution_service = KnowledgeAttributionService()

    async def submit_correction(
        self,
        original_task_id: str,
        student_id: str,
        corrections: list[dict],
        original_results: dict,
    ) -> CorrectionResult:
        """
        学生提交订正作业，触发二次批改

        Args:
            original_task_id: 原始批改任务ID
            student_id: 学生ID
            corrections: [{"question_id": "q1", "type": "image", "url": "...", "image_bytes": bytes}]
            original_results: 原始批改结果（从tasks_db获取）
        """
        correction_id = f"corr_{uuid.uuid4().hex[:8]}"
        comparisons = []
        new_errors = []

        for correction in corrections:
            question_id = correction["question_id"]
            image_bytes = correction.get("image_bytes", b"")

            # 获取原始评分
            original_grading = original_results.get("grading", {})
            original_score = original_grading.get("total_score", 0)
            max_score = original_grading.get("max_score", 5)
            original_rubric = original_results.get("rubric", {})

            # OCR识别订正作业
            ocr_result = await self.ocr_service.recognize(image_bytes)

            # 基于相同rubric进行二次批改
            question = original_results.get("question", "")
            standard_answer = original_results.get("standard_answer", "")

            if original_rubric and ocr_result.text:
                grading_result = await self.grading_service.math_grader.grade(
                    question=question,
                    standard_answer=standard_answer,
                    student_answer_ocr=ocr_result.text,
                    rubric=original_rubric,
                )
                correction_score = grading_result.get("total_score", 0)

                # 找出仍存在的错误步骤
                remaining_errors = [
                    s["step_id"] for s in grading_result.get("steps", [])
                    if not s.get("correct", True)
                ]

                # 如果仍有错误，记录为新的ErrorEvent
                if correction_score < max_score:
                    knowledge_points = grading_result.get("knowledge_points", [])
                    for kp in knowledge_points:
                        new_errors.append(ErrorEvent(
                            knowledge_node_id=kp,
                            error_weight=(max_score - correction_score) / max_score,
                            timestamp=date.today(),
                            question_content=f"订正后仍有错误: {question[:30]}",
                        ))
            else:
                correction_score = original_score
                remaining_errors = []

            improved = correction_score > original_score
            comparisons.append(CorrectionComparison(
                question_id=question_id,
                original_score=original_score,
                correction_score=correction_score,
                max_score=max_score,
                improved=improved,
                remaining_errors=remaining_errors,
                new_comment=f"订正后得分从{original_score}提升至{correction_score}" if improved
                           else f"订正后仍有错误，建议继续复习相关知识点",
            ))

        # 学情更新：基于二次批改结果更新知识归因
        knowledge_update = {"weakened": [], "strengthened": [], "still_weak": []}
        for comp in comparisons:
            if comp.improved:
                # 知识点薄弱度降低
                original_grading = original_results.get("grading", {})
                for kp in original_grading.get("knowledge_points", []):
                    if kp not in knowledge_update["strengthened"]:
                        knowledge_update["strengthened"].append(kp)
            if comp.remaining_errors:
                knowledge_update["still_weak"].extend(comp.remaining_errors)

        return CorrectionResult(
            correction_id=correction_id,
            original_task_id=original_task_id,
            student_id=student_id,
            status="completed",
            comparisons=comparisons,
            knowledge_update=knowledge_update,
        )


class ExplainabilityService:
    """可解释性服务"""

    @staticmethod
    def generate_explain(task_result: dict) -> ExplainResult:
        """
        从批改结果生成可解释性数据

        Args:
            task_result: 批改结果（从tasks_db获取）
        """
        annotations = []
        reasoning_trace = []

        ocr_result = task_result.get("ocr_result", {})
        grading_result = task_result.get("grading", {})
        rubric = task_result.get("rubric", {})
        rubric_steps = rubric.get("steps", [])

        # 1. OCR区域高亮标注
        for region in ocr_result.get("regions", []):
            bbox = region.get("bbox", [0, 0, 0, 0])
            text = region.get("text", "")
            confidence = region.get("confidence", 0.5)

            if confidence >= 0.9:
                color = "green"
            elif confidence >= 0.7:
                color = "yellow"
            else:
                color = "red"

            # 尝试匹配到grading的step
            matched_step = None
            for step in grading_result.get("steps", []):
                step_content = step.get("content", "")
                if step_content and step_content in text:
                    matched_step = step.get("step_id")
                    break

            annotations.append(ExplainAnnotation(
                type="ocr_region",
                bbox=bbox,
                label=text,
                confidence=confidence,
                color=color,
                step_id=matched_step,
            ))

        # 2. 错误步骤高亮
        for step in grading_result.get("steps", []):
            if not step.get("correct", True):
                step_content = step.get("content", "")
                # 步骤有内容：找对应OCR区域
                if step_content:
                    for region in ocr_result.get("regions", []):
                        if step_content in region.get("text", ""):
                            annotations.append(ExplainAnnotation(
                                type="error_highlight",
                                bbox=region.get("bbox", [0, 0, 0, 0]),
                                label=f"错误：{step.get('error_reason', step_content)}",
                                color="red",
                                step_id=step.get("step_id"),
                            ))
                            break
                else:
                    # 步骤缺失（学生未写）：标注为缺失
                    rubric_ref = step.get("rubric_ref", "")
                    rubric_desc = ""
                    for rs in rubric_steps:
                        if rs.get("step_id") == rubric_ref:
                            rubric_desc = rs.get("description", "")
                            break
                    annotations.append(ExplainAnnotation(
                        type="error_highlight",
                        bbox=[0, 0, 0, 0],
                        label=f"缺失步骤：{rubric_desc or rubric_ref} ({step.get('error_reason', '未作答')})",
                        color="red",
                        step_id=step.get("step_id"),
                    ))

        # 3. Rubric引用标注
        for step in grading_result.get("steps", []):
            rubric_ref = step.get("rubric_ref", "")
            if rubric_ref:
                # 查找rubric中的对应步骤描述
                rubric_step = next(
                    (rs for rs in rubric_steps if rs.get("step_id") == rubric_ref), None
                )
                if rubric_step:
                    annotations.append(ExplainAnnotation(
                        type="rubric_ref",
                        bbox=[0, 0, 0, 0],  # rubric引用不需要bbox
                        label=f"评分标准: {rubric_step.get('description', '')} ({rubric_step.get('score', 0)}分)",
                        step_id=rubric_ref,
                        rubric_text=rubric_step.get("description", ""),
                        matched=step.get("correct", False),
                    ))

        # 4. 构建推理链
        step_num = 0
        for step in grading_result.get("steps", []):
            step_num += 1
            observation = f"识别到'{step.get('content', '')}'"
            judgment = "正确" if step.get("correct", True) else f"错误({step.get('error_reason', '未知原因')})"

            reasoning_trace.append(ReasoningStep(
                step=step_num,
                observation=observation,
                judgment=judgment,
                rubric_ref=step.get("rubric_ref"),
            ))

        return ExplainResult(
            task_id=task_result.get("task_id", ""),
            image_url="",  # 前端自行拼接
            annotations=annotations,
            reasoning_trace=reasoning_trace,
        )


def tier_classify(weakness_scores: dict[str, float]) -> dict[str, str]:
    """
    基于DecayPropagate薄弱度自动分层

    Args:
        weakness_scores: {knowledge_node_id: weakness_score} 归一化薄弱度

    Returns:
        {knowledge_node_id: tier} tier: "优等生" | "中等生" | "学困生"
    """
    tiers = {}
    for kid, score in weakness_scores.items():
        if score < 0.3:
            tiers[kid] = "优等生"
        elif score < 0.7:
            tiers[kid] = "中等生"
        else:
            tiers[kid] = "学困生"
    return tiers


def get_push_strategy(tier: str, error_question: str = "") -> dict:
    """根据分层返回推送策略"""
    strategies = {
        "优等生": {
            "mode": "root_cause",
            "description": "只推送根源薄弱母题，减少重复刷题",
            "exercise_count": 1,
            "exercise_type": "根源母题",
            "support": "自主订正即可",
        },
        "中等生": {
            "mode": "variant",
            "description": "错题 + 同类变式各2道",
            "exercise_count": 4,
            "exercise_type": "错题原题 + 同类变式",
            "support": "AI提示+同类变式练习",
        },
        "学困生": {
            "mode": "scaffolded",
            "description": "错题 + 基础铺垫小题，配套微课链接",
            "exercise_count": 6,
            "exercise_type": "基础铺垫 + 错题原题 + 进阶",
            "support": "分步提示 + 微课视频 + 一对一辅导建议",
        },
    }
    return strategies.get(tier, strategies["中等生"])


class PersonalizedCorrectionService:
    """分层个性化订正推送服务"""

    def __init__(self):
        self.correction_service = CorrectionService()
        from app.attribution import KnowledgeAttributionService
        self.attribution_service = KnowledgeAttributionService()

    async def get_personalized_tasks(
        self,
        student_id: str,
        errors: list,
        correction_records: list | None = None,
    ) -> dict:
        """生成分层个性化订正任务"""
        from datetime import date

        # Step 1: 获取薄弱度
        report = await self.attribution_service.analyze(
            errors=errors,
            reference_date=date.today(),
            correction_records=correction_records,
        )

        # Step 2: 构建薄弱度映射
        weakness_scores = {
            wp.knowledge_id: wp.weakness_score
            for wp in report.weak_points
        }

        # Step 3: 分层
        tiers = tier_classify(weakness_scores)

        # Step 4: 生成个性化任务
        tasks = []
        for kid, tier in tiers.items():
            strategy = get_push_strategy(tier)
            node = self.attribution_service.kg.get_node(kid)
            wp = next((w for w in report.weak_points if w.knowledge_id == kid), None)

            tasks.append({
                "knowledge_id": kid,
                "knowledge_name": node["name"] if node else kid,
                "tier": tier,
                "weakness_score": weakness_scores.get(kid, 0),
                "strategy": strategy,
                "error_cause_distribution": wp.error_cause_distribution if wp else {},
                "suggestion": wp.suggestion if wp else "",
                "recent_errors": wp.recent_errors if wp else [],
            })

        # 按薄弱度排序
        tasks.sort(key=lambda t: t["weakness_score"], reverse=True)

        return {
            "student_id": student_id,
            "total_weak_points": len(tasks),
            "tier_summary": {
                "优等生": sum(1 for t in tasks if t["tier"] == "优等生"),
                "中等生": sum(1 for t in tasks if t["tier"] == "中等生"),
                "学困生": sum(1 for t in tasks if t["tier"] == "学困生"),
            },
            "tasks": tasks,
        }
