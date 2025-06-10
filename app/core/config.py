import os
from pathlib import Path

from pydantic import Field
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

current_file_path = Path(__file__).resolve()
ENV_FILE_PATH = os.path.join(current_file_path.parent.parent.parent, ".env")


class Settings(BaseSettings):
    # 应用基本配置
    APP_NAME: str = "MinerU API Application"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(False, env="APP_DEBUG")

    # 安全配置
    SECRET_KEY: str = "your_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # 可选配置项
    LOG_LEVEL: Optional[str] = "INFO"

    # S3配置
    ENABLE_S3_STORAGE: bool = Field(True, env="ENABLE_S3_STORAGE")
    S3_BUCKET_NAME: Optional[str] = Field(None, env="S3_BUCKET_NAME")
    S3_ACCESS_KEY: Optional[str] = Field(None, env="S3_ACCESS_KEY")
    S3_SECRET_KEY: Optional[str] = Field(None, env="S3_SECRET_KEY")
    S3_ENDPOINT_URL: Optional[str] = Field(None, env="S3_ENDPOINT_URL")
    S3_BUCKET_PREFIX: Optional[str] = Field("tmp", env="S3_BUCKET_PREFIX")

    # 配置模型：明确环境变量加载规则
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,  # 从指定路径加载.env文件
        env_file_encoding="utf-8",  # .env文件编码
        case_sensitive=True,  # 环境变量名大小写敏感（如APP_DEBUG不会匹配app_debug）
        extra="ignore"  # 关键优化：显式忽略未定义的额外环境变量（Pydantic v2+特性）
    )


# 缓存配置实例，避免重复加载
@lru_cache()
def get_settings():
    return Settings()


if __name__ == "__main__":
    settings = get_settings()
    print(ENV_FILE_PATH)
    print(settings.S3_BUCKET_NAME)
