"""希沃智教π AI解题服务 — 无答案场景AI先做题 + 简略答案补充

核心功能：
1. solve_question: 无答案时，AI先完成题目，输出完整解题过程和最终答案
2. expand_brief_answer: 简略答案（如"略"/仅有结果）补充为完整解题过程
3. solve_subjective: 主观题/作文评分要点生成（输出主旨+关键点而非完整范文）
"""
import logging

from app.llm_utils import parse_llm_json, get_siliconflow_client
from app.config import settings

logger = logging.getLogger(__name__)

# ===== Prompt 模板 =====

SOLVE_QUESTION_PROMPT = """你是一位资深的{subject}教师，请完整解答以下题目。

## 题目（{total_score}分）
{question}

请完成以下任务：
1. 给出完整的解题过程（每一步都要写出）
2. 给出最终答案
3. 建议评分标准（列出关键步骤及对应分值）

严格输出以下JSON格式，不要输出其他内容：
{{"solution": "完整解题过程文本", "final_answer": "最终答案（简短）", "rubric_suggestion": {{"steps": [{{"step_id": "s1", "description": "步骤描述", "score": N, "required": true, "keywords": ["关键词"], "example": "示例表达"}}]}}}}"""

EXPAND_BRIEF_ANSWER_PROMPT = """你是一位资深的{subject}教师，请将以下简略答案补充为完整解题过程。

## 题目（{total_score}分）
{question}

## 简略答案
{brief_answer}

请完成以下任务：
1. 根据简略答案和题目，推导出完整的解题过程
2. 补充每个步骤的推导理由和中间结果
3. 保持最终答案与简略答案一致

严格输出以下JSON格式，不要输出其他内容：
{{"full_solution": "完整解题过程文本", "standard_answer": "完整参考答案（含解题过程和最终答案）"}}"""

SOLVE_SUBJECTIVE_PROMPT = """你是一位资深的{subject}教师，请为以下主观题/作文题生成评分要点。

## 题目
{question}

请完成以下任务：
1. 给出文章主旨/核心论点
2. 列出关键得分点（不写完整范文，只写评分要点）
3. 建议各得分点的分值

严格输出以下JSON格式，不要输出其他内容：
{{"main_theme": "文章主旨", "key_points": [{{"point": "得分点描述", "score": N, "description": "评分标准说明"}}], "scoring_criteria": "总体评分标准说明"}}"""


