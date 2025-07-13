#!/usr/bin/env python3
import os
import sys
import re
import time
import hmac
import hashlib
import json
import datetime
import requests
from urllib.parse import urlencode

# 官方API基础配置
API_BASE_URL = "https://openapi.123pan.com"
API_VERSION = "v1"

def generate_signature(access_key, secret_key, timestamp, nonce):
    """生成签名（参考官方鉴权规范）"""
    sign_str = f"accessKey={access_key}&nonce={nonce}&timestamp={timestamp}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest().upper()
    return signature

def api_request(access_key, secret_key, method, path, params=None, data=None):
    """通用API请求函数"""
    timestamp = int(time.time() * 1000)
    nonce = int(time.time() * 1000000)  # 随机数
    signature = generate_signature(access_key, secret_key, timestamp, nonce)
    
    headers = {
        "Content-Type": "application/json",
        "X-Access-Key": access_key,
        "X-Timestamp": str(timestamp),
        "X-Nonce": str(nonce),
        "X-Signature": signature
    }
    
    url = f"{API_BASE_URL}/{API_VERSION}/{path}"
    if params:
        url += "?" + urlencode(params)
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        resp_json = resp.json()
        if resp_json.get("code") != 0:
            raise Exception(f"API error: {resp_json.get('message')}")
        return resp_json
    except Exception as e:
        raise Exception(f"Request failed: {str(e)}")

def main() -> None:
    # -------------- 参数解析 --------------
    if len(sys.argv) < 4:
        print("Usage: python upload.py <access_key> <secret_key> <mode> [build_number]")
        sys.exit(1)

    access_key = sys.argv[1]
    secret_key = sys.argv[2]
    mode = sys.argv[3]

    # -------------- 目录名生成 --------------
    if mode == "scheduled":
        dir_name = f"debian-{datetime.datetime.now().strftime('%Y-%m-%d')}"
    elif mode == "manual":
        build_number = sys.argv[4] if len(sys.argv) >= 5 else "0"
        dir_name = f"debian-custom-{build_number}"
    else:
        print("Invalid mode. Use 'scheduled' or 'manual'.")
        sys.exit(1)

    # -------------- 创建目录 --------------
    dir_id = None
    try:
        # 检查目录是否已存在
        list_resp = api_request(
            access_key, secret_key,
            "GET",
            "file/list",
            params={"parent_file_id": 0, "keyword": dir_name, "search_mode": 1}
        )
        if list_resp["data"]["files"]:
            dir_id = list_resp["data"]["files"][0]["file_id"]
            print(f"[!] Directory '{dir_name}' already exists (ID: {dir_id})")
        else:
            # 创建新目录
            mkdir_resp = api_request(
                access_key, secret_key,
                "POST",
                "file/create_directory",
                data={"parent_file_id": 0, "name": dir_name}
            )
            dir_id = mkdir_resp["data"]["file_id"]
            print(f"[✓] Directory '{dir_name}' created (ID: {dir_id})")
    except Exception as e:
        print(f"[✗] Directory operation failed: {e}")
        sys.exit(1)

    # -------------- 上传ISO文件 --------------
    iso_files = [f for f in os.listdir(".") if f.lower().endswith(".iso")]
    if not iso_files:
        print("[!] No .iso files found in current directory")
        sys.exit(0)

    MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB
    file_ids = []

    for iso in iso_files:
        iso_path = os.path.join(".", iso)
        size = os.path.getsize(iso_path)
        
        # 文件名与大小校验
        if len(iso) > 255 or re.search(r'[\\/*?:"<>|]', iso):
            print(f"[✗] Invalid filename '{iso}'")
            sys.exit(1)
        if size > MAX_FILE_SIZE:
            print(f"[✗] File '{iso}' exceeds 10GB limit")
            sys.exit(1)

        try:
            # 1. 计算文件MD5
            md5_hash = hashlib.md5()
            with open(iso_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            etag = md5_hash.hexdigest()

            # 2. 创建上传任务
            create_resp = api_request(
                access_key, secret_key,
                "POST",
                "file/create_upload_task",
                data={
                    "parent_file_id": dir_id,
                    "file_name": iso,
                    "file_size": size,
                    "etag": etag,
                    "duplicate_strategy": 1  # 保留重复文件
                }
            )
            preupload_id = create_resp["data"]["preupload_id"]
            print(f"[*] Created upload task for {iso} (preupload_id: {preupload_id})")

            # 3. 获取上传地址（分片上传）
            slice_size = 5 * 1024 * 1024  # 5MB/分片
            slice_count = (size + slice_size - 1) // slice_size

            for slice_no in range(1, slice_count + 1):
                upload_url_resp = api_request(
                    access_key, secret_key,
                    "GET",
                    "file/get_upload_url",
                    params={"preupload_id": preupload_id, "slice_no": slice_no}
                )
                upload_url = upload_url_resp["data"]["upload_url"]

                # 上传分片
                with open(iso_path, "rb") as f:
                    f.seek((slice_no - 1) * slice_size)
                    chunk_data = f.read(slice_size)
                    put_resp = requests.put(upload_url, data=chunk_data, timeout=60)
                    if put_resp.status_code != 200:
                        raise Exception(f"Slice {slice_no} upload failed (HTTP {put_resp.status_code})")
                print(f"[*] Uploaded slice {slice_no}/{slice_count} for {iso}")

            # 4. 完成上传
            complete_resp = api_request(
                access_key, secret_key,
                "POST",
                "file/complete_upload",
                data={"preupload_id": preupload_id}
            )

            # 5. 轮询上传结果
            file_id = None
            for _ in range(30):  # 最多轮询30次（60秒）
                result_resp = api_request(
                    access_key, secret_key,
                    "GET",
                    "file/get_upload_result",
                    params={"preupload_id": preupload_id}
                )
                if result_resp["data"]["status"] == "completed":
                    file_id = result_resp["data"]["file_id"]
                    break
                elif result_resp["data"]["status"] == "failed":
                    raise Exception("Upload failed")
                time.sleep(2)

            if not file_id:
                raise Exception("Upload timed out")
            
            file_ids.append(file_id)
            print(f"[✓] Uploaded {iso} (ID: {file_id})")

        except Exception as e:
            print(f"[✗] Upload failed for {iso}: {e}")
            sys.exit(1)

    # -------------- 创建永久分享 --------------
    try:
        share_resp = api_request(
            access_key, secret_key,
            "POST",
            "share/create",
            data={
                "share_name": dir_name,
                "file_id_list": file_ids,
                "expire_days": 0,  # 0表示永久
                # 可选：添加提取码
                # "password": "123456",
                # 可选：流量限制
                # "traffic_limit_switch": 1,
                # "traffic_limit": 100 * 1024 * 1024  # 100MB
            }
        )
        share_url = share_resp["data"]["share_url"]
        share_id = share_resp["data"]["share_id"]
        print(f"[✓] Share created (ID: {share_id}): {share_url}")

        # 写入GitHub Actions输出
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as gh_out:
                gh_out.write(f"share_url={share_url}\n")
                gh_out.write(f"share_id={share_id}\n")

    except Exception as e:
        print(f"[✗] Share failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
