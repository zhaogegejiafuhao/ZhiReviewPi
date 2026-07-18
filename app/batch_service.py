"""
希沃智教π 批量异步智能调度服务 (Phase 2 - 7.2.4)

核心功能：
1. 班级批量批改专属队列
2. 按图片清晰度（OCR置信度）、题型优先级排序
3. 优先批改清晰简单作业，低质量模糊图片延后
4. 前端实时展示批量进度条

调度策略：
- 优先级 = OCR置信度权重(0.6) + 题型简单度权重(0.3) + 图片大小权重(0.1)
- OCR置信度：图片越大 -> 可能越清晰 -> 优先级越高
- 题型简单度：题目越短 -> 可能越简单 -> 优先级越高
- 图片大小：大图片可能包含更多有效信息
"""
import asyncio
import uuid
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class BatchTask:
    """批量批改中的单个任务

    Attributes:
        task_id: 任务唯一标识
        homework_id: 作业ID
        student_id: 学生ID
        question: 题目文本
        standard_answer: 标准答案
        total_score: 题目总分
        image_bytes: 学生手写图片字节
        priority: 优先级分数，越高越先处理
        ocr_confidence: OCR预估置信度（基于图片大小简单预估）
        status: 任务状态 pending/processing/completed/failed
        subject: 学科（默认math）
        grade: 年级（默认7）
        result: 批改结果（完成后填充）
        error_message: 失败原因（失败时填充）
    """
    task_id: str
    homework_id: str
    student_id: str
    question: str
    standard_answer: str
    total_score: int
    image_bytes: bytes
    priority: float = 0.0
    ocr_confidence: float = 0.0
    status: str = "pending"
    subject: str = "math"
    grade: int = 7
    result: dict | None = None
    error_message: str = ""


@dataclass
class BatchJob:
    """批量批改作业

    Attributes:
        batch_id: 批量任务唯一标识
        total_count: 总任务数
        completed_count: 已完成数
        failed_count: 失败数
        status: 批量任务状态 pending/processing/completed
        tasks: 排序后的任务列表
        results: 已完成的批改结果列表
        created_at: 创建时间
    """
    batch_id: str
    total_count: int
    completed_count: int = 0
    failed_count: int = 0
    status: str = "pending"
    tasks: list[BatchTask] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    created_at: str = ""


