from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Body, UploadFile, File, HTTPException, Request
from pydantic import BaseModel, Field
from starlette import status

from app.services.file_parser import S3Config, FileProcessor

router = APIRouter(prefix="/extract")
s3_config = S3Config()
processor = FileProcessor(s3_config)


class BatchTaskSubmitRequest(BaseModel):
    """批量任务提交请求模型（可选参数）"""
    file_paths: Optional[List[str]] = Field(None, description="文件路径列表（本地/URL/S3）")


class TaskSubmitResponse(BaseModel):
    """任务提交响应模型（支持批量）"""
    task_ids: List[str] = Field(..., description="生成的任务ID列表")
    submit_time: str = Field(..., description="任务提交时间")
    total_tasks: int = Field(..., description="总提交任务数")


@router.post("/task",
             response_model=TaskSubmitResponse,
             status_code=status.HTTP_202_ACCEPTED,
             summary="提交文件解析任务")
async def submit_extraction_task(
        request: Request,
        submit_request: Optional[BatchTaskSubmitRequest] = Body(None, description="批量文件路径参数（本地/URL/S3）"),
        files: Optional[List[UploadFile]] = File(None, description="上传的文件流列表")
) -> TaskSubmitResponse:
    """
    提交文件解析任务，支持两种方式：
    - 通过表单上传文件 (multipart/form-data)
    - 通过表单提交文件路径 (application/x-www-form-urlencoded)

    优先级: 文件上传 > 文件路径
    """
    # 验证至少有一个输入来源
    if not submit_request and not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="需要提供file_paths或上传文件列表")

    task_ids = []
    submit_time = datetime.now().isoformat()

    # 处理批量文件上传（优先于路径处理）
    if files:
        for file in files:
            file_bytes = await file.read()
            task_id = request.app.state.task_queue.submit_task(processor.process, file_bytes)
            task_ids.append(task_id)

    if submit_request and submit_request.file_paths:
        for file_path in submit_request.file_paths:
            task_id = request.app.state.task_queue.submit_task(processor.process, file_path)
            task_ids.append(task_id)

    return TaskSubmitResponse(
        task_ids=task_ids,
        submit_time=submit_time,
        total_tasks=len(task_ids)
    )


@router.get("/task/{task_id}",
            summary="查询任务结果",
            description="根据任务ID查询解析任务状态和结果")
async def get_task_status(request: Request, task_id: str) -> dict:
    """
    根据任务ID查询处理状态和结果

    - **task_id**: 提交任务时返回的任务ID
    - returns: 包含任务状态和结果的字典
        {
            "task_id": task_id,
            "status": TaskStatus枚举类,
            "data": ParserResult(BaseModel).model_dump(),
            "error": error | None,
            "created_at": time.time(),
            "started_at": time.time(),
            "completed_at": time.time()
        }
    """
    result = request.app.state.task_queue.get_task_status(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务ID不存在")

    return result
