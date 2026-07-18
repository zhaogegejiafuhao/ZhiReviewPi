"""DynamicModelRouter 智能动态模型路由单元测试

测试目标：
- _classify_question: 题型分类（geometry/calculation/proof/application）
- _is_simple_question: 简单题判断
- route: 路由选择逻辑
- _is_model_reliable: 模型可靠性判断（准确率阈值）
- record_feedback: 教师反馈记录
- get_performance_stats: 统计数据

每个测试创建新的 DynamicModelRouter() 实例，避免状态污染。
"""
from app.model_router import (
    DynamicModelRouter,
    ACCURACY_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
)


# ===== _classify_question 测试 =====


def test_classify_question_geometry():
    """几何题关键词>=2 → "geometry" """
    router = DynamicModelRouter()
    # "三角形" + "证明" 都在 GEOMETRY_KEYWORDS 中，计2个
    result = router._classify_question("证明三角形全等")
    assert result == "geometry"


def test_classify_question_proof():
    """证明题关键词>=2 → "proof" """
    router = DynamicModelRouter()
    # "证明" + "求证" 都在 PROOF_KEYWORDS 中，计2个
    result = router._classify_question("证明并求证AB=CD")
    assert result == "proof"


def test_classify_question_application():
    """应用题关键词>=1 → "application" """
    router = DynamicModelRouter()
    # "应用" 在 APPLICATION_KEYWORDS 中
    result = router._classify_question("应用题：销售问题")
    assert result == "application"


def test_classify_question_calculation():
    """计算关键词>=1 → "calculation" """
    router = DynamicModelRouter()
    # "计算" 在 SIMPLE_QUESTION_KEYWORDS 中
    result = router._classify_question("计算 2+3")
    assert result == "calculation"


def test_classify_question_default():
    """无关键词 → "calculation" (默认) """
    router = DynamicModelRouter()
    result = router._classify_question("普通题目内容")
    assert result == "calculation"


# ===== _is_simple_question 测试 =====


def test_is_simple_question_short_calc():
    """短文本+计算关键词 → True"""
    router = DynamicModelRouter()
    # 文本短，包含"计算"关键词，不含证明/应用特征
    assert router._is_simple_question("计算 12+34") is True


def test_is_simple_question_with_proof():
    """包含证明关键词 → False"""
    router = DynamicModelRouter()
    # 包含"证明"，应排除简单题
    assert router._is_simple_question("证明：AB=CD") is False


def test_is_simple_question_long_text():
    """长文本但开头是"计算" → True"""
    router = DynamicModelRouter()
    # 以"计算"开头，无论文本多长都是简单题
    long_text = "计算" + "a" * 300
    assert router._is_simple_question(long_text) is True


# ===== route 测试 =====


def test_route_geometry_question():
    """is_geometry=True → "multimodal" """
    router = DynamicModelRouter()
    result = router.route("证明三角形ABC全等", confidence=0.9, is_geometry=True)
    assert result == "multimodal"


def test_route_geometry_low_confidence():
    """is_geometry=True + confidence<0.7 → "multimodal" """
    router = DynamicModelRouter()
    # 低置信度几何题仍路由到多模态模型
    result = router.route("三角形证明题", confidence=0.3, is_geometry=True)
    assert result == "multimodal"


def test_route_simple_question():
    """简单计算题 → "lightweight" """
    router = DynamicModelRouter()
    result = router.route("计算 12 + 34", confidence=0.9, is_geometry=False)
    assert result == "lightweight"


def test_route_complex_question():
    """证明题 → "long_context" """
    router = DynamicModelRouter()
    # 包含"证明"+"求证"+"因为"+"所以" → proof，路由到 long_context
    question = "已知AB=AC，求证：∠B=∠C，因为所以每一步都要写清楚"
    result = router.route(question, confidence=0.9, is_geometry=False)
    assert result == "long_context"