class BatchGradingService:
    """批量异步智能调度服务

    调度策略：
    1. 创建批量任务时，为每个子任务预估优先级
    2. 按优先级降序排列，高优先级先处理
    3. 优先级计算：
       - OCR预估置信度（基于图片大小）：权重 0.6
         图片越大 -> 可能越清晰 -> 置信度预估越高
       - 题型简单度（基于题目长度）：权重 0.3
         题目越短 -> 可能越简单 -> 优先级越高
       - 图片大小归一化分：权重 0.1
         大图片可能包含更多有效信息
    4. 逐个执行批改，更新进度，支持前端轮询查询
    """

    # 图片大小与置信度的映射阈值（字节）
    _SIZE_THRESHOLDS = {
        "high": 200_000,    # >200KB 视为高质量图片
        "medium": 50_000,   # 50KB-200KB 中等质量
        "low": 0,           # <50KB 低质量
    }

    # 图片大小归一化的最大值（1MB以上视为满分）
    _MAX_IMAGE_SIZE = 1_000_000

    def __init__(self):
        self._jobs: dict[str, BatchJob] = {}

    def create_batch(self, tasks_data: list[dict]) -> BatchJob:
        """创建批量批改任务

        Args:
            tasks_data: 批量任务数据列表，每项包含：
                - homework_id: 作业ID
                - student_id: 学生ID
                - question: 题目文本
                - standard_answer: 标准答案
                - total_score: 题目总分
                - image_bytes: 学生手写图片字节
                - subject: 学科（可选，默认math）
                - grade: 年级（可选，默认7）

        Returns:
            BatchJob: 创建的批量任务对象（已按优先级排序）
        """
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        tasks: list[BatchTask] = []

        for i, item in enumerate(tasks_data):
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            image_bytes = item.get("image_bytes", b"")
            question = item.get("question", "")

            # 输入校验：跳过无效条目
            if not image_bytes:
                logger.warning(f"[BatchGradingService] 任务#{i}缺少图片数据，跳过")
                continue
            if not question:
                logger.warning(f"[BatchGradingService] 任务#{i}缺少题目文本，跳过")
                continue

            # 预估OCR置信度（基于图片大小）
            ocr_confidence = self._estimate_ocr_confidence(image_bytes)

            # 计算优先级
            priority = self._calculate_priority(
                ocr_confidence=ocr_confidence,
                question=question,
                image_size=len(image_bytes),
            )

            task = BatchTask(
                task_id=task_id,
                homework_id=item.get("homework_id", ""),
                student_id=item.get("student_id", ""),
                question=question,
                standard_answer=item.get("standard_answer", ""),
                total_score=item.get("total_score", 5),
                image_bytes=image_bytes,
                priority=priority,
                ocr_confidence=ocr_confidence,
                subject=item.get("subject", "math"),
                grade=item.get("grade", 7),
            )
            tasks.append(task)

        # 按优先级降序排序（高优先级先处理）
        tasks.sort(key=lambda t: t.priority, reverse=True)

        job = BatchJob(
            batch_id=batch_id,
            total_count=len(tasks),
            tasks=tasks,
            created_at=datetime.now().isoformat(),
        )
        self._jobs[batch_id] = job
        logger.info(f"[BatchGradingService] 创建批量任务 batch_id={batch_id}, "
                     f"total={len(tasks)}, 优先级范围=[{tasks[-1].priority:.2f}, {tasks[0].priority:.2f}]"
                     if tasks else "")
        return job

    async def execute_batch(self, batch_id: str) -> BatchJob:
        """执行批量批改（按优先级顺序逐个处理）

        Args:
            batch_id: 批量任务ID

        Returns:
            BatchJob: 执行完成后的批量任务对象

        Raises:
            ValueError: 批量任务不存在
        """
        job = self._jobs.get(batch_id)
        if not job:
            raise ValueError(f"批量任务不存在: {batch_id}")

        if job.status == "processing":
            return job

        job.status = "processing"
        logger.info(f"[BatchGradingService] 开始执行批量任务 batch_id={batch_id}, total={job.total_count}")

        # 导入批改所需服务（延迟导入避免循环依赖）
        from app.ocr import OCRService
        from app.grader import GradingService
        from app.geometry_analyzer import is_geometry_question

        ocr_service = OCRService()
        grading_service = GradingService()

        for i, task in enumerate(job.tasks):
            if task.status in ("completed", "failed"):
                continue

            task.status = "processing"
            t0 = time.time()
            logger.info(f"[BatchGradingService] [{i+1}/{job.total_count}] 处理任务 {task.task_id}, "
                        f"priority={task.priority:.2f}, student={task.student_id}")

            try:
                # Step 1: OCR识别
                ocr_result = await ocr_service.recognize(task.image_bytes)
                actual_confidence = ocr_result.confidence
                logger.info(f"[BatchGradingService]   OCR完成 ({time.time()-t0:.1f}s), "
                            f"confidence={actual_confidence:.2f}, "
                            f"预估={task.ocr_confidence:.2f}")

                # Step 2: 完整批改流程（复用GradingService）
                grading_result = await grading_service.grade_math(
                    question=task.question,
                    standard_answer=task.standard_answer,
                    student_answer_ocr=ocr_result.text,
                    total_score=task.total_score,
                    image_bytes=task.image_bytes,
                    confidence=actual_confidence,
                )

                # 组装结果
                task.result = {
                    "task_id": task.task_id,
                    "homework_id": task.homework_id,
                    "student_id": task.student_id,
                    "status": "completed",
                    "review_status": "pending_review",
                    "question": task.question,
                    "standard_answer": task.standard_answer,
                    "ocr_result": {
                        "text": ocr_result.text,
                        "confidence": actual_confidence,
                        "engines_used": ocr_result.engines_used,
                    },
                    "rubric": grading_result.get("rubric", {}),
                    "grading": grading_result.get("grading", {}),
                    "comment": grading_result.get("comment", ""),
                    "suggested_score": grading_result.get("suggested_score", 0),
                    "max_score": grading_result.get("max_score", task.total_score),
                    "confidence": actual_confidence,
                    "flagged": grading_result.get("flagged", False),
                    "model_key": grading_result.get("model_key", "standard"),
                }

                # 几何题辅助线分析结果
                if grading_result.get("geometry_analysis"):
                    task.result["geometry_analysis"] = grading_result["geometry_analysis"]

                task.status = "completed"
                job.completed_count += 1
                job.results.append(task.result)

                logger.info(f"[BatchGradingService]   批改完成 ({time.time()-t0:.1f}s), "
                            f"score={grading_result.get('suggested_score', 0)}/{task.total_score}")

            except Exception as e:
                task.status = "failed"
                task.error_message = f"{type(e).__name__}: {e}"
                job.failed_count += 1
                job.results.append({
                    "task_id": task.task_id,
                    "homework_id": task.homework_id,
                    "student_id": task.student_id,
                    "status": "failed",
                    "error": task.error_message,
                })
                logger.error(f"[BatchGradingService]   批改失败: {task.error_message}")

            # 每个任务之间短暂间隔，避免API限流
            if i < job.total_count - 1:
                await asyncio.sleep(0.1)

        job.status = "completed"
        logger.info(f"[BatchGradingService] 批量任务完成 batch_id={batch_id}, "
                    f"completed={job.completed_count}, failed={job.failed_count}")
        return job

    def get_batch_status(self, batch_id: str) -> dict | None:
        """获取批量任务进度

        Args:
            batch_id: 批量任务ID

        Returns:
            dict | None: 进度信息，包含：
                - batch_id: 批量任务ID
                - total: 总任务数
                - completed: 已完成数
                - failed: 失败数
                - progress_pct: 进度百分比（0-100）
                - status: 批量任务状态
                - current_task: 当前正在处理的任务信息（如有）
                - results: 已完成的批改结果列表
                如果批量任务不存在返回None
        """
        job = self._jobs.get(batch_id)
        if not job:
            return None

        progress_pct = round(
            (job.completed_count + job.failed_count) / job.total_count * 100, 1
        ) if job.total_count > 0 else 0

        # 当前正在处理的任务
        current_task = None
        for task in job.tasks:
            if task.status == "processing":
                current_task = {
                    "task_id": task.task_id,
                    "student_id": task.student_id,
                    "homework_id": task.homework_id,
                    "priority": task.priority,
                    "ocr_confidence": task.ocr_confidence,
                }
                break

        # 待处理任务数
        pending_count = sum(1 for t in job.tasks if t.status == "pending")

        return {
            "batch_id": job.batch_id,
            "total": job.total_count,
            "completed": job.completed_count,
            "failed": job.failed_count,
            "pending": pending_count,
            "progress_pct": progress_pct,
            "status": job.status,
            "current_task": current_task,
            "created_at": job.created_at,
        }

    def get_batch_results(self, batch_id: str) -> list[dict] | None:
        """获取批量任务全部结果

        Args:
            batch_id: 批量任务ID

        Returns:
            list[dict] | None: 批改结果列表，批量任务不存在返回None
        """
        job = self._jobs.get(batch_id)
        if not job:
            return None
        return job.results

    def _estimate_ocr_confidence(self, image_bytes: bytes) -> float:
        """基于图片大小预估OCR置信度

        Args:
            image_bytes: 图片字节

        Returns:
            float: 预估置信度（0.0-1.0）
        """
        size = len(image_bytes)
        if size >= self._SIZE_THRESHOLDS["high"]:
            return 0.85 + min(0.10, (size - self._SIZE_THRESHOLDS["high"]) / 1_000_000 * 0.10)
        elif size >= self._SIZE_THRESHOLDS["medium"]:
            return 0.60 + (size - self._SIZE_THRESHOLDS["medium"]) / (self._SIZE_THRESHOLDS["high"] - self._SIZE_THRESHOLDS["medium"]) * 0.25
        elif size >= self._SIZE_THRESHOLDS["low"]:
            return 0.30 + size / self._SIZE_THRESHOLDS["medium"] * 0.30
        else:
            return 0.10

    def _calculate_priority(
        self,
        ocr_confidence: float,
        question: str,
        image_size: int,
    ) -> float:
        """计算任务优先级

        优先级 = OCR置信度权重(0.6) + 题型简单度权重(0.3) + 图片大小归一化权重(0.1)

        Args:
            ocr_confidence: OCR预估置信度（0.0-1.0）
            question: 题目文本
            image_size: 图片字节数

        Returns:
            float: 优先级分数（0.0-1.0），越高越先处理
        """
        # 题型简单度：题目越短越简单
        question_length = len(question)
        if question_length <= 20:
            simplicity = 1.0
        elif question_length <= 50:
            simplicity = 0.8
        elif question_length <= 100:
            simplicity = 0.6
        elif question_length <= 200:
            simplicity = 0.4
        else:
            simplicity = 0.2

        # 图片大小归一化
        size_score = min(1.0, image_size / self._MAX_IMAGE_SIZE) if self._MAX_IMAGE_SIZE > 0 else 0.0

        priority = (
            ocr_confidence * 0.6
            + simplicity * 0.3
            + size_score * 0.1
        )
        return round(priority, 4)


# 全局单例
batch_grading_service = BatchGradingService()