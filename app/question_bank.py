"""希沃智教π 题库记忆缓存 — JSON文件持久化

核心功能：
1. 查询题库：输入题目文本 → 返回匹配的缓存答案（含评分标准）
2. 存入题库：题目+答案+评分标准 → 持久化到JSON文件
3. 答案纠错：标记旧答案有误 → 删除旧答案 → 等待AI重新生成后存入
4. 简略答案检测：识别"略"/仅有结果的答案类型

存储格式：JSON文件，key=题目MD5哈希，value=题目条目
"""
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 简略答案关键词（表示答案不完整，需要AI补充）
BRIEF_ANSWER_KEYWORDS = ["略", "略写", "省略", "同上", "略答"]


class QuestionBank:
    """题库记忆缓存（JSON文件持久化）

    数据结构：
    {
        "md5hash_of_question": {
            "question": "原始题目文本",
            "standard_answer": "参考答案（完整解题过程）",
            "rubric": { ... },              # 缓存的评分标准
            "source": "user_provided",       # user_provided | ai_generated | ai_corrected
            "status": "valid",               # valid | invalid | pending_review
            "subject": "math",
            "grade": 7,
            "total_score": 5,
            "created_at": "2026-07-17T10:00:00",
            "updated_at": "2026-07-17T10:00:00"
        }
    }
    """

    def __init__(self, storage_path: str = "data/question_bank.json"):
        self._path = Path(storage_path)
        self._bank: dict = {}
        self._load()

    def _question_hash(self, question: str) -> str:
        """题目文本 → 唯一hash（去空格+小写后MD5，确保相似题目命中）

        Args:
            question: 题目文本

        Returns:
            str: MD5哈希值
        """
        # 去除多余空格和换行，统一大小写，确保语义相同的不同格式题目能命中
        normalized = question.strip().lower().replace(" ", "").replace("\n", "")
        return hashlib.md5(normalized.encode()).hexdigest()

    def lookup(self, question: str) -> Optional[dict]:
        """查询题库：返回缓存的答案和评分标准

        Args:
            question: 题目文本

        Returns:
            dict | None: 缓存条目（含standard_answer, rubric等），不存在或已标记无效返回None
        """
        key = self._question_hash(question)
        entry = self._bank.get(key)
        if entry and entry.get("status") == "valid":
            logger.info(f"[QuestionBank] 命中题库缓存: key={key[:8]}, source={entry.get('source')}")
            return entry
        return None

    def store(
        self,
        question: str,
        standard_answer: str,
        rubric: Optional[dict] = None,
        source: str = "user_provided",
        subject: str = "math",
        grade: int = 7,
        total_score: int = 5,
    ) -> str:
        """存入题库：题目+答案+评分标准 → 持久化

        Args:
            question: 题目文本
            standard_answer: 参考答案（完整解题过程）
            rubric: 评分标准（可选，后续批改时可能重新生成）
            source: 答案来源（user_provided | ai_generated | ai_corrected）
            subject: 学科
            grade: 年级
            total_score: 满分

        Returns:
            str: 题目哈希key
        """
        key = self._question_hash(question)
        now = datetime.now().isoformat()

        # 如果已有条目，保留created_at
        existing = self._bank.get(key)
        created_at = existing.get("created_at", now) if existing else now

        self._bank[key] = {
            "question": question,
            "standard_answer": standard_answer,
            "rubric": rubric or {},
            "source": source,
            "status": "valid",
            "subject": subject,
            "grade": grade,
            "total_score": total_score,
            "created_at": created_at,
            "updated_at": now,
        }
        self._save()
        logger.info(f"[QuestionBank] 存入题库: key={key[:8]}, source={source}, status=valid")
        return key

    def mark_invalid(self, question: str) -> bool:
        """标记答案有误：将状态改为invalid，下次查询不再返回

        Args:
            question: 题目文本

        Returns:
            bool: 是否成功标记（题目不存在时返回False）
        """
        key = self._question_hash(question)
        if key in self._bank:
            self._bank[key]["status"] = "invalid"
            self._bank[key]["updated_at"] = datetime.now().isoformat()
            self._save()
            logger.info(f"[QuestionBank] 标记答案无效: key={key[:8]}")
            return True
        logger.warning(f"[QuestionBank] 标记无效失败: 题目不存在, key={key[:8]}")
        return False

    def mark_invalid_by_hash(self, question_hash: str) -> bool:
        """通过hash直接标记答案无效（供API接口使用）

        Args:
            question_hash: 题目哈希key

        Returns:
            bool: 是否成功标记
        """
        if question_hash in self._bank:
            self._bank[question_hash]["status"] = "invalid"
            self._bank[question_hash]["updated_at"] = datetime.now().isoformat()
            self._save()
            logger.info(f"[QuestionBank] 标记答案无效: key={question_hash[:8]}")
            return True
        logger.warning(f"[QuestionBank] 标记无效失败: hash不存在, key={question_hash[:8]}")
        return False

    def is_brief_answer(self, answer: str) -> bool:
        """检测答案是否简略（如"略"/仅有结果无过程）

        Args:
            answer: 答案文本

        Returns:
            bool: 是否为简略答案
        """
        if not answer:
            return True  # 空答案视为简略
        stripped = answer.strip()
        # 1. 答案仅为简略关键词
        if stripped in BRIEF_ANSWER_KEYWORDS:
            return True
        # 2. 答案很短（<=20字符）且不包含解题过程关键词
        process_keywords = ["解", "因为", "所以", "由", "得", "代入", "化简", "证明", "步骤"]
        if len(stripped) <= 20 and not any(kw in stripped for kw in process_keywords):
            return True
        return False

    def get_stats(self) -> dict:
        """获取题库统计信息

        Returns:
            dict: {total, valid, invalid, by_source}
        """
        total = len(self._bank)
        valid = sum(1 for e in self._bank.values() if e.get("status") == "valid")
        invalid = sum(1 for e in self._bank.values() if e.get("status") == "invalid")
        by_source = {}
        for entry in self._bank.values():
            src = entry.get("source", "unknown")
            by_source[src] = by_source.get(src, 0) + 1
        return {
            "total": total,
            "valid": valid,
            "invalid": invalid,
            "by_source": by_source,
        }

    def list_entries(
        self,
        status_filter: str = "all",
        source_filter: str = "all",
        search: str = "",
    ) -> list[dict]:
        """获取题库条目列表（支持过滤和搜索）

        Args:
            status_filter: 状态过滤 "all" | "valid" | "invalid"
            source_filter: 来源过滤 "all" | "user_provided" | "ai_generated" | "ai_expanded" | "user_corrected"
            search: 模糊搜索题目文本（大小写不敏感）

        Returns:
            list[dict]: 条目列表，每项含 question_hash + 完整条目数据，按 updated_at 降序
        """
        entries = []
        search_lower = search.lower() if search else ""
        for key, entry in self._bank.items():
            # 状态过滤
            if status_filter != "all" and entry.get("status") != status_filter:
                continue
            # 来源过滤
            if source_filter != "all" and entry.get("source") != source_filter:
                continue
            # 模糊搜索
            if search_lower and search_lower not in entry.get("question", "").lower():
                continue
            entries.append({
                "question_hash": key,
                **entry,
            })
        # 按 updated_at 降序排列
        entries.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return entries

    def delete_entry(self, question_hash: str) -> bool:
        """删除题库中指定条目

        Args:
            question_hash: 题目哈希key

        Returns:
            bool: 是否删除成功（hash 不存在返回 False）
        """
        if question_hash in self._bank:
            del self._bank[question_hash]
            self._save()
            logger.info(f"[QuestionBank] 删除条目: key={question_hash[:8]}")
            return True
        logger.warning(f"[QuestionBank] 删除失败: hash不存在, key={question_hash[:8]}")
        return False

    def _load(self):
        """从JSON文件加载题库"""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._bank = json.load(f)
                logger.info(f"[QuestionBank] 加载题库: {len(self._bank)} 条记录, path={self._path}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"[QuestionBank] 加载题库失败: {type(e).__name__}: {e}, 使用空题库")
                self._bank = {}
        else:
            logger.info(f"[QuestionBank] 题库文件不存在, 使用空题库, path={self._path}")

    def _save(self):
        """持久化到JSON文件"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._bank, f, ensure_ascii=False, indent=2)
            logger.debug(f"[QuestionBank] 持久化完成: {len(self._bank)} 条记录")
        except IOError as e:
            logger.error(f"[QuestionBank] 持久化失败: {type(e).__name__}: {e}")
