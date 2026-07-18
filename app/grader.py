"""希沃智教π LLM批改层 - 柔性Rubric + 过程分判定"""
import json
import logging
import re
import hashlib
from collections import OrderedDict
from typing import Optional

from openai import AsyncOpenAI

from app.llm_utils import parse_llm_json
from app.config import settings
from app.geometry_analyzer import GeometryAnalyzer, is_geometry_question
from app.model_router import DynamicModelRouter, model_router, MODELS

logger = logging.getLogger(__name__)


# ===== Prompt 模板 =====

RUBRIC_GENERATION_PROMPT = """你是一位资深的{subject}教师，请为以下题目推导步骤评分标准。

## 题目（{total_score}分）
{question}

## 标准答案
{standard_answer}

请推导评分标准，输出JSON：
1. 列出解题关键步骤（3-6步）
2. 为每个步骤分配分值（总和={total_score}）
3. 标注 required（true=必须项，没写直接0分 / false=加分项）
4. 提供该步骤的关键词匹配列表和示例表达

严格输出以下JSON格式，不要输出其他内容：
{{"steps": [{{"step_id": "s1", "description": "...", "score": N, "required": true, "keywords": ["..."], "example": "..."}}]}}"""

MATH_GRADING_PROMPT = """你是一位专业的数学教师，请基于以下评分标准对学生解答进行逐步批改。

## 题目
{question}

## 评分标准（Rubric）
{rubric_json}

## 标准答案
{standard_answer}

## 学生解答（OCR提取）
{student_answer}
{geometry_section}
请逐步骤判定：
1. 匹配每个rubric步骤，判断学生是否完成
2. 对每个步骤给出correct/partial/missing判定和得分
3. 指出具体错误原因（如有）
4. 生成一句个性化评语（结合错因与知识薄弱点）
5. 对每个错误步骤标注错因标签（从以下6种选择：计算粗心、概念混淆、审题不清、辅助线缺失、逻辑跳步、知识缺失）

严格输出以下JSON格式，不要输出其他内容：
{{"steps": [{{"step_id": "s1", "content": "学生写的步骤内容", "correct": true, "score": N, "rubric_ref": "s1", "error_reason": null}}], "error_type": "calculation_error|concept_error|process_error|none", "error_cause": "计算粗心|概念混淆|审题不清|辅助线缺失|逻辑跳步|知识缺失|none", "knowledge_points": ["知识点1"], "comment": "个性化评语"}}"""

# 几何题辅助线评估指令（追加到MATH_GRADING_PROMPT的geometry_section占位符）
GEOMETRY_AUXILIARY_LINE_PROMPT_SECTION = """
## 几何辅助线评估提示
本题是几何证明/计算题，请特别关注以下方面：
- 学生是否画了辅助线（如虚线、延长线、连接线等）
- 辅助线是否正确（方向、位置是否合理）
- 是否缺失关键辅助线
- 辅助线使用情况应反映在错因标签中（如"辅助线缺失"）
- 评语中需包含辅助线相关的提示或建议
"""

COMMENT_GENERATION_PROMPT = """基于以下批改结果，生成一句简短个性化评语。

题目：{question}
学生得分：{score}/{max_score}
错误步骤：{error_steps}
错因类型：{error_type}
薄弱知识点：{knowledge_points}

要求：评语要具体指出问题并给出改进建议，不要空泛鼓励。"""


# ===== 作文批改 Prompt =====

ESSAY_OCR_LOW_CONFIDENCE_HINT = """**OCR识别提示**：本次OCR置信度较低（{confidence:.2f}），可能存在字迹潦草、卷面不整洁问题，书写维度评分时请适当关注。"""

ESSAY_GRADING_PROMPT = """你是一位资深的语文作文阅卷老师，请按中考作文四维评分标准对以下作文进行批改。

## 作文题目
{question}

## 写作要求（参考）
{standard_answer}

## 学生作文（OCR提取）
{student_answer}

{ocr_confidence_hint}

## 评分标准（总分100分）
请按以下四个维度独立评分：

1. **内容**（满分40分）：审题立意是否准确、主题是否明确、素材是否丰富贴切、思想感情是否真实健康
2. **结构**（满分20分）：篇章布局是否合理、段落过渡是否自然、开头结尾是否呼应、详略是否得当
3. **语言**（满分25分）：用词是否准确丰富、修辞是否恰当、句式是否有变化、是否通顺流畅
4. **书写**（满分15分）：字迹是否工整、卷面是否整洁、是否有错别字（基于OCR文本质量与置信度推断）

## 评分要求
- 每个维度给出具体分数和评语，评语要具体指出问题（引用原文片段最佳），不要空泛
- 每个维度从以下5种错因中选1种最贴切的（无错填"none"）：素材匮乏、逻辑断层、修辞单一、偏题跑题、书写潦草
- 选出最主要的一个错因作为整体错因（primary_error_cause）
- 列出最薄弱的1-2个维度名称作为knowledge_points（从"内容/结构/语言/书写"中选）

严格输出以下JSON格式，不要输出其他内容：
{{"dimensions": {{"content": {{"score": N, "max_score": 40, "comment": "...", "error_cause": "偏题跑题|素材匮乏|none"}}, "structure": {{"score": N, "max_score": 20, "comment": "...", "error_cause": "逻辑断层|none"}}, "language": {{"score": N, "max_score": 25, "comment": "...", "error_cause": "修辞单一|none"}}, "handwriting": {{"score": N, "max_score": 15, "comment": "...", "error_cause": "书写潦草|none"}}}}, "primary_error_cause": "素材匮乏|逻辑断层|修辞单一|偏题跑题|书写潦草|none", "knowledge_points": ["薄弱维度1"], "overall_comment": "综合评语"}}"""

