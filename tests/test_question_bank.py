"""QuestionBank 题库记忆缓存单元测试

测试目标：
- _question_hash: 题目文本→唯一hash（去空格+小写后MD5）
- lookup: 查询题库缓存
- store: 存入题库（含持久化）
- mark_invalid: 标记答案无效
- is_brief_answer: 检测简略答案
- get_stats: 获取统计信息
"""
import json
import os
import tempfile
import pytest

from app.question_bank import QuestionBank, BRIEF_ANSWER_KEYWORDS


@pytest.fixture
def temp_bank():
    """创建临时题库（使用临时文件，测试后自动清理）"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = f.name
    bank = QuestionBank(storage_path=path)
    yield bank
    # 清理临时文件
    if os.path.exists(path):
        os.unlink(path)


# ===== _question_hash 测试 =====


def test_question_hash_normal(temp_bank):
    """正常题目文本→hash"""
    hash1 = temp_bank._question_hash("解方程：2x + 3 = 7")
    assert len(hash1) == 32  # MD5哈希长度
    assert isinstance(hash1, str)


def test_question_hash_normalization(temp_bank):
    """空格和大小写不影响hash（语义相同题目应命中同一缓存）"""
    hash1 = temp_bank._question_hash("解方程：2x + 3 = 7")
    hash2 = temp_bank._question_hash("解方程：2x+3=7")
    hash3 = temp_bank._question_hash("  解方程：2x + 3 = 7  ")
    assert hash1 == hash2 == hash3


def test_question_hash_different_questions(temp_bank):
    """不同题目应产生不同hash"""
    hash1 = temp_bank._question_hash("解方程：2x + 3 = 7")
    hash2 = temp_bank._question_hash("求函数y=x^2的最大值")
    assert hash1 != hash2


# ===== lookup 测试 =====


def test_lookup_not_found(temp_bank):
    """查询不存在的题目返回None"""
    result = temp_bank.lookup("不存在的一道题目")
    assert result is None


def test_lookup_found(temp_bank):
    """查询已存入的题目返回缓存条目"""
    temp_bank.store(
        question="解方程：2x + 3 = 7",
        standard_answer="x = 2\n解：2x = 4, x = 2",
        rubric={"steps": [{"step_id": "s1", "score": 3}]},
    )
    result = temp_bank.lookup("解方程：2x + 3 = 7")
    assert result is not None
    assert result["standard_answer"] == "x = 2\n解：2x = 4, x = 2"
    assert result["source"] == "user_provided"


def test_lookup_invalid_returns_none(temp_bank):
    """标记无效的题目查询返回None"""
    temp_bank.store(
        question="求面积公式",
        standard_answer="旧答案（有误）",
    )
    temp_bank.mark_invalid("求面积公式")
    result = temp_bank.lookup("求面积公式")
    assert result is None


# ===== store 测试 =====


def test_store_creates_entry(temp_bank):
    """存入题库创建完整条目"""
    key = temp_bank.store(
        question="解方程：2x = 4",
        standard_answer="x = 2",
        rubric={"steps": [{"step_id": "s1"}]},
        source="user_provided",
        subject="math",
        grade=7,
        total_score=5,
    )
    assert len(key) == 32
    entry = temp_bank._bank[key]
    assert entry["question"] == "解方程：2x = 4"
    assert entry["standard_answer"] == "x = 2"
    assert entry["source"] == "user_provided"
    assert entry["status"] == "valid"


def test_store_persistence(temp_bank):
    """存入题库后持久化到JSON文件"""
    temp_bank.store(
        question="求圆面积",
        standard_answer="S = πr²",
    )
    # 读取JSON文件验证
    with open(temp_bank._path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) >= 1
    # 查找刚存入的题目
    found = False
    for entry in data.values():
        if entry["question"] == "求圆面积":
            found = True
            break
    assert found


def test_store_overwrite(temp_bank):
    """同一题目多次存入，更新而非创建多个条目"""
    temp_bank.store(question="同一题", standard_answer="第一次答案")
    temp_bank.store(question="同一题", standard_answer="第二次答案")
    # 应只有1个条目
    assert len(temp_bank._bank) == 1
    result = temp_bank.lookup("同一题")
    assert result["standard_answer"] == "第二次答案"


# ===== mark_invalid 测试 =====


def test_mark_invalid_existing(temp_bank):
    """标记已有题目的答案为无效"""
    temp_bank.store(question="测试题", standard_answer="正确答案")
    success = temp_bank.mark_invalid("测试题")
    assert success is True
    assert temp_bank._bank[temp_bank._question_hash("测试题")]["status"] == "invalid"


def test_mark_invalid_nonexistent(temp_bank):
    """标记不存在的题目返回False"""
    success = temp_bank.mark_invalid("不存在的题目")
    assert success is False


def test_mark_invalid_by_hash(temp_bank):
    """通过hash直接标记无效"""
    key = temp_bank.store(question="hash测试题", standard_answer="答案")
    success = temp_bank.mark_invalid_by_hash(key)
    assert success is True
    assert temp_bank._bank[key]["status"] == "invalid"


# ===== is_brief_answer 测试 =====


def test_is_brief_answer_empty(temp_bank):
    """空答案视为简略"""
    assert temp_bank.is_brief_answer("") is True


def test_is_brief_answer_keyword(temp_bank):
    """简略关键词视为简略"""
    for kw in BRIEF_ANSWER_KEYWORDS:
        assert temp_bank.is_brief_answer(kw) is True


def test_is_brief_answer_short_no_process(temp_bank):
    """短答案且无过程关键词视为简略"""
    assert temp_bank.is_brief_answer("x = 2") is True
    assert temp_bank.is_brief_answer("42") is True


def test_is_brief_answer_with_process(temp_bank):
    """包含解题过程的答案不是简略"""
    assert temp_bank.is_brief_answer("解：2x+3=7，2x=4，x=2") is False
    assert temp_bank.is_brief_answer("因为AB=CD，所以三角形全等") is False


def test_is_brief_answer_long_answer(temp_bank):
    """长答案（>20字符）即使无过程关键词也不视为简略"""
    assert temp_bank.is_brief_answer("这是一个非常详细的长答案文本内容超过二十个字符") is False


# ===== get_stats 测试 =====


def test_get_stats_empty(temp_bank):
    """空题库统计"""
    stats = temp_bank.get_stats()
    assert stats["total"] == 0
    assert stats["valid"] == 0
    assert stats["invalid"] == 0


def test_get_stats_with_entries(temp_bank):
    """有条目的题库统计"""
    temp_bank.store(question="题1", standard_answer="答1", source="user_provided")
    temp_bank.store(question="题2", standard_answer="答2", source="ai_generated")
    temp_bank.mark_invalid("题1")
    stats = temp_bank.get_stats()
    assert stats["total"] == 2
    assert stats["valid"] == 1
    assert stats["invalid"] == 1
    assert stats["by_source"]["user_provided"] == 1
    assert stats["by_source"]["ai_generated"] == 1


# ===== load/save 测试 =====


def test_load_from_file():
    """从JSON文件加载已有题库"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = f.name
        json.dump({"testkey": {"question": "测试题", "standard_answer": "答案", "status": "valid"}}, f)

    bank = QuestionBank(storage_path=path)
    assert len(bank._bank) == 1
    os.unlink(path)


def test_load_corrupted_file():
    """损坏的JSON文件时使用空题库"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = f.name
        f.write("corrupted json content {{{")

    bank = QuestionBank(storage_path=path)
    assert len(bank._bank) == 0
    os.unlink(path)


def test_load_nonexistent_file():
    """文件不存在时使用空题库"""
    path = tempfile.mktemp(suffix=".json")
    bank = QuestionBank(storage_path=path)
    assert len(bank._bank) == 0
