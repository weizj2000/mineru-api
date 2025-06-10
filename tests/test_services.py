import pytest
import os
import shutil
from unittest.mock import MagicMock, patch

from app.services.file_parser import FileParser
from app.services.storage import LocalStorageBackend, S3StorageBackend, StorageFactory


# 文件解析器测试
class TestFileParser:
    
    def setup_method(self):
        # 创建测试目录
        self.test_output_dir = "test_output"
        os.makedirs(self.test_output_dir, exist_ok=True)
        os.makedirs(os.path.join(self.test_output_dir, "images"), exist_ok=True)
        
        # 创建测试文件
        self.test_file = os.path.join(self.test_output_dir, "test.pdf")
        with open(self.test_file, "wb") as f:
            f.write(b"Test PDF content")
    
    def teardown_method(self):
        # 清理测试目录
        if os.path.exists(self.test_output_dir):
            shutil.rmtree(self.test_output_dir)
    
    @patch("app.services.file_parser.PymuDocDataset")
    @patch("app.services.file_parser.doc_analyze")
    def test_parse_file(self, mock_doc_analyze, mock_dataset):
        # 创建模拟对象
        mock_ds = MagicMock()
        mock_dataset.return_value = mock_ds
        
        # 设置模拟行为
        mock_ds.apply.return_value = mock_ds
        mock_ds.pipe_ocr_mode.return_value = mock_ds
        
        # 创建测试图片
        test_image = os.path.join(self.test_output_dir, "images", "test_image.png")
        with open(test_image, "wb") as f:
            f.write(b"Test image content")
        
        # 创建测试Markdown文件
        test_md = os.path.join(self.test_output_dir, "test.md")
        with open(test_md, "w") as f:
            f.write("# Test Markdown")
        
        # 模拟dump_md方法，创建输出文件
        def mock_dump_md(writer, filename, image_dir):
            with open(os.path.join(self.test_output_dir, filename), "w") as f:
                f.write("# Test Markdown")
        
        mock_ds.dump_md.side_effect = mock_dump_md
        
        # 创建文件解析器
        parser = FileParser(output_base_dir=self.test_output_dir)
        
        # 调用解析方法
        result = parser.parse_file(self.test_file)
        
        # 验证结果
        assert len(result) >= 1
        assert any(path.endswith(".md") for path in result)


# 存储后端测试
class TestStorageBackend:
    
    def setup_method(self):
        # 创建测试目录
        self.test_storage_dir = "test_storage"
        os.makedirs(self.test_storage_dir, exist_ok=True)
        
        # 创建测试文件
        self.test_file_content = b"Test file content"
        self.test_file_path = "test/file.txt"
    
    def teardown_method(self):
        # 清理测试目录
        if os.path.exists(self.test_storage_dir):
            shutil.rmtree(self.test_storage_dir)
    
    def test_local_storage_backend(self):
        # 创建本地存储后端
        storage = LocalStorageBackend(base_dir=self.test_storage_dir)
        
        # 测试保存文件
        saved_path = storage.save_file(self.test_file_content, self.test_file_path)
        assert os.path.exists(os.path.join(self.test_storage_dir, self.test_file_path))
        
        # 测试获取文件
        file_content = storage.get_file(self.test_file_path)
        assert file_content == self.test_file_content
        
        # 测试列出文件
        files = storage.list_files("test")
        assert self.test_file_path in files
        
        # 测试删除文件
        result = storage.delete_file(self.test_file_path)
        assert result is True
        assert not os.path.exists(os.path.join(self.test_storage_dir, self.test_file_path))
    
    @patch("boto3.client")
    def test_s3_storage_backend(self, mock_boto3_client):
        # 创建模拟S3客户端
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        
        # 模拟head_bucket方法
        mock_s3.head_bucket.return_value = {}
        
        # 模拟get_object方法
        mock_body = MagicMock()
        mock_body.read.return_value = self.test_file_content
        mock_s3.get_object.return_value = {"Body": mock_body}
        
        # 模拟list_objects_v2方法
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": self.test_file_path}
                ]
            }
        ]
        
        # 创建S3存储后端
        storage = S3StorageBackend(bucket_name="test-bucket")
        
        # 测试保存文件
        saved_path = storage.save_file(self.test_file_content, self.test_file_path)
        mock_s3.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key=self.test_file_path,
            Body=self.test_file_content
        )
        
        # 测试获取文件
        file_content = storage.get_file(self.test_file_path)
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket",
            Key=self.test_file_path
        )
        assert file_content == self.test_file_content
        
        # 测试列出文件
        files = storage.list_files("test")
        mock_s3.get_paginator.assert_called_once_with("list_objects_v2")
        assert self.test_file_path in files
        
        # 测试删除文件
        result = storage.delete_file(self.test_file_path)
        mock_s3.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key=self.test_file_path
        )
        assert result is True
    
    def test_storage_factory(self):
        # 测试创建本地存储后端
        storage = StorageFactory.create_storage("local", base_dir=self.test_storage_dir)
        assert isinstance(storage, LocalStorageBackend)
        
        # 测试创建S3存储后端
        with patch("boto3.client"):
            storage = StorageFactory.create_storage("s3", bucket_name="test-bucket")
            assert isinstance(storage, S3StorageBackend)
        
        # 测试不支持的存储类型
        with pytest.raises(ValueError):
            StorageFactory.create_storage("invalid")
