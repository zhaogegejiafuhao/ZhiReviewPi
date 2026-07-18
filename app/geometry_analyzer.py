"""希沃智教π 几何辅助线溯源分析（降级版）

Phase 2 - 7.2.7 CapGeo几何辅助线溯源
功能：VL模型识别学生辅助线 → LLM匹配标准方案 → 输出辅助线评估与提示
降级策略：VL模型不可用时跳过辅助线分析，返回默认结果
"""
import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from openai import AsyncOpenAI, OpenAI

from app.config import settings
from app.llm_utils import parse_llm_json

logger = logging.getLogger(__name__)


# ===== 几何题关键词 =====

GEOMETRY_KEYWORDS = [
    "三角形", "全等", "相似", "四边形", "圆", "证明", "辅助线",
    "平行", "垂直", "角平分线", "中垂线", "中线", "高线",
    "菱形", "矩形", "正方形", "梯形", "弦", "切线", "弧",
]


def is_geometry_question(question: str) -> bool:
    """判断题目是否为几何题

    Args:
        question: 题目文本

    Returns:
        bool: 是否包含几何关键词
    """
    return any(kw in question for kw in GEOMETRY_KEYWORDS)


# ===== 几何符号（用于 OCR 文本级检测） =====
GEOMETRY_SYMBOLS = ["△", "∠", "⊥", "∥", "⊙", "○", "π", "≈", "≡", "∟", "⌒"]
GEOMETRY_LATEX = [r"\triangle", r"\angle", r"\perp", r"\parallel", r"\circ", r"\odot"]


def detect_geometry_enhanced(
    question_text: str,
    question_image_bytes: bytes | None = None,
) -> dict:
    """三层增强版几何检测

    Layer 1: 关键词匹配（零成本）
    Layer 2: 几何符号 + LaTeX公式检测（零额外成本，复用OCR结果）
    Layer 3: VL模型图片级检测（可选，需API Key）

    Returns:
        dict: {
            "is_geometry": bool,
            "source": str,  # "keyword"|"symbol"|"vl"|"none"
            "hints": list[str],
            "sources": dict,  # 各层检测结果
            "combined_score": float,
        }
    """
    sources = {}
    hints = []

    # Layer 1: 关键词匹配
    keyword_hit = is_geometry_question(question_text)
    sources["keyword_match"] = keyword_hit
    if keyword_hit:
        matched = [kw for kw in GEOMETRY_KEYWORDS if kw in question_text]
        hints.append(f"关键词命中：{', '.join(matched)}")

    # Layer 2: OCR文本中的几何符号检测
    symbol_hits = [s for s in GEOMETRY_SYMBOLS if s in question_text]
    sources["ocr_symbol_match"] = len(symbol_hits) > 0
    if symbol_hits:
        hints.append(f"检测到几何符号：{', '.join(symbol_hits)}")

    # Layer 2.5: LaTeX公式中的几何命令检测
    formula_hit = any(cmd in question_text for cmd in GEOMETRY_LATEX)
    sources["formula_geometry"] = formula_hit
    if formula_hit:
        hints.append("检测到LaTeX几何公式")

    # Layer 3: VL模型图片级检测（仅在Layer1+2都未命中时调用）
    vl_detected = False
    if question_image_bytes and not keyword_hit and not symbol_hits and not formula_hit:
        try:
            from app.config import settings
            if settings.SILICONFLOW_API_KEY:
                vl_detected = _vl_detect_geometry(question_image_bytes)
                sources["vl_model_detection"] = vl_detected
                if vl_detected:
                    hints.append("VL模型检测：图片包含几何图形")
        except Exception as e:
            logger.warning(f"VL模型几何检测失败: {type(e).__name__}: {e}")
            sources["vl_model_detection"] = False
    elif not (keyword_hit or symbol_hits or formula_hit):
        sources["vl_model_detection"] = False

    # 综合判定：任一层检测到即为几何题
    is_geometry = keyword_hit or len(symbol_hits) > 0 or formula_hit or vl_detected

    # 来源标记
    if keyword_hit:
        source = "keyword"
    elif symbol_hits:
        source = "symbol"
    elif formula_hit:
        source = "formula"
    elif vl_detected:
        source = "vl"
    else:
        source = "none"

    # 综合置信度
    score = 0.0
    if keyword_hit: score += 0.4
    if symbol_hits: score += 0.3
    if formula_hit: score += 0.15
    if vl_detected: score += 0.15

    return {
        "is_geometry": is_geometry,
        "source": source,
        "hints": hints,
        "sources": sources,
        "combined_score": min(score, 1.0),
    }


