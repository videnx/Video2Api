"""对外视频接口模型。"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class VideoCreateRequest(BaseModel):
    prompt: str = Field(..., description="视频生成提示词")
    image_url: Optional[str] = Field(default=None, description="参考图片 URL（可选）")
    image: Optional[Any] = Field(default=None, description="兼容字段，支持 image.url 或字符串")
    model: Optional[Any] = Field(default=None, description="模型标识（可选，支持解析时长与比例）")


class VideoCreateResponse(BaseModel):
    id: int
    status: str = "pending"
    message: str = "任务创建成功"


class VideoDetailResponse(BaseModel):
    id: str
    object: str = "video"
    status: str
    progress: int
    progress_message: Optional[str] = None
    created_at: str
    video_url: Optional[str] = None
    completed_at: Optional[str] = None
    prompt: Optional[str] = None