ESSAY_COMMENT_GENERATION_PROMPT = """基于以下作文四维批改结果，生成一段简短的个性化评语。

## 作文题目
{question}

## 总得分
{score}/{max_score}

## 四维详情
- 内容（{content_score}/{content_max}）：{content_comment}
- 结构（{structure_score}/{structure_max}）：{structure_comment}
- 语言（{language_score}/{language_max}）：{language_comment}
- 书写（{handwriting_score}/{handwriting_max}）：{handwriting_comment}

## 主要错因
{error_cause}

## 薄弱维度
{knowledge_points}

## 要求
1. 评语要贴合语文作文特性，避免出现"步骤评分""推理过程"等数学化术语
2. 先肯定优点，再指出最关键的1-2个改进方向
3. 不要超过100字，简洁有力，给出可操作的修改建议"""

# Level 0降级：作文四维占位 rubric（供题库存储使用）
FALLBACK_ESSAY_RUBRIC = {
    "type": "essay",
    "dimensions": [
        {"step_id": "dim_content", "description": "内容", "score": 40, "required": True, "keywords": [], "example": ""},
        {"step_id": "dim_structure", "description": "结构", "score": 20, "required": True, "keywords": [], "example": ""},
        {"step_id": "dim_language", "description": "语言", "score": 25, "required": True, "keywords": [], "example": ""},
        {"step_id": "dim_handwriting", "description": "书写", "score": 15, "required": True, "keywords": [], "example": ""},
    ],
}


# ===== Rubric LRU 缓存 =====

class LRUCache:
    def __init__(self, maxsize=500):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize

    def get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self):
        self._cache.clear()

    def __len__(self):
        return len(self._cache)


_rubric_cache = LRUCache(maxsize=500)

# Level 0降级：规则兜底评分标准（所有LLM失败时使用）
FALLBACK_RUBRIC = {
    "steps": [
        {"step_id": "s1", "description": "列式/建立方程", "score": 2, "required": True, "keywords": ["设", "令", "因为", "所以", "="], "example": ""},
        {"step_id": "s2", "description": "计算过程", "score": 2, "required": True, "keywords": ["代入", "化简", "解得", "计算"], "example": ""},
        {"step_id": "s3", "description": "最终答案", "score": 1, "required": True, "keywords": ["答", "故", "因此"], "example": ""},
    ]
}


def rule_based_grade(question: str, student_answer: str, rubric: dict) -> dict:
    """Level 1降级：基于关键词的规则评分"""
    steps = []
    total_score = 0
    rubric_steps = rubric.get("steps", FALLBACK_RUBRIC["steps"])

    for rs in rubric_steps:
        score = 0
        correct = False
        keywords = rs.get("keywords", [])

        # 检查学生答案中是否包含关键词
        matched_keywords = [kw for kw in keywords if kw in student_answer]

        if matched_keywords:
            # 命中关键词数占比决定得分
            ratio = len(matched_keywords) / max(len(keywords), 1)
            score = round(rs.get("score", 1) * ratio, 1)
            correct = ratio >= 0.5

        steps.append({
            "step_id": rs["step_id"],
            "content": f"关键词匹配: {', '.join(matched_keywords)}" if matched_keywords else "未匹配到关键词",
            "correct": correct,
            "score": score,
            "rubric_ref": rs["step_id"],
            "error_reason": None if correct else "未检测到关键步骤",
        })
        total_score += score

    return {
        "steps": steps,
        "total_score": total_score,
        "max_score": sum(s.get("score", 0) for s in rubric_steps),
        "error_type": "rule_based",
        "error_cause": "none",
        "knowledge_points": [],
        "comment": "（降级评分：基于关键词匹配，建议教师复核）",
        "grading_method": "rule_based_fallback",
    }


