# 文件解析服务

## 一、项目功能说明

本项目是一个基于FastAPI构建的文件解析服务，主要提供文件解析和任务状态查询的API服务。它允许用户通过两种方式提交文件解析任务：一是上传文件流，二是提交文件路径（本地、URL或S3）。系统会将这些任务放入处理队列中进行处理，并为每个任务生成唯一的任务ID。用户可以根据任务ID查询任务的状态和结果。

### 主要功能模块
1. **任务队列管理**：使用`get_processing_queue`函数初始化任务队列，支持设置最大工作线程数。队列负责接收和处理文件解析任务，确保任务按顺序执行。
2. **文件处理器**：`FileProcessor`类用于处理文件解析任务，它依赖于`S3Config`进行S3存储配置。
3. **API服务**：提供两个主要的API接口，分别用于提交文件解析任务和查询任务状态。

## 二、使用介绍

### 环境准备
确保你已经安装了以下依赖库：
- FastAPI
- Pydantic
- Uvicorn

你可以使用以下命令安装这些依赖：
```bash
pip install fastapi pydantic uvicorn
```

### 配置文件
下载模型权重
```bash
python download_model.py
```
在运行项目之前，需要设置环境变量`MINERU_TOOLS_CONFIG_JSON`，指定配置文件的路径。例如：
```bash
export MINERU_TOOLS_CONFIG_JSON=./magic-pdf.json
```

### 启动服务
在项目根目录下，运行以下命令启动FastAPI服务：
```bash
python app/main.py
```
服务将在`http://0.0.0.0:8000`上启动。

## 三、接口请求文档

### 1. 提交文件解析任务
- **接口地址**：`/api/v1/extract/task`
- **请求方法**：`POST`
- **请求参数**：支持两种请求方式，优先级为文件上传 > 文件路径。
    - **通过表单上传文件（multipart/form-data）**：使用`files`参数，类型为`List[UploadFile]`，可以上传多个文件。
    - **通过表单提交文件路径（application/x-www-form-urlencoded）**：使用`request`参数，类型为`BatchTaskSubmitRequest`，包含`file_paths`字段，为文件路径列表（本地/URL/S3）。
- **响应模型**：`TaskSubmitResponse`
    - **task_ids**：生成的任务ID列表，类型为`List[str]`。
    - **submit_time**：任务提交时间，类型为`str`。
    - **total_tasks**：总提交任务数，类型为`int`。
- **状态码**：`202 Accepted`
- **示例请求**：
    - **上传文件**：
```python
import requests

url = 'http://0.0.0.0:8000/api/v1/extract/task'
files = {'files': open('test_file.txt', 'rb')}
response = requests.post(url, files=files)
print(response.json())
```
    - **提交文件路径**：
```python
import requests
import json

url = 'http://0.0.0.0:8000/api/v1/extract/task'
payload = {'file_paths': ['https://example.com/test_file.txt']}
headers = {'Content-Type': 'application/x-www-form-urlencoded'}
response = requests.post(url, data=json.dumps(payload), headers=headers)
print(response.json())
```

### 2. 查询任务结果
- **接口地址**：`/api/v1/extract/task/{task_id}`
- **请求方法**：`GET`
- **请求参数**：
    - **task_id**：提交任务时返回的任务ID，类型为`str`。
- **响应内容**：包含任务状态和结果的字典。
```json
{
    "task_id": "your_task_id",
    "status": "TaskStatus枚举类",
    "data": {"ParserResult(BaseModel).model_dump()"},
    "error": "error | None",
    "created_at": 1625234567.89,
    "started_at": 1625234568.90,
    "completed_at": 1625234569.01
}
```
- **状态码**：
    - `200 OK`：任务ID存在，返回任务状态和结果。
    - `404 Not Found`：任务ID不存在。
- **示例请求**：
```python
import requests

url = 'http://0.0.0.0:8000/api/v1/extract/task/your_task_id'
response = requests.get(url)
print(response.json())
```
