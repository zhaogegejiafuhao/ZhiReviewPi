"""EssayGrader 语文作文四维批改单元测试

测试目标：
- _validate_error_cause: 白名单校验
- _build_compatible_steps: steps 兼容 MathGrader 结构
- _normalize_to_total: 100分制→题目总分缩放
- _template_grade: Level 2 启发式降级
- grade: LLM 主路径 + doubao 降级 + 全失败 template 降级
- generate_comment: 评语生成 + 模板兜底

mock 模式参考 tests/test_geometry_analyzer.py。
"""
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# 防御性 import：缺少 openai 时跳过整个模块
try:
    from app.grader import EssayGrader, FALLBACK_ESSAY_RUBRIC
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

pytestmark = pytest.mark.skipif(not _HAS_OPENAI, reason="缺少 openai 依赖")


# ===== 辅助函数 =====


def _make_chat_response(content: str):
    """构造一个模拟的 chat.completions.create 返回值"""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


def _make_valid_dimensions_json() -> str:
    """返回一个合法的 LLM 四维评分 JSON 字符串"""
    import json
    payload = {
        "dimensions": {
            "content": {"score": 32, "max_score": 40, "comment": "立意准确，素材丰富", "error_cause": "none"},
            "structure": {"score": 16, "max_score": 20, "comment": "结构清晰，过渡自然", "error_cause": "none"},
            "language": {"score": 18, "max_score": 25, "comment": "用词略显单一", "error_cause": "修辞单一"},
            "handwriting": {"score": 13, "max_score": 15, "comment": "字迹工整", "error_cause": "none"},
        },
        "primary_error_cause": "修辞单一",
        "knowledge_points": ["语言"],
        "overall_comment": "整体表现良好，语言可进一步丰富。",
    }
    return json.dumps(payload, ensure_ascii=False)


# ===== _validate_error_cause 测试 =====


def test_validate_error_cause_valid():
    """5 个白名单标签原样返回"""
    grader = EssayGrader()
    for cause in EssayGrader.ESSAY_ERROR_CAUSES:
        assert grader._validate_error_cause(cause) == cause


def test_validate_error_cause_none_pass_through():
    """'none' 原样返回"""
    assert EssayGrader()._validate_error_cause("none") == "none"


def test_validate_error_cause_invalid():
    """非法值降为 'none'"""
    assert EssayGrader()._validate_error_cause("不存在的错因") == "none"
    assert EssayGrader()._validate_error_cause("") == "none"
    assert EssayGrader()._validate_error_cause(None) == "none"


# ===== _build_compatible_steps 测试 =====


def test_build_compatible_steps_structure():
    """steps 含 4 项，每项字段齐全且 step_id 为 dim_xxx"""
    grader = EssayGrader()
    dimensions = {
        "content": {"score": 32, "max_score": 40, "comment": "ok", "error_cause": "none"},
        "structure": {"score": 16, "max_score": 20, "comment": "ok", "error_cause": "none"},
        "language": {"score": 18, "max_score": 25, "comment": "ok", "error_cause": "修辞单一"},
        "handwriting": {"score": 13, "max_score": 15, "comment": "ok", "error_cause": "none"},
    }
    steps = grader._build_compatible_steps(dimensions)
    assert len(steps) == 4
    expected_ids = {"dim_content", "dim_structure", "dim_language", "dim_handwriting"}
    assert {s["step_id"] for s in steps} == expected_ids
    for s in steps:
        # MathGrader 兼容字段
        assert "content" in s
        assert "correct" in s
        assert "score" in s
        assert "rubric_ref" in s
        assert "error_reason" in s
        assert "max_score" in s
    # 得分率 >= 0.8 应判 correct=True（32/40=0.8）
    content_step = next(s for s in steps if s["step_id"] == "dim_content")
    assert content_step["correct"] is True
    # 18/25=0.72 < 0.8，应判 correct=False，error_reason 来自 error_cause
    language_step = next(s for s in steps if s["step_id"] == "dim_language")
    assert language_step["correct"] is False
    assert language_step["error_reason"] == "修辞单一"


# ===== _normalize_to_total 测试 =====


def test_normalize_to_total_100():
    """100 分制不变"""
    grader = EssayGrader()
    raw = {
        "dimensions": {
            "content": {"score": 32, "max_score": 40, "comment": "", "error_cause": "none"},
            "structure": {"score": 16, "max_score": 20, "comment": "", "error_cause": "none"},
            "language": {"score": 18, "max_score": 25, "comment": "", "error_cause": "none"},
            "handwriting": {"score": 13, "max_score": 15, "comment": "", "error_cause": "none"},
        },
    }
    result = grader._normalize_to_total(raw, 100)
    assert result["total_score"] == 79  # 32+16+18+13
    assert result["max_score"] == 100


