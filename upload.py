import os
import sys
import datetime
from cpan123 import Pan123, File, Share

def main():
    # 检查命令行参数
    if len(sys.argv) < 4:
        print("Usage: python upload_and_share.py <access_key> <secret_key> <mode> [build_number]")
        sys.exit(1)

    # 获取命令行传入的机密信息
    access_key = sys.argv[1]
    secret_key = sys.argv[2]
    mode = sys.argv[3]

    # 初始化 123 云盘客户端
    pan = Pan123(access_key=access_key, secret_key=secret_key)
    file_client = File(auth=pan.auth)
    share_client = Share(auth=pan.auth)

    if mode == "scheduled":
        # 定时任务：使用日期作为目录名
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        target_dir_name = f"debian-{today}"
    elif mode == "manual":
        # 手动触发任务：使用构建次数作为目录名
        build_number = sys.argv[4]  # 获取构建次数
        target_dir_name = f"debian-custom-{build_number}"
    else:
        print("Invalid mode. Use 'scheduled' or 'manual'.")
        sys.exit(1)

    # 创建目标目录
    try:
        root_dir_id = 0  # 根目录 ID
        target_dir_info = file_client.mkdir(name=target_dir_name, parentID=root_dir_id)
        target_dir_id = target_dir_info['data']['file_id']
        print(f"Directory '{target_dir_name}' created successfully.")
    except Exception as e:
        print(f"Failed to create directory '{target_dir_name}': {e}")
        sys.exit(1)

    # 上传 /live-build/ 下的所有 ISO 文件
    source_dir = "/live-build/"
    file_ids = []  # 用于存储上传文件的 ID
    for filename in os.listdir(source_dir):
        if filename.endswith(".iso"):
            source_path = os.path.join(source_dir, filename)
            try:
                # 创建文件上传任务
                upload_task = file_client.create(
                    parentFileID=target_dir_id,
                    filename=filename,
                    size=os.path.getsize(source_path),
                    etag=file_client.calculate_md5(source_path)
                )
                preupload_id = upload_task['data']['preupload_id']

                # 获取上传 URL
                upload_url = file_client.get_upload_url(preuploadID=preupload_id, sliceNo=1)

                # 上传文件
                with open(source_path, 'rb') as f:
                    response = requests.put(upload_url['data']['upload_url'], data=f)
                    if response.status_code != 200:
                        raise Exception(f"Failed to upload file '{filename}': {response.text}")

                # 完成上传
                file_client.upload_complete(preuploadID=preupload_id)
                file_ids.append(upload_task['data']['file_id'])
                print(f"File '{filename}' uploaded successfully.")
            except Exception as e:
                print(f"Failed to upload file '{filename}': {e}")

    # 分享目标目录，永久分享
    try:
        share_info = share_client.create_free(
            shareName=target_dir_name,
            shareExpire=0,  # 设置为 0 表示永久分享
            fileIDList=",".join(map(str, file_ids))
        )
        share_url = share_info['data']['share_url']
        print(f"Directory '{target_dir_name}' shared successfully.")
        print(f"Share URL: {share_url}")
        # 将分享链接输出到环境变量，供 GitHub Actions 使用
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"share_url={share_url}\n")
    except Exception as e:
        print(f"Failed to share directory '{target_dir_name}': {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()