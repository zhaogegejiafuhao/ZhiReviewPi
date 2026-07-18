"""希沃智教π 相似题推荐服务 — 基于分层策略的LLM变式出题

3套Prompt策略（按tier分层）：
- 优等生（root_cause）：根源变式，改变题设考察深层概念
- 中等生（same_type）：同类变式，仅改变数值和情境
- 学困生（scaffolded）：基础铺垫 → 简化原题 → 进阶题

LLM调用模式：复用 llm_utils.py 的 get_siliconflow_client() + parse_llm_json()
降级：LLM失败返回空列表而非报错
"""
import logging
from typing import Optional

from app.llm_utils import get_siliconflow_client, parse_llm_json

logger = logging.getLogger(__name__)

# ===== Prompt 模板 =====

ROOT_CAUSE_PROMPT = """你是一位资深数学教师，正在为**优等生**设计根源变式题。

原题：{question}
标准答案：{standard_answer}
错因：{error_type}
涉及知识点：{knowledge_points}

**变式策略**：改变题设条件，考察学生对深层概念的理解。不要只改数字，要改变问题的本质结构或条件，让学生从不同角度思考同一知识点。

请生成 {count} 道根源变式题，返回JSON格式：
{{
  "questions": [
    {{
      "question_text": "变式题目文本",
      "standard_answer": "参考答案（含解题过程）",
      "rubric_suggestion": {{"steps": [{{"step_id": "s1", "description": "评分步骤", "score": 2}}]}},
      "difficulty": "中等/较难",
      "variant_type": "根源变式"
    }}
  ]
}}"""

SAME_TYPE_PROMPT = """你是一位资深数学教师，正在为**中等生**设计同类变式题。

原题：{question}
标准答案：{standard_answer}
错因：{error_type}
涉及知识点：{knowledge_points}

**变式策略**：保持题目结构和考查方向不变，仅改变数值、情境或表述方式。让学生通过多次练习同类题巩固方法。

请生成 {count} 道同类变式题，返回JSON格式：
{{
  "questions": [
    {{
      "question_text": "变式题目文本",
      "standard_answer": "参考答案（含解题过程）",
      "rubric_suggestion": {{"steps": [{{"step_id": "s1", "description": "评分步骤", "score": 2}}]}},
      "difficulty": "中等",
      "variant_type": "同类变式"
    }}
  ]
}}"""

SCAFFOLDED_PROMPT = """你是一位资深数学教师，正在为**学困生**设计基础铺垫变式题。

原题：{question}
标准答案：{standard_answer}
错因：{error_type}
涉及知识点：{knowledge_points}

**变式策略**：分层递进设计——
1. 第一题：基础铺垫题，考查最基础的概念或计算
2. 第二题：简化版原题，降低难度和计算量
3. 第三题（如有）：适度进阶题，接近原题难度

请生成 {count} 道分层铺垫题，返回JSON格式：
{{
  "questions": [
    {{
      "question_text": "题目文本",
      "standard_answer": "参考答案（含详细解题过程，每步都要写清楚）",
      "rubric_suggestion": {{"steps": [{{"step_id": "s1", "description": "评分步骤", "score": 1}}]}},
      "difficulty": "基础/简化/进阶",
      "variant_type": "基础铺垫/简化原题/进阶题"
    }}
  ]
}}"""


class SimilarQuestionService:
    """相似题推荐服务

    基于学生分层（优等生/中等生/学困生）使用不同的LLM Prompt策略
    生成相似练习题，实现"查看→推荐→练习→追踪"的学习闭环。
    """

    # 分层 → Prompt模板映射
    TIER_PROMPT_MAP = {
        "优等生": ROOT_CAUSE_PROMPT,
        "中等生": SAME_TYPE_PROMPT,
        "学困生": SCAFFOLDED_PROMPT,
    }

    async def generate_similar_questions(
        self,
        question: str,
        knowledge_points: list[str],
        error_type: str,
        tier: str = "中等生",
        count: int = 3,
        standard_answer: str = "",
    ) -> list[dict]:
        """根据分层策略生成相似练习题

        Args:
            question: 原题文本
            knowledge_points: 涉及的知识点列表
            error_type: 错因类型
            tier: 学生分层（优等生/中等生/学困生）
            count: 生成题目数量
            standard_answer: 原题标准答案

        Returns:
            list[dict]: 生成的相似题列表，每项包含：
                - question_text: 题目文本
                - standard_answer: 参考答案
                - rubric_suggestion: 评分标准建议
                - difficulty: 难度标签
                - variant_type: 变式类型
        """
        # 选择Prompt模板
        prompt_template = self.TIER_PROMPT_MAP.get(tier, SAME_TYPE_PROMPT)

        # 格式化知识点
        kp_str = "、".join(knowledge_points) if knowledge_points else "综合"

        # 构建Prompt
        prompt = prompt_template.format(
            question=question,
            standard_answer=standard_answer or "（未提供）",
            error_type=error_type or "未知",
            knowledge_points=kp_str,
            count=count,
        )

        try:
            # 调用LLM
            client = get_siliconflow_client(timeout=60.0)
            response = await client.chat.completions.create(
                model="Qwen/Qwen2.5-72B-Instruct",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的中学数学教师，擅长设计分层变式练习题。请严格按照要求的JSON格式输出。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )

            raw_text = response.choices[0].message.content or ""
            parsed = parse_llm_json(raw_text, fallback={"questions": []})
            questions = parsed.get("questions", [])

            # 验证并规范化输出
            validated_questions = []
            for q in questions[:count]:
                if not q.get("question_text"):
                    continue
                validated_questions.append({
                    "question_text": q.get("question_text", ""),
                    "standard_answer": q.get("standard_answer", ""),
                    "rubric_suggestion": q.get("rubric_suggestion", {}),
                    "difficulty": q.get("difficulty", "中等"),
                    "variant_type": q.get("variant_type", "变式题"),
                })

            logger.info(
                f"[SimilarQuestion] tier={tier}, generated={len(validated_questions)}/{count}, "
                f"question={question[:30]}"
            )
            return validated_questions

        except Exception as e:
            logger.warning(
                f"[SimilarQuestion] LLM生成失败: tier={tier}, "
                f"error={type(e).__name__}: {e}, 返回空列表"
            )
            # 降级：返回空列表而非报错
            return []
