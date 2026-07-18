"""BatchGradingService 批量异步智能调度服务单元测试

测试目标：
- _estimate_ocr_confidence: OCR置信度预估（基于图片大小）
- _calculate_priority: 优先级计算（权重0.6+0.3+0.1）
- create_batch: 创建批量任务并按优先级排序
- get_batch_status: 查询批量任务状态
- get_batch_results: 查询批量任务结果

注意：execute_batch 依赖 OCRService 和 GradingService，不在本测试范围。
每个测试创建新的 BatchGradingService() 实例。
"""
from app.batch_service import (
    BatchGradingService,
    BatchJob,
)


# ===== _estimate_ocr_confidence 测试 =====


def test_estimate_ocr_confidence_high():
    """大图片(>200KB) → 高置信度(~0.85+)"""
    service = BatchGradingService()
    # 500KB 图片，超过 200KB 阈值
    conf = service._estimate_ocr_confidence(b"\x00" * 500_000)
    assert conf >= 0.85


def test_estimate_ocr_confidence_medium():
    """中等图片(50-200KB) → 中等置信度(~0.60-0.85)"""
    service = BatchGradingService()
    # 100KB 图片，在 50KB-200KB 区间
    conf = service._estimate_ocr_confidence(b"\x00" * 100_000)
    assert 0.60 <= conf < 0.85


def test_estimate_ocr_confidence_low():
    """小图片(<50KB) → 低置信度(~0.30-0.60)"""
    service = BatchGradingService()
    # 10KB 图片，在 0-50KB 区间
    conf = service._estimate_ocr_confidence(b"\x00" * 10_000)
    assert 0.30 <= conf < 0.60


def test_estimate_ocr_confidence_zero():
    """空图片(0字节) → 低置信度(0.30)
    注：源码中 _SIZE_THRESHOLDS["low"]=0，size>=0 走第三分支，返回 0.30+0=0.30
    """
    service = BatchGradingService()
    conf = service._estimate_ocr_confidence(b"")
    assert conf == 0.30


# ===== _calculate_priority 测试 =====


def test_calculate_priority_short_question():
    """短题+高置信+大图 → 高优先级"""
    service = BatchGradingService()
    # 短题(1字符 → simplicity=1.0)、高OCR置信度(0.9)、大图(500KB → size_score=0.5)
    # priority = 0.9*0.6 + 1.0*0.3 + 0.5*0.1 = 0.54 + 0.30 + 0.05 = 0.89
    priority = service._calculate_priority(
        ocr_confidence=0.9,
        question="计算",
        image_size=500_000,
    )
    assert priority >= 0.8  # 高优先级


def test_calculate_priority_long_question():
    """长题+低置信+小图 → 低优先级"""
    service = BatchGradingService()
    # 长题(250字符 → simplicity=0.2)、低OCR置信度(0.3)、小图(1KB → size_score≈0.001)
    # priority = 0.3*0.6 + 0.2*0.3 + 0.001*0.1 ≈ 0.18 + 0.06 + 0.0001 ≈ 0.24
    priority = service._calculate_priority(
        ocr_confidence=0.3,
        question="x" * 250,
        image_size=1_000,
    )
    assert priority < 0.3  # 低优先级


def test_calculate_priority_weights():
    """验证权重0.6+0.3+0.1=1.0"""
    service = BatchGradingService()
    # 当所有维度都为1.0时，优先级应精确为1.0
    # ocr_confidence=1.0, question=1字符(simplicity=1.0), image_size=1_000_000(size_score=1.0)
    # priority = 1.0*0.6 + 1.0*0.3 + 1.0*0.1 = 0.6 + 0.3 + 0.1 = 1.0
    priority = service._calculate_priority(
        ocr_confidence=1.0,
        question="x",
        image_size=1_000_000,
    )
    assert priority == 1.0
    # 验证权重之和为1.0（使用 pytest.approx 避免浮点精度问题）
    from pytest import approx
    assert (0.6 + 0.3 + 0.1) == approx(1.0)


# ===== create_batch 测试 =====


def test_create_batch_single_task():
    """创建单个任务的批量作业"""
    service = BatchGradingService()
    job = service.create_batch([
        {
            "homework_id": "hw1",
            "student_id": "s1",
            "question": "计算 1+1",
            "standard_answer": "2",
            "total_score": 5,
            "image_bytes": b"\x00" * 100_000,
        }
    ])
    assert isinstance(job, BatchJob)
    assert job.total_count == 1
    assert len(job.tasks) == 1
    task = job.tasks[0]
    assert task.homework_id == "hw1"
    assert task.student_id == "s1"
    assert task.question == "计算 1+1"
    assert task.standard_answer == "2"
    assert task.total_score == 5
    assert task.priority > 0
    assert task.ocr_confidence > 0
    assert task.status == "pending"


def test_create_batch_multiple_tasks():
    """创建多个任务，按优先级排序"""
    service = BatchGradingService()
    job = service.create_batch([
        {
            "homework_id": "hw1",
            "student_id": "s1",
            "question": "x" * 250,          # 长题，低优先级
            "standard_answer": "2",
            "total_score": 5,
            "image_bytes": b"\x00" * 1_000,  # 小图
        },
        {
            "homework_id": "hw2",
            "student_id": "s2",
            "question": "计算",              # 短题，高优先级
            "standard_answer": "2",
            "total_score": 5,
            "image_bytes": b"\x00" * 500_000,  # 大图
        },
    ])
    assert job.total_count == 2
    # 高优先级应排在前面
    assert job.tasks[0].priority > job.tasks[1].priority
    assert job.tasks[0].student_id == "s2"


def test_create_batch_priority_ordering():
    """高优先级任务排在前面"""
    service = BatchGradingService()
    job = service.create_batch([
        {
            "homework_id": "hw1",
            "student_id": "s1",
            "question": "x" * 250,
            "standard_answer": "2",
            "image_bytes": b"\x00" * 1_000,     # 低优先级
        },
        {
            "homework_id": "hw2",
            "student_id": "s2",
            "question": "x" * 30,
            "standard_answer": "2",
            "image_bytes": b"\x00" * 100_000,   # 中优先级
        },
        {
            "homework_id": "hw3",
            "student_id": "s3",
            "question": "计算",
            "standard_answer": "2",
            "image_bytes": b"\x00" * 500_000,   # 高优先级
        },
    ])
    priorities = [t.priority for t in job.tasks]
    # 应严格降序
    assert priorities[0] > priorities[1] > priorities[2]
    # 高优先级(s3)排在最前
    assert job.tasks[0].student_id == "s3"
    # 低优先级(s1)排在最后
    assert job.tasks[2].student_id == "s1"


# ===== get_batch_status 测试 =====


def test_get_batch_status_pending():
    """初始状态为pending"""
    service = BatchGradingService()
    job = service.create_batch([
        {
            "homework_id": "hw1",
            "student_id": "s1",
            "question": "计算",
            "standard_answer": "2",
            "image_bytes": b"\x00" * 100_000,
        }
    ])
    status = service.get_batch_status(job.batch_id)
    assert status is not None
    assert status["status"] == "pending"
    assert status["completed"] == 0
    assert status["failed"] == 0
    assert status["progress_pct"] == 0.0


def test_get_batch_status_not_found():
    """不存在的batch_id返回None"""
    service = BatchGradingService()
    assert service.get_batch_status("non_existent_batch_id") is None


# ===== get_batch_results 测试 =====


def test_get_batch_results_not_found():
    """不存在的batch_id返回None"""
    service = BatchGradingService()
    assert service.get_batch_results("non_existent_batch_id") is None
