import multiprocessing
import os
import threading
import time
import queue as PyQueue
import uuid
from concurrent.futures import ProcessPoolExecutor, Future
from typing import Dict, Any, Callable, Optional, List, Tuple, Set
import json
import logging
import enum

from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    FAILED = "failed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELED = "canceled"


class Task:
    """任务类，表示一个异步处理任务"""
    
    def __init__(self, task_id: str, func: Callable, args: List[Any], kwargs: Dict[str, Any]):
        self._task_id = task_id
        self._func = func
        self._args = args.copy()
        self._kwargs = kwargs.copy()
        self._status = TaskStatus.PENDING
        self._result: Any = None
        self._error: Optional[Exception] = None
        self._created_at = time.time()
        self._started_at: Optional[float] = None
        self._completed_at: Optional[float] = None

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def func(self) -> Callable:
        return self._func

    @property
    def args(self) -> List[Any]:
        return self._args.copy()

    @property
    def kwargs(self) -> Dict[str, Any]:
        return self._kwargs.copy()

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def result(self) -> Any:
        return self._result

    @property
    def error(self) -> Optional[Exception]:
        return self._error

    @property
    def created_at(self) -> float:
        return self._created_at

    @property
    def started_at(self) -> Optional[float]:
        return self._started_at

    @property
    def completed_at(self) -> Optional[float]:
        return self._completed_at

    def update_status(self, status: TaskStatus) -> None:
        """状态更新校验"""
        valid_transitions = {
            TaskStatus.PENDING: [TaskStatus.PROCESSING],
            TaskStatus.PROCESSING: [TaskStatus.COMPLETED, TaskStatus.FAILED],
            TaskStatus.COMPLETED: [],
            TaskStatus.FAILED: []
        }
        current = self._status
        if status not in valid_transitions.get(current, []):
            raise ValueError(f"无效的状态转换: {current} -> {status} (任务ID: {self._task_id})")
        self._status = status

    def set_started(self) -> None:
        if self._status != TaskStatus.PENDING:
            raise RuntimeError(f"任务 {self._task_id} 未处于待处理状态，无法开始")
        self.update_status(TaskStatus.PROCESSING)
        self._started_at = time.time()

    def set_completed(self, result: Any) -> None:
        if self._status != TaskStatus.PROCESSING:
            raise RuntimeError(f"任务 {self._task_id} 未处于处理中状态，无法标记完成")
        self.update_status(TaskStatus.COMPLETED)
        self._result = result
        self._completed_at = time.time()

    def set_failed(self, error: Exception) -> None:
        if self._status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
            raise RuntimeError(f"任务 {self._task_id} 未处于待处理或处理中状态，无法标记失败")
        self.update_status(TaskStatus.FAILED)
        self._error = error
        self._completed_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self._task_id,
            "status": self._status.value,
            "data": self._result.model_dump() if isinstance(self._result, BaseModel) else self._result,
            "error": str(self._error) if self._error else None,
            "created_at": self._created_at,
            "started_at": self._started_at,
            "completed_at": self._completed_at
        }


