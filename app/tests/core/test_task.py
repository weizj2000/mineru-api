import os

import pytest
from unittest.mock import patch
import time
from app.core.task import AsyncProcessingQueue, TaskStatus


# 定义正常任务（模拟耗时1秒）
def normal_task(seconds=1):
    time.sleep(seconds)
    return "success"


# 定义异常任务（模拟耗时1秒后抛错）
def failing_task(seconds=1):
    time.sleep(seconds)
    raise ValueError("Task failed")


def test_task_status_flow():
    # 初始化队列（使用临时目录存储状态）
    queue = AsyncProcessingQueue()
    queue.start()

    # 测试正常任务状态流转
    task_id = queue.submit_task(normal_task, 1)
    for _ in range(10):  # 轮询10次（间隔0.5秒）
        status = queue.get_task_status(task_id)
        if status["status"] == TaskStatus.COMPLETED.value:
            break
        time.sleep(0.5)
    assert status["status"] == TaskStatus.COMPLETED.value
    assert status["result"] == "success"
    assert status["error"] is None

    # 测试失败任务状态流转
    task_id = queue.submit_task(failing_task, 1)
    for _ in range(10):
        status = queue.get_task_status(task_id)
        if status["status"] == TaskStatus.FAILED.value:
            break
        time.sleep(0.5)
    assert status["status"] == TaskStatus.FAILED.value
    assert "Task failed" in status["error"]

    queue.stop()


def time_task(index):
    return index, time.time()


def test_task_ordering():
    queue = AsyncProcessingQueue(max_workers=1)  # 强制单进程
    queue.start()

    # 提交5个有序任务（携带序号）
    task_ids = []
    for i in range(5):
        task_id = queue.submit_task(time_task, i)
        task_ids.append(task_id)

    # 等待所有任务完成
    results = []
    for task_id in task_ids:
        while True:
            status = queue.get_task_status(task_id)
            if status["status"] == TaskStatus.COMPLETED.value:
                results.append(status["result"])  # 结果应为 (序号, 开始时间)
                break
            time.sleep(0.1)

    # 验证顺序：序号必须严格递增
    for i in range(len(results) - 1):
        assert results[i][0] == i, f"任务顺序错误：期望{i}，实际{results[i][0]}"
        # 验证开始时间非递减（允许同一时间）
        assert results[i][1] <= results[i + 1][1], f"任务{results[i][0]}开始时间晚于任务{results[i + 1][0]}"

    queue.stop()