class RubricGenerator:
    """柔性Rubric生成器"""

    def __init__(self):
        # 主引擎：硅基流动 Qwen2.5-14B（JSON输出稳定）
        self.sf_client = AsyncOpenAI(
            api_key=settings.SILICONFLOW_API_KEY,
            base_url=settings.SILICONFLOW_BASE_URL,
            timeout=30.0,
        )
        self.sf_model = "Qwen/Qwen2.5-14B-Instruct"

        # 备用引擎：豆包
        self.doubao_client = AsyncOpenAI(
            api_key=settings.VOLCENGINE_API_KEY,
            base_url=settings.VOLCENGINE_BASE_URL,
            timeout=30.0,
        )
        self.doubao_model = settings.DOUBAO_ENDPOINT_ID

    async def generate(
        self, question: str, standard_answer: str, total_score: int, subject: str = "math", grade: int = 7
    ) -> dict:
        """AI自动推导评分标准（带降级）"""
        # 查缓存
        cache_key = hashlib.md5(f"{question}||{standard_answer}||{total_score}".encode()).hexdigest()
        cached = _rubric_cache.get(cache_key)
        if cached:
            logger.debug(f"[RubricGenerator] 命中缓存! key={cache_key[:8]}")
            return cached.copy()

        prompt = RUBRIC_GENERATION_PROMPT.format(
            subject=subject,
            total_score=total_score,
            question=question,
            standard_answer=standard_answer,
        )

        # 先尝试硅基流动（响应快），超时降级到豆包
        try:
            logger.info("[RubricGenerator] 尝试硅基流动API...")
            response = await self.sf_client.chat.completions.create(
                model=self.sf_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1024,
            )
            content = response.choices[0].message.content
            result = parse_llm_json(content)
            _rubric_cache.put(cache_key, result.copy() if isinstance(result, dict) else result)
            logger.info(f"[RubricGenerator] 已缓存, key={cache_key[:8]}, 当前缓存条数={len(_rubric_cache._cache)}")
            return result
        except Exception as e:
            logger.warning(f"[RubricGenerator] 硅基流动失败: {type(e).__name__}, 降级到豆包...")

        # 降级到豆包
        try:
            response = await self.doubao_client.chat.completions.create(
                model=self.doubao_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1024,
            )
            content = response.choices[0].message.content
            result = parse_llm_json(content)
            _rubric_cache.put(cache_key, result.copy() if isinstance(result, dict) else result)
            logger.info(f"[RubricGenerator] 已缓存(豆包), key={cache_key[:8]}, 当前缓存条数={len(_rubric_cache._cache)}")
            return result
        except Exception as e:
            logger.error(f"[RubricGenerator] 豆包也失败: {type(e).__name__}: {e}")
            # Level 0降级：返回规则兜底评分标准
            logger.warning("[RubricGenerator] Level 0降级：使用规则兜底评分标准")
            return FALLBACK_RUBRIC.copy()


