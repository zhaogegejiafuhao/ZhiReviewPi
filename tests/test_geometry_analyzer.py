"""GeometryAnalyzer 几何辅助线溯源逻辑单元测试

测试目标：
- is_geometry_question: 几何题关键词识别
- _default_result: 降级默认结果字段校验
- parse_llm_json: 通用JSON解析（直接/Markdown代码块/混合文本/无效/空字符串）
- analyze: VL模型不可用时返回默认结果、VL调用失败时降级返回默认结果
- 异步测试使用 pytest.mark.asyncio 装饰器
"""
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# 由于 geometry_analyzer 顶部 from openai import AsyncOpenAI，
# 若 openai 未安装则跳过整个测试模块
try:
    from app.geometry_analyzer import (
        is_geometry_question,
        GeometryAnalyzer,
        GeometryAnalysisResult,
    )
    from app.llm_utils import parse_llm_json
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False
    is_geometry_question = None
    GeometryAnalyzer = None
    GeometryAnalysisResult = None

pytestmark = pytest.mark.skipif(not _HAS_OPENAI, reason="缺少 openai 依赖")


# ===== is_geometry_question 测试 =====


def test_is_geometry_question_triangle():
    """'三角形' → True"""
    assert is_geometry_question("求三角形的面积") is True


def test_is_geometry_question_circle():
    """'圆的面积' → True"""
    assert is_geometry_question("圆的面积是多少") is True


def test_is_geometry_question_not():
    """'计算2+3' → False"""
    assert is_geometry_question("计算2+3") is False


def test_is_geometry_question_proof():
    """'证明三角形全等' → True"""
    assert is_geometry_question("证明三角形全等") is True


# ===== _default_result 测试 =====


def test_default_result_fields():
    """默认结果字段值正确"""
    result = GeometryAnalyzer._default_result()
    assert isinstance(result, GeometryAnalysisResult)
    assert result.has_auxiliary_line is False
    assert result.assessment == "缺失关键辅助线"
    assert result.standard_line_desc == ""
    assert result.hint == ""


# ===== parse_llm_json 测试 =====


def test_parse_json_valid():
    """有效JSON字符串解析成功"""
    text = '{"has_auxiliary_line": true, "auxiliary_line_desc": "连接了AC"}'
    result = parse_llm_json(text)
    assert result["has_auxiliary_line"] is True
    assert result["auxiliary_line_desc"] == "连接了AC"


def test_parse_json_with_markdown():
    """```json...``` 格式解析成功"""
    text = '```json\n{"key": "value"}\n```'
    result = parse_llm_json(text)
    assert result == {"key": "value"}


def test_parse_json_with_braces():
    """混合文本中的{...}提取成功"""
    text = '分析结果如下：\n{"key": "value"}\n以上是结果'
    result = parse_llm_json(text)
    assert result == {"key": "value"}


def test_parse_json_invalid():
    """无效JSON返回空字典"""
    result = parse_llm_json("not a json at all")
    assert result == {}


def test_parse_json_empty():
    """空字符串返回空字典"""
    result = parse_llm_json("")
    assert result == {}


# ===== analyze 异步测试 =====


@pytest.mark.asyncio
async def test_analyze_no_api_key():
    """VL模型不可用时返回默认结果"""
    with patch("app.geometry_analyzer.settings") as mock_settings:
        mock_settings.SILICONFLOW_API_KEY = None
        mock_settings.SILICONFLOW_BASE_URL = "http://fake"
        analyzer = GeometryAnalyzer()
        result = await analyzer.analyze("证明三角形全等", b"image_bytes")
        assert isinstance(result, GeometryAnalysisResult)
        assert result.has_auxiliary_line is False
        assert result.assessment == "缺失关键辅助线"


@pytest.mark.asyncio
async def test_analyze_vl_failure():
    """VL调用失败时降级返回默认结果"""
    with patch("app.geometry_analyzer.settings") as mock_settings:
        mock_settings.SILICONFLOW_API_KEY = "fake_key"
        mock_settings.SILICONFLOW_BASE_URL = "http://fake"

        with patch("app.geometry_analyzer.AsyncOpenAI") as mock_openai_cls:
            mock_vl_client = MagicMock()
            mock_vl_client.chat.completions.create = AsyncMock(side_effect=Exception("VL error"))
            mock_llm_client = MagicMock()

            mock_openai_cls.side_effect = [mock_vl_client, mock_llm_client]

            analyzer = GeometryAnalyzer()
            result = await analyzer.analyze("证明三角形全等", b"image_bytes")

            assert isinstance(result, GeometryAnalysisResult)
            assert result.has_auxiliary_line is False
            assert result.assessment == "缺失关键辅助线"
