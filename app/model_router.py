"""希沃智教π 智能动态模型路由

根据题型、置信度、模型历史准确率动态选择最优LLM模型，
实现低置信几何题自动切换多模态模型、高峰期分流、
基于教师修正反馈的长期模型效果评估与自动切换。
"""
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ===== 模型常量定义 =====

MODELS = {
    "lightweight": "Qwen/Qwen2.5-7B-Instruct",       # 轻量模型：简单计算题
    "standard": "Qwen/Qwen2.5-14B-Instruct",          # 标准模型：通用批改
    "multimodal": "doubao-vision",                     # 豆包多模态：几何题/低置信重审
    "long_context": "Qwen/Qwen2.5-14B-Instruct",      # 长文本模型：复杂大题（复用standard，可独立配置）
}

# 低于此准确率自动切换到备选模型
ACCURACY_THRESHOLD = 0.8

# 低置信度阈值（与config.py中LOW_CONFIDENCE_THRESHOLD对齐）
LOW_CONFIDENCE_THRESHOLD = 0.7

# 简单题特征关键词
SIMPLE_QUESTION_KEYWORDS = [
    "计算", "求值", "化简",
    "+", "-", "*", "/", "加", "减", "乘", "除",
]

# 几何题特征关键词
GEOMETRY_KEYWORDS = [
    "证明", "三角形", "圆", "平行", "垂直", "角", "线段",
    "辅助线", "相似", "全等", "四边形", "矩形", "菱形",
    "梯形", "弧", "弦", "切线", "割线", "垂心", "内心",
    "外心", "重心", "对称", "旋转", "平移",
]

# 证明/应用题特征关键词
PROOF_KEYWORDS = [
    "证明", "求证", "推导", "已知", "求证", "因为", "所以",
]

APPLICATION_KEYWORDS = [
    "应用", "实际", "生活", "工程", "方案", "设计",
    "至少", "最多", "不超过", "不小于",
]


# ===== 数据类 =====

@dataclass
class ModelPerformance:
    """单个模型在各题型上的准确率统计

    Attributes:
        model_id: 模型标识（对应MODELS中的key）
        total_calls: 总调用次数
        corrected_calls: 被教师修正的次数
        accuracy: 综合准确率 = 1 - (corrected_calls / total_calls)，total_calls为0时为0.0
        by_question_type: 按题型细分的统计 {q_type: {total, corrected, accuracy}}
    """
    model_id: str
    total_calls: int = 0
    corrected_calls: int = 0
    accuracy: float = 0.0
    by_question_type: dict[str, dict] = field(default_factory=dict)

    def recalculate(self):
        """重新计算综合准确率和各题型准确率"""
        if self.total_calls > 0:
            self.accuracy = round(1.0 - (self.corrected_calls / self.total_calls), 4)
        else:
            self.accuracy = 0.0

        for q_type, stats in self.by_question_type.items():
            t = stats.get("total", 0)
            c = stats.get("corrected", 0)
            stats["accuracy"] = round(1.0 - (c / t), 4) if t > 0 else 0.0


# ===== 动态模型路由器 =====