def _vl_detect_geometry(image_bytes: bytes) -> bool:
    """使用VL模型检测图片是否包含几何图形"""
    import base64
    try:
        from app.config import settings
        client = OpenAI(
            api_key=settings.SILICONFLOW_API_KEY,
            base_url=settings.SILICONFLOW_BASE_URL,
        )
        b64 = base64.b64encode(image_bytes).decode()
        resp = client.chat.completions.create(
            model="Qwen/Qwen3-VL-32B-Instruct",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": "请判断这张图片是否包含几何图形（三角形、四边形、圆、角度标注、辅助线等）。严格输出JSON：{\"is_geometry\": true或false, \"reason\": \"简要说明\"}"},
                ],
            }],
            temperature=0.1,
            max_tokens=128,
        )
        # 使用同步 OpenAI 客户端，在同步上下文中调用，无需 await
        result = resp.choices[0].message.content
        import json
        parsed = json.loads(result)
        return bool(parsed.get("is_geometry", False))
    except Exception as e:
        logger.warning(f"VL几何检测失败: {e}")
        return False


# ===== 数据类 =====

@dataclass
class GeometryAnalysisResult:
    """几何辅助线分析结果"""
    has_auxiliary_line: bool          # 学生是否画了辅助线
    auxiliary_line_desc: str          # 辅助线描述
    standard_line_desc: str           # 标准辅助线描述
    assessment: str                   # 辅助线正确|辅助线方向偏差|缺失关键辅助线|辅助线多余
    hint: str                         # 辅助线提示

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "has_auxiliary_line": self.has_auxiliary_line,
            "auxiliary_line_desc": self.auxiliary_line_desc,
            "standard_line_desc": self.standard_line_desc,
            "assessment": self.assessment,
            "hint": self.hint,
        }


# ===== Prompt 模板 =====

VL_AUXILIARY_LINE_PROMPT = """你是一位几何教学专家，请仔细观察这张学生手写几何题图片，判断学生是否画了辅助线。

辅助线通常表现为：
1. 用虚线表示的线段
2. 延长线（将某条边延长至某点）
3. 连接两点的线段（如连接对角线）
4. 作垂线、平行线、角平分线等构造线
5. 用不同颜色或不同线型标注的线条

请输出JSON格式：
{{"has_auxiliary_line": true或false, "auxiliary_line_desc": "描述学生画的辅助线，如'连接了AC，作了BD的垂线'，若没有则填'无'"}}

严格输出JSON，不要输出其他内容。"""

LLM_AUXILIARY_LINE_EVAL_PROMPT = """你是一位几何教学专家，请根据题目和标准解法，判断学生辅助线的正确性。

## 题目
{question}

## 学生画的辅助线
{auxiliary_line_desc}

请分析：
1. 这道题的标准辅助线方案是什么
2. 学生的辅助线与标准方案的匹配程度
3. 给出评估结论

评估结论只能从以下4种选择其一：
- 辅助线正确：学生的辅助线与标准方案一致
- 辅助线方向偏差：学生画了辅助线但方向或位置不太对
- 缺失关键辅助线：学生没有画必要的辅助线
- 辅助线多余：学生画了不需要的辅助线

严格输出JSON格式，不要输出其他内容：
{{"standard_line_desc": "标准辅助线描述", "assessment": "辅助线正确|辅助线方向偏差|缺失关键辅助线|辅助线多余", "hint": "给学生的辅助线提示，如'建议连接AC构造全等三角形'"}}"""


# ===== 几何辅助线分析器 =====

