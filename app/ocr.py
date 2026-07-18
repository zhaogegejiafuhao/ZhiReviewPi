"""希沃智教π OCR识别层 - 双引擎置信度融合"""
import asyncio
import base64
import hashlib
import logging
import httpx
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from app.config import settings


@dataclass
class OCRResult:
    """单引擎OCR识别结果"""
    text: str
    confidence: float
    engine: str  # baidu_ocr | paddleocr_vl
    formulas: list[str] = field(default_factory=list)  # LaTeX公式列表
    regions: list[dict] = field(default_factory=list)  # [{bbox, text, confidence}]


@dataclass
class FusedOCRResult:
    """双引擎融合后的OCR结果"""
    text: str
    confidence: float
    formulas: list[str]
    regions: list[dict]
    engines_used: list[str]
    per_engine_results: dict[str, OCRResult]
    needs_manual_input: bool = False


class BaiduOCREngine:
    """百度智能云手写OCR API"""

    OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/handwriting"
    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    _token_cache: dict = {}

    async def _get_access_token(self) -> str:
        if "token" in self._token_cache:
            return self._token_cache["token"]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                params={
                    "grant_type": "client_credentials",
                    "client_id": settings.BAIDU_OCR_API_KEY,
                    "client_secret": settings.BAIDU_OCR_SECRET_KEY,
                },
            )
            data = resp.json()
            self._token_cache["token"] = data["access_token"]
            return data["access_token"]

    async def recognize(self, image_bytes: bytes) -> OCRResult:
        """识别图片中的手写文字"""
        if not settings.BAIDU_OCR_API_KEY:
            return OCRResult(text="", confidence=0.0, engine="baidu_ocr")

        token = await self._get_access_token()
        img_b64 = base64.b64encode(image_bytes).decode()

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.OCR_URL,
                params={"access_token": token},
                data={"image": img_b64, "language_type": "CHN_ENG"},
            )
            data = resp.json()

        words_result = data.get("words_result", [])
        text_parts = []
        regions = []
        total_conf = 0.0

        for item in words_result:
            word = item.get("words", "")
            text_parts.append(word)
            loc = item.get("location", {})
            conf = item.get("probability", {}).get("average", 0.5)
            total_conf += conf
            regions.append({
                "bbox": [loc.get("left", 0), loc.get("top", 0),
                         loc.get("left", 0) + loc.get("width", 0),
                         loc.get("top", 0) + loc.get("height", 0)],
                "text": word,
                "confidence": round(conf, 3),
            })

        avg_conf = total_conf / len(words_result) if words_result else 0.0
        return OCRResult(
            text="\n".join(text_parts),
            confidence=round(avg_conf, 3),
            engine="baidu_ocr",
            regions=regions,
        )


class PaddleOCREngine:
    """PaddleOCR-VL本地识别引擎（公式+手写增强）"""

    _ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                show_log=False,
                use_gpu=False,
            )
        return self._ocr

    async def recognize(self, image_bytes: bytes) -> OCRResult:
        """本地PaddleOCR识别（同步调用包装为异步）"""
        import tempfile
        import os

        # 将bytes写入临时文件（PaddleOCR需要文件路径）
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(image_bytes)
            tmp_path = f.name

        try:
            ocr = self._get_ocr()
            # 在线程池中运行同步OCR
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, ocr.ocr, tmp_path, True)

            text_parts = []
            regions = []
            total_conf = 0.0

            for line in result[0] if result[0] else []:
                box, (text, conf) = line
                text_parts.append(text)
                total_conf += conf
                # box格式: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                x_coords = [p[0] for p in box]
                y_coords = [p[1] for p in box]
                regions.append({
                    "bbox": [min(x_coords), min(y_coords),
                             max(x_coords), max(y_coords)],
                    "text": text,
                    "confidence": round(conf, 3),
                })

            avg_conf = total_conf / len(regions) if regions else 0.0
            return OCRResult(
                text="\n".join(text_parts),
                confidence=round(avg_conf, 3),
                engine="paddleocr_vl",
                regions=regions,
            )
        finally:
            os.unlink(tmp_path)


def fuse_results(baidu: OCRResult, paddle: OCRResult) -> FusedOCRResult:
    """双引擎置信度融合：取置信度较高的引擎结果为主"""
    engines_used = []
    per_engine = {}

    if baidu.confidence > 0:
        engines_used.append("baidu_ocr")
        per_engine["baidu_ocr"] = baidu
    if paddle.confidence > 0:
        engines_used.append("paddleocr_vl")
        per_engine["paddleocr_vl"] = paddle

    # 选择置信度更高的引擎结果作为主结果
    if baidu.confidence >= paddle.confidence and baidu.confidence > 0:
        primary = baidu
    elif paddle.confidence > 0:
        primary = paddle
    else:
        primary = OCRResult(text="", confidence=0.0, engine="none")

    # 融合公式：优先使用PaddleOCR识别到的公式
    formulas = paddle.formulas if paddle.formulas else []

    return FusedOCRResult(
        text=primary.text,
        confidence=primary.confidence,
        formulas=formulas,
        regions=primary.regions,
        engines_used=engines_used,
        per_engine_results=per_engine,
    )


class OCRService:
    """OCR识别服务 - 对外统一接口"""

    def __init__(self):
        self.baidu = BaiduOCREngine()
        self.paddle = PaddleOCREngine()

    async def recognize(self, image_bytes: bytes) -> FusedOCRResult:
        """双引擎并行识别 + 置信度融合（含多级降级）"""
        # 并行调用两个引擎
        baidu_task = self.baidu.recognize(image_bytes)
        paddle_task = self.paddle.recognize(image_bytes)

        results = await asyncio.gather(
            baidu_task, paddle_task, return_exceptions=True
        )

        baidu_result = results[0] if not isinstance(results[0], Exception) else OCRResult(
            text="", confidence=0.0, engine="baidu_ocr"
        )
        paddle_result = results[1] if not isinstance(results[1], Exception) else OCRResult(
            text="", confidence=0.0, engine="paddleocr_vl"
        )

        # 检查两个引擎是否都失败
        both_failed = (baidu_result.confidence == 0.0 and paddle_result.confidence == 0.0)

        if both_failed:
            # Level 2: 两个引擎均无有效结果
            logger.warning("[OCRService] Level 2降级：双引擎均失败，标记需人工录入")
            # Level 3: 标记需要人工录入
            return FusedOCRResult(
                text="",
                confidence=0.0,
                formulas=[],
                regions=[],
                engines_used=["manual_fallback"],
                per_engine_results={},
                needs_manual_input=True,
            )

        return fuse_results(baidu_result, paddle_result)

    async def recognize_single(self, image_bytes: bytes, engine: str = "baidu_ocr") -> OCRResult:
        """单引擎识别（调试用）"""
        if engine == "baidu_ocr":
            return await self.baidu.recognize(image_bytes)
        else:
            return await self.paddle.recognize(image_bytes)