def test_normalize_to_total_50():
    """100 分制 → 50 分制按比例缩放"""
    grader = EssayGrader()
    raw = {
        "dimensions": {
            "content": {"score": 32, "max_score": 40, "comment": "", "error_cause": "none"},
            "structure": {"score": 16, "max_score": 20, "comment": "", "error_cause": "none"},
            "language": {"score": 18, "max_score": 25, "comment": "", "error_cause": "none"},
            "handwriting": {"score": 13, "max_score": 15, "comment": "", "error_cause": "none"},
        },
    }
    result = grader._normalize_to_total(raw, 50)
    assert result["max_score"] == 50
    # 32 * 0.5 = 16
    assert result["dimensions"]["content"]["score"] == 16
    assert result["dimensions"]["content"]["max_score"] == 20
    # 13 * 0.5 = 6.5
    assert result["dimensions"]["handwriting"]["score"] == 6.5
    # 总分 79 * 0.5 = 39.5
    assert result["total_score"] == 39.5


# ===== _template_grade 测试 =====


def test_template_grade_returns_complete_fields():
    """Level 2 降级返回字段齐全"""
    grader = EssayGrader()
    long_essay = "段落一。\n段落二。\n段落三。\n" + "字" * 600
    result = grader._template_grade("我的梦想", long_essay, 100, confidence=0.5)
    assert "dimensions" in result
    assert "primary_error_cause" in result
    assert "knowledge_points" in result
    assert "overall_comment" in result
    # 四维齐全
    for dim_key in EssayGrader.DIMENSION_WEIGHTS:
        assert dim_key in result["dimensions"]
        dim_data = result["dimensions"][dim_key]
        assert "score" in dim_data
        assert "max_score" in dim_data
        assert "comment" in dim_data
        assert "error_cause" in dim_data


def test_template_grade_low_confidence_triggers_handwriting_cause():
    """低置信度时 handwriting 维度 error_cause 为 '书写潦草'"""
    grader = EssayGrader()
    long_essay = "段落一。\n段落二。\n" + "字" * 600
    result = grader._template_grade("题目", long_essay, 100, confidence=0.5)
    # confidence=0.5 → handwriting_ratio=0.5 < 0.6 → error_cause='书写潦草'
    assert result["dimensions"]["handwriting"]["error_cause"] == "书写潦草"


# ===== grade() 主路径测试 =====


@pytest.mark.asyncio
async def test_grade_success_mock_llm():
    """mock qwen_client 返回合法 dimensions，验证 grade() 输出字段齐全"""
    grader = EssayGrader()
    # 替换 qwen_client 为 mock
    mock_qwen = MagicMock()
    mock_qwen.chat.completions.create = AsyncMock(return_value=_make_chat_response(_make_valid_dimensions_json()))
    grader.qwen_client = mock_qwen

    result = await grader.grade(
        question="请以《我的梦想》为题写一篇不少于600字的作文",
        standard_answer="立意新颖，结构完整，语言流畅",
        student_answer="（作文正文略）" + "字" * 600,
        total_score=100,
        confidence=0.9,
    )

    # 必须字段齐全
    for key in ["steps", "total_score", "max_score", "error_type", "error_cause",
                "knowledge_points", "_model_key", "dimensions"]:
        assert key in result, f"缺少字段 {key}"
    # _model_key 为 standard（qwen 路径）
    assert result["_model_key"] == "standard"
    assert result["grading_method"] == "essay_llm"
    # error_cause 在白名单内
    assert result["error_cause"] in EssayGrader.ESSAY_ERROR_CAUSES + ["none"]
    # steps 含 4 项
    assert len(result["steps"]) == 4
    # dimensions 含 4 维
    for dim_key in EssayGrader.DIMENSION_WEIGHTS:
        assert dim_key in result["dimensions"]