class GeometryAnalyzer:
    """几何辅助线分析器（降级版）

    Step 1: VL模型（Qwen3-VL-32B）识别学生是否画了辅助线
    Step 2: LLM匹配标准辅助线方案并评估
    降级策略：VL模型不可用时跳过辅助线分析，返回默认结果
    """

    def __init__(self):
        # VL模型客户端（硅基流动 Qwen3-VL-32B）
        self.vl_client: Optional[AsyncOpenAI] = None
        self.vl_model = "Qwen/Qwen3-VL-32B-Instruct"

        # LLM客户端（用于辅助线评估）
        self.llm_client: Optional[AsyncOpenAI] = None
        self.llm_model = "Qwen/Qwen2.5-14B-Instruct"

        # 延迟初始化客户端（仅在API Key可用时创建）
        if settings.SILICONFLOW_API_KEY:
            self.vl_client = AsyncOpenAI(
                api_key=settings.SILICONFLOW_API_KEY,
                base_url=settings.SILICONFLOW_BASE_URL,
                timeout=30.0,
            )
            self.llm_client = AsyncOpenAI(
                api_key=settings.SILICONFLOW_API_KEY,
                base_url=settings.SILICONFLOW_BASE_URL,
                timeout=30.0,
            )

    async def analyze(self, question: str, image_bytes: bytes) -> GeometryAnalysisResult:
        """分析几何辅助线（降级版）

        Args:
            question: 题目文本
            image_bytes: 学生手写图片字节数据

        Returns:
            GeometryAnalysisResult: 辅助线分析结果
        """
        # 前置检查：VL模型是否可用
        if self.vl_client is None:
            logger.warning("[GeometryAnalyzer] VL模型不可用（缺少SILICONFLOW_API_KEY），跳过辅助线分析")
            return self._default_result()

        # Step 1: VL模型识别辅助线
        auxiliary_line_desc = ""
        has_auxiliary_line = False

        try:
            logger.info("[GeometryAnalyzer] Step 1: VL模型识别辅助线...")
            vl_result = await self._vl_detect_auxiliary_line(image_bytes)
            has_auxiliary_line = vl_result.get("has_auxiliary_line", False)
            auxiliary_line_desc = vl_result.get("auxiliary_line_desc", "无")
            logger.info(f"[GeometryAnalyzer] VL识别结果: has_auxiliary_line={has_auxiliary_line}, desc={auxiliary_line_desc[:50]}")
        except Exception as e:
            logger.warning(f"[GeometryAnalyzer] VL模型调用失败: {type(e).__name__}: {e}, 跳过辅助线分析")
            return self._default_result()

        # Step 2: LLM匹配标准方案并评估
        try:
            logger.info("[GeometryAnalyzer] Step 2: LLM评估辅助线...")
            eval_result = await self._llm_evaluate_auxiliary_line(question, auxiliary_line_desc)

            # 校验assessment值是否合法
            assessment = eval_result.get("assessment", "")
            valid_assessments = ["辅助线正确", "辅助线方向偏差", "缺失关键辅助线", "辅助线多余"]
            if assessment not in valid_assessments:
                logger.warning(f"[GeometryAnalyzer] LLM返回的assessment不合法: {assessment}，使用默认值")
                assessment = "缺失关键辅助线" if not has_auxiliary_line else "辅助线方向偏差"

            return GeometryAnalysisResult(
                has_auxiliary_line=has_auxiliary_line,
                auxiliary_line_desc=auxiliary_line_desc,
                standard_line_desc=eval_result.get("standard_line_desc", ""),
                assessment=assessment,
                hint=eval_result.get("hint", ""),
            )
        except Exception as e:
            logger.warning(f"[GeometryAnalyzer] LLM评估失败: {type(e).__name__}: {e}, 返回基础结果")
            return GeometryAnalysisResult(
                has_auxiliary_line=has_auxiliary_line,
                auxiliary_line_desc=auxiliary_line_desc,
                standard_line_desc="",
                assessment="缺失关键辅助线" if not has_auxiliary_line else "辅助线方向偏差",
                hint="",
            )

    async def _vl_detect_auxiliary_line(self, image_bytes: bytes) -> dict:
        """使用VL模型识别学生是否画了辅助线

        Args:
            image_bytes: 图片字节数据

        Returns:
            dict: {"has_auxiliary_line": bool, "auxiliary_line_desc": str}
        """
        img_b64 = base64.b64encode(image_bytes).decode()

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                    {
                        "type": "text",
                        "text": VL_AUXILIARY_LINE_PROMPT,
                    },
                ],
            }
        ]

        response = await self.vl_client.chat.completions.create(
            model=self.vl_model,
            messages=messages,
            temperature=0.1,
            max_tokens=512,
        )

        content = response.choices[0].message.content
        return parse_llm_json(content)

    async def _llm_evaluate_auxiliary_line(self, question: str, auxiliary_line_desc: str) -> dict:
        """使用LLM匹配标准辅助线方案并评估

        Args:
            question: 题目文本
            auxiliary_line_desc: 学生辅助线描述

        Returns:
            dict: {"standard_line_desc": str, "assessment": str, "hint": str}
        """
        prompt = LLM_AUXILIARY_LINE_EVAL_PROMPT.format(
            question=question,
            auxiliary_line_desc=auxiliary_line_desc,
        )

        response = await self.llm_client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=512,
        )

        content = response.choices[0].message.content
        return parse_llm_json(content)

    @staticmethod
    def _default_result() -> GeometryAnalysisResult:
        """降级时返回的默认结果（VL模型不可用）"""
        return GeometryAnalysisResult(
            has_auxiliary_line=False,
            auxiliary_line_desc="（VL模型不可用，跳过辅助线识别）",
            standard_line_desc="",
            assessment="缺失关键辅助线",
            hint="",
        )
