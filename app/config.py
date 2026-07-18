"""希沃智教π 全局配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # 百度 OCR
    BAIDU_OCR_API_KEY: str = os.getenv("BAIDU_OCR_API_KEY", "")
    BAIDU_OCR_SECRET_KEY: str = os.getenv("BAIDU_OCR_SECRET_KEY", "")

    # 硅基流动
    SILICONFLOW_API_KEY: str = os.getenv("SILICONFLOW_API_KEY", "")
    SILICONFLOW_BASE_URL: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

    # 火山引擎豆包
    VOLCENGINE_API_KEY: str = os.getenv("ARK_API_KEY", os.getenv("VOLCENGINE_API_KEY", ""))
    VOLCENGINE_BASE_URL: str = os.getenv("VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    DOUBAO_ENDPOINT_ID: str = os.getenv("DOUBAO_ENDPOINT_ID", "")

    # 飞书
    FEISHU_APP_ID: str = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET: str = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_VERIFICATION_TOKEN: str = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    FEISHU_ENCRYPT_KEY: str = os.getenv("FEISHU_ENCRYPT_KEY", "")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # 题库记忆缓存路径
    QUESTION_BANK_PATH: str = os.getenv("QUESTION_BANK_PATH", "data/question_bank.json")

    # 低置信度阈值
    LOW_CONFIDENCE_THRESHOLD: float = 0.7


settings = Settings()
