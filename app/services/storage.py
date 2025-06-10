import os
import shutil
from abc import ABC, abstractmethod
from typing import List, BinaryIO, Optional

import boto3
from botocore.exceptions import ClientError


class StorageBackend(ABC):
    """存储后端的抽象基类，定义了存储接口"""
    
    @abstractmethod
    def save_file(self, file_content: bytes, file_path: str) -> str:
        """
        保存文件到存储后端
        
        Args:
            file_content: 文件内容
            file_path: 文件路径
            
        Returns:
            str: 保存后的文件路径
        """
        pass
    
    @abstractmethod
    def get_file(self, file_path: str) -> bytes:
        """
        从存储后端获取文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            bytes: 文件内容
        """
        pass

    @abstractmethod
    def exist_file(self, file_path: str) -> bool:
        pass
    
    @abstractmethod
    def delete_file(self, file_path: str) -> bool:
        """
        从存储后端删除文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否删除成功
        """
        pass
    
    @abstractmethod
    def list_files(self, directory: str) -> List[str]:
        """
        列出存储后端中指定目录下的所有文件
        
        Args:
            directory: 目录路径
            
        Returns:
            List[str]: 文件路径列表
        """
        pass


class LocalStorageBackend(StorageBackend):
    """本地文件系统存储后端"""
    
    def __init__(self, base_dir: str = "storage"):
        """
        初始化本地存储后端
        
        Args:
            base_dir: 基础目录
        """
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
    
    def save_file(self, file_content: bytes, file_path: str) -> str:
        """
        保存文件到本地文件系统
        
        Args:
            file_content: 文件内容
            file_path: 文件路径（相对于base_dir）
            
        Returns:
            str: 保存后的文件完整路径
        """
        full_path = os.path.join(self.base_dir, file_path)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # 写入文件
        with open(full_path, 'wb') as f:
            f.write(file_content)
        
        return full_path

    def exist_file(self, file_path: str) -> bool:
        """
        判断文件是否存在

        Args:
            file_path: 文件路径（相对于base_dir）

        Returns:
            bool: 文件是否存在
        """
        full_path = os.path.join(self.base_dir, file_path)
        return os.path.exists(full_path)
    
    def get_file(self, file_path: str) -> bytes:
        """
        从本地文件系统获取文件
        
        Args:
            file_path: 文件路径（相对于base_dir）
            
        Returns:
            bytes: 文件内容
        """
        full_path = os.path.join(self.base_dir, file_path)
        
        with open(full_path, 'rb') as f:
            return f.read()
    
    def delete_file(self, file_path: str) -> bool:
        """
        从本地文件系统删除文件
        
        Args:
            file_path: 文件路径（相对于base_dir）
            
        Returns:
            bool: 是否删除成功
        """
        full_path = os.path.join(self.base_dir, file_path)
        
        try:
            os.remove(full_path)
            return True
        except (FileNotFoundError, PermissionError):
            return False
    
    def list_files(self, directory: str) -> List[str]:
        """
        列出本地文件系统中指定目录下的所有文件
        
        Args:
            directory: 目录路径（相对于base_dir）
            
        Returns:
            List[str]: 文件路径列表（相对于base_dir）
        """
        full_dir_path = os.path.join(self.base_dir, directory)
        
        if not os.path.exists(full_dir_path):
            return []
        
        result = []
        for root, _, files in os.walk(full_dir_path):
            for file in files:
                full_file_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_file_path, self.base_dir)
                result.append(rel_path)
        
        return result


class S3StorageBackend(StorageBackend):
    """Amazon S3存储后端"""
    
    def __init__(self, bucket_name: str,
                 aws_access_key_id: Optional[str] = None,
                 aws_secret_access_key: Optional[str] = None,
                 endpoint_url: Optional[str] = None,
                 region_name: Optional[str] = None):
        """
        初始化S3存储后端
        
        Args:
            bucket_name: S3桶名称
            aws_access_key_id: AWS访问密钥ID（可选，如果不提供则使用环境变量或IAM角色）
            aws_secret_access_key: AWS秘密访问密钥（可选，如果不提供则使用环境变量或IAM角色）
            region_name: AWS区域名称（可选，如果不提供则使用环境变量或默认区域）
        """
        self.bucket_name = bucket_name
        
        # 初始化S3客户端
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
            endpoint_url=endpoint_url
        )
        
        # 确保桶存在
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == '404':
                # 桶不存在，创建它
                self.s3_client.create_bucket(Bucket=self.bucket_name)
            else:
                # 其他错误，抛出异常
                raise e
    
    def save_file(self, file_content: bytes, file_path: str) -> str:
        """
        保存文件到S3
        
        Args:
            file_content: 文件内容
            file_path: S3中的文件路径（键）
            
        Returns:
            str: 保存后的文件路径（键）
        """
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=file_path,
            Body=file_content
        )
        
        return file_path

    def exist_file(self, file_path: str) -> bool:
        """
        检查文件是否存在

        Args:
            file_path: S3中的文件路径（键）

        Returns:
            bool: 文件是否存在
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=file_path)
            return True
        except Exception as e:
            print(f"发生未知错误: {e}")
            return False
        
    def get_file(self, file_path: str) -> bytes:
        """
        从S3获取文件
        
        Args:
            file_path: S3中的文件路径（键）
            
        Returns:
            bytes: 文件内容
        """
        response = self.s3_client.get_object(
            Bucket=self.bucket_name,
            Key=file_path
        )
        
        return response['Body'].read()
    
    def delete_file(self, file_path: str) -> bool:
        """
        从S3删除文件
        
        Args:
            file_path: S3中的文件路径（键）
            
        Returns:
            bool: 是否删除成功
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            return True
        except ClientError:
            return False
    
    def list_files(self, directory: str) -> List[str]:
        """
        列出S3中指定目录下的所有文件
        
        Args:
            directory: 目录路径（S3前缀）
            
        Returns:
            List[str]: 文件路径列表（键）
        """
        # 确保目录以/结尾
        if directory and not directory.endswith('/'):
            directory += '/'
        
        result = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=directory):
            if 'Contents' in page:
                for obj in page['Contents']:
                    result.append(obj['Key'])
        
        return result


class StorageFactory:
    """存储后端工厂，用于创建不同类型的存储后端"""
    
    @staticmethod
    def create_storage(storage_type: str, **kwargs) -> StorageBackend:
        """
        创建存储后端
        
        Args:
            storage_type: 存储类型，'local'或's3'
            **kwargs: 传递给存储后端构造函数的参数
            
        Returns:
            StorageBackend: 存储后端实例
        """
        if storage_type.lower() == 'local':
            return LocalStorageBackend(**kwargs)
        elif storage_type.lower() == 's3':
            return S3StorageBackend(**kwargs)
        else:
            raise ValueError(f"不支持的存储类型: {storage_type}")
