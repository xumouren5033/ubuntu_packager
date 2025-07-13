#!/usr/bin/env python3
import os
import sys
import datetime
import requests
from cpan123 import File, Share, Auth

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

    # -------------- 初始化客户端 --------------
    auth = Auth(access_key=access_key, secret_key=secret_key)
    file_client = File(auth=auth)
    share_client = Share(auth=auth)

    # -------------- 创建目录 --------------
    try:
        resp = file_client.mkdir(name=dir_name, parentID=0)
        dir_id = resp["data"]["file_id"]
        print(f"[✓] Directory '{dir_name}' created (ID: {dir_id})")
    except Exception as e:
        print(f"[✗] mkdir failed: {e}")
        sys.exit(1)

    # -------------- 上传 ISO 文件 --------------
    iso_files = [f for f in os.listdir(".") if f.lower().endswith(".iso")]
    if not iso_files:
        print("[!] No .iso files found in current directory")
        sys.exit(0)

    file_ids = []
    for iso in iso_files:
        iso_path = os.path.join(".", iso)
        size = os.path.getsize(iso_path)
        etag = file_client.calculate_md5(iso_path)

        try:
            # 1. 创建上传任务
            task = file_client.create(
                parentFileID=dir_id,
                filename=iso,
                size=size,
                etag=etag
            )
            preupload_id = task["data"]["preupload_id"]

            # 2. 获取上传 URL
            url_resp = file_client.get_upload_url(preuploadID=preupload_id, sliceNo=1)
            upload_url = url_resp["data"]["upload_url"]

            # 3. 上传文件内容
            with open(iso_path, "rb") as f:
                up_resp = requests.put(upload_url, data=f)
                if up_resp.status_code != 200:
                    raise Exception(f"Upload HTTP {up_resp.status_code}")

            # 4. 完成上传
            file_client.upload_complete(preuploadID=preupload_id)
            file_ids.append(task["data"]["file_id"])
            print(f"[✓] Uploaded {iso}")
        except Exception as e:
            print(f"[✗] Upload failed for {iso}: {e}")
            sys.exit(1)

    # -------------- 创建永久分享 --------------
    try:
        share_resp = share_client.create_free(
            shareName=dir_name,
            shareExpire=0,  # 0 表示永久
            fileIDList=",".join(map(str, file_ids))
        )
        share_url = share_resp["data"]["share_url"]
        print(f"[✓] Share created: {share_url}")

        # 写入 GitHub Actions 输出
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as gh_out:
                gh_out.write(f"share_url={share_url}\n")
    except Exception as e:
        print(f"[✗] Share failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
