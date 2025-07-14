import os
import requests
import hashlib
import json
import argparse
from datetime import datetime

# 城通网盘 API 配置
API_URL = "https://rest.ctfile.com/v1"
UPLOAD_URL = f"{API_URL}/public/file/upload"
GET_SHARE_URL = f"{API_URL}/public/file/share"
CREATE_FOLDER_URL = f"{API_URL}/public/folder/create"

# 计算文件的 checksum 和 size
def calculate_checksum(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

# 创建文件夹
def create_folder(session, parent_folder_id, folder_name):
    try:
        response = requests.post(
            CREATE_FOLDER_URL,
            json={
                "session": session,
                "folder_id": parent_folder_id,
                "name": folder_name,
            },
        )
        response.raise_for_status()
        folder_data = response.json()
        if folder_data.status_code == 200:
            return folder_data["folder_id"]
        else:
            print(f"Failed to create folder {folder_name}: {folder_data}")
    except requests.RequestException as e:
        print(f"Failed to create folder {folder_name}: {e}")
    return None

# 上传文件并获取直链
def upload_file(session, folder_id, file_path):
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    checksum = calculate_checksum(file_path)

    # 获取上传 URL
    try:
        response = requests.post(
            UPLOAD_URL,
            json={
                "session": session,
                "folder_id": folder_id,
                "checksum": checksum,
                "size": file_size,
                "name": file_name,
            },
        )
        response.raise_for_status()
        upload_data = response.json()
        if upload_data.status_code == 200:
            upload_url = upload_data["upload_url"]
            # 上传文件
            with open(file_path, "rb") as f:
                upload_response = requests.post(
                    upload_url,
                    files={"file": (file_name, f)},
                    data={"filesize": file_size, "name": file_name},
                )
                upload_response.raise_for_status()
                if upload_response.status_code == 200:
                    print(f"File {file_name} uploaded successfully.")
                    return upload_data["file_id"]
                else:
                    print(f"Failed to upload {file_name}: {upload_response.json()}")
        else:
            print(f"Failed to get upload URL for {file_name}: {upload_data}")
    except requests.RequestException as e:
        print(f"Failed to upload {file_name}: {e}")
    return None

# 获取文件分享链接
def get_share_url(session, file_id):
    try:
        response = requests.post(
            GET_SHARE_URL,
            json={
                "session": session,
                "ids": [file_id],
            },
        )
        response.raise_for_status()
        share_data = response.json()
        if share_data.status_code == 200:
            return share_data["results"][0]["directlink"]
        else:
            print(f"Failed to get share URL for file {file_id}: {share_data}")
    except requests.RequestException as e:
        print(f"Failed to get share URL for file {file_id}: {e}")
    return None

# 主程序
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Upload .iso files to CTFile and get share links.")
    parser.add_argument("session", help="User session token for CTFile.")
    args = parser.parse_args()

    session = args.session
    parent_folder_id = "d69010315"  # Debian 文件夹 ID

    # 创建子文件夹
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    folder_name = f"debian-{timestamp}"
    new_folder_id = create_folder(session, parent_folder_id, folder_name)
    if not new_folder_id:
        print("Failed to create the folder. Exiting.")
        sys.exit(1)

    print(f"Created folder: {folder_name} with ID: {new_folder_id}")

    # 获取当前目录下的所有.iso文件
    iso_files = [f for f in os.listdir(".") if f.endswith(".iso")]

    if not iso_files:
        print("No .iso files found in the current directory.")
        sys.exit(0)

    share_urls = []
    for iso_file in iso_files:
        file_id = upload_file(session, new_folder_id, iso_file)
        if file_id:
            share_url = get_share_url(session, file_id)
            if share_url:
                share_urls.append(share_url)
                print(f"Share URL for {iso_file}: {share_url}")

    # 输出所有分享链接到 GITHUB_OUTPUT（如果在 GitHub Actions 环境中）
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            for url in share_urls:
                f.write(f"share_url={url}\n")