class AnswerSolver:
    """AI解题器 — 处理无答案和简略答案场景"""

    async def solve_question(
        self,
        question: str,
        total_score: int = 5,
        subject: str = "math",
        grade: int = 7,
    ) -> dict:
        """无答案场景：AI先完成题目，输出解题过程和最终答案

        Args:
            question: 题目文本
            total_score: 满分
            subject: 学科
            grade: 年级

        Returns:
            dict: {
                "solution": 完整解题过程,
                "final_answer": 最终答案,
                "rubric_suggestion": 建议评分标准,
                "standard_answer": 合并后的参考答案（解题过程+最终答案）
            }
        """
        if not settings.SILICONFLOW_API_KEY:
            logger.warning("[AnswerSolver] 硅基流动API不可用，无法自动解题")
            return {
                "solution": "",
                "final_answer": "",
                "rubric_suggestion": {},
                "standard_answer": "",
            }

        client = get_siliconflow_client()
        prompt = SOLVE_QUESTION_PROMPT.format(
            subject=subject,
            total_score=total_score,
            question=question,
        )

        try:
            logger.info(f"[AnswerSolver] AI解题开始: question={question[:30]}...")
            response = await client.chat.completions.create(
                model="Qwen/Qwen2.5-14B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
            content = response.choices[0].message.content
            logger.info(f"[AnswerSolver] LLM原始输出长度: {len(content)}, 前200字: {content[:200]}")
            result = parse_llm_json(content)
            solution = result.get("solution", "")
            final_answer = result.get("final_answer", "")
            standard_answer = f"{solution}\n最终答案：{final_answer}" if solution and final_answer else final_answer or solution

            logger.info(f"[AnswerSolver] AI解题完成: answer={final_answer[:30] if final_answer else '无'}")
            return {
                "solution": solution,
                "final_answer": final_answer,
                "rubric_suggestion": result.get("rubric_suggestion", {}),
                "standard_answer": standard_answer,
            }
        except Exception as e:
            logger.error(f"[AnswerSolver] AI解题失败: {type(e).__name__}: {e}", exc_info=True)
            return {
                "solution": "",
                "final_answer": "",
                "rubric_suggestion": {},
                "standard_answer": "",
                "error": f"{type(e).__name__}: {str(e)[:100]}",
            }

    async def expand_brief_answer(
        self,
        question: str,
        brief_answer: str,
        total_score: int = 5,
        subject: str = "math",
    ) -> dict:
        """简略答案补充：将"略"/仅有结果的答案扩展为完整解题过程

        Args:
            question: 题目文本
            brief_answer: 简略答案文本
            total_score: 满分
            subject: 学科

        Returns:
            dict: {
                "full_solution": 完整解题过程,
                "standard_answer": 合并后的参考答案
            }
        """
        if not settings.SILICONFLOW_API_KEY:
            logger.warning("[AnswerSolver] 硅基流动API不可用，无法补充简略答案")
            return {"full_solution": brief_answer, "standard_answer": brief_answer}

        client = get_siliconflow_client()
        prompt = EXPAND_BRIEF_ANSWER_PROMPT.format(
            subject=subject,
            total_score=total_score,
            question=question,
            brief_answer=brief_answer,
        )

        try:
            logger.info(f"[AnswerSolver] 补充简略答案开始: brief={brief_answer[:30]}...")
            response = await client.chat.completions.create(
                model="Qwen/Qwen2.5-14B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
            content = response.choices[0].message.content
            result = parse_llm_json(content)

            full_solution = result.get("full_solution", brief_answer)
            standard_answer = result.get("standard_answer", brief_answer)

            logger.info(f"[AnswerSolver] 简略答案补充完成: answer={standard_answer[:30]}...")
            return {
                "full_solution": full_solution,
                "standard_answer": standard_answer,
            }
        except Exception as e:
            logger.error(f"[AnswerSolver] 简略答案补充失败: {type(e).__name__}: {e}")
            return {"full_solution": brief_answer, "standard_answer": brief_answer}

    async def solve_subjective(
        self,
        question: str,
        subject: str = "chinese",
    ) -> dict:
        """主观题/作文：生成评分要点而非完整答案

        Args:
            question: 题目文本
            subject: 学科

        Returns:
            dict: {
                "main_theme": 文章主旨,
                "key_points": 关键得分点列表,
                "scoring_criteria": 总体评分标准说明,
                "standard_answer": 主旨+关键点合并文本（作为参考答案）
            }
        """
        if not settings.SILICONFLOW_API_KEY:
            logger.warning("[AnswerSolver] 硅基流动API不可用，无法生成评分要点")
            return {"main_theme": "", "key_points": [], "scoring_criteria": "", "standard_answer": ""}

        client = get_siliconflow_client()
        prompt = SOLVE_SUBJECTIVE_PROMPT.format(
            subject=subject,
            question=question,
        )

        try:
            logger.info(f"[AnswerSolver] 主观题评分要点生成: question={question[:30]}...")
            response = await client.chat.completions.create(
                model="Qwen/Qwen2.5-14B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
            content = response.choices[0].message.content
            result = parse_llm_json(content)

            # 合并主旨和关键点作为参考答案
            main_theme = result.get("main_theme", "")
            key_points = result.get("key_points", [])
            scoring_criteria = result.get("scoring_criteria", "")

            points_text = "\n".join([f"- {p.get('point', '')} ({p.get('score', 0)}分)" for p in key_points])
            standard_answer = f"主旨：{main_theme}\n\n评分要点：\n{points_text}" if main_theme else ""

            logger.info(f"[AnswerSolver] 主观题评分要点生成完成: theme={main_theme[:20]}")
            return {
                "main_theme": main_theme,
                "key_points": key_points,
                "scoring_criteria": scoring_criteria,
                "standard_answer": standard_answer,
            }
        except Exception as e:
            logger.error(f"[AnswerSolver] 主观题评分要点生成失败: {type(e).__name__}: {e}")
            return {"main_theme": "", "key_points": [], "scoring_criteria": "", "standard_answer": ""}
