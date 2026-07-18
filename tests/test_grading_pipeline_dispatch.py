"""_execute_grading_pipeline 学科分发测试

测试目标：
- subject=chinese → 调用 essay_grader.grade，不调用 math_grader.grade
- subject=math → 调用 math_grader.grade（回归）
- subject=chinese → 跳过 rubric_generator.generate
- subject=chinese → 即使题目含"证明"，geometry_analyzer.analyze 不被调用
- subject=chinese → 评语由 essay_grader.generate_comment 生成
"""
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

try:
    from app.grader import FALLBACK_ESSAY_RUBRIC
    import app.main as main_module
    from app.main import _execute_grading_pipeline
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

pytestmark = pytest.mark.skipif(not _HAS_OPENAI, reason="缺少依赖")


# ===== 辅助函数 =====


def _make_ocr_result(text="作文正文", confidence=0.9):
    """构造一个模拟的 OCR 结果对象"""
    ocr = MagicMock()
    ocr.text = text
    ocr.confidence = confidence
    ocr.engines_used = ["paddle"]
    ocr.regions = []
    # needs_manual_input 属性默认不存在（None 即 falsy）
    ocr.needs_manual_input = False
    return ocr


def _make_essay_grading_result(total_score=79, max_score=100):
    """构造一个 EssayGrader.grade 返回值（兼容结构）"""
    return {
        "steps": [
            {"step_id": "dim_content", "content": "内容：ok", "correct": True, "score": 32,
             "rubric_ref": "dim_content", "error_reason": None, "max_score": 40},
            {"step_id": "dim_structure", "content": "结构：ok", "correct": True, "score": 16,
             "rubric_ref": "dim_structure", "error_reason": None, "max_score": 20},
            {"step_id": "dim_language", "content": "语言：weak", "correct": False, "score": 18,
             "rubric_ref": "dim_language", "error_reason": "修辞单一", "max_score": 25},
            {"step_id": "dim_handwriting", "content": "书写：ok", "correct": True, "score": 13,
             "rubric_ref": "dim_handwriting", "error_reason": None, "max_score": 15},
        ],
        "total_score": total_score,
        "max_score": max_score,
        "error_type": "language_issue",
        "error_cause": "修辞单一",
        "knowledge_points": ["语言"],
        "grading_method": "essay_llm",
        "_model_key": "standard",
        "dimensions": {
            "content": {"score": 32, "max_score": 40, "comment": "立意准确", "error_cause": "none"},
            "structure": {"score": 16, "max_score": 20, "comment": "结构清晰", "error_cause": "none"},
            "language": {"score": 18, "max_score": 25, "comment": "用词单一", "error_cause": "修辞单一"},
            "handwriting": {"score": 13, "max_score": 15, "comment": "字迹工整", "error_cause": "none"},
        },
        "overall_comment": "整体表现良好。",
        "comment": "整体表现良好。",
    }


def _make_math_grading_result(total_score=4, max_score=5):
    """构造一个 MathGrader.grade 返回值"""
    return {
        "steps": [
            {"step_id": "s1", "content": "列方程", "correct": True, "score": 2,
             "rubric_ref": "s1", "error_reason": None},
            {"step_id": "s2", "content": "计算过程", "correct": True, "score": 2,
             "rubric_ref": "s2", "error_reason": None},
            {"step_id": "s3", "content": "答案", "correct": False, "score": 0,
             "rubric_ref": "s3", "error_reason": "计算错误"},
        ],
        "total_score": total_score,
        "max_score": max_score,
        "error_type": "calculation_error",
        "error_cause": "计算粗心",
        "knowledge_points": ["一元一次方程"],
        "comment": "思路正确，计算出错。",
        "_model_key": "standard",
    }


# ===== 分发测试 =====


@pytest.mark.asyncio
async def test_pipeline_chinese_dispatches_to_essay_grader():
    """subject=chinese → 调用 essay_grader.grade，不调用 math_grader.grade"""
    ocr_mock = _make_ocr_result()
    with patch("app.main.ocr_service.recognize", new_callable=AsyncMock, return_value=ocr_mock), \
         patch("app.main.grading_service.essay_grader.grade",
               new_callable=AsyncMock, return_value=_make_essay_grading_result()) as mock_essay_grade, \
         patch("app.main.grading_service.essay_grader.generate_comment",
               new_callable=AsyncMock, return_value="评语") as mock_essay_comment, \
         patch("app.main.grading_service.math_grader.grade",
               new_callable=AsyncMock) as mock_math_grade, \
         patch("app.main.question_bank.store") as mock_qb_store:
        result = await _execute_grading_pipeline(
            question="以《我的梦想》为题写一篇作文",
            standard_answer="立意深刻",
            all_image_bytes=[b"fake_image_bytes"],
            subject="chinese",
            grade=7,
            total_score=100,
            homework_id="hw_001",
            student_id="stu_001",
        )
    # essay_grader.grade 被调用一次
    mock_essay_grade.assert_awaited_once()
    # math_grader.grade 不应被调用
    mock_math_grade.assert_not_awaited()
    # 评语由 essay_grader 生成
    mock_essay_comment.assert_awaited_once()
    # 结果状态
    assert result["status"] == "completed"
    assert result["suggested_score"] == 79
    assert result["model_key"] == "standard"


