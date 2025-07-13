#!/usr/bin/env python3
import os
import sys
import re
import time
import json
import hmac
import hashlib
import datetime
import requests
from urllib.parse import urlencode

# 官方API基础配置
API_DOMAIN = "https://open-api.123pan.com"
TOKEN_URL = f"{API_DOMAIN}/api/v1/auth/token"  # 获取token接口（假设路径）
FILE_UPLOAD_V2_PREFIX = "/api/v2/file"  # 上传文件v2接口前缀
SHARE_V1_PREFIX = "/api/v1/share"       # 分享接口v1前缀

def get_access_token(access_key, secret_key):
    """获取访问令牌（Authorization所需的token）"""
    timestamp = int(time.time() * 1000)
    nonce = int(time.time() * 1000000)
    
    # 生成签名（参考官方鉴权规则）
    sign_str = f"accessKey={access_key}&nonce={nonce}&timestamp={timestamp}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest().upper()
    
    try:
        resp = requests.post(
            TOKEN_URL,
            headers={
                "Content-Type": "application/json",
                "Platform": "open_platform"
            },
            json={
                "accessKey": access_key,
                "secretKey": secret_key,
                "timestamp": timestamp,
                "nonce": nonce,
                "signature": signature
            },
            timeout=30
        )
        resp_json = resp.json()
        if resp_json.get("code") != 0:
            raise Exception(f"获取token失败: {resp_json.get('message')}")
        return resp_json["data"]["access_token"]  # 假设返回结构包含access_token
    except Exception as e:
        raise Exception(f"token请求失败: {str(e)}")