@pytest.mark.asyncio
async def test_grade_doubao_fallback():
    """qwen 抛异常，豆包成功，验证 _model_key == 'doubao'"""
    grader = EssayGrader()
    mock_qwen = MagicMock()
    mock_qwen.chat.completions.create = AsyncMock(side_effect=Exception("Qwen unavailable"))
    grader.qwen_client = mock_qwen

    mock_doubao = MagicMock()
    mock_doubao.chat.completions.create = AsyncMock(return_value=_make_chat_response(_make_valid_dimensions_json()))
    grader.doubao_client = mock_doubao

    result = await grader.grade(
        question="以《秋天》为题写作文",
        standard_answer="描写生动",
        student_answer="（作文略）" + "字" * 500,
        total_score=100,
        confidence=0.85,
    )
    assert result["_model_key"] == "doubao"
    assert result["grading_method"] == "essay_llm"
    assert "dimensions" in result


@pytest.mark.asyncio
async def test_grade_all_llm_fail():
    """qwen 和 doubao 都失败，验证 grading_method == 'essay_template_fallback'"""
    grader = EssayGrader()
    mock_qwen = MagicMock()
    mock_qwen.chat.completions.create = AsyncMock(side_effect=Exception("Qwen down"))
    grader.qwen_client = mock_qwen

    mock_doubao = MagicMock()
    mock_doubao.chat.completions.create = AsyncMock(side_effect=Exception("Doubao down"))
    grader.doubao_client = mock_doubao

    result = await grader.grade(
        question="请以《成长》为题写一篇作文",
        standard_answer="",
        student_answer="段落一。\n段落二。\n" + "字" * 600,
        total_score=100,
        confidence=0.9,
    )
    assert result["grading_method"] == "essay_template_fallback"
    assert result["_model_key"] == "template_fallback"
    # 仍需输出兼容字段
    assert "dimensions" in result
    assert "steps" in result
    assert "total_score" in result


@pytest.mark.asyncio
async def test_grade_with_total_score_50():
    """total_score=50 时四维按比例缩放"""
    grader = EssayGrader()
    mock_qwen = MagicMock()
    mock_qwen.chat.completions.create = AsyncMock(return_value=_make_chat_response(_make_valid_dimensions_json()))
    grader.qwen_client = mock_qwen

    result = await grader.grade(
        question="以《家乡》为题",
        standard_answer="",
        student_answer="（作文）" + "字" * 600,
        total_score=50,
        confidence=0.9,
    )
    # max_score 应为 50（不是 100）
    assert result["max_score"] == 50
    # content 原始 32/40，缩放后 16/20
    assert result["dimensions"]["content"]["score"] == 16
    assert result["dimensions"]["content"]["max_score"] == 20


# ===== generate_comment 测试 =====


@pytest.mark.asyncio
async def test_generate_comment_success():
    """mock qwen 返回评语，验证非空"""
    grader = EssayGrader()
    mock_qwen = MagicMock()
    mock_qwen.chat.completions.create = AsyncMock(return_value=_make_chat_response("本文立意深刻，语言流畅，结构清晰。"))
    grader.qwen_client = mock_qwen

    dimensions = {
        "content": {"score": 32, "max_score": 40, "comment": "立意准确", "error_cause": "none"},
        "structure": {"score": 16, "max_score": 20, "comment": "结构清晰", "error_cause": "none"},
        "language": {"score": 18, "max_score": 25, "comment": "用词单一", "error_cause": "修辞单一"},
        "handwriting": {"score": 13, "max_score": 15, "comment": "字迹工整", "error_cause": "none"},
    }
    comment = await grader.generate_comment(
        question="我的梦想",
        score=79,
        max_score=100,
        dimensions=dimensions,
        error_cause="修辞单一",
        knowledge_points=["语言"],
    )
    assert comment
    assert "本文立意深刻" in comment


@pytest.mark.asyncio
async def test_generate_comment_fallback():
    """LLM 失败时降级为模板评语，含'本文'关键字"""
    grader = EssayGrader()
    mock_qwen = MagicMock()
    mock_qwen.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))
    grader.qwen_client = mock_qwen

    dimensions = {
        "content": {"score": 20, "max_score": 40, "comment": "立意不清", "error_cause": "偏题跑题"},
        "structure": {"score": 10, "max_score": 20, "comment": "结构松散", "error_cause": "逻辑断层"},
        "language": {"score": 12, "max_score": 25, "comment": "语言平淡", "error_cause": "修辞单一"},
        "handwriting": {"score": 8, "max_score": 15, "comment": "字迹潦草", "error_cause": "书写潦草"},
    }
    comment = await grader.generate_comment(
        question="我的梦想",
        score=50,
        max_score=100,
        dimensions=dimensions,
        error_cause="偏题跑题",
        knowledge_points=["内容"],
    )
    # 模板评语应包含"本文"
    assert "本文" in comment