class DynamicModelRouter:
    """智能动态模型路由器

    根据题型、置信度、模型历史表现动态选择最优LLM模型：
    1. 几何题+低置信度 -> 多模态模型（doubao-vision）
    2. 简单计算题 -> 轻量模型（Qwen2.5-7B）
    3. 复杂大题 -> 长文本模型
    4. 如果某模型在对应题型上准确率<80% -> 自动切换到备选模型

    线程安全：所有写操作通过 threading.Lock 保护。
    路由是"可选增强"，出错时回退到默认模型（standard）。
    """

    # 备选模型映射：当某模型准确率不达标时切换的备选
    FALLBACK_MAP = {
        "lightweight": "standard",
        "standard": "long_context",
        "multimodal": "standard",
        "long_context": "standard",
    }

    def __init__(self):
        self._performances: dict[str, ModelPerformance] = {}
        self._lock = threading.Lock()
        # 初始化所有模型的统计记录
        for model_key in MODELS:
            self._performances[model_key] = ModelPerformance(model_id=model_key)

    def route(
        self,
        question: str,
        confidence: float = 0.0,
        is_geometry: bool = False,
    ) -> str:
        """根据题目特征路由到最优模型

        Args:
            question: 题目文本
            confidence: 置信度（0.0-1.0），通常来自OCR或前一轮LLM判定
            is_geometry: 是否为几何题（外部检测传入）

        Returns:
            model_key: MODELS中对应的模型key（如"standard"、"multimodal"等）
        """
        try:
            model_key = self._do_route(question, confidence, is_geometry)
            # 记录调用
            with self._lock:
                perf = self._performances.get(model_key)
                if perf:
                    perf.total_calls += 1
                    q_type = self._classify_question(question)
                    type_stats = perf.by_question_type.setdefault(q_type, {"total": 0, "corrected": 0, "accuracy": 0.0})
                    type_stats["total"] += 1
            return model_key
        except Exception as e:
            # 路由出错时回退到默认模型
            logger.warning(f"[DynamicModelRouter] 路由异常: {type(e).__name__}: {e}, 回退到standard模型")
            return "standard"

    def _do_route(self, question: str, confidence: float, is_geometry: bool) -> str:
        """核心路由逻辑（内部方法）"""
        q_type = self._classify_question(question)

        # 规则1: 几何题优先判定（几何题不走轻量模型）
        if is_geometry:
            candidate = "multimodal"
            if self._is_model_reliable(candidate, q_type):
                suffix = "低置信度重审" if confidence < LOW_CONFIDENCE_THRESHOLD else "高置信度"
                logger.info(f"[DynamicModelRouter] 几何题({suffix}, conf={confidence:.2f}) -> 多模态模型({candidate})")
                return candidate
            fallback = self.FALLBACK_MAP.get(candidate, "standard")
            logger.warning(f"[DynamicModelRouter] 多模态模型准确率不足，降级到{fallback}")
            return fallback

        # 规则2: 复杂大题（证明题/应用题/长文本）-> 长文本模型
        if q_type in ("proof", "application") or len(question) > 200:
            candidate = "long_context"
            if self._is_model_reliable(candidate, q_type):
                logger.info(f"[DynamicModelRouter] 复杂大题({q_type}) -> 长文本模型({candidate})")
                return candidate
            fallback = self.FALLBACK_MAP.get(candidate, "standard")
            logger.warning(f"[DynamicModelRouter] 长文本模型准确率不足，降级到{fallback}")
            return fallback

        # 规则3: 简单计算题 -> 轻量模型
        if self._is_simple_question(question):
            candidate = "lightweight"
            if self._is_model_reliable(candidate, q_type):
                logger.info(f"[DynamicModelRouter] 简单计算题 -> 轻量模型({candidate})")
                return candidate
            fallback = self.FALLBACK_MAP.get(candidate, "standard")
            logger.warning(f"[DynamicModelRouter] 轻量模型准确率不足，降级到{fallback}")
            return fallback

        # 默认: 标准模型
        candidate = "standard"
        if self._is_model_reliable(candidate, q_type):
            return candidate
        fallback = self.FALLBACK_MAP.get(candidate, "standard")
        logger.warning(f"[DynamicModelRouter] 标准模型准确率不足，降级到{fallback}")
        return fallback

    def _is_model_reliable(self, model_key: str, q_type: str) -> bool:
        """判断模型在指定题型上是否可靠（准确率>=阈值）

        至少需要5次调用数据才做判断，数据不足时默认可靠。
        """
        with self._lock:
            perf = self._performances.get(model_key)
            if not perf:
                return True
            type_stats = perf.by_question_type.get(q_type)
            if not type_stats or type_stats.get("total", 0) < 5:
                return True  # 数据不足，默认可靠
            return type_stats.get("accuracy", 1.0) >= ACCURACY_THRESHOLD

    def record_feedback(self, model_id: str, question_type: str, was_corrected: bool):
        """记录教师修正反馈

        当教师修正或确认AI批改结果时调用此方法，用于统计各模型准确率。
        注意：每次调用都会增加 total_calls（因为每次教师审核都代表一次完整反馈），
        仅当 was_corrected=True 时才增加 corrected_calls。

        Args:
            model_id: 模型key（如"standard"）
            question_type: 题型（geometry/calculation/proof/application）
            was_corrected: 是否被教师修正（True=修正，False=确认正确）
        """
        with self._lock:
            perf = self._performances.get(model_id)
            if not perf:
                perf = ModelPerformance(model_id=model_id)
                self._performances[model_id] = perf

            # 每次反馈都算一次审核记录
            perf.total_calls += 1
            type_stats = perf.by_question_type.setdefault(
                question_type, {"total": 0, "corrected": 0, "accuracy": 0.0}
            )
            type_stats["total"] += 1

            if was_corrected:
                perf.corrected_calls += 1
                type_stats["corrected"] += 1

            perf.recalculate()
            logger.info(f"[DynamicModelRouter] 反馈记录: model={model_id}, "
                f"q_type={question_type}, corrected={was_corrected}, "
                f"accuracy={perf.accuracy:.2%}"
            )

    def get_performance_stats(self) -> dict:
        """获取各模型表现统计

        Returns:
            dict: {
                "models": {
                    "standard": {"total_calls": N, "corrected_calls": N, "accuracy": 0.xx,
                                 "by_question_type": {...}},
                    ...
                },
                "accuracy_threshold": 0.8,
                "low_confidence_threshold": 0.7
            }
        """
        with self._lock:
            result = {}
            for key, perf in self._performances.items():
                result[key] = {
                    "model_id": perf.model_id,
                    "model_name": MODELS.get(key, key),
                    "total_calls": perf.total_calls,
                    "corrected_calls": perf.corrected_calls,
                    "accuracy": perf.accuracy,
                    "by_question_type": {
                        qt: dict(stats) for qt, stats in perf.by_question_type.items()
                    },
                }
            return {
                "models": result,
                "accuracy_threshold": ACCURACY_THRESHOLD,
                "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
            }

    @staticmethod
    def _classify_question(question: str) -> str:
        """题型分类

        Args:
            question: 题目文本

        Returns:
            str: 题型标识 geometry/calculation/proof/application
        """
        q = question.lower()

        # 几何题检测
        geo_count = sum(1 for kw in GEOMETRY_KEYWORDS if kw in q)
        if geo_count >= 2:
            return "geometry"

        # 证明题检测
        proof_count = sum(1 for kw in PROOF_KEYWORDS if kw in q)
        if proof_count >= 2:
            return "proof"

        # 应用题检测
        app_count = sum(1 for kw in APPLICATION_KEYWORDS if kw in q)
        if app_count >= 1:
            return "application"

        # 计算题检测（默认）
        calc_count = sum(1 for kw in SIMPLE_QUESTION_KEYWORDS if kw in q)
        if calc_count >= 1:
            return "calculation"

        # 默认归类为计算题
        return "calculation"

    @staticmethod
    def _is_simple_question(question: str) -> bool:
        """判断是否为简单题

        判定条件（满足任一）：
        1. 题目较短（<=100字符）且包含计算关键词，且不含证明/应用特征
        2. 题目以"计算"、"求值"、"化简"开头（排除"求证"）
        3. 仅包含数字和运算符的简短表达式

        Args:
            question: 题目文本

        Returns:
            bool: 是否为简单题
        """
        stripped = question.strip()

        # 排除条件：包含证明/应用特征的不算简单题
        proof_indicators = ("证明", "求证", "推导", "因为", "所以")
        app_indicators = ("应用", "实际", "工程", "方案", "设计")
        if any(kw in stripped for kw in proof_indicators):
            return False
        if any(kw in stripped for kw in app_indicators):
            return False

        # 短文本+计算关键词
        if len(stripped) <= 100:
            calc_kw_count = sum(1 for kw in SIMPLE_QUESTION_KEYWORDS if kw in stripped)
            if calc_kw_count >= 1:
                # 排除含未知数表达式的中等题目（如 x^2、2x+1 等代数表达式）
                algebra_pattern = re.search(r'[a-zA-Z]\s*[\^²]', stripped)
                if not algebra_pattern:
                    return True

        # 以计算类关键词开头（"求"需要特殊处理：求值/计算是简单，求证不是）
        simple_starts = ("计算", "求值", "化简", "求解")
        if any(stripped.startswith(s) for s in simple_starts):
            return True
        # "求"开头但后面不是"证"，且题目较短
        if stripped.startswith("求") and not stripped.startswith("求证") and len(stripped) <= 100:
            return True

        # 纯数学表达式（含数字、运算符、括号，不含未知数）
        if len(stripped) <= 80:
            math_expr = re.sub(r'[\d+\-*/().\s]', '', stripped)
            # 排除含字母（代数变量）的表达式
            has_variable = bool(re.search(r'[a-zA-Z]', stripped))
            if len(math_expr) <= 10 and any(c.isdigit() for c in stripped) and not has_variable:
                return True

        return False


# 全局路由器实例
model_router = DynamicModelRouter()