class AsyncProcessingQueue:
    """异步处理队列，使用多进程处理任务"""
    _instance: Optional['AsyncProcessingQueue'] = None

    def __new__(cls, max_workers: int = None, status_dir: str = "task_status"):
        # 允许通过参数重新初始化实例
        if not cls._instance or (max_workers is not None or status_dir != cls._instance._status_dir):
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_workers: int = None, status_dir: str = "task_status"):
        if self._initialized:
            return
        self._max_workers = max_workers or multiprocessing.cpu_count()
        self._status_dir = status_dir
        self._task_queue: PyQueue.Queue[Task] = PyQueue.Queue()
        self._tasks: Dict[str, Task] = {}
        self._executor: Optional[ProcessPoolExecutor] = None
        self._running: bool = False
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()  # 线程安全锁
        self._active_tasks: Set[str] = set()  # 跟踪当前活跃的任务ID

        # 初始化状态目录
        os.makedirs(self._status_dir, exist_ok=True)
        self._initialized = True
    
    def start(self) -> None:
        """启动处理队列（幂等操作）"""
        with self._lock:
            if self._running:
                logger.info("队列已启动，无需重复启动")
                return
            # 初始化进程池（如果未初始化）
            if self._executor is None:
                self._executor = ProcessPoolExecutor(max_workers=self._max_workers)
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="ProcessingWorkerThread",
                daemon=True
            )
            self._worker_thread.start()
            logger.info(f"处理队列已启动，最大工作进程数：{self._max_workers}")
    
    def stop(self) -> None:
        """停止处理队列（优雅关闭）"""
        with self._lock:
            if not self._running:
                # logger.info("队列未运行，无需停止")
                return
            self._running = False
            # 等待当前任务处理完成
            while not self._task_queue.empty() or self._active_tasks:
                logger.info(f"等待任务处理完成... 剩余任务数: {len(self._active_tasks)}")
                time.sleep(1)
            # 关闭进程池
            if self._executor:
                self._executor.shutdown(wait=True)
                self._executor = None
            # 清理线程
            if self._worker_thread:
                self._worker_thread.join(timeout=5)
                self._worker_thread = None

            # 清理内存任务缓存
            self._tasks.clear()
            self._active_tasks.clear()
            logger.info("处理队列已停止")
    
    def submit_task(self, func: Callable, *args: Any, **kwargs: Any) -> str:
        """提交任务（线程安全）"""
        with self._lock:
            if not self._running:
                raise RuntimeError("队列未启动，无法提交任务")
            task_id = str(uuid.uuid4())
            # 深拷贝参数防止外部修改
            args_copy = list(args)
            kwargs_copy = kwargs.copy()
            task = Task(task_id, func, args_copy, kwargs_copy)
            self._tasks[task_id] = task
            self._task_queue.put(task)
            self._save_task_status(task)
            logger.debug(f"任务提交成功，task_id: {task_id}")
            return task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态（线程安全）"""
        with self._lock:
            # 优先检查内存中的任务
            if task_id in self._tasks:
                return self._tasks[task_id].to_dict()
            # 检查已完成/失败的任务（可能已被清理）
            status_file = os.path.join(self._status_dir, f"{task_id}.json")
            if os.path.exists(status_file):
                try:
                    with open(status_file, "r") as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"加载任务状态失败，task_id: {task_id}, 错误: {str(e)}")
            return None
    
    def _worker_loop(self) -> None:
        """工作线程主循环：串行处理任务"""
        logger.info("工作线程启动")
        while self._running:
            try:
                task = self._task_queue.get(timeout=1)  # 避免永久阻塞
                if not self._running:
                    self._task_queue.put(task)  # 放回队列，等待下次启动
                    break
                self._process_single_task(task)
            except PyQueue.Empty:
                continue
            except Exception as e:
                logger.error(f"工作线程异常: {str(e)}", exc_info=True)

    def _process_single_task(self, task: Task) -> None:
        """处理单个任务（串行执行，等待完成）"""
        try:
            with self._lock:
                if task.task_id not in self._tasks:
                    logger.warning(f"任务已取消，跳过处理，task_id: {task.task_id}")
                    return
                self._active_tasks.add(task.task_id)

            logger.info(f"开始处理任务，task_id: {task.task_id}")
            task.set_started()
            self._save_task_status(task)

            # 执行任务（使用进程池）
            future: Future = self._executor.submit(
                self._execute_task,
                task.func,
                *task.args,
                **task.kwargs
            )
            # 阻塞等待任务完成（保证顺序）
            result, error = future.result()

            with self._lock:
                if error:
                    task.set_failed(error)
                else:
                    task.set_completed(result)
                self._active_tasks.discard(task.task_id)
                self._save_task_status(task)
                logger.info(f"任务处理完成，task_id: {task.task_id}, 状态: {task.status}")

        except Exception as e:
            with self._lock:
                if task.task_id in self._active_tasks:
                    self._active_tasks.discard(task.task_id)
                try:
                    task.set_failed(e)
                except RuntimeError:
                    # 任务可能已被外部取消
                    logger.warning(f"任务 {task.task_id} 状态异常，可能已取消")
                self._save_task_status(task)
                logger.error(f"任务处理失败，task_id: {task.task_id}, 错误: {str(e)}", exc_info=True)

    @staticmethod
    def _execute_task(func: Callable, *args: Any, **kwargs: Any) -> Tuple[Any, Optional[Exception]]:
        """执行任务函数，返回(结果, 异常)"""
        try:
            result = func(*args, **kwargs)
            return result, None
        except Exception as e:
            return None, e
    
    def _save_task_status(self, task: Task) -> None:
        """保存任务状态到文件（带错误处理）"""
        status_file = os.path.join(self._status_dir, f"{task.task_id}.json")
        try:
            with open(status_file, "w") as f:
                json.dump(task.to_dict(), f, indent=2)
        except IOError as e:
            logger.warning(f"保存任务状态失败，task_id: {task.task_id}, 错误: {str(e)}")

    def cancel_task(self, task_id: str) -> bool:
        """取消未开始的任务（线程安全）"""
        with self._lock:
            if task_id not in self._tasks:
                # 检查是否在活跃任务中（正在处理）
                if task_id in self._active_tasks:
                    logger.warning(f"无法取消正在处理的任务，task_id: {task_id}")
                    return False
                # 任务可能已完成或失败，无需取消
                return True
            # 从队列中移除任务
            try:
                # 由于queue.Queue不支持直接删除，需要重建队列
                temp_queue = PyQueue.Queue()
                while not self._task_queue.empty():
                    t = self._task_queue.get_nowait()
                    if t.task_id != task_id:
                        temp_queue.put(t)
                self._task_queue = temp_queue
                # 从内存中移除任务
                del self._tasks[task_id]
                # 删除状态文件（可选）
                status_file = os.path.join(self._status_dir, f"{task_id}.json")
                if os.path.exists(status_file):
                    os.remove(status_file)
                logger.info(f"任务已取消，task_id: {task_id}")
                return True
            except Exception as e:
                logger.error(f"取消任务失败，task_id: {task_id}, 错误: {str(e)}")
                return False

    def __del__(self):
        self.stop()


# 单例访问入口
def get_processing_queue(**kwargs) -> AsyncProcessingQueue:
    return AsyncProcessingQueue(**kwargs)


# 确保应用退出时优雅关闭
import atexit
atexit.register(get_processing_queue().stop)


if __name__ == "__main__":
    from app.services.file_parser import S3Config, FileProcessor

    os.environ["MINERU_TOOLS_CONFIG_JSON"] = "/Users/weizhanjun/Workspace/PythonProjects/tmp/magic-pdf.json"
    s3_config = S3Config(prefix="test5")
    processor = FileProcessor(s3_config)

    queue = AsyncProcessingQueue(max_workers=1)  # 强制单进程
    queue.start()

    task_id = queue.submit_task(processor.process, "http://localhost:9000/demo/test.pdf")
    times = 0
    while times < 10:
        status = queue.get_task_status(task_id)
        print(status)
        time.sleep(5)
        times += 1

    queue.stop()
