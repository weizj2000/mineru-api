from fastapi import FastAPI
from typing import AsyncGenerator

from contextlib import asynccontextmanager
from starlette.middleware.cors import CORSMiddleware
from app.api.extract import extract_router
from app.core.task import get_processing_queue
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    task_queue = get_processing_queue(max_workers=1)
    try:
        task_queue.start()
        logger.info("FastAPI启动，处理队列已启动")
        app.state.task_queue = task_queue
        yield
    finally:
        task_queue.stop()
        logger.info("FastAPI关闭，处理队列已优雅停止")


app = FastAPI(
    title="文件解析服务",
    description="提供文件解析和任务状态查询的API服务",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(extract_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