def api_request(token, method, path, params=None, data=None, is_v2=False):
    """通用API请求函数（区分v1/v2接口）"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Platform": "open_platform"
    }
    
    # 拼接完整URL（v2接口使用单独前缀）
    full_path = f"{FILE_UPLOAD_V2_PREFIX}{path}" if is_v2 else f"{SHARE_V1_PREFIX}{path}"
    url = f"{API_DOMAIN}{full_path}"
    
    if params:
        url += "?" + urlencode(params)
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            raise ValueError(f"不支持的方法: {method}")
        
        resp_json = resp.json()
        if resp_json.get("code") != 0:
            raise Exception(f"接口错误({path}): {resp_json.get('message')}")
        return resp_json
    except Exception as e:
        raise Exception(f"请求失败({url}): {str(e)}")

def main() -> None:
    # 参数解析
    if len(sys.argv) < 5 and sys.argv[3] == "manual":
        print("Usage: python upload.py <access_key> <secret_key> <mode> <build_number>")
        sys.exit(1)
    access_key = sys.argv[1]
    secret_key = sys.argv[2]
    mode = sys.argv[3]
    build_number = sys.argv[4] if mode == "manual" else ""

    # 生成目录名
    if mode == "scheduled":
        dir_name = f"debian-{datetime.datetime.now().strftime('%Y-%m-%d')}"
    elif mode == "manual":
        dir_name = f"debian-custom-{build_number}"
    else:
        print("模式错误，使用 'scheduled' 或 'manual'")
        sys.exit(1)

    # 获取访问token
    try:
        token = get_access_token(access_key, secret_key)
        print(f"[✓] 已获取token: {token[:10]}...")
    except Exception as e:
        print(f"[✗] token获取失败: {e}")
        sys.exit(1)

    # 创建目录（使用v2接口）
    dir_id = None
    try:
        # 检查目录是否存在（v2文件列表接口）
        list_resp = api_request(
            token,
            "GET",
            "/list",  # 完整路径为 /api/v2/file/list
            params={"parent_file_id": 0, "keyword": dir_name, "search_mode": 1},
            is_v2=True
        )
        if list_resp["data"]["files"]:
            dir_id = list_resp["data"]["files"][0]["file_id"]
            print(f"[!] 目录 '{dir_name}' 已存在 (ID: {dir_id})")
        else:
            # 创建目录（v2创建目录接口）
            mkdir_resp = api_request(
                token,
                "POST",
                "/create",  # 完整路径为 /api/v2/file/create
                data={
                    "parent_file_id": 0,
                    "name": dir_name,
                    "type": "directory"
                },
                is_v2=True
            )
            dir_id = mkdir_resp["data"]["file_id"]
            print(f"[✓] 目录 '{dir_name}' 创建成功 (ID: {dir_id})")
    except Exception as e:
        print(f"[✗] 目录操作失败: {e}")
        sys.exit(1)

    # 上传ISO文件（使用v2接口）
    iso_files = [f for f in os.listdir(".") if f.lower().endswith(".iso")]
    if not iso_files:
        print("[!] 未找到ISO文件")
        sys.exit(0)

    file_ids = []
    MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB
    for iso in iso_files:
        iso_path = os.path.join(".", iso)
        size = os.path.getsize(iso_path)
        
        # 校验文件名和大小
        if len(iso) > 255 or re.search(r'[\\/*?:"<>|]', iso):
            print(f"[✗] 文件名 '{iso}' 无效")
            sys.exit(1)
        if size > MAX_FILE_SIZE:
            print(f"[✗] 文件 '{iso}' 超过10GB限制")
            sys.exit(1)

        try:
            # 计算MD5
            md5_hash = hashlib.md5()
            with open(iso_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            etag = md5_hash.hexdigest()

            # 创建上传任务（v2接口）
            create_resp = api_request(
                token,
                "POST",
                "/create_upload_task",  # 完整路径 /api/v2/file/create_upload_task
                data={
                    "parent_file_id": dir_id,
                    "file_name": iso,
                    "file_size": size,
                    "etag": etag,
                    "duplicate_strategy": 1
                },
                is_v2=True
            )
            preupload_id = create_resp["data"]["preupload_id"]
            print(f"[*] 已创建上传任务: {preupload_id}")

            # 分片上传（v2接口）
            slice_size = 5 * 1024 * 1024
            slice_count = (size + slice_size - 1) // slice_size
            for slice_no in range(1, slice_count + 1):
                url_resp = api_request(
                    token,
                    "GET",
                    "/get_upload_url",  # 完整路径 /api/v2/file/get_upload_url
                    params={"preupload_id": preupload_id, "slice_no": slice_no},
                    is_v2=True
                )
                upload_url = url_resp["data"]["upload_url"]

                with open(iso_path, "rb") as f:
                    f.seek((slice_no - 1) * slice_size)
                    chunk = f.read(slice_size)
                    put_resp = requests.put(upload_url, data=chunk, timeout=60)
                    if put_resp.status_code != 200:
                        raise Exception(f"分片 {slice_no} 上传失败")
                print(f"[*] 分片 {slice_no}/{slice_count} 上传完成")

            # 完成上传（v2接口）
            api_request(
                token,
                "POST",
                "/complete_upload",  # 完整路径 /api/v2/file/complete_upload
                data={"preupload_id": preupload_id},
                is_v2=True
            )

            # 获取文件ID
            result_resp = api_request(
                token,
                "GET",
                "/get_upload_result",  # 完整路径 /api/v2/file/get_upload_result
                params={"preupload_id": preupload_id},
                is_v2=True
            )
            file_id = result_resp["data"]["file_id"]
            file_ids.append(str(file_id))
            print(f"[✓] 文件 '{iso}' 上传成功 (ID: {file_id})")
        except Exception as e:
            print(f"[✗] 文件 '{iso}' 上传失败: {e}")
            sys.exit(1)

    # 创建分享链接（使用v1接口，严格遵循官方文档）
    try:
        share_resp = api_request(
            token,
            "POST",
            "/create",  # 完整路径 /api/v1/share/create（与官方文档一致）
            data={
                "shareName": dir_name,
                "shareExpire": 0,  # 永久有效
                "fileIDList": ",".join(file_ids),
                # 可选参数
                # "sharePwd": "123456",
                # "trafficSwitch": 2,
                # "trafficLimitSwitch": 2,
                # "trafficLimit": 100*1024*1024
            },
            is_v2=False  # 分享使用v1
        )
        share_key = share_resp["data"]["shareKey"]
        share_url = f"https://www.123pan.com/s/{share_key}"
        print(f"[✓] 分享链接创建成功: {share_url}")

        # 写入GitHub Actions输出
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"share_url={share_url}\n")
    except Exception as e:
        print(f"[✗] 分享创建失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