class MathGrader:
    """数学题过程分批改引擎（集成动态模型路由）"""

    def __init__(self):
        # 豆包用于数学推理（备用）
        self.doubao_client = AsyncOpenAI(
            api_key=settings.VOLCENGINE_API_KEY,
            base_url=settings.VOLCENGINE_BASE_URL,
            timeout=30.0,
        )
        # Qwen2.5-14B用于过程分判定和评语生成
        self.qwen_client = AsyncOpenAI(
            api_key=settings.SILICONFLOW_API_KEY,
            base_url=settings.SILICONFLOW_BASE_URL,
            timeout=30.0,
        )
        # 动态模型路由器
        self.router = model_router

    def _get_client_and_model(self, model_key: str):
        """根据路由key获取对应的API客户端和模型名称

        Args:
            model_key: 路由模型key（如"standard"、"lightweight"、"multimodal"）

        Returns:
            tuple: (client, model_name) API客户端实例与模型标识
        """
        model_name = MODELS.get(model_key, MODELS["standard"])

        if model_key == "multimodal":
            # 多模态模型使用火山引擎豆包
            return self.doubao_client, model_name
        elif model_key == "lightweight":
            # 轻量模型使用硅基流动
            return self.qwen_client, model_name
        else:
            # standard / long_context 均使用硅基流动
            return self.qwen_client, model_name

    async def grade(
        self,
        question: str,
        standard_answer: str,
        student_answer: str,
        rubric: dict,
        is_geometry: bool = False,
        confidence: float = 0.0,
    ) -> dict:
        """基于rubric的过程分批改（集成动态模型路由，带降级）

        Args:
            question: 题目文本
            standard_answer: 标准答案
            student_answer: 学生解答（OCR提取）
            rubric: 评分标准
            is_geometry: 是否为几何题
            confidence: 置信度（0.0-1.0），用于动态路由决策

        Returns:
            dict: 批改结果，含 steps/total_score/max_score 等
        """
        rubric_json = json.dumps(rubric.get("steps", []), ensure_ascii=False)

        # 几何题时追加辅助线评估指令
        geometry_section = GEOMETRY_AUXILIARY_LINE_PROMPT_SECTION if is_geometry else ""

        prompt = MATH_GRADING_PROMPT.format(
            question=question,
            rubric_json=rubric_json,
            standard_answer=standard_answer,
            student_answer=student_answer,
            geometry_section=geometry_section,
        )

        # 动态路由选择模型
        try:
            model_key = self.router.route(
                question=question,
                confidence=confidence,
                is_geometry=is_geometry,
            )
            logger.info(f"[MathGrader] 动态路由选择模型: {model_key} ({MODELS.get(model_key, model_key)})")
        except Exception as e:
            logger.warning(f"[MathGrader] 路由异常，使用默认模型: {type(e).__name__}: {e}")
            model_key = "standard"

        client, model_name = self._get_client_and_model(model_key)

        # 根据路由结果调用对应模型，失败降级
        result = await self._grade_with_fallback(client, model_name, model_key, prompt, question, student_answer, rubric)

        # 在结果中记录使用的模型key（供后续反馈追踪）
        result["_model_key"] = model_key

        # 计算总过程分
        steps = result.get("steps", [])
        total_score = sum(s.get("score", 0) for s in steps)
        max_score = sum(s.get("score", 0) for s in rubric.get("steps", []))

        result["total_score"] = total_score
        result["max_score"] = max_score

        return result

    async def _grade_with_fallback(
        self,
        primary_client: AsyncOpenAI,
        primary_model: str,
        primary_key: str,
        prompt: str,
        question: str,
        student_answer: str,
        rubric: dict,
    ) -> dict:
        """带降级的批改调用

        优先使用路由指定的模型，失败后按 lightweight -> standard -> doubao -> rule_based 降级。

        Args:
            primary_client: 首选API客户端
            primary_model: 首选模型名称
            primary_key: 首选模型路由key
            prompt: 批改提示词
            question: 题目
            student_answer: 学生答案
            rubric: 评分标准

        Returns:
            dict: 批改结果
        """
        # 尝试首选模型
        try:
            logger.info(f"[MathGrader] 尝试模型 {primary_key} ({primary_model})...")
            # 多模态模型使用豆包endpoint ID
            actual_model = settings.DOUBAO_ENDPOINT_ID if primary_key == "multimodal" else primary_model
            response = await primary_client.chat.completions.create(
                model=actual_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2048,
            )
            content = response.choices[0].message.content
            return parse_llm_json(content)
        except Exception as e:
            logger.warning(f"[MathGrader] 模型 {primary_key} 失败: {type(e).__name__}, 降级...")

        # 降级到标准模型（如果首选不是标准模型）
        if primary_key != "standard":
            try:
                logger.info("[MathGrader] 降级到标准模型 Qwen2.5-14B...")
                response = await self.qwen_client.chat.completions.create(
                    model=MODELS["standard"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=2048,
                )
                content = response.choices[0].message.content
                return parse_llm_json(content)
            except Exception as e:
                logger.warning(f"[MathGrader] 标准模型失败: {type(e).__name__}, 降级到豆包...")

        # 降级到豆包
        try:
            response = await self.doubao_client.chat.completions.create(
                model=settings.DOUBAO_ENDPOINT_ID,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2048,
            )
            content = response.choices[0].message.content
            return parse_llm_json(content)
        except Exception as e:
            logger.error(f"[MathGrader] 豆包也失败: {type(e).__name__}: {e}")

        # Level 1降级：基于关键词的规则评分
        logger.warning("[MathGrader] Level 1降级：使用关键词规则评分")
        return rule_based_grade(question, student_answer, rubric)

    async def generate_comment(
        self,
        question: str,
        score: float,
        max_score: float,
        error_steps: list,
        error_type: str,
        knowledge_points: list,
    ) -> str:
        """生成个性化评语"""
        prompt = COMMENT_GENERATION_PROMPT.format(
            question=question,
            score=score,
            max_score=max_score,
            error_steps=json.dumps(error_steps, ensure_ascii=False),
            error_type=error_type,
            knowledge_points="、".join(knowledge_points),
        )

        try:
            response = await self.qwen_client.chat.completions.create(
                model="Qwen/Qwen2.5-14B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=256,
            )
            return response.choices[0].message.content
        except Exception:
            # 降级为模板评语
            if score == max_score:
                return "解答完全正确，继续保持！"
            return f"本次得分{score}/{max_score}，请注意{knowledge_points[0] if knowledge_points else '相关知识点'}的巩固练习。"


class EssayGrader:
    """语文作文四维批改引擎（内容40%+结构20%+语言25%+书写15%）

    输出结构兼容 MathGrader：含 steps/total_score/max_score/error_type/
    error_cause/knowledge_points/_model_key，下游归因、错题本、导出无需改动。
    额外输出 dimensions 字段供前端展示四维详情。

    错因标签与 writing_graph.WRITING_ERROR_CAUSE_MAPPING 对齐：
    素材匮乏 / 逻辑断层 / 修辞单一 / 偏题跑题 / 书写潦草
    """

    DIMENSION_WEIGHTS = OrderedDict([
        ("content",     {"name": "内容", "max_score": 40}),
        ("structure",   {"name": "结构", "max_score": 20}),
        ("language",    {"name": "语言", "max_score": 25}),
        ("handwriting", {"name": "书写", "max_score": 15}),
    ])

    ESSAY_ERROR_CAUSES = ["素材匮乏", "逻辑断层", "修辞单一", "偏题跑题", "书写潦草"]

    # 维度→错因的默认映射（用于 _template_grade 降级时根据最低维度推算错因）
    _DIM_ERROR_MAP = {
        "content": "偏题跑题",
        "structure": "逻辑断层",
        "language": "修辞单一",
        "handwriting": "书写潦草",
    }

    # 维度→error_type 映射
    _DIM_ERROR_TYPE_MAP = {
        "content": "theme_deviation",
        "structure": "structure_issue",
        "language": "language_issue",
        "handwriting": "handwriting_issue",
    }

    def __init__(self):
        # Qwen2.5-14B 用于四维评分和评语生成
        self.qwen_client = AsyncOpenAI(
            api_key=settings.SILICONFLOW_API_KEY,
            base_url=settings.SILICONFLOW_BASE_URL,
            timeout=45.0,  # 作文文本较长，超时放宽
        )
        self.qwen_model = "Qwen/Qwen2.5-14B-Instruct"
        # 豆包用于降级
        self.doubao_client = AsyncOpenAI(
            api_key=settings.VOLCENGINE_API_KEY,
            base_url=settings.VOLCENGINE_BASE_URL,
            timeout=45.0,
        )
        self.doubao_model = settings.DOUBAO_ENDPOINT_ID

    def _validate_error_cause(self, cause: str) -> str:
        """错因白名单校验，非法值降为 none"""
        if cause and cause in self.ESSAY_ERROR_CAUSES:
            return cause
        if cause and cause != "none":
            logger.warning(f"[EssayGrader] 非法 error_cause: {cause}，降级为 none")
        return "none"

    def _build_compatible_steps(self, dimensions: dict) -> list:
        """将四维结果转为 MathGrader 兼容的 steps 数组"""
        steps = []
        for dim_key, dim_meta in self.DIMENSION_WEIGHTS.items():
            dim_data = dimensions.get(dim_key, {})
            dim_score = float(dim_data.get("score", 0))
            dim_max = dim_meta["max_score"]
            dim_comment = dim_data.get("comment", "")
            dim_error_cause = dim_data.get("error_cause", "none")

            # correct 判定：得分率 >= 0.8 视为正确
            ratio = dim_score / dim_max if dim_max > 0 else 0
            correct = ratio >= 0.8

            steps.append({
                "step_id": f"dim_{dim_key}",
                "content": f"{dim_meta['name']}维度：{dim_comment}",
                "correct": correct,
                "score": dim_score,
                "rubric_ref": f"dim_{dim_key}",
                "error_reason": None if correct else (dim_error_cause if dim_error_cause != "none" else "维度得分偏低"),
                "max_score": dim_max,
            })
        return steps

    def _normalize_to_total(self, raw_result: dict, total_score: int) -> dict:
        """将100分制四维分数归一化到题目总分（如 total_score=50 则按比例缩放）"""
        dimensions = raw_result.get("dimensions", {})
        if total_score == 100:
            # 无需缩放
            for dim_key in self.DIMENSION_WEIGHTS:
                dim_data = dimensions.get(dim_key, {})
                dim_data["max_score"] = self.DIMENSION_WEIGHTS[dim_key]["max_score"]
            total = sum(d.get("score", 0) for d in dimensions.values())
            raw_result["total_score"] = round(total, 1)
            raw_result["max_score"] = 100
            return raw_result

        # 按 total_score 缩放
        scale = total_score / 100.0
        new_dims = {}
        new_total = 0
        for dim_key, dim_meta in self.DIMENSION_WEIGHTS.items():
            dim_data = dimensions.get(dim_key, {})
            orig_max = dim_meta["max_score"]
            new_max = round(orig_max * scale, 1)
            new_score = round(float(dim_data.get("score", 0)) * scale, 1)
            # 钳制
            new_score = min(new_score, new_max)
            new_dims[dim_key] = {
                "score": new_score,
                "max_score": new_max,
                "comment": dim_data.get("comment", ""),
                "error_cause": self._validate_error_cause(dim_data.get("error_cause", "none")),
            }
            new_total += new_score

        raw_result["dimensions"] = new_dims
        raw_result["total_score"] = round(new_total, 1)
        raw_result["max_score"] = float(total_score)
        return raw_result

    def _template_grade(self, question: str, student_answer: str, total_score: int, confidence: float = 0.0) -> dict:
        """Level 2 降级：模板评分（基于文本长度/段落/置信度的启发式）"""
        text_len = len(student_answer)
        paragraphs = [p for p in student_answer.split("\n") if p.strip()]

        # 内容分：基于作文长度启发式
        if text_len < 200:
            content_ratio = 0.4
        elif text_len < 500:
            content_ratio = 0.6
        elif text_len < 800:
            content_ratio = 0.8
        else:
            content_ratio = 0.9

        # 结构分：基于段落分布
        if len(paragraphs) <= 1:
            structure_ratio = 0.3
        elif 2 <= len(paragraphs) <= 3:
            structure_ratio = 0.6
        elif 4 <= len(paragraphs) <= 6:
            structure_ratio = 0.85
        else:
            structure_ratio = 0.7

        # 语言分：默认
        language_ratio = 0.7

        # 书写分：基于 OCR 置信度
        if confidence > 0.85:
            handwriting_ratio = 0.9
        elif confidence > 0.7:
            handwriting_ratio = 0.7
        else:
            handwriting_ratio = 0.5

        scale = total_score / 100.0
        dimensions = {}
        ratios = {
            "content": content_ratio,
            "structure": structure_ratio,
            "language": language_ratio,
            "handwriting": handwriting_ratio,
        }
        for dim_key, dim_meta in self.DIMENSION_WEIGHTS.items():
            orig_max = dim_meta["max_score"]
            new_max = round(orig_max * scale, 1)
            new_score = round(orig_max * ratios[dim_key] * scale, 1)
            dimensions[dim_key] = {
                "score": new_score,
                "max_score": new_max,
                "comment": f"（降级评分：基于{dim_meta['name']}维度启发式规则，建议教师复核）",
                "error_cause": self._DIM_ERROR_MAP[dim_key] if ratios[dim_key] < 0.6 else "none",
            }

        # 选最低维度作为整体错因
        min_dim = min(ratios.items(), key=lambda x: x[1])[0]
        primary_error_cause = self._DIM_ERROR_MAP[min_dim] if ratios[min_dim] < 0.6 else "none"
        knowledge_points = [self.DIMENSION_WEIGHTS[min_dim]["name"]] if ratios[min_dim] < 0.8 else []

        return {
            "dimensions": dimensions,
            "primary_error_cause": primary_error_cause,
            "knowledge_points": knowledge_points,
            "overall_comment": f"（模板降级评分）本次作文得分偏低，主要薄弱维度为{self.DIMENSION_WEIGHTS[min_dim]['name']}，建议教师人工复核。",
        }

    async def _grade_with_fallback(self, prompt: str, question: str, student_answer: str, total_score: int) -> dict:
        """带降级的批改调用：qwen → doubao → template 三级降级"""
        # Level 0: Qwen2.5-14B
        try:
            logger.info("[EssayGrader] 尝试 Qwen2.5-14B 评分...")
            response = await self.qwen_client.chat.completions.create(
                model=self.qwen_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2048,
            )
            content = response.choices[0].message.content
            result = parse_llm_json(content)
            if isinstance(result, dict) and "dimensions" in result:
                result["_model_key"] = "standard"
                result["grading_method"] = "essay_llm"
                logger.info(f"[EssayGrader] Qwen 评分成功: primary_error_cause={result.get('primary_error_cause')}")
                return result
            logger.warning(f"[EssayGrader] Qwen 返回结构异常: {str(result)[:100]}")
        except Exception as e:
            logger.warning(f"[EssayGrader] Qwen 失败: {type(e).__name__}: {e}")

        # Level 1: 豆包降级
        try:
            logger.info("[EssayGrader] 降级到豆包...")
            response = await self.doubao_client.chat.completions.create(
                model=self.doubao_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2048,
            )
            content = response.choices[0].message.content
            result = parse_llm_json(content)
            if isinstance(result, dict) and "dimensions" in result:
                result["_model_key"] = "doubao"
                result["grading_method"] = "essay_llm"
                logger.info(f"[EssayGrader] 豆包评分成功: primary_error_cause={result.get('primary_error_cause')}")
                return result
            logger.warning(f"[EssayGrader] 豆包返回结构异常: {str(result)[:100]}")
        except Exception as e:
            logger.warning(f"[EssayGrader] 豆包失败: {type(e).__name__}: {e}")

        # Level 2: 模板降级
        logger.warning("[EssayGrader] Level 2 降级：使用模板评分")
        template_result = self._template_grade(question, student_answer, total_score)
        template_result["_model_key"] = "template_fallback"
        template_result["grading_method"] = "essay_template_fallback"
        return template_result

    async def grade(
        self,
        question: str,
        standard_answer: str,
        student_answer: str,
        rubric: Optional[dict] = None,  # 接收但不使用，保持与 MathGrader.grade 签名兼容
        total_score: int = 100,
        confidence: float = 0.0,
        image_bytes: Optional[bytes] = None,  # 预留：未来用 VL 模型识别书写
        is_geometry: bool = False,  # 接收但不使用，保持签名兼容
    ) -> dict:
        """四维批改主入口

        Args:
            question: 作文题目
            standard_answer: 写作要求（参考）
            student_answer: 学生作文（OCR提取）
            rubric: 接收但不使用（保持签名兼容）
            total_score: 题目总分（默认100，若为50则按比例缩放四维）
            confidence: OCR置信度，作为书写维度弱信号
            image_bytes: 预留 VL 识别书写
            is_geometry: 接收但不使用（保持签名兼容）

        Returns:
            dict: 兼容 MathGrader 输出的批改结果，额外含 dimensions 字段
        """
        # OCR 置信度提示
        if confidence < 0.7:
            ocr_hint = ESSAY_OCR_LOW_CONFIDENCE_HINT.format(confidence=confidence)
        else:
            ocr_hint = ""

        # 截断超长作文（避免 prompt 过长）
        truncated_answer = student_answer[:3000] if len(student_answer) > 3000 else student_answer

        prompt = ESSAY_GRADING_PROMPT.format(
            question=question,
            standard_answer=standard_answer or "（无特殊要求）",
            student_answer=truncated_answer,
            ocr_confidence_hint=ocr_hint,
        )

        # 调用 LLM 评分
        raw_result = await self._grade_with_fallback(prompt, question, truncated_answer, total_score)

        # 校验并归一化
        dimensions = raw_result.get("dimensions", {})
        for dim_key in self.DIMENSION_WEIGHTS:
            if dim_key not in dimensions:
                logger.warning(f"[EssayGrader] LLM 输出缺失维度 {dim_key}，补默认值")
                dimensions[dim_key] = {
                    "score": 0,
                    "max_score": self.DIMENSION_WEIGHTS[dim_key]["max_score"],
                    "comment": "（LLM 未输出该维度，已补默认值）",
                    "error_cause": "none",
                }
            else:
                # 校验每个维度
                dim_data = dimensions[dim_key]
                dim_data["error_cause"] = self._validate_error_cause(dim_data.get("error_cause", "none"))
                # 分数钳制
                max_s = self.DIMENSION_WEIGHTS[dim_key]["max_score"]
                try:
                    s = float(dim_data.get("score", 0))
                except (TypeError, ValueError):
                    s = 0
                dim_data["score"] = max(0, min(s, max_s))
                dim_data["max_score"] = max_s
        raw_result["dimensions"] = dimensions

        # 归一化到题目总分
        raw_result = self._normalize_to_total(raw_result, total_score)

        # error_cause / error_type
        primary_error_cause = self._validate_error_cause(raw_result.get("primary_error_cause", "none"))
        raw_result["error_cause"] = primary_error_cause

        # error_type：根据 primary_error_cause 反推
        cause_to_type = {v: self._DIM_ERROR_TYPE_MAP[k] for k, v in self._DIM_ERROR_MAP.items()}
        raw_result["error_type"] = cause_to_type.get(primary_error_cause, "none")

        # knowledge_points
        if not raw_result.get("knowledge_points"):
            # 找得分率最低的维度
            min_dim = min(
                self.DIMENSION_WEIGHTS.keys(),
                key=lambda k: raw_result["dimensions"][k]["score"] / max(self.DIMENSION_WEIGHTS[k]["max_score"], 1)
            )
            raw_result["knowledge_points"] = [self.DIMENSION_WEIGHTS[min_dim]["name"]]
        else:
            # 清洗：只保留字符串
            kps = [str(k) for k in raw_result["knowledge_points"] if k]
            raw_result["knowledge_points"] = kps[:2]

        # 构造兼容 MathGrader 的 steps 数组
        raw_result["steps"] = self._build_compatible_steps(raw_result["dimensions"])

        # 保留 overall_comment 作为综合评语（如 LLM 已生成则直接用，否则由 generate_comment 生成）
        if not raw_result.get("comment"):
            raw_result["comment"] = raw_result.get("overall_comment", "")

        return raw_result

    async def generate_comment(
        self,
        question: str,
        score: float,
        max_score: float,
        dimensions: dict,
        error_cause: str,
        knowledge_points: list,
    ) -> str:
        """生成作文综合评语（基于四维详情，评语更贴合作文特性）"""
        # 准备四维详情
        dim_data = {}
        for dim_key, dim_meta in self.DIMENSION_WEIGHTS.items():
            d = dimensions.get(dim_key, {})
            dim_data[f"{dim_key}_score"] = d.get("score", 0)
            dim_data[f"{dim_key}_max"] = d.get("max_score", dim_meta["max_score"])
            dim_data[f"{dim_key}_comment"] = d.get("comment", "（无评语）")

        prompt = ESSAY_COMMENT_GENERATION_PROMPT.format(
            question=question,
            score=score,
            max_score=max_score,
            error_cause=error_cause,
            knowledge_points="、".join(knowledge_points) if knowledge_points else "无明显薄弱",
            **dim_data,
        )

        try:
            response = await self.qwen_client.chat.completions.create(
                model=self.qwen_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=256,
            )
            return response.choices[0].message.content
        except Exception:
            # 降级为模板评语
            ratio = score / max_score if max_score > 0 else 0
            if ratio >= 0.85:
                return "本文整体表现优秀，继续保持。"
            elif ratio >= 0.6:
                weak = knowledge_points[0] if knowledge_points else "相关维度"
                return f"本文得分{score}/{max_score}，{weak}有待加强，建议针对性练习。"
            else:
                weak = knowledge_points[0] if knowledge_points else "整体结构"
                return f"本文得分{score}/{max_score}偏低，{weak}问题突出，请认真修改。"


class GradingService:
    """批改服务 - 对外统一接口"""

    def __init__(self):
        self.rubric_generator = RubricGenerator()
        self.math_grader = MathGrader()
        self.geometry_analyzer = GeometryAnalyzer()
        self.essay_grader = EssayGrader()

    async def grade_math(
        self,
        question: str,
        standard_answer: str,
        student_answer_ocr: str,
        total_score: int,
        rubric: Optional[dict] = None,
        image_bytes: Optional[bytes] = None,
        confidence: float = 0.0,
    ) -> dict:
        """完整的数学题批改流程：rubric生成(如无) → 过程分判定 → 几何辅助线分析(可选) → 评语生成

        Args:
            question: 题目文本
            standard_answer: 标准答案
            student_answer_ocr: 学生解答（OCR提取）
            total_score: 题目总分
            rubric: 评分标准（可选，不传则自动生成）
            image_bytes: 学生手写图片字节（可选，用于几何辅助线分析）
            confidence: 置信度（0.0-1.0），用于动态模型路由决策

        Returns:
            dict: 完整批改结果
        """

        # 检测是否为几何题
        geometry_detected = is_geometry_question(question)

        # Step 1: 柔性Rubric生成（如果未提供）
        if rubric is None:
            rubric = await self.rubric_generator.generate(
                question=question,
                standard_answer=standard_answer,
                total_score=total_score,
            )

        # Step 2: 基于rubric的过程分判定（集成动态模型路由）
        grading_result = await self.math_grader.grade(
            question=question,
            standard_answer=standard_answer,
            student_answer=student_answer_ocr,
            rubric=rubric,
            is_geometry=geometry_detected,
            confidence=confidence,
        )

        # Step 2.5: 几何辅助线分析（仅几何题且有图片时触发）
        geometry_analysis = None
        if geometry_detected and image_bytes:
            logger.info("[GradingService] 检测到几何题，启动辅助线分析...")
            try:
                geo_result = await self.geometry_analyzer.analyze(
                    question=question,
                    image_bytes=image_bytes,
                )
                geometry_analysis = geo_result.to_dict()
                logger.info(f"[GradingService] 辅助线分析完成: assessment={geo_result.assessment}")
            except Exception as e:
                logger.warning(f"[GradingService] 辅助线分析失败: {type(e).__name__}: {e}")

        # Step 3: 生成个性化评语（几何题时追加辅助线提示）
        error_steps = [
            {"step_id": s.get("step_id"), "content": s.get("content"), "reason": s.get("error_reason")}
            for s in grading_result.get("steps", [])
            if not s.get("correct", True)
        ]

        comment = await self.math_grader.generate_comment(
            question=question,
            score=grading_result.get("total_score", 0),
            max_score=grading_result.get("max_score", total_score),
            error_steps=error_steps,
            error_type=grading_result.get("error_type", "none"),
            knowledge_points=grading_result.get("knowledge_points", []),
        )

        # 几何题评语追加辅助线提示
        if geometry_analysis and geometry_analysis.get("hint"):
            comment = f"{comment} {geometry_analysis['hint']}"

        result = {
            "rubric": rubric,
            "grading": grading_result,
            "comment": comment,
            "suggested_score": grading_result.get("total_score", 0),
            "max_score": grading_result.get("max_score", total_score),
            "confidence": confidence if confidence > 0 else 0.85,
            "flagged": confidence < settings.LOW_CONFIDENCE_THRESHOLD if confidence > 0 else False,
            "model_key": grading_result.get("_model_key", "standard"),
        }

        # 几何题时增加辅助线分析结果
        if geometry_analysis is not None:
            result["geometry_analysis"] = geometry_analysis

        return result

    async def grade_essay(
        self,
        question: str,
        standard_answer: str,
        student_answer_ocr: str,
        total_score: int,
        rubric: Optional[dict] = None,
        image_bytes: Optional[bytes] = None,
        confidence: float = 0.0,
    ) -> dict:
        """完整的语文作文批改流程：四维评分 → 综合评语

        Args:
            question: 作文题目
            standard_answer: 写作要求（参考）
            student_answer_ocr: 学生作文（OCR提取）
            total_score: 题目总分（默认100，支持按比例缩放四维）
            rubric: 评分标准（作文场景不使用，保留参数对齐签名）
            image_bytes: 学生手写图片字节（预留：未来用于 VL 识别书写）
            confidence: OCR置信度，作为书写维度弱信号

        Returns:
            dict: 与 grade_math() 同构的批改结果
        """
        # 四维评分（内部已含 qwen→doubao→template 三级降级）
        grading_result = await self.essay_grader.grade(
            question=question,
            standard_answer=standard_answer,
            student_answer=student_answer_ocr,
            rubric=rubric or FALLBACK_ESSAY_RUBRIC,
            total_score=total_score,
            confidence=confidence,
            image_bytes=image_bytes,
        )

        # 综合评语（基于四维详情，避免数学化术语）
        comment = await self.essay_grader.generate_comment(
            question=question,
            score=grading_result.get("total_score", 0),
            max_score=grading_result.get("max_score", total_score),
            dimensions=grading_result.get("dimensions", {}),
            error_cause=grading_result.get("error_cause", "none"),
            knowledge_points=grading_result.get("knowledge_points", []),
        )

        # 若 generate_comment 返回空（LLM 失败且降级也失败），用 overall_comment 兜底
        if not comment:
            comment = grading_result.get("overall_comment", "")

        return {
            "rubric": rubric or FALLBACK_ESSAY_RUBRIC,
            "grading": grading_result,
            "comment": comment,
            "suggested_score": grading_result.get("total_score", 0),
            "max_score": grading_result.get("max_score", total_score),
            "confidence": confidence if confidence > 0 else 0.85,
            "flagged": confidence < settings.LOW_CONFIDENCE_THRESHOLD if confidence > 0 else False,
            "model_key": grading_result.get("_model_key", "standard"),
        }
