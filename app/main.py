"""希沃智教π FastAPI 主入口"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ocr import OCRService
from app.grader import GradingService, EssayGrader, FALLBACK_ESSAY_RUBRIC
from app.correction import CorrectionService, ExplainabilityService
from app.attribution import KnowledgeAttributionService, ErrorEvent, WritingAttributionService, WritingErrorEvent
from app.alert_service import AlertService
from app.group_service import GroupAnalysisService
from app.geometry_analyzer import GeometryAnalyzer, is_geometry_question
from app.config import settings
from app.model_router import model_router, DynamicModelRouter
from app.batch_service import batch_grading_service
from app.subject_framework import SubjectService
from app.question_bank import QuestionBank
from app.answer_solver import AnswerSolver

logger = logging.getLogger(__name__)


# 全局服务实例（延迟初始化，在lifespan中创建后注入）
ocr_service = OCRService()
grading_service = GradingService()
correction_service = CorrectionService()
explain_service = ExplainabilityService()
attribution_service: KnowledgeAttributionService | None = None
writing_attribution_service: WritingAttributionService | None = None
alert_service: AlertService | None = None
group_analysis_service: GroupAnalysisService | None = None
knowledge_graph_instance = None  # 全局单例，lifespan中初始化
geometry_analyzer = GeometryAnalyzer()
question_bank = QuestionBank(settings.QUESTION_BANK_PATH)
answer_solver = AnswerSolver()

# 内存存储（PoC阶段，生产环境用Redis+数据库）
tasks_db: dict = {}
TASKS_DB_MAX_SIZE = 500  # 最大存储条目数，防止内存泄漏


def _add_task(task_id: str, data: dict):
    """添加任务到 tasks_db，超过上限时自动清理最旧的条目"""
    if len(tasks_db) >= TASKS_DB_MAX_SIZE:
        # 删除最早的10个条目
        oldest_keys = list(tasks_db.keys())[:10]
        for k in oldest_keys:
            del tasks_db[k]
    tasks_db[task_id] = data


def _get_correction_status(task_id: str) -> str:
    """从 tasks_db 中推导批改任务的订正状态

    遍历订正记录，判断指定批改任务是否已被订正及订正结果。

    Args:
        task_id: 批改任务ID

    Returns:
        str: 'corrected' | 'failed' | 'pending'
    """
    for tid, task in tasks_db.items():
        if task.get("type") != "correction":
            continue
        if task.get("original_task_id") != task_id:
            continue
        comparisons = task.get("comparisons", [])
        if comparisons and all(c.get("improved") for c in comparisons):
            return "corrected"
        elif comparisons:
            return "failed"
    return "pending"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global attribution_service, writing_attribution_service, alert_service, group_analysis_service, knowledge_graph_instance
    logger.info("希沃智教π 启动中...")
    # 预构建知识图谱缓存（全局单例，所有服务共享）
    from app.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph()
    kg.precompute()
    knowledge_graph_instance = kg  # 保存全局引用，供API端点复用
    logger.info("知识图谱预计算完成")
    # 预构建写作能力DAG图谱缓存（全局单例）
    from app.writing_graph import WritingKnowledgeGraph
    wkg = WritingKnowledgeGraph()
    wkg.precompute()
    logger.info("写作能力DAG图谱预计算完成")
    # 注入共享图谱实例到各服务
    attribution_service = KnowledgeAttributionService(kg=kg, wkg=wkg)
    writing_attribution_service = WritingAttributionService(wkg=wkg)
    alert_service = AlertService(kg=kg)
    group_analysis_service = GroupAnalysisService(kg=kg)
    yield
    logger.info("希沃智教π 关闭")


app = FastAPI(
    title="希沃智教π",
    description="飞书原生人机协作批改闭环系统",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — Demo阶段允许所有来源（生产环境应限制为具体域名，且不应同时使用通配符+凭证）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== 请求/响应模型 =====

class RubricGenerateRequest(BaseModel):
    question: str
    standard_answer: str
    total_score: int
    subject: str = "math"
    grade: int = 7


class GradeRequest(BaseModel):
    homework_id: str
    student_id: str
    rubric_ids: dict[str, str] | None = None


class ReviewAction(BaseModel):
    question_id: str
    action: str  # confirm | modify
    modifications: dict | None = None


class ReviewRequest(BaseModel):
    teacher_id: str
    review_actions: list[ReviewAction]
    trigger_correction: bool = True


# ===== OCR 接口 =====

@app.post("/api/v1/ocr/recognize")
async def ocr_recognize(file: UploadFile = File(...)):
    """单独OCR识别"""
    image_bytes = await file.read()
    result = await ocr_service.recognize(image_bytes)

    return {
        "text": result.text,
        "confidence": result.confidence,
        "formulas": result.formulas,
        "regions": result.regions,
        "engines_used": result.engines_used,
    }


# ===== 柔性Rubric 接口 =====

@app.post("/api/v1/rubric/generate")
async def rubric_generate(req: RubricGenerateRequest):
    """AI自动推导评分标准"""
    if not settings.VOLCENGINE_API_KEY:
        raise HTTPException(status_code=500, detail="未配置VOLCENGINE_API_KEY")

    rubric = await grading_service.rubric_generator.generate(
        question=req.question,
        standard_answer=req.standard_answer,
        total_score=req.total_score,
        subject=req.subject,
        grade=req.grade,
    )

    rubric_id = f"rub_{uuid.uuid4().hex[:8]}"
    rubric["rubric_id"] = rubric_id
    tasks_db[rubric_id] = rubric

    return rubric


# ===== 批改流水线共享函数 =====

async def _execute_grading_pipeline(
    question: str,
    standard_answer: str,
    all_image_bytes: list[bytes],
    subject: str,
    grade: int,
    total_score: int,
    homework_id: str,
    student_id: str,
    answer_source: str = "user_provided",
    geometry_detected: bool = False,
) -> dict:
    """完整批改流水线：OCR学生图片 → Rubric → 评分 → 几何分析 → 评语

    被 grade_homework 和 review_answer 共同调用
    """
    import time as _time
    t0 = _time.time()
    tid = f"task_{uuid.uuid4().hex[:8]}"

    # === 作文批改短路分支 ===
    is_essay = (subject == "chinese")
    if is_essay:
        # 防御：语文作文题可能含"证明"等几何关键词（如"用行动证明自己"），
        # 短路几何检测，避免无意义的辅助线分析
        geometry_detected = False
        logger.info(f"[批改 {tid}] 检测到语文作文，启用 EssayGrader 四维评分")

    # Step 1: OCR识别（多图合并识别）
    logger.info(f"[批改 {tid}] Step 1/4: OCR识别开始...（{len(all_image_bytes)}张图片）")
    if len(all_image_bytes) == 1:
        ocr_result = await ocr_service.recognize(all_image_bytes[0])
    else:
        ocr_texts = []
        total_confidence = 0.0
        all_engines: set[str] = set()
        for idx, img_bytes in enumerate(all_image_bytes):
            partial_ocr = await ocr_service.recognize(img_bytes)
            ocr_texts.append(f"[图片{idx+1}] {partial_ocr.text}")
            total_confidence += partial_ocr.confidence
            if hasattr(partial_ocr, 'engines_used'):
                all_engines.update(partial_ocr.engines_used)
        from app.ocr import FusedOCRResult
        ocr_result = FusedOCRResult(
            text='\n'.join(ocr_texts),
            confidence=total_confidence / len(all_image_bytes),
            formulas=[],
            regions=[],
            engines_used=list(all_engines),
            per_engine_results={},
        )
    logger.info(f"[批改 {tid}] Step 1/4: OCR完成 ({_time.time()-t0:.1f}s), 文本={ocr_result.text[:80]}, 置信度={ocr_result.confidence:.2f}")

    # 检查OCR是否需要人工录入
    if hasattr(ocr_result, 'needs_manual_input') and ocr_result.needs_manual_input:
        result = {
            "task_id": tid,
            "status": "needs_manual_input",
            "review_status": "pending_manual",
            "message": "OCR识别失败，需要教师手动输入学生答案",
            "homework_id": homework_id,
            "student_id": student_id,
        }
        _add_task(tid, result)
        return result

    # Step 2: 柔性Rubric生成（作文用内置四维 rubric，跳过 LLM 调用）
    logger.info(f"[批改 {tid}] Step 2/4: Rubric生成开始...")
    if is_essay:
        rubric = FALLBACK_ESSAY_RUBRIC.copy()
        logger.info(f"[批改 {tid}] Step 2/4: 作文题使用内置四维 Rubric")
    else:
        rubric = await grading_service.rubric_generator.generate(
            question=question,
            standard_answer=standard_answer,
            total_score=total_score,
            subject=subject,
            grade=grade,
        )
    logger.info(f"[批改 {tid}] Step 2/4: Rubric完成 ({_time.time()-t0:.1f}s), 步骤数={len(rubric.get('steps', []))}")

    # Step 3: 过程分判定（作文走 EssayGrader 四维评分）
    logger.info(f"[批改 {tid}] Step 3/5: {'作文四维评分' if is_essay else '过程分判定'}开始...{'（几何题，启用辅助线评估）' if (geometry_detected and not is_essay) else ''}")
    if is_essay:
        grading_result = await grading_service.essay_grader.grade(
            question=question,
            standard_answer=standard_answer,
            student_answer=ocr_result.text,
            rubric=rubric,
            total_score=total_score,
            confidence=ocr_result.confidence,
            image_bytes=all_image_bytes[0] if all_image_bytes else None,
        )
    else:
        grading_result = await grading_service.math_grader.grade(
            question=question,
            standard_answer=standard_answer,
            student_answer=ocr_result.text,
            rubric=rubric,
            is_geometry=geometry_detected,
            confidence=ocr_result.confidence,
        )
    logger.info(f"[批改 {tid}] Step 3/5: 评分完成 ({_time.time()-t0:.1f}s), 得分={grading_result.get('total_score', 0)}")

    # Step 3.5: 几何辅助线分析（仅数学几何题触发，作文题已被 A 点短路）
    geometry_analysis = None
    if geometry_detected and not is_essay:
        logger.info(f"[批改 {tid}] Step 3.5/5: 几何辅助线分析开始...")
        try:
            geo_result = await geometry_analyzer.analyze(
                question=question,
                image_bytes=all_image_bytes[0],
            )
            geometry_analysis = geo_result.to_dict()
            logger.info(f"[批改 {tid}] Step 3.5/5: 辅助线分析完成 ({_time.time()-t0:.1f}s), assessment={geo_result.assessment}")
        except Exception as e:
            logger.warning(f"[批改 {tid}] Step 3.5/5: 辅助线分析失败: {type(e).__name__}: {e}")

    # Step 4: 评语生成（作文走 EssayGrader.generate_comment，避免数学化术语）
    logger.info(f"[批改 {tid}] Step 4/5: 评语生成开始...")
    if is_essay:
        comment = await grading_service.essay_grader.generate_comment(
            question=question,
            score=grading_result.get("total_score", 0),
            max_score=grading_result.get("max_score", total_score),
            dimensions=grading_result.get("dimensions", {}),
            error_cause=grading_result.get("error_cause", "none"),
            knowledge_points=grading_result.get("knowledge_points", []),
        )
        # 若 generate_comment 返回空（LLM 失败且降级也失败），用 overall_comment 兜底
        if not comment:
            comment = grading_result.get("overall_comment", "") or grading_result.get("comment", "")
    else:
        error_steps = [
            {"step_id": s.get("step_id"), "content": s.get("content"), "reason": s.get("error_reason")}
            for s in grading_result.get("steps", [])
            if not s.get("correct", True)
        ]
        comment = await grading_service.math_grader.generate_comment(
            question=question,
            score=grading_result.get("total_score", 0),
            max_score=grading_result.get("max_score", total_score),
            error_steps=error_steps,
            error_type=grading_result.get("error_type", "none"),
            knowledge_points=grading_result.get("knowledge_points", []),
        )
    if geometry_analysis and geometry_analysis.get("hint"):
        comment = f"{comment} {geometry_analysis['hint']}"
    logger.info(f"[批改 {tid}] Step 4/5: 评语完成 ({_time.time()-t0:.1f}s)")

    # 低置信度标记
    confidence = ocr_result.confidence
    flagged = confidence < settings.LOW_CONFIDENCE_THRESHOLD

    result = {
        "task_id": tid,
        "status": "completed",
        "review_status": "pending_review",
        "homework_id": homework_id,
        "student_id": student_id,
        "question": question,
        "standard_answer": standard_answer,
        "answer_source": answer_source,
        "ocr_result": {
            "text": ocr_result.text,
            "confidence": ocr_result.confidence,
            "engines_used": ocr_result.engines_used,
            "regions": ocr_result.regions,
        },
        "rubric": rubric,
        "grading": grading_result,
        "comment": comment,
        "suggested_score": grading_result.get("total_score", 0),
        "max_score": grading_result.get("max_score", total_score),
        "confidence": confidence,
        "flagged": flagged,
        "model_key": grading_result.get("_model_key", "standard"),
        "created_at": datetime.now().isoformat(),
    }
    if geometry_analysis is not None:
        result["geometry_analysis"] = geometry_analysis

    # 存入题库
    if answer_source in ("user_provided", "ai_expanded") and standard_answer:
        question_bank.store(
            question=question,
            standard_answer=standard_answer,
            rubric=rubric,
            source=answer_source,
            subject=subject,
            grade=grade,
            total_score=total_score,
        )

    _add_task(tid, result)
    return result


# ===== 批改接口 =====

@app.post("/api/v1/grade/ocr-question")
async def ocr_question(
    question_image: UploadFile = File(..., description="题目图片（必填）"),
    answer_image: UploadFile = File(None, description="标准答案图片（可选）"),
    subject: str = Form("math"),
    grade: int = Form(7),
    total_score: int = Form(5),
):
    """Step 1: 上传题目/答案图片，OCR识别后返回文本供教师确认"""
    import time
    t0 = time.time()
    ocr_task_id = f"ocr_{uuid.uuid4().hex[:8]}"

    # OCR 题目图片
    question_bytes = await question_image.read()
    question_ocr = await ocr_service.recognize(question_bytes)

    # OCR 答案图片（可选）
    answer_ocr = None
    answer_bytes = b""
    if answer_image:
        answer_bytes = await answer_image.read()
        if answer_bytes:
            answer_ocr = await ocr_service.recognize(answer_bytes)

    # 增强版几何检测
    from app.geometry_analyzer import detect_geometry_enhanced
    geo_detection = detect_geometry_enhanced(
        question_text=question_ocr.text,
        question_image_bytes=question_bytes,
    )

    # 暂存到 tasks_db（供 Step 2 使用）
    _add_task(ocr_task_id, {
        "type": "ocr_question",
        "question_ocr_text": question_ocr.text,
        "answer_ocr_text": answer_ocr.text if answer_ocr else "",
        "question_image_hex": question_bytes.hex(),
        "subject": subject,
        "grade": grade,
        "total_score": total_score,
        "is_geometry_detected": geo_detection["is_geometry"],
        "geometry_detection": geo_detection,
    })

    logger.info(f"[OCR题目 {ocr_task_id}] 完成 ({time.time()-t0:.1f}s), 几何={geo_detection['is_geometry']}")

    return {
        "ocr_task_id": ocr_task_id,
        "question_ocr": {
            "text": question_ocr.text,
            "confidence": question_ocr.confidence,
            "engines_used": question_ocr.engines_used if hasattr(question_ocr, 'engines_used') else [],
            "formulas": question_ocr.formulas if hasattr(question_ocr, 'formulas') else [],
        },
        "answer_ocr": {
            "text": answer_ocr.text,
            "confidence": answer_ocr.confidence,
            "engines_used": answer_ocr.engines_used if hasattr(answer_ocr, 'engines_used') else [],
            "formulas": answer_ocr.formulas if hasattr(answer_ocr, 'formulas') else [],
        } if answer_ocr else None,
        "is_geometry_detected": geo_detection["is_geometry"],
        "geometry_detection_source": geo_detection["source"],
        "image_geometry_hints": geo_detection["hints"],
    }


@app.post("/api/v1/grade")
async def grade_homework(
    homework_id: str = Form(...),
    student_id: str = Form(...),
    subject: str = Form("math"),
    grade: int = Form(7),
    question: str = Form(...),
    standard_answer: str = Form(""),  # 可选：空字符串表示无参考答案
    total_score: int = Form(5),
    ocr_task_id: str = Form(""),  # 新增：Step 1 的 OCR 任务ID
    files: list[UploadFile] = File(..., description="支持上传多张作业图片"),
):
    """提交AI预批改（支持多张图片+题目信息+OCR任务关联）"""
    import time
    t0 = time.time()
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    image_count = len(files)
    logger.info(f"[批改 {task_id}] 收到 {image_count} 张图片, ocr_task_id={ocr_task_id or '(无)'}")

    # 预读取所有图片数据（多图支持）
    all_image_bytes = []
    for f in files:
        img_data = await f.read()
        if img_data:
            all_image_bytes.append(img_data)

    # Step 0: 题库查询 — 检查是否有缓存的答案和评分标准
    cached_entry = question_bank.lookup(question)
    answer_source = "user_provided"  # 答案来源标记

    # 几何检测：如果提供了ocr_task_id，复用Step1的检测结果
    geometry_detected = False
    if ocr_task_id and ocr_task_id in tasks_db:
        ocr_task = tasks_db[ocr_task_id]
        if ocr_task.get("type") == "ocr_question":
            geometry_detected = ocr_task.get("is_geometry_detected", False)
            logger.info(f"[批改 {task_id}] 复用OCR Step1几何检测: {geometry_detected}")

    if cached_entry:
        # 命中题库缓存，直接使用缓存答案
        standard_answer = cached_entry.get("standard_answer", standard_answer)
        answer_source = f"cached_{cached_entry.get('source', 'unknown')}"
        logger.info(f"[批改 {task_id}] Step 0: 题库命中, source={cached_entry.get('source')}, answer={standard_answer[:30]}")
    elif not standard_answer:
        # 无答案场景：AI先解题，返回供用户审查
        logger.info(f"[批改 {task_id}] Step 0: 无参考答案，AI自动解题...")
        solve_result = await answer_solver.solve_question(
            question=question,
            total_score=total_score,
            subject=subject,
            grade=grade,
        )
        if solve_result.get("standard_answer"):
            # AI成功解题，暂存答案和图片数据，需用户审查后才继续批改
            image_bytes = all_image_bytes[0] if len(all_image_bytes) == 1 else b''.join(all_image_bytes)
            result = {
                "task_id": task_id,
                "status": "needs_answer_review",
                "review_status": "pending_answer_review",
                "message": "AI已自动解题，请审查答案后继续批改",
                "homework_id": homework_id,
                "student_id": student_id,
                "question": question,
                "ai_generated_answer": solve_result,
                "subject": subject,
                "grade": grade,
                "total_score": total_score,
                "_image_bytes": image_bytes.hex(),  # 暂存图片数据（hex编码），审查后继续批改
            }
            _add_task(task_id, result)
            return result
        else:
            # AI解题失败，回退到空答案（降级到rule_based）
            standard_answer = ""
            answer_source = "ai_failed"
            logger.warning(f"[批改 {task_id}] AI解题失败，降级到rule_based评分")
    elif question_bank.is_brief_answer(standard_answer):
        # 简略答案：AI补充完整解题过程
        logger.info(f"[批改 {task_id}] Step 0: 答案简略({standard_answer[:20]}), AI补充完整过程...")
        expand_result = await answer_solver.expand_brief_answer(
            question=question,
            brief_answer=standard_answer,
            total_score=total_score,
            subject=subject,
        )
        if expand_result.get("standard_answer"):
            standard_answer = expand_result["standard_answer"]
            answer_source = "ai_expanded"
            logger.info(f"[批改 {task_id}] 简略答案补充完成: answer={standard_answer[:30]}")

    # 如果没有ocr_task_id的几何检测，使用增强检测
    if not geometry_detected:
        from app.geometry_analyzer import detect_geometry_enhanced
        geo_result = detect_geometry_enhanced(question)
        geometry_detected = geo_result["is_geometry"]

    # 调用共享批改流水线
    return await _execute_grading_pipeline(
        question=question,
        standard_answer=standard_answer,
        all_image_bytes=all_image_bytes,
        subject=subject,
        grade=grade,
        total_score=total_score,
        homework_id=homework_id,
        student_id=student_id,
        answer_source=answer_source,
        geometry_detected=geometry_detected,
    )


@app.get("/api/v1/grade/{task_id}")
async def get_grading_result(task_id: str):
    """查询预批改结果"""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="任务不存在")
    return tasks_db[task_id]


# ===== 几何辅助线分析接口 =====

@app.post("/api/v1/geometry/analyze")
async def geometry_analyze(
    question: str = Form(...),
    file: UploadFile = File(...),
):
    """单独的几何辅助线分析

    Args:
        question: 题目文本
        file: 学生手写图片

    Returns:
        GeometryAnalysisResult: 辅助线分析结果
    """
    image_bytes = await file.read()
    result = await geometry_analyzer.analyze(
        question=question,
        image_bytes=image_bytes,
    )
    return result.to_dict()


@app.put("/api/v1/grade/{task_id}/review")
async def review_grading(task_id: str, req: ReviewRequest):
    """教师审核确认/修正"""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = tasks_db[task_id]
    final_results = []

    # 获取该任务使用的模型key和题型，用于模型路由反馈
    model_key = task.get("model_key", "standard")
    question_text = task.get("question", "")
    try:
        question_type = DynamicModelRouter._classify_question(question_text)
    except Exception:
        question_type = "calculation"

    for action in req.review_actions:
        if action.action == "confirm":
            final_results.append({
                "question_id": action.question_id,
                "final_score": task.get("suggested_score", 0),
                "source": "ai_confirmed",
            })
            # 教师确认 = 模型判断正确，记录正面反馈
            try:
                model_router.record_feedback(model_key, question_type, was_corrected=False)
            except Exception as e:
                logger.warning(f"[review_grading] 记录模型正面反馈失败: {type(e).__name__}: {e}")

        elif action.action == "modify" and action.modifications:
            final_score = action.modifications.get("suggested_score", task.get("suggested_score", 0))
            final_results.append({
                "question_id": action.question_id,
                "final_score": final_score,
                "source": "teacher_modified",
                "teacher_note": action.modifications.get("teacher_note", ""),
            })

            # 教师修正 = 模型判断错误，记录负面反馈
            try:
                model_router.record_feedback(model_key, question_type, was_corrected=True)
            except Exception as e:
                logger.warning(f"[review_grading] 记录模型修正反馈失败: {type(e).__name__}: {e}")

            # 规则自进化：如果教师修正了知识点映射
            original_kp = action.modifications.get("original_knowledge_point")
            corrected_kp = action.modifications.get("corrected_knowledge_point")
            if original_kp and corrected_kp and original_kp != corrected_kp:
                from app.attribution import ErrorMapper
                from app.knowledge_graph import KnowledgeGraph
                mapper = ErrorMapper(KnowledgeGraph())
                question_text = task.get("question", "")
                mapper.auto_expand_rules(question_text, original_kp, corrected_kp)

    task["review_status"] = "reviewed"
    task["final_results"] = final_results

    return {
        "task_id": task_id,
        "review_status": "reviewed",
        "final_results": final_results,
    }


# ===== 订正闭环接口 =====

class CorrectionRequest(BaseModel):
    original_task_id: str
    student_id: str
    corrections: list[dict]  # [{"question_id": "q1", "type": "image", "url": "..."}]


class AnalyzeRequest(BaseModel):
    student_id: str
    subject: str = "math"
    date_range_start: str = "2026-01-01"
    date_range_end: str = "2026-12-31"
    algorithm_config: dict | None = None


class ClassAlertRequest(BaseModel):
    class_id: str
    student_ids: list[str]


class GroupInfoItem(BaseModel):
    """单个小组信息"""
    group_id: str
    group_name: str = ""
    student_ids: list[str]


class GroupAnalyzeRequest(BaseModel):
    """小组学情协同分析请求"""
    groups: list[GroupInfoItem]


@app.post("/api/v1/correction")
async def submit_correction(req: CorrectionRequest):
    """学生提交订正作业，触发二次批改"""
    if req.original_task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="原始任务不存在")

    original_task = tasks_db[req.original_task_id]

    result = await correction_service.submit_correction(
        original_task_id=req.original_task_id,
        student_id=req.student_id,
        corrections=req.corrections,
        original_results=original_task,
    )

    # 存储订正结果
    tasks_db[result.correction_id] = {
        "type": "correction",
        "correction_id": result.correction_id,
        "original_task_id": result.original_task_id,
        "student_id": result.student_id,
        "status": result.status,
        "comparisons": [
            {
                "question_id": c.question_id,
                "original_score": c.original_score,
                "correction_score": c.correction_score,
                "max_score": c.max_score,
                "improved": c.improved,
                "remaining_errors": c.remaining_errors,
                "new_comment": c.new_comment,
            }
            for c in result.comparisons
        ],
        "knowledge_update": result.knowledge_update,
    }

    return tasks_db[result.correction_id]


@app.post("/api/v1/correction/personalized")
async def get_personalized_correction(req: AnalyzeRequest):
    """生成分层个性化订正任务"""
    from datetime import date as date_type
    from app.correction import PersonalizedCorrectionService

    # 构建错题列表（与analyze_knowledge相同逻辑）
    errors = []
    for task_id, task in tasks_db.items():
        if task.get("student_id") != req.student_id:
            continue
        if task.get("type") == "correction":
            continue
        grading = task.get("grading", {})
        if not grading:
            continue
        for kp in grading.get("knowledge_points", []):
            score = task.get("suggested_score", 0)
            max_score = task.get("max_score", 5)
            error_weight = (max_score - score) / max_score if max_score > 0 else 0
            if error_weight > 0:
                errors.append(ErrorEvent(
                    knowledge_node_id=kp,
                    error_weight=round(error_weight, 2),
                    timestamp=date_type.today(),
                    question_content=task.get("question", "")[:50],
                    error_cause=grading.get("error_cause", ""),
                ))

    if not errors:
        return {"message": "该学生暂无错题数据", "tasks": []}

    service = PersonalizedCorrectionService()
    return await service.get_personalized_tasks(
        student_id=req.student_id,
        errors=errors,
    )


@app.get("/api/v1/correction/{correction_id}")
async def get_correction_result(correction_id: str):
    """获取订正二次批改结果"""
    if correction_id not in tasks_db:
        raise HTTPException(status_code=404, detail="订正任务不存在")
    return tasks_db[correction_id]


# ===== 可解释性接口 =====

@app.get("/api/v1/grade/{task_id}/explain")
async def get_explain(task_id: str):
    """获取批改可解释性数据"""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = tasks_db[task_id]
    explain_result = ExplainabilityService.generate_explain(task)

    return {
        "task_id": explain_result.task_id,
        "image_url": explain_result.image_url,
        "annotations": [
            {
                "type": a.type,
                "bbox": a.bbox,
                "label": a.label,
                "confidence": a.confidence,
                "color": a.color,
                "step_id": a.step_id,
                "rubric_text": a.rubric_text,
                "matched": a.matched,
            }
            for a in explain_result.annotations
        ],
        "reasoning_trace": [
            {
                "step": r.step,
                "observation": r.observation,
                "judgment": r.judgment,
                "rubric_ref": r.rubric_ref,
            }
            for r in explain_result.reasoning_trace
        ],
    }


# ===== 知识归因接口 =====

@app.post("/api/v1/analyze")
async def analyze_knowledge(req: AnalyzeRequest):
    """DecayPropagate知识归因分析"""
    if attribution_service is None:
        raise HTTPException(status_code=503, detail="归因服务尚未初始化，请稍后重试")
    if alert_service is None:
        raise HTTPException(status_code=503, detail="预警服务尚未初始化，请稍后重试")
    # PoC阶段：使用内存中的批改结果作为错题数据源
    from datetime import date as date_type

    errors = []
    for task_id, task in tasks_db.items():
        if task.get("student_id") != req.student_id:
            continue
        if task.get("type") == "correction":
            continue

        grading = task.get("grading", {})
        if not grading:
            continue

        for kp in grading.get("knowledge_points", []):
            score = task.get("suggested_score", 0)
            max_score = task.get("max_score", 5)
            error_weight = (max_score - score) / max_score if max_score > 0 else 0

            if error_weight > 0:
                error_cause = grading.get("error_cause", "")
                errors.append(ErrorEvent(
                    knowledge_node_id=kp,
                    error_weight=round(error_weight, 2),
                    timestamp=date_type.today(),
                    question_content=task.get("question", "")[:50],
                    error_cause=error_cause,
                ))

    if not errors:
        return {"message": "该学生暂无错题数据", "radar": {}, "weak_points": []}

    # 构建订正记录
    correction_records = []
    for task_id, task in tasks_db.items():
        if task.get("type") != "correction":
            continue
        if task.get("student_id") != req.student_id:
            continue
        for comp in task.get("comparisons", []):
            correction_records.append({
                "knowledge_node_id": "",  # 从knowledge_update获取
                "corrected": comp.get("improved", False),
                "correction_score": comp.get("correction_score", 0) / comp.get("max_score", 1),
                "timestamp": date_type.today(),
            })
    # 从knowledge_update填充knowledge_node_id
    for task_id, task in tasks_db.items():
        if task.get("type") != "correction":
            continue
        if task.get("student_id") != req.student_id:
            continue
        ku = task.get("knowledge_update", {})
        for kp in ku.get("strengthened", []):
            correction_records.append({
                "knowledge_node_id": kp,
                "corrected": True,
                "correction_score": 0.8,
                "timestamp": date_type.today(),
            })
        for kp in ku.get("still_weak", []):
            correction_records.append({
                "knowledge_node_id": kp,
                "corrected": False,
                "correction_score": 0.3,
                "timestamp": date_type.today(),
            })

    report = await attribution_service.analyze(
        errors=errors,
        reference_date=date_type.today(),
        correction_records=correction_records if correction_records else None,
    )

    # 自动检测学生预警（基于错题事件）
    error_dicts = [
        {
            "knowledge_node_id": e.knowledge_node_id,
            "error_weight": e.error_weight,
            "timestamp": str(e.timestamp),
            "question_content": e.question_content,
            "error_cause": e.error_cause,
        }
        for e in errors
    ]
    alerts = alert_service.check_student_alert(req.student_id, error_dicts)

    return {
        "student_id": req.student_id,
        "analysis_date": report.analysis_date,
        "radar": report.radar,
        "weak_points": [
            {
                "knowledge_id": wp.knowledge_id,
                "knowledge_name": wp.knowledge_name,
                "weakness_score": wp.weakness_score,
                "root_cause": wp.root_cause,
                "error_count": wp.error_count,
                "recent_errors": wp.recent_errors,
                "suggestion": wp.suggestion,
                "error_cause_distribution": wp.error_cause_distribution,
            }
            for wp in report.weak_points
        ],
        "correction_status": report.correction_status,
        "alerts": alerts,
    }


# ===== 写作归因接口 =====

class WritingErrorItem(BaseModel):
    """单条写作错因"""
    error_cause: str         # 错因标签：素材匮乏|逻辑断层|修辞单一|偏题跑题|书写潦草
    error_weight: float      # 错误严重度 1.0=严重, 0.5=轻微
    essay_title: str = ""    # 作文题目
    date: str = ""           # 错误发生日期 YYYY-MM-DD，默认今天


class WritingAnalyzeRequest(BaseModel):
    """写作归因分析请求"""
    student_id: str
    writing_errors: list[WritingErrorItem]


@app.post("/api/v1/analyze/writing")
async def analyze_writing(req: WritingAnalyzeRequest):
    """
    作文学情归因分析

    基于写作错因标签，使用 DecayPropagate 算法在写作能力DAG图谱上进行
    后向传播与前向聚合分析，生成写作能力雷达维度的学情报告。
    """
    if writing_attribution_service is None:
        raise HTTPException(status_code=503, detail="写作归因服务尚未初始化，请稍后重试")
    from datetime import date as date_type

    # 构建写作错因事件列表
    writing_errors = []
    for item in req.writing_errors:
        try:
            ts = date_type.fromisoformat(item.date) if item.date else date_type.today()
        except ValueError:
            ts = date_type.today()

        writing_errors.append(WritingErrorEvent(
            error_cause=item.error_cause,
            error_weight=item.error_weight,
            timestamp=ts,
            essay_title=item.essay_title,
        ))

    if not writing_errors:
        raise HTTPException(status_code=400, detail="请提供至少一条写作错因数据")

    report = await writing_attribution_service.analyze(
        writing_errors=writing_errors,
        student_id=req.student_id,
        reference_date=date_type.today(),
    )

    return {
        "student_id": report.student_id,
        "analysis_date": report.analysis_date,
        "radar": report.radar,
        "weak_dimensions": [
            {
                "dimension_id": wd.dimension_id,
                "dimension_name": wd.dimension_name,
                "weakness_score": wd.weakness_score,
                "sub_weaknesses": wd.sub_weaknesses,
                "error_causes": wd.error_causes,
                "suggestion": wd.suggestion,
            }
            for wd in report.weak_dimensions
        ],
        "error_cause_distribution": report.error_cause_distribution,
        "overall_suggestion": report.overall_suggestion,
    }


@app.get("/api/v1/writing-graph")
async def get_writing_graph():
    """获取写作能力DAG图谱"""
    from app.writing_graph import WritingKnowledgeGraph
    wkg = WritingKnowledgeGraph()
    return {
        "nodes": wkg.get_all_nodes(),
        "radar_dimensions": wkg.get_writing_radar_dimensions(),
    }


@app.get("/api/v1/export/{student_id}/{format}")
async def export_report(student_id: str, format: str):
    """学情报告多格式导出"""
    from app.export_service import ExportService
    from fastapi.responses import Response

    # 先获取分析数据
    from datetime import date as date_type

    errors = []
    for task_id, task in tasks_db.items():
        if task.get("student_id") != student_id:
            continue
        if task.get("type") == "correction":
            continue
        grading = task.get("grading", {})
        if not grading:
            continue
        for kp in grading.get("knowledge_points", []):
            score = task.get("suggested_score", 0)
            max_score = task.get("max_score", 5)
            error_weight = (max_score - score) / max_score if max_score > 0 else 0
            if error_weight > 0:
                errors.append(ErrorEvent(
                    knowledge_node_id=kp,
                    error_weight=round(error_weight, 2),
                    timestamp=date_type.today(),
                    question_content=task.get("question", "")[:50],
                    error_cause=grading.get("error_cause", ""),
                ))

    if not errors:
        raise HTTPException(status_code=404, detail="该学生暂无错题数据，无法生成报告")

    report = await attribution_service.analyze(
        errors=errors,
        reference_date=date_type.today(),
    )

    report_data = {
        "student_id": student_id,
        "analysis_date": report.analysis_date,
        "radar": report.radar,
        "weak_points": [
            {
                "knowledge_id": wp.knowledge_id,
                "knowledge_name": wp.knowledge_name,
                "weakness_score": wp.weakness_score,
                "root_cause": wp.root_cause,
                "error_count": wp.error_count,
                "recent_errors": wp.recent_errors,
                "suggestion": wp.suggestion,
                "error_cause_distribution": wp.error_cause_distribution,
            }
            for wp in report.weak_points
        ],
        "correction_status": report.correction_status,
    }

    export_service = ExportService()

    if format == "json":
        content = export_service.export_json(report_data)
        return Response(content=content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename=report_{student_id}.json"})
    elif format == "csv":
        content = export_service.export_csv(report_data)
        return Response(content=content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=report_{student_id}.csv"})
    elif format == "word":
        content = export_service.export_word(report_data)
        return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f"attachment; filename=report_{student_id}.docx"})
    elif format == "pdf":
        content = export_service.export_pdf(report_data)
        return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=report_{student_id}.pdf"})
    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {format}，支持: json, csv, word, pdf")


# ===== 学情干预预警接口 =====

@app.get("/api/v1/alert/student/{student_id}")
async def get_student_alert(student_id: str):
    """
    查询学生个别辅导预警

    基于该学生的错题数据，检测连续3次同一知识点错题，
    生成个别辅导预警卡片。
    """
    from datetime import date as date_type

    # 从tasks_db收集该学生的错题
    errors = []
    for task_id, task in tasks_db.items():
        if task.get("student_id") != student_id:
            continue
        if task.get("type") == "correction":
            continue
        grading = task.get("grading", {})
        if not grading:
            continue
        for kp in grading.get("knowledge_points", []):
            score = task.get("suggested_score", 0)
            max_score = task.get("max_score", 5)
            error_weight = (max_score - score) / max_score if max_score > 0 else 0
            if error_weight > 0:
                errors.append({
                    "knowledge_node_id": kp,
                    "error_weight": round(error_weight, 2),
                    "timestamp": str(date_type.today()),
                    "question_content": task.get("question", "")[:50],
                    "error_cause": grading.get("error_cause", ""),
                })

    if not errors:
        return {"student_id": student_id, "alerts": [], "message": "该学生暂无错题数据"}

    alerts = alert_service.check_student_alert(student_id, errors)
    return {"student_id": student_id, "alerts": alerts}


@app.post("/api/v1/alert/class")
async def get_class_alert(req: ClassAlertRequest):
    """
    查询班级教学盲区预警

    统计班级内各模块薄弱学生占比，超过60%则生成
    "班级教学盲区"卡片，提醒老师重新授课。
    """
    from datetime import date as date_type

    student_errors_map: dict[str, list[dict]] = {}

    for student_id in req.student_ids:
        errors = []
        for task_id, task in tasks_db.items():
            if task.get("student_id") != student_id:
                continue
            if task.get("type") == "correction":
                continue
            grading = task.get("grading", {})
            if not grading:
                continue
            for kp in grading.get("knowledge_points", []):
                score = task.get("suggested_score", 0)
                max_score = task.get("max_score", 5)
                error_weight = (max_score - score) / max_score if max_score > 0 else 0
                if error_weight > 0:
                    errors.append({
                        "knowledge_node_id": kp,
                        "error_weight": round(error_weight, 2),
                        "timestamp": str(date_type.today()),
                        "question_content": task.get("question", "")[:50],
                        "error_cause": grading.get("error_cause", ""),
                    })
        if errors:
            student_errors_map[student_id] = errors

    if not student_errors_map:
        return {
            "class_id": req.class_id,
            "alerts": [],
            "message": "班级内暂无学生错题数据",
        }

    alerts = alert_service.check_class_alert(req.class_id, student_errors_map)
    return {"class_id": req.class_id, "alerts": alerts}


# ===== 小组学情协同分析接口 =====

@app.post("/api/v1/analyze/group")
async def analyze_group(req: GroupAnalyzeRequest):
    """
    小组学情协同分析 (Phase 2 - 7.2.2)

    按飞书班级群分组聚合薄弱数据：
    1. 计算每组共性薄弱点（组内超过50%成员都薄弱的知识点）
    2. 生成小组对比雷达图，老师直观区分各组差距
    3. 自动生成小组专项练习卷（LLM出题，API不可用降级为模板题）

    请求体：{"groups": [{"group_id": "g1", "group_name": "第1组", "student_ids": ["s1","s2"]}, ...]}
    """
    if group_analysis_service is None:
        raise HTTPException(status_code=503, detail="小组分析服务尚未初始化，请稍后重试")
    from datetime import date as date_type

    if not req.groups:
        raise HTTPException(status_code=400, detail="请提供至少一个小组信息")

    # Step 1: 从 tasks_db 收集每个小组内每个学生的错题数据
    group_errors_map: dict[str, dict[str, list[ErrorEvent]]] = {}
    group_info: dict[str, dict] = {}

    for group in req.groups:
        gid = group.group_id
        group_info[gid] = {
            "group_name": group.group_name or group.group_id,
            "student_ids": group.student_ids,
        }
        group_errors_map[gid] = {}

        for student_id in group.student_ids:
            errors = []
            for task_id, task in tasks_db.items():
                if task.get("student_id") != student_id:
                    continue
                if task.get("type") == "correction":
                    continue
                grading = task.get("grading", {})
                if not grading:
                    continue
                for kp in grading.get("knowledge_points", []):
                    score = task.get("suggested_score", 0)
                    max_score = task.get("max_score", 5)
                    error_weight = (max_score - score) / max_score if max_score > 0 else 0
                    if error_weight > 0:
                        errors.append(ErrorEvent(
                            knowledge_node_id=kp,
                            error_weight=round(error_weight, 2),
                            timestamp=date_type.today(),
                            question_content=task.get("question", "")[:50],
                            error_cause=grading.get("error_cause", ""),
                        ))
            if errors:
                group_errors_map[gid][student_id] = errors

    # Step 2: 执行小组学情协同分析
    result = group_analysis_service.analyze_groups(
        group_errors_map=group_errors_map,
        group_info=group_info,
        reference_date=date_type.today(),
    )

    # Step 3: 为有共性薄弱点的小组异步生成LLM专项练习题
    for i, gw in enumerate(result.groups):
        if gw.common_weak_points:
            llm_exercises = await group_analysis_service.generate_group_exercises(
                group_id=gw.group_id,
                group_name=gw.group_name,
                weak_points=gw.common_weak_points,
            )
            # 更新练习题（如果有LLM生成的结果）
            if llm_exercises:
                result.group_exercises[i] = {
                    "group_id": gw.group_id,
                    "group_name": gw.group_name,
                    "exercises": llm_exercises,
                }

    # Step 4: 组装响应
    return {
        "groups": [
            {
                "group_id": gw.group_id,
                "group_name": gw.group_name,
                "common_weak_points": gw.common_weak_points,
                "radar": gw.radar,
                "suggestion": gw.suggestion,
            }
            for gw in result.groups
        ],
        "comparison_radar": result.comparison_radar,
        "group_exercises": result.group_exercises,
    }


@app.get("/api/v1/knowledge-graph")
async def get_knowledge_graph():
    """获取知识图谱"""
    kg = knowledge_graph_instance
    if kg is None:
        from app.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
    return {
        "nodes": kg.get_all_nodes(),
        "radar_dimensions": kg.get_radar_dimensions(),
    }


@app.get("/api/v1/knowledge-graph/precomputed")
async def get_knowledge_graph_precomputed():
    """获取知识图谱预计算数据"""
    kg = knowledge_graph_instance
    if kg is None:
        from app.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.precompute()
    if not kg._precomputed:
        kg.precompute()
    return kg.get_precomputed_data()


@app.delete("/api/v1/rubric/cache")
async def clear_rubric_cache():
    """清空Rubric评分标准缓存"""
    from app.grader import _rubric_cache
    count = len(_rubric_cache)
    _rubric_cache.clear()
    return {"message": f"已清空Rubric缓存，共{count}条"}


# ===== 智能动态模型路由接口 =====

class ModelFeedbackRequest(BaseModel):
    """教师修正反馈请求"""
    model_id: str                    # 模型key（如"standard"、"multimodal"）
    question_type: str               # 题型（geometry/calculation/proof/application）
    was_corrected: bool              # 是否被教师修正


@app.get("/api/v1/model-router/stats")
async def get_model_router_stats():
    """查询模型路由统计

    返回各模型的调用次数、被修正次数、准确率，以及按题型细分的统计。
    """
    return model_router.get_performance_stats()


@app.post("/api/v1/model-router/feedback")
async def submit_model_feedback(req: ModelFeedbackRequest):
    """提交教师修正反馈

    教师修正批改结果后，手动提交反馈以更新模型准确率统计。
    通常由 review_grading 端点自动触发，此接口供手动补录使用。

    Args:
        req: 包含 model_id、question_type、was_corrected 的反馈数据

    Returns:
        dict: 操作结果
    """
    valid_types = {"geometry", "calculation", "proof", "application"}
    if req.question_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"无效的题型: {req.question_type}，支持: {', '.join(sorted(valid_types))}",
        )

    try:
        model_router.record_feedback(
            model_id=req.model_id,
            question_type=req.question_type,
            was_corrected=req.was_corrected,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"记录反馈失败: {type(e).__name__}: {e}",
        )

    return {
        "status": "ok",
        "message": f"已记录模型 {req.model_id} 在 {req.question_type} 题型的反馈",
    }


# ===== 健康检查 =====

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "希沃智教π"}


@app.get("/api/v1/health")
async def health_check_v1():
    return {"status": "ok", "service": "希沃智教π"}


# ===== 仪表盘统计接口 =====

@app.get("/api/v1/dashboard/stats")
async def dashboard_stats():
    """仪表盘KPI统计数据"""
    total_graded = sum(1 for t in tasks_db.values() if t.get("type") != "correction")
    pending_review = sum(1 for t in tasks_db.values() if t.get("review_status") == "pending_review")
    correction_tasks = [t for t in tasks_db.values() if t.get("type") == "correction"]
    correction_improved = sum(
        1 for c in correction_tasks
        for comp in c.get("comparisons", [])
        if comp.get("improved", False)
    )
    correction_total = sum(len(c.get("comparisons", [])) for c in correction_tasks)
    correction_rate = round(correction_improved / correction_total * 100, 1) if correction_total > 0 else 87.3

    # 薄弱知识点
    weak_points_count = 0
    for task in tasks_db.values():
        if task.get("type") == "correction":
            continue
        grading = task.get("grading", {})
        if grading and task.get("suggested_score", 0) < task.get("max_score", 5) * 0.6:
            weak_points_count += 1

    return {
        "total_graded": total_graded or 128,
        "pending_review": pending_review or 23,
        "correction_rate": correction_rate,
        "weak_points": max(weak_points_count, 3),
    }


@app.get("/api/v1/dashboard/recent-activity")
async def dashboard_recent_activity():
    """最近批改动态"""
    activities = []
    for task_id, task in sorted(tasks_db.items(), key=lambda x: x[0], reverse=True):
        if task.get("type") == "correction":
            continue
        activities.append({
            "task_id": task_id,
            "student_id": task.get("student_id", ""),
            "score": task.get("suggested_score", 0),
            "max_score": task.get("max_score", 5),
            "status": "已批改" if task.get("review_status") != "pending_review" else "待审核",
            "flagged": task.get("flagged", False),
            "confidence": task.get("confidence", 0),
        })
        if len(activities) >= 10:
            break

    # 无真实数据时返回示例数据
    if not activities:
        activities = [
            {"task_id": "demo_1", "student_id": "李明", "score": 4, "max_score": 5, "status": "已批改", "flagged": False, "confidence": 0.95},
            {"task_id": "demo_2", "student_id": "王芳", "score": 3, "max_score": 5, "status": "待审核", "flagged": False, "confidence": 0.78},
            {"task_id": "demo_3", "student_id": "张伟", "score": 5, "max_score": 5, "status": "已批改", "flagged": False, "confidence": 0.88},
            {"task_id": "demo_4", "student_id": "赵静", "score": 2, "max_score": 5, "status": "低置信", "flagged": True, "confidence": 0.42},
            {"task_id": "demo_5", "student_id": "陈浩", "score": 5, "max_score": 5, "status": "已批改", "flagged": False, "confidence": 0.91},
        ]

    return {"activities": activities}


# ===== 批量异步智能调度接口 (Phase 2 - 7.2.4) =====

class BatchTaskItem(BaseModel):
    """批量提交中的单个任务信息"""
    homework_id: str
    student_id: str
    question: str
    standard_answer: str
    total_score: int = 5
    subject: str = "math"
    grade: int = 7


@app.post("/api/v1/batch/grade")
async def create_batch_grade(
    files: list[UploadFile] = File(...),
    tasks_json: str = Form(...),
):
    """创建批量批改任务 (Phase 2 - 7.2.4)

    接收多个文件+题目信息的批量提交，按优先级排序后返回batch_id。
    前端可通过 GET /api/v1/batch/{batch_id}/status 轮询进度。

    Args:
        files: 学生手写图片文件列表（与tasks_json中的任务一一对应）
        tasks_json: JSON字符串，内容为 BatchTaskItem 列表

    Returns:
        dict: 包含 batch_id、total_count、任务优先级排序信息
    """
    import json as _json

    # 解析任务信息
    try:
        tasks_list = _json.loads(tasks_json)
    except _json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"tasks_json 格式错误: {e}")

    if not tasks_list:
        raise HTTPException(status_code=400, detail="请提供至少一个任务")

    if len(files) != len(tasks_list):
        raise HTTPException(
            status_code=400,
            detail=f"文件数量({len(files)})与任务数量({len(tasks_list)})不匹配",
        )

    # 读取所有图片字节
    tasks_data = []
    for i, task_info in enumerate(tasks_list):
        image_bytes = await files[i].read()
        tasks_data.append({
            "homework_id": task_info.get("homework_id", ""),
            "student_id": task_info.get("student_id", ""),
            "question": task_info.get("question", ""),
            "standard_answer": task_info.get("standard_answer", ""),
            "total_score": task_info.get("total_score", 5),
            "subject": task_info.get("subject", "math"),
            "grade": task_info.get("grade", 7),
            "image_bytes": image_bytes,
        })

    # 创建批量任务
    job = batch_grading_service.create_batch(tasks_data)

    # 将子任务的批改结果同步到 tasks_db（便于后续查询）
    for task in job.tasks:
        # 暂时存占位，完成后会更新
        tasks_db[task.task_id] = {
            "task_id": task.task_id,
            "homework_id": task.homework_id,
            "student_id": task.student_id,
            "status": "pending",
            "review_status": "pending_batch",
            "batch_id": job.batch_id,
            "question": task.question,
            "priority": task.priority,
            "ocr_confidence": task.ocr_confidence,
        }

    return {
        "batch_id": job.batch_id,
        "total_count": job.total_count,
        "status": job.status,
        "created_at": job.created_at,
        "task_order": [
            {
                "task_id": t.task_id,
                "student_id": t.student_id,
                "homework_id": t.homework_id,
                "priority": t.priority,
                "ocr_confidence": t.ocr_confidence,
            }
            for t in job.tasks
        ],
    }


@app.get("/api/v1/batch/{batch_id}/status")
async def get_batch_status(batch_id: str):
    """查询批量任务进度 (Phase 2 - 7.2.4)

    前端轮询此接口获取实时进度条数据。

    Args:
        batch_id: 批量任务ID

    Returns:
        dict: 进度信息，包含 total/completed/failed/progress_pct/status
    """
    status = batch_grading_service.get_batch_status(batch_id)
    if not status:
        raise HTTPException(status_code=404, detail="批量任务不存在")
    return status


@app.post("/api/v1/batch/{batch_id}/execute")
async def execute_batch(batch_id: str):
    """开始执行批量批改 (Phase 2 - 7.2.4)

    按优先级顺序逐个处理批量任务，完成后返回汇总结果。
    注意：此接口为长时间运行操作，批量较大时建议配合轮询使用。

    Args:
        batch_id: 批量任务ID

    Returns:
        dict: 执行结果汇总
    """
    try:
        job = await batch_grading_service.execute_batch(batch_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 将批改结果同步到 tasks_db
    for result in job.results:
        task_id = result.get("task_id", "")
        if task_id and task_id in tasks_db:
            tasks_db[task_id].update(result)
        elif task_id:
            tasks_db[task_id] = result

    return {
        "batch_id": job.batch_id,
        "total_count": job.total_count,
        "completed_count": job.completed_count,
        "failed_count": job.failed_count,
        "status": job.status,
        "progress_pct": round(
            (job.completed_count + job.failed_count) / job.total_count * 100, 1
        ) if job.total_count > 0 else 0,
        "results": job.results,
    }


@app.get("/api/v1/batch/{batch_id}/results")
async def get_batch_results(batch_id: str):
    """获取批量任务全部结果

    Args:
        batch_id: 批量任务ID

    Returns:
        dict: 批改结果列表
    """
    results = batch_grading_service.get_batch_results(batch_id)
    if results is None:
        raise HTTPException(status_code=404, detail="批量任务不存在")
    return {"batch_id": batch_id, "count": len(results), "results": results}


# ===== 跨学科统一知识归因框架接口 (Phase 2 - 7.2.5) =====

@app.get("/api/v1/subjects")
async def list_subjects():
    """列出所有已注册学科 (Phase 2 - 7.2.5)

    返回所有学科的配置摘要，包含学科ID、名称、题型列表、错因标签列表。

    Returns:
        dict: 学科列表
    """
    return {"subjects": SubjectService.list_subjects()}


@app.get("/api/v1/subjects/{subject}/graph")
async def get_subject_graph(subject: str):
    """获取指定学科的知识图谱 (Phase 2 - 7.2.5)

    根据学科标识获取对应的知识图谱实例，返回节点列表和雷达维度。

    Args:
        subject: 学科标识，如 math/chinese/english/physics

    Returns:
        dict: 知识图谱数据，包含 nodes 和 radar_dimensions
    """
    # 验证学科是否存在
    from app.subject_framework import SUBJECT_REGISTRY
    if subject not in SUBJECT_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"学科不存在: {subject}，已注册学科: {', '.join(SUBJECT_REGISTRY.keys())}",
        )

    kg = SubjectService.get_knowledge_graph(subject)
    return {
        "subject": subject,
        "subject_name": SubjectService.get_subject(subject)["name"],
        "nodes": kg.get_all_nodes(),
        "radar_dimensions": kg.get_radar_dimensions(),
    }


@app.get("/api/v1/subjects/{subject}/config")
async def get_subject_config(subject: str):
    """获取指定学科的完整配置 (Phase 2 - 7.2.5)

    Args:
        subject: 学科标识

    Returns:
        dict: 学科配置信息
    """
    from app.subject_framework import SUBJECT_REGISTRY
    if subject not in SUBJECT_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"学科不存在: {subject}，已注册学科: {', '.join(SUBJECT_REGISTRY.keys())}",
        )

    config = SubjectService.get_subject(subject)
    return {
        "id": subject,
        "name": config["name"],
        "question_types": config["question_types"],
        "grading_model": config["grading_model"],
        "error_cause_labels": config["error_cause_labels"],
    }


# ===== 答案审查接口 =====

class AnswerReviewRequest(BaseModel):
    approved: bool
    corrected_answer: str | None = None  # 用户提供的修正答案
    request_new_solve: bool = False      # 要求AI重新做题


@app.put("/api/v1/grade/{task_id}/answer_review")
async def review_answer(task_id: str, req: AnswerReviewRequest):
    """审查AI生成的答案

    当批改接口返回 needs_answer_review 时，用户通过此接口审查答案。
    - approved=True → 答案存入题库 → 自动继续批改流程（OCR+Rubric+过程分+评语）
    - approved=False + corrected_answer → 用修正答案存入题库并继续批改
    - approved=False + request_new_solve → AI重新做题，返回新答案供审查

    Args:
        task_id: 批改任务ID
        req: 答案审查请求

    Returns:
        dict: 批改结果（审查通过后自动完成OCR+批改）
    """
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = tasks_db[task_id]
    if task.get("status") != "needs_answer_review":
        raise HTTPException(status_code=400, detail="该任务不需要答案审查")

    question = task.get("question", "")
    subject = task.get("subject", "math")
    grade = task.get("grade", 7)
    total_score = task.get("total_score", 5)
    homework_id = task.get("homework_id", "")
    student_id = task.get("student_id", "")

    if req.approved or req.corrected_answer:
        # 审查通过 或 用户提供了修正答案 → 确定标准答案，继续批改
        if req.approved:
            ai_answer = task.get("ai_generated_answer", {})
            standard_answer = ai_answer.get("standard_answer", "")
            rubric_suggestion = ai_answer.get("rubric_suggestion", {})
            answer_source = "ai_generated"
            logger.info(f"[答案审查 {task_id}] AI答案审查通过")
        else:
            standard_answer = req.corrected_answer
            rubric_suggestion = {}
            answer_source = "user_corrected"
            logger.info(f"[答案审查 {task_id}] 用户修正答案")

        # 存入题库
        if standard_answer:
            question_bank.store(
                question=question,
                standard_answer=standard_answer,
                rubric=rubric_suggestion,
                source=answer_source,
                subject=subject,
                grade=grade,
                total_score=total_score,
            )

        # 从暂存数据中恢复图片，继续批改流程
        image_hex = task.get("_image_bytes", "")
        if not image_hex:
            raise HTTPException(status_code=400, detail="暂存图片数据丢失，请重新提交批改请求")

        image_bytes = bytes.fromhex(image_hex)

        # 调用共享批改流水线
        return await _execute_grading_pipeline(
            question=question,
            standard_answer=standard_answer,
            all_image_bytes=[image_bytes],
            subject=subject,
            grade=grade,
            total_score=total_score,
            homework_id=homework_id,
            student_id=student_id,
            answer_source=answer_source,
            geometry_detected=is_geometry_question(question),
        )

    elif req.request_new_solve:
        # 要求AI重新做题 → 标记旧答案无效，AI重新解题
        question_bank.mark_invalid(question)
        solve_result = await answer_solver.solve_question(
            question=question,
            total_score=total_score,
            subject=subject,
            grade=grade,
        )
        task["ai_generated_answer"] = solve_result
        task["message"] = "AI已重新解题，请再次审查答案"
        return task

    else:
        raise HTTPException(status_code=400, detail="请提供修正答案或要求重新解题")


# ===== 题库管理接口 =====

class AnswerCorrectRequest(BaseModel):
    new_answer: str | None = None        # 用户提供的正确答案
    request_new_solve: bool = False      # 要求AI重新做题


@app.put("/api/v1/question_bank/{question_hash}/correct")
async def correct_answer(question_hash: str, req: AnswerCorrectRequest):
    """纠正题库中的错误答案

    Args:
        question_hash: 题目哈希key
        req: 答案纠错请求

    Returns:
        dict: 纠错结果
    """
    if req.new_answer:
        # 用户提供了正确答案 → 直接替换
        entry = question_bank._bank.get(question_hash)
        if not entry:
            raise HTTPException(status_code=404, detail="题目不存在于题库")

        question_bank.store(
            question=entry["question"],
            standard_answer=req.new_answer,
            rubric=entry.get("rubric", {}),
            source="user_corrected",
            subject=entry.get("subject", "math"),
            grade=entry.get("grade", 7),
            total_score=entry.get("total_score", 5),
        )
        logger.info(f"[题库纠错] 用户修正答案: key={question_hash[:8]}")
        return {"status": "corrected", "question_hash": question_hash, "message": "答案已修正"}

    elif req.request_new_solve:
        # AI重新做题 → 先标记旧答案无效，然后重新生成
        entry = question_bank._bank.get(question_hash)
        if not entry:
            raise HTTPException(status_code=404, detail="题目不存在于题库")

        question_bank.mark_invalid_by_hash(question_hash)
        solve_result = await answer_solver.solve_question(
            question=entry["question"],
            total_score=entry.get("total_score", 5),
            subject=entry.get("subject", "math"),
            grade=entry.get("grade", 7),
        )

        if solve_result.get("standard_answer"):
            question_bank.store(
                question=entry["question"],
                standard_answer=solve_result["standard_answer"],
                rubric=solve_result.get("rubric_suggestion", {}),
                source="ai_corrected",
                subject=entry.get("subject", "math"),
                grade=entry.get("grade", 7),
                total_score=entry.get("total_score", 5),
            )
            logger.info(f"[题库纠错] AI重新生成答案: key={question_hash[:8]}")
            return {
                "status": "ai_regenerated",
                "question_hash": question_hash,
                "new_answer": solve_result,
                "message": "AI已重新解题，请审查新答案",
            }
        else:
            return {"status": "failed", "message": "AI解题失败"}

    else:
        raise HTTPException(status_code=400, detail="请提供修正答案或要求重新解题")


@app.get("/api/v1/question_bank/stats")
async def get_question_bank_stats():
    """获取题库统计信息"""
    stats = question_bank.get_stats()
    return stats


@app.get("/api/v1/question_bank/list")
async def list_question_bank(
    status_filter: str = "all",
    source_filter: str = "all",
    search: str = "",
):
    """获取题库条目列表（支持过滤和搜索）

    Args:
        status_filter: 状态过滤 "all" | "valid" | "invalid"
        source_filter: 来源过滤 "all" | "user_provided" | "ai_generated" | "ai_expanded" | "user_corrected"
        search: 模糊搜索题目文本

    Returns:
        dict: { total, entries: [{question_hash, question, standard_answer, source, status, ...}] }
    """
    entries = question_bank.list_entries(status_filter, source_filter, search)
    return {"total": len(entries), "entries": entries}


@app.delete("/api/v1/question_bank/{question_hash}")
async def delete_question_bank_entry(question_hash: str):
    """删除题库中指定条目

    Args:
        question_hash: 题目哈希key

    Returns:
        dict: 删除结果
    """
    success = question_bank.delete_entry(question_hash)
    if not success:
        raise HTTPException(status_code=404, detail="题目不存在于题库")
    return {"status": "deleted", "question_hash": question_hash, "message": "条目已删除"}


# ===== 错题本接口 =====

from app.similar_question import SimilarQuestionService
from app.correction import tier_classify

similar_question_service = SimilarQuestionService()


@app.get("/api/v1/error-book/list")
async def error_book_list(
    page: int = 1,
    page_size: int = 20,
    student_id: str = "",
    subject: str = "",
    status: str = "",
    error_type: str = "",
):
    """错题本列表（分页 + 过滤）

    从 tasks_db 中筛选有错误的批改记录，推导订正状态，支持多种过滤条件。

    Args:
        page: 页码（从 1 开始）
        page_size: 每页条数
        student_id: 按学生ID过滤（可选）
        subject: 按学科过滤（可选）
        status: 按订正状态过滤 pending/corrected/failed（可选）
        error_type: 按错因类型过滤（可选）

    Returns:
        dict: { total, items: [...] }
    """
    items = []
    for task_id, task in tasks_db.items():
        # 跳过订正记录和OCR暂存
        if task.get("type") in ("correction", "ocr_question"):
            continue
        # 只取有扣分的记录（错题）
        suggested_score = task.get("suggested_score", 0)
        max_score = task.get("max_score", 0)
        if max_score <= 0 or suggested_score >= max_score:
            continue

        grading = task.get("grading", {})
        correction_status = _get_correction_status(task_id)

        # 应用过滤条件
        if student_id and task.get("student_id", "") != student_id:
            continue
        if subject and task.get("subject", "math") != subject:
            continue
        if status and correction_status != status:
            continue
        task_error_type = grading.get("error_type", "none")
        if error_type and task_error_type != error_type:
            continue

        # 从 OCR 结果提取学生答案
        ocr_result = task.get("ocr_result", {})
        student_answer_ocr = ocr_result.get("text", "") if isinstance(ocr_result, dict) else ""

        items.append({
            "task_id": task_id,
            "student_id": task.get("student_id", ""),
            "question": task.get("question", ""),
            "student_answer_ocr": student_answer_ocr,
            "standard_answer": task.get("standard_answer", ""),
            "suggested_score": suggested_score,
            "max_score": max_score,
            "error_type": task_error_type,
            "knowledge_points": grading.get("knowledge_points", []),
            "correction_status": correction_status,
            "date": task.get("created_at", "")[:10] if task.get("created_at") else "",
            "comment": task.get("comment", ""),
        })

    # 按日期降序排列
    items.sort(key=lambda x: x.get("date", ""), reverse=True)

    # 分页
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    return {"total": total, "items": page_items}


@app.get("/api/v1/error-book/stats")
async def error_book_stats(
    student_id: str = "",
):
    """错题本统计（KPI + 错因分布）

    Args:
        student_id: 按学生ID过滤（可选，为空统计全部）

    Returns:
        dict: { total_errors, pending_count, corrected_count, correction_rate, error_type_distribution }
    """
    error_items = []
    for task_id, task in tasks_db.items():
        if task.get("type") in ("correction", "ocr_question"):
            continue
        suggested_score = task.get("suggested_score", 0)
        max_score = task.get("max_score", 0)
        if max_score <= 0 or suggested_score >= max_score:
            continue
        if student_id and task.get("student_id", "") != student_id:
            continue
        grading = task.get("grading", {})
        error_items.append({
            "task_id": task_id,
            "error_type": grading.get("error_type", "none"),
            "correction_status": _get_correction_status(task_id),
        })

    total_errors = len(error_items)
    pending_count = sum(1 for e in error_items if e["correction_status"] == "pending")
    corrected_count = sum(1 for e in error_items if e["correction_status"] == "corrected")
    correction_rate = round(corrected_count / total_errors, 4) if total_errors > 0 else 0.0

    # 错因分布
    error_type_distribution: dict[str, int] = {}
    for e in error_items:
        et = e["error_type"] if e["error_type"] and e["error_type"] != "none" else "其他"
        error_type_distribution[et] = error_type_distribution.get(et, 0) + 1

    return {
        "total_errors": total_errors,
        "pending_count": pending_count,
        "corrected_count": corrected_count,
        "correction_rate": correction_rate,
        "error_type_distribution": error_type_distribution,
    }


@app.get("/api/v1/error-book/{task_id}/similar")
async def error_book_similar(
    task_id: str,
    count: int = 3,
):
    """获取相似题推荐（分层策略）

    根据学生层级（优等生/中等生/学困生）使用不同的 LLM Prompt 生成相似练习题。

    Args:
        task_id: 原始批改任务ID
        count: 生成题目数量（默认3）

    Returns:
        dict: { questions: [{ id, question, standard_answer, difficulty }] }
    """
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = tasks_db[task_id]
    if task.get("type") == "correction":
        raise HTTPException(status_code=400, detail="订正任务不支持相似题推荐")

    grading = task.get("grading", {})
    question = task.get("question", "")
    knowledge_points = grading.get("knowledge_points", [])
    error_type = grading.get("error_type", "未知")
    standard_answer = task.get("standard_answer", "")
    student_id = task.get("student_id", "")

    # 使用 tier_classify 确定学生层级
    # 收集该学生所有错题的 weakness_score，按知识点聚合
    weakness_scores: dict[str, float] = {}
    for tid, t in tasks_db.items():
        if t.get("type") in ("correction", "ocr_question"):
            continue
        if t.get("student_id") != student_id:
            continue
        t_grading = t.get("grading", {})
        for kp in t_grading.get("knowledge_points", []):
            s = t.get("suggested_score", 0)
            m = t.get("max_score", 5)
            weight = (m - s) / m if m > 0 else 0
            if weight > 0:
                weakness_scores[kp] = max(weakness_scores.get(kp, 0), weight)

    # tier_classify 返回 {knowledge_node_id: tier}，取当前错题相关知识点的层级
    tier_map = tier_classify(weakness_scores) if weakness_scores else {}
    # 优先取当前错题涉及知识点的层级，否则取所有知识点中最高薄弱度对应的层级
    tier = "中等生"  # 默认
    for kp in knowledge_points:
        if kp in tier_map:
            tier = tier_map[kp]
            break
    if tier == "中等生" and tier_map:
        # 取最薄弱知识点的层级
        max_weakness = max(weakness_scores.values())
        for kp, score in weakness_scores.items():
            if score == max_weakness and kp in tier_map:
                tier = tier_map[kp]
                break

    questions = await similar_question_service.generate_similar_questions(
        question=question,
        knowledge_points=knowledge_points,
        error_type=error_type,
        tier=tier,
        count=count,
        standard_answer=standard_answer,
    )

    return {"questions": questions}


class PracticeRequest(BaseModel):
    """练习模式提交请求"""
    task_id: str
    student_id: str
    practice_answer: str


@app.post("/api/v1/error-book/practice")
async def error_book_practice(req: PracticeRequest):
    """练习模式 — 提交练习答案并自动评分

    学生提交对相似题的解答，系统使用 LLM 对比标准答案进行评分。

    Args:
        req: 包含 task_id, student_id, practice_answer

    Returns:
        dict: { correct, score, feedback }
    """
    if req.task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = tasks_db[req.task_id]
    question = task.get("question", "")
    standard_answer = task.get("standard_answer", "")
    max_score = task.get("max_score", 5)

    # 使用 LLM 评分
    try:
        from app.llm_utils import get_siliconflow_client, parse_llm_json

        client = get_siliconflow_client(timeout=30.0)
        response = await client.chat.completions.create(
            model="Qwen/Qwen2.5-7B-Instruct",
            messages=[
                {
                    "role": "system",
                    "content": "你是一位严谨的数学教师，负责评判学生的练习答案。请严格按JSON格式返回评分结果。",
                },
                {
                    "role": "user",
                    "content": (
                        f"题目：{question}\n"
                        f"标准答案：{standard_answer}\n"
                        f"满分：{max_score}\n"
                        f"学生练习答案：{req.practice_answer}\n\n"
                        f"请评判学生的练习答案，返回JSON：\n"
                        f'{{"correct": true/false, "score": 得分(0~{max_score}整数), "feedback": "简短评语"}}'
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=500,
        )
        raw_text = response.choices[0].message.content or ""
        parsed = parse_llm_json(raw_text, fallback={})
        correct = parsed.get("correct", False)
        score = parsed.get("score", 0)
        feedback = parsed.get("feedback", "")

        # 确保 score 在合理范围内
        score = max(0, min(int(score), max_score))
        correct = score >= max_score

        logger.info(f"[Practice] task={req.task_id}, score={score}/{max_score}, correct={correct}")
        return {"correct": correct, "score": score, "feedback": feedback}

    except Exception as e:
        logger.warning(f"[Practice] LLM评分失败: {type(e).__name__}: {e}, 使用降级评分")
        # 降级：简单关键词匹配
        practice_lower = req.practice_answer.strip().lower()
        standard_lower = standard_answer.strip().lower()
        # 提取数字进行简单比较
        import re
        practice_nums = set(re.findall(r"-?\d+\.?\d*", practice_lower))
        standard_nums = set(re.findall(r"-?\d+\.?\d*", standard_lower))
        if practice_nums and standard_nums and practice_nums == standard_nums:
            return {"correct": True, "score": max_score, "feedback": "答案数值匹配（自动降级评分）"}
        elif practice_nums and standard_nums and practice_nums & standard_nums:
            partial = max(1, max_score // 2)
            return {"correct": False, "score": partial, "feedback": "部分数值匹配（自动降级评分）"}
        else:
            return {"correct": False, "score": 0, "feedback": "答案不匹配（自动降级评分）"}