def test_route_default_question():
    """普通题 → "standard" """
    router = DynamicModelRouter()
    # 不是几何、不是简单题、不是证明/应用题、长度<=200
    result = router.route("这是一道普通题目", confidence=0.9, is_geometry=False)
    assert result == "standard"


def test_route_with_unreliable_model():
    """模型准确率<80%时降级到备选模型"""
    router = DynamicModelRouter()
    # 让 lightweight 在 calculation 题型上准确率不达标
    # 5次调用，3次被修正 → accuracy = 1 - 3/5 = 0.4 < 0.8
    for _ in range(2):
        router.record_feedback("lightweight", "calculation", False)
    for _ in range(3):
        router.record_feedback("lightweight", "calculation", True)
    # 简单计算题应路由到 lightweight，但因不可靠降级到 standard
    result = router.route("计算 12+34", confidence=0.9, is_geometry=False)
    assert result == "standard"


# ===== record_feedback 测试 =====


def test_record_feedback_positive():
    """教师确认（was_corrected=False）不增加corrected_calls"""
    router = DynamicModelRouter()
    router.record_feedback("standard", "calculation", was_corrected=False)
    stats = router.get_performance_stats()
    assert stats["models"]["standard"]["corrected_calls"] == 0


def test_record_feedback_negative():
    """教师修正（was_corrected=True）增加corrected_calls"""
    router = DynamicModelRouter()
    router.record_feedback("standard", "calculation", was_corrected=True)
    stats = router.get_performance_stats()
    assert stats["models"]["standard"]["corrected_calls"] == 1


def test_record_feedback_accuracy_calculation():
    """多次反馈后准确率正确计算"""
    router = DynamicModelRouter()
    # 4次确认正确 + 1次修正 → accuracy = 1 - 1/5 = 0.8
    for _ in range(4):
        router.record_feedback("standard", "calculation", was_corrected=False)
    router.record_feedback("standard", "calculation", was_corrected=True)
    stats = router.get_performance_stats()
    assert stats["models"]["standard"]["accuracy"] == 0.8


# ===== get_performance_stats 测试 =====


def test_get_performance_stats():
    """统计数据格式正确"""
    router = DynamicModelRouter()
    stats = router.get_performance_stats()
    # 顶层结构
    assert "models" in stats
    assert "accuracy_threshold" in stats
    assert "low_confidence_threshold" in stats
    assert stats["accuracy_threshold"] == ACCURACY_THRESHOLD
    assert stats["low_confidence_threshold"] == LOW_CONFIDENCE_THRESHOLD
    # 每个模型应包含必要字段
    for model_stats in stats["models"].values():
        assert "model_id" in model_stats
        assert "model_name" in model_stats
        assert "total_calls" in model_stats
        assert "corrected_calls" in model_stats
        assert "accuracy" in model_stats
        assert "by_question_type" in model_stats


# ===== _is_model_reliable 测试 =====


def test_is_model_reliable_no_data():
    """无数据时默认可靠"""
    router = DynamicModelRouter()
    # 新实例无任何反馈数据，应默认可靠
    assert router._is_model_reliable("standard", "calculation") is True


def test_is_model_reliable_with_data():
    """有足够数据时根据准确率判断"""
    router = DynamicModelRouter()
    # 5次调用，3次修正 → accuracy = 1 - 3/5 = 0.4 < 0.8 → 不可靠
    for _ in range(2):
        router.record_feedback("standard", "calculation", was_corrected=False)
    for _ in range(3):
        router.record_feedback("standard", "calculation", was_corrected=True)
    assert router._is_model_reliable("standard", "calculation") is False

    # 重新测试：5次调用，1次修正 → accuracy = 1 - 1/5 = 0.8 >= 0.8 → 可靠
    router2 = DynamicModelRouter()
    for _ in range(4):
        router2.record_feedback("standard", "calculation", was_corrected=False)
    router2.record_feedback("standard", "calculation", was_corrected=True)
    assert router2._is_model_reliable("standard", "calculation") is True
