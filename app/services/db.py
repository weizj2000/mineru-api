import time
import requests
import requests
import zipfile
import io
import os

url='https://mineru.net/api/v4/file-urls/batch'
header = {
    'Content-Type':'application/json',
    "Authorization":"Bearer eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiIxMDIwNTkzMyIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc0Nzk4NTg3NywiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiZjI0ZTEwZDMtYjRmNC00OTc4LTg3YmEtYTgwMjVmYWRhNWE2IiwiZW1haWwiOiIiLCJleHAiOjE3NDkxOTU0Nzd9.bMo637LUF-dURuAUC6HjiWV_58MbTygu3uc2nQtlNumokfPcPkk12CKPKWXLXXvYM2-JcRPrztAKN6sbTGyu7Q"
}


def main(files) -> str:
    
    data = {
        "enable_formula": True,
        "enable_table": True,
        "files": [{"name": file.name, "is_ocr": True, "data_id": "abcd"} for file in files]
    }
    
    try:
        response = requests.post(url,headers=header,json=data)
        if response.status_code == 200:
            result = response.json()
            print('response success. result:{}'.format(result))
            
            if result["code"] == 0:
                batch_id = result["data"]["batch_id"]
                urls = result["data"]["file_urls"]
                print('batch_id:{},urls:{}'.format(batch_id, urls))
                
                for i in range(0, len(urls)):
                    with open(files[i].url, 'rb') as f:
                        res_upload = requests.put(urls[i], data=f)
                        if res_upload.status_code == 200:
                            print(f"{urls[i]} upload success")
                            return batch_id
                        else:
                            raise f"{urls[i]} upload failed"
            else:
                raise f'apply upload url failed,reason:{result.msg}'
        else:
            raise f'response not success. status:{response.status_code} ,result:{response}'
    except Exception as err:
        raise err


def main_1(batch_id: str):
    interval = 5
    retries = 0
    url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
    file_done = set()
    result = []
    
    while True:
        res = requests.get(url, headers=header)
        res_json = res.json()
        if res.status_code == 200 and res_json["code"] == 0:
            extract_result = res_json["data"]["extract_result"]
            for file in extract_result:
                if file["state"] == "done":
                    file_done.add(file["data_id"])
                elif file["status"] == "failed":
                    print(f"extract result failed,reason:{file['error_msg']}")
                else:
                    print(f"extract result not done,file:{file['file_name']} state:{file['state']}")
        else:
            raise f"get extract result failed,reason:{res_json}"
        
        retries += 1
        if len(result) == len(extract_result) or retries > 5: 
            break
        time.sleep(interval)

    files = res_json["data"]["extract_result"]
    for id in file_done:
        for file in files:
            if file["data_id"] == id:
                result.append({"file_name": file["file_name"], "file_url": file["full_zip_url"]})
    
    return result


from app.services.storage import StorageBackend

def download_and_extract_zip(zip_file_urls: list, storage: StorageBackend) -> str:
    """
    下载zip文件并解压，处理full.md和图片文件
    
    Args:
        zip_file_urls (list): zip文件的URL列表
        storage (StorageBackend): 存储后端实例
    
    Returns:
        str: 处理后的full.md内容（图片链接已替换为S3地址）
    """
    import uuid
    import shutil
    
    result_list = []
    for url in zip_file_urls:
        try:
            # 下载zip文件
            response = requests.get(url)
            response.raise_for_status()
            
            # 创建内存中的zip文件对象
            zip_file = zipfile.ZipFile(io.BytesIO(response.content))
            
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # 解压zip文件到临时目录
                zip_file.extractall(temp_dir)

                # 定位full.md和images目录
                full_md_path = None
                images_dir = None
                for root, dirs, files in os.walk(temp_dir):
                    if "full.md" in files:
                        full_md_path = os.path.join(root, "full.md")
                    if "images" in dirs:
                        images_dir = os.path.join(root, "images")
                # 读取full.md内容
                if full_md_path:
                    with open(full_md_path, "r", encoding="utf-8") as f:
                        content = f.read()  
                else:
                    raise FileNotFoundError("未找到full.md文件")
                
                
            
            # 解压zip文件到唯一临时目录（避免冲突）
            temp_dir = f"temp_zip_extract_{uuid.uuid4()}"
            os.makedirs(temp_dir, exist_ok=True)
            zip_file.extractall(temp_dir)
            
            # 定位full.md和images目录
            full_md_path = None
            images_dir = None
            for root, dirs, files in os.walk(temp_dir):
                if "full.md" in files:
                    full_md_path = os.path.join(root, "full.md")
                if "images" in dirs:
                    images_dir = os.path.join(root, "images")
            
            # 读取full.md内容
            if full_md_path:
                with open(full_md_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                raise FileNotFoundError("未找到full.md文件")
            
            # 提取file_name（从URL中获取文件名）
            file_name = os.path.basename(url)
            
            # 上传images目录下的图片到S3（每个zip单独处理）
            image_url_mapping = {}
            if images_dir and os.path.isdir(images_dir):
                for img_file in os.listdir(images_dir):
                    img_path = os.path.join(images_dir, img_file)
                    if os.path.isfile(img_path):
                        with open(img_path, "rb") as f:
                            img_content = f.read()
                        s3_path = f"images/{img_file}"
                        s3_url = storage.save_file(img_content, s3_path)
                        image_url_mapping[img_file] = s3_url
            
            # 替换content中的图片链接
            for img_file, s3_url in image_url_mapping.items():
                content = content.replace(f"images/{img_file}", s3_url)
            
            # 添加结果到列表
            result_list.append({"file_name": file_name, "content": content})
            
            print(f"成功处理 {url} 中的文件")
        except Exception as e:
            print(f"处理 {url} 失败: {e}")
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    return result_list