@pytest.mark.asyncio
async def test_pipeline_math_dispatches_to_math_grader():
    """subject=math → 调用 math_grader.grade，不调用 essay_grader.grade（回归）"""
    ocr_mock = _make_ocr_result(text="2x+3=7\nx=2")
    with patch("app.main.ocr_service.recognize", new_callable=AsyncMock, return_value=ocr_mock), \
         patch("app.main.grading_service.rubric_generator.generate",
               new_callable=AsyncMock, return_value={"steps": []}) as mock_rubric_gen, \
         patch("app.main.grading_service.math_grader.grade",
               new_callable=AsyncMock, return_value=_make_math_grading_result()) as mock_math_grade, \
         patch("app.main.grading_service.math_grader.generate_comment",
               new_callable=AsyncMock, return_value="评语"), \
         patch("app.main.grading_service.essay_grader.grade",
               new_callable=AsyncMock) as mock_essay_grade, \
         patch("app.main.question_bank.store"):
        result = await _execute_grading_pipeline(
            question="解方程 2x+3=7",
            standard_answer="x=2",
            all_image_bytes=[b"fake_image_bytes"],
            subject="math",
            grade=7,
            total_score=5,
            homework_id="hw_002",
            student_id="stu_001",
        )
    mock_math_grade.assert_awaited_once()
    mock_essay_grade.assert_not_awaited()
    # math 路径会调用 rubric_generator
    mock_rubric_gen.assert_awaited_once()
    assert result["suggested_score"] == 4


@pytest.mark.asyncio
async def test_pipeline_chinese_skips_rubric_generator():
    """subject=chinese → rubric_generator.generate 不被调用，使用 FALLBACK_ESSAY_RUBRIC"""
    ocr_mock = _make_ocr_result()
    with patch("app.main.ocr_service.recognize", new_callable=AsyncMock, return_value=ocr_mock), \
         patch("app.main.grading_service.rubric_generator.generate",
               new_callable=AsyncMock) as mock_rubric_gen, \
         patch("app.main.grading_service.essay_grader.grade",
               new_callable=AsyncMock, return_value=_make_essay_grading_result()), \
         patch("app.main.grading_service.essay_grader.generate_comment",
               new_callable=AsyncMock, return_value="评语"), \
         patch("app.main.question_bank.store") as mock_qb_store:
        result = await _execute_grading_pipeline(
            question="以《成长》为题",
            standard_answer="立意深刻，结构完整，语言流畅",
            all_image_bytes=[b"image"],
            subject="chinese",
            grade=7,
            total_score=100,
            homework_id="hw_003",
            student_id="stu_002",
        )
    mock_rubric_gen.assert_not_awaited()
    # rubric 字段应为 FALLBACK_ESSAY_RUBRIC 副本
    assert result["rubric"]["type"] == "essay"
    assert len(result["rubric"]["dimensions"]) == 4
    # question_bank.store 接收到的 rubric 也是 FALLBACK_ESSAY_RUBRIC
    _, kwargs = mock_qb_store.call_args
    assert kwargs.get("rubric", {}).get("type") == "essay"


@pytest.mark.asyncio
async def test_pipeline_chinese_skips_geometry_analysis():
    """subject=chinese → 题目含'证明'，geometry_analyzer.analyze 也不被调用"""
    ocr_mock = _make_ocr_result()
    # 题目含 "证明" — 几何关键词，但因 is_essay 短路，不应触发几何分析
    with patch("app.main.ocr_service.recognize", new_callable=AsyncMock, return_value=ocr_mock), \
         patch("app.main.grading_service.essay_grader.grade",
               new_callable=AsyncMock, return_value=_make_essay_grading_result()), \
         patch("app.main.grading_service.essay_grader.generate_comment",
               new_callable=AsyncMock, return_value="评语"), \
         patch("app.main.geometry_analyzer.analyze",
               new_callable=AsyncMock) as mock_geo_analyze, \
         patch("app.main.question_bank.store"):
        result = await _execute_grading_pipeline(
            question="请以《用行动证明自己》为题写一篇不少于600字的作文",
            standard_answer="",
            all_image_bytes=[b"image"],
            subject="chinese",
            grade=7,
            total_score=100,
            homework_id="hw_004",
            student_id="stu_003",
            geometry_detected=True,  # 模拟上游误判
        )
    # 即使 geometry_detected=True，因 is_essay 短路，几何分析不应触发
    mock_geo_analyze.assert_not_awaited()
    assert "geometry_analysis" not in result


@pytest.mark.asyncio
async def test_pipeline_chinese_comment_from_essay_grader():
    """subject=chinese → 评语由 essay_grader.generate_comment 生成（而非 math_grader）"""
    ocr_mock = _make_ocr_result()
    expected_comment = "本文立意深刻，语言流畅，建议在修辞上多下功夫。"
    with patch("app.main.ocr_service.recognize", new_callable=AsyncMock, return_value=ocr_mock), \
         patch("app.main.grading_service.essay_grader.grade",
               new_callable=AsyncMock, return_value=_make_essay_grading_result()), \
         patch("app.main.grading_service.essay_grader.generate_comment",
               new_callable=AsyncMock, return_value=expected_comment) as mock_essay_comment, \
         patch("app.main.grading_service.math_grader.generate_comment",
               new_callable=AsyncMock) as mock_math_comment, \
         patch("app.main.question_bank.store"):
        result = await _execute_grading_pipeline(
            question="以《家乡》为题写作文",
            standard_answer="",
            all_image_bytes=[b"image"],
            subject="chinese",
            grade=7,
            total_score=100,
            homework_id="hw_005",
            student_id="stu_004",
        )
    mock_essay_comment.assert_awaited_once()
    mock_math_comment.assert_not_awaited()
    assert result["comment"] == expected_comment
