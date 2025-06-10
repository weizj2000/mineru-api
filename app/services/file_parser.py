import json
import os
import hashlib
import requests
from typing import Union, Optional, Dict
from magic_pdf.data.data_reader_writer import S3DataReader, S3DataWriter
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.config.enums import SupportedPdfParseMethod
import re
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()


class S3Config:
    """S3存储配置类"""

    def __init__(self,
                 bucket_name: str = settings.S3_BUCKET_NAME,
                 access_key: str = settings.S3_ACCESS_KEY,
                 secret_key: str = settings.S3_SECRET_KEY,
                 endpoint_url: str = settings.S3_ENDPOINT_URL,
                 prefix: str = settings.S3_BUCKET_PREFIX):
        self.bucket_name = bucket_name
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint_url = endpoint_url
        self.prefix = prefix


class ParserResult(BaseModel):
    """解析结果类"""
    is_cache: bool = False
    content: Optional[str] = None
    status: Optional[str] = "success"
    markdown_path: Optional[str] = None
    image_dir: Optional[str] = None
    message: Optional[str] = None


class FileProcessor:
    """PDF文件处理核心类"""

    def __init__(self, s3_config: S3Config):
        self.config = s3_config
        # self._storage = StorageFactory.create_storage(
        #     "s3",
        #     bucket_name=s3_config.bucket_name,
        #     aws_access_key_id=s3_config.access_key,
        #     aws_secret_access_key=s3_config.secret_key,
        #     endpoint_url=s3_config.endpoint_url
        # )

    def _get_storage(self):
        """动态创建S3存储客户端（每次调用时创建）"""
        from app.services.storage import StorageFactory
        return StorageFactory.create_storage(
            "s3",
            bucket_name=self.config.bucket_name,
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
            endpoint_url=self.config.endpoint_url
        )

    def _get_s3_reader(self) -> S3DataReader:
        """内部方法：获取S3数据读取器"""
        return S3DataReader(
            self.config.prefix,
            self.config.bucket_name,
            self.config.access_key,
            self.config.secret_key,
            self.config.endpoint_url
        )

    def _get_s3_writer(self, sub_dir: Optional[str] = None) -> S3DataWriter:
        """内部方法：获取S3数据写入器（支持子目录）"""
        full_prefix = os.path.join(self.config.prefix, sub_dir) if sub_dir else self.config.prefix
        return S3DataWriter(
            full_prefix,
            self.config.bucket_name,
            self.config.access_key,
            self.config.secret_key,
            self.config.endpoint_url
        )

    def _replace_image_urls(self, md_content: str, md5_hash: str) -> str:
        """内部方法：替换Markdown中的图片URL为完整S3路径"""
        pattern = r"!\[(.*?)\]\((.*?)\)"
        s3_image_prefix = os.path.join(
            self.config.endpoint_url,
            self.config.bucket_name,
            self.config.prefix,
            md5_hash
        ).replace("\\", "/")  # 统一路径分隔符

        def replacer(match):
            alt_text = match.group(1)
            rel_path = match.group(2)
            full_path = f"{s3_image_prefix}/{rel_path}".replace("\\", "/")
            return f"![{alt_text}]({full_path})"

        return re.sub(pattern, replacer, md_content)

    def _validate_and_get_file_bytes(self, input_source: Union[str, bytes]) -> tuple[bytes, str]:
        """内部方法：验证输入源并获取文件字节数据"""
        try:
            if isinstance(input_source, bytes):
                return input_source, "input.pdf"

            if input_source.startswith("s3://"):
                reader = self._get_s3_reader()
                return reader.read(input_source), os.path.basename(input_source)

            if input_source.startswith(("http://", "https://")):
                response = requests.get(input_source)
                response.raise_for_status()
                return response.content, os.path.basename(input_source)

            if os.path.exists(input_source):
                with open(input_source, "rb") as f:
                    return f.read(), os.path.basename(input_source)

            raise ValueError(f"输入类型不支持或文件不存在: {input_source}")

        except Exception as e:
            raise RuntimeError(f"获取文件数据失败：{str(e)}")

    def _check_result_exists(self, md5_hash: str) -> bool:
        """内部方法：检查S3中是否已存在处理结果"""
        check_path = f"{self.config.prefix}/{md5_hash}/full.md"
        storage = self._get_storage()
        try:
            return storage.exist_file(check_path)
        except Exception as e:
            print(f"检查文件是否存在时出错：{str(e)}")
            return False

    def process(self, input_source: Union[str, bytes], image_dir: str = "images") -> ParserResult:
        """
        完整处理PDF文件并生成带完整图片URL的Markdown
        :param input_source: 输入源（s3路径、本地路径、url、bytes）
        :param image_dir: 图片存储子目录
        :return: 处理结果字典（包含md5、markdown内容等）
        """
        try:
            # 1. 获取文件字节数据和文件名
            file_bytes, file_name = self._validate_and_get_file_bytes(input_source)
            md5_hash = hashlib.md5(file_bytes).hexdigest()
            # name_without_suff = os.path.splitext(file_name)[0]

            # 2. 检查结果是否已存在
            if self._check_result_exists(md5_hash):
                storage = self._get_storage()
                return ParserResult(
                    is_cache=True,
                    content=storage.get_file(f"{self.config.prefix}/{md5_hash}/full.md"),
                    markdown_path=f"s3://{self.config.bucket_name}/{self.config.prefix}/{md5_hash}/full.md",
                    image_dir=f"s3://{self.config.bucket_name}/{self.config.prefix}/{md5_hash}/{image_dir}"
                )

            # 3. 初始化写入器
            image_writer = self._get_s3_writer(sub_dir=f"{md5_hash}/{image_dir}")
            md_writer = self._get_s3_writer(sub_dir=md5_hash)

            # 4. 处理PDF文件
            ds = PymuDocDataset(file_bytes)
            if ds.classify() == SupportedPdfParseMethod.OCR:
                infer_result = ds.apply(doc_analyze, ocr=True)
                pipe_result = infer_result.pipe_ocr_mode(image_writer)
            else:
                infer_result = ds.apply(doc_analyze, ocr=False)
                pipe_result = infer_result.pipe_txt_mode(image_writer)

            # 5. 生成并保存Markdown
            original_md = pipe_result.get_markdown(image_dir)
            processed_md = self._replace_image_urls(original_md, md5_hash)
            md_writer.write("full.md", processed_md.encode("utf-8"))

            return ParserResult(
                status="success",
                is_cache=False,
                markdown_path=f"s3://{self.config.bucket_name}/{self.config.prefix}/{md5_hash}/full.md",
                image_dir=f"s3://{self.config.bucket_name}/{self.config.prefix}/{md5_hash}/{image_dir}",
                content=processed_md
            )

        except Exception as e:
            return ParserResult(
                status="error",
                message=f"处理PDF时发生错误：{str(e)}"
            )


if __name__ == "__main__":
    s3_config = S3Config(prefix="test5")
    processor = FileProcessor(s3_config)

    result = processor.process("http://localhost:9000/demo/test.pdf")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=4))
