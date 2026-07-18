"""希沃智教π LLM工具函数 — 通用JSON解析、客户端复用"""
import json
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_llm_json(text: str, fallback: Optional[dict] = None) -> dict:
    """从LLM输出中提取JSON（四级解析策略）

    依次尝试：
    1. 直接json.loads
    2. 提取```json```块
    3. 提取第一个{...}块 + 括号平衡修复
    4. 从左到右逐步修复多余闭合括号

    Args:
        text: LLM输出文本
        fallback: 解析失败时的默认返回值，默认为空字典

    Returns:
        dict: 解析后的JSON字典
    """
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取```json...```块
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取第一个 {...} 块（贪婪匹配，然后括号平衡修复）
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        # 括号平衡修复：从末尾逐步移除多余的 }
        open_count = json_str.count("{") - json_str.count("}")
        if open_count < 0:
            # 右括号过多，从末尾移除多余的 }
            fixed = json_str.rstrip()
            while fixed.endswith("}") and open_count < 0:
                fixed = fixed[:-1].rstrip()
                open_count = json_str.count("{") - fixed.count("}")
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
        # 从左到右找到第一个合法的完整JSON对象
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(json_str):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    # 找到最外层闭合点
                    try:
                        return json.loads(json_str[: i + 1])
                    except json.JSONDecodeError:
                        break

    logger.warning(f"LLM JSON解析失败, 原文前100字: {text[:100]}")
    logger.debug(f"LLM JSON解析失败, 完整原文: {text}")
    return fallback or {}


def get_siliconflow_client(timeout: float = 30.0):
    """获取硅基流动API客户端（统一配置，延迟导入避免循环依赖）

    Args:
        timeout: 请求超时时间（秒）

    Returns:
        AsyncOpenAI: 硅基流动API客户端实例
    """
    from openai import AsyncOpenAI
    from app.config import settings

    return AsyncOpenAI(
        api_key=settings.SILICONFLOW_API_KEY,
        base_url=settings.SILICONFLOW_BASE_URL,
        timeout=timeout,
    )
