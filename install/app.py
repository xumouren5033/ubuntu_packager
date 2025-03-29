from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit
import os
import subprocess
import threading
import time
import py7zr  # 引入 7z 模块

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# 设置上传文件的保存路径
UPLOAD_FOLDER = '/mnt/ext4_partition/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    disks = get_sd_disks()
    return render_template('index.html', disks=disks)

@app.route('/partition_and_upload', methods=['POST'])
def partition_and_upload():
    disk = request.form.get('disk')
    if not disk:
        return '未选择磁盘', 400

    # 启动后台线程执行磁盘操作
    thread = threading.Thread(target=perform_partition_operations, args=(disk,))
    thread.start()

    # 返回到前端页面，前端页面会通过 WebSocket 监听操作完成事件
    return render_template('index.html', disks=get_sd_disks())

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.7z'):  # 修改为支持 .7z 文件
            # 保存上传的文件
            file_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(file_path)
            # 启动后台线程解压文件
            thread = threading.Thread(target=extract_7z, args=(file_path,))
            thread.start()
            return render_template('upload.html', progress=0)
        else:
            return '仅支持上传 .7z 文件', 400
    return render_template('upload.html', progress=0)

@socketio.on('start_partition_operations')
def handle_start_partition_operations(data):
    disk = data['disk']
    perform_partition_operations(disk)

def perform_partition_operations(disk):
    # 删除磁盘所有分区
    delete_partitions(disk)
    # 创建 ESP 分区和 ext4 分区
    create_partitions(disk)
    # 挂载 ext4 分区
    mount_ext4_partition(disk)
    # 将 /efi.img 写入 ESP 分区
    write_efi_img_to_esp_partition(disk)
    # 通知前端操作完成
    socketio.emit('partition_operations_finished', {'status': 'finished'})

def delete_partitions(disk):
    command = f'sudo sgdisk -Z /dev/{disk}'
    run_command(command)

def create_partitions(disk):
    commands = [
        f'sudo sgdisk -n 1:0:+512M -t 1:ef00 /dev/{disk}',
        f'sudo sgdisk -n 2:0:0 -t 2:8300 /dev/{disk}',
        f'sudo mkfs.fat -F32 /dev/{disk}1',
        f'sudo mkfs.ext4 /dev/{disk}2'
    ]
    for command in commands:
        run_command(command)

def mount_ext4_partition(disk):
    mount_point = '/mnt/ext4_partition'
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    command = f'sudo mount /dev/{disk}2 {mount_point}'
    run_command(command)

def write_efi_img_to_esp_partition(disk):
    # 将 /efi.img 写入 ESP 分区
    command = f'sudo dd if=/efi.img of=/dev/{disk}1 bs=1M'
    run_command(command)

def run_command(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    while True:
        output = process.stdout.readline()
        if process.poll() is not None and output == b'':
            break
        if output:
            socketio.emit('command_output', {'output': output.decode('utf-8')})

def extract_7z(file_path):
    def extract():
        with py7zr.SevenZipFile(file_path, mode='r') as z:
            total_files = len(z.getnames())
            for i, member in enumerate(z.getnames()):
                z.extract(member, path=UPLOAD_FOLDER)
                progress = (i + 1) / total_files * 100
                socketio.emit('extract_progress', {'progress': progress})
        socketio.emit('extract_finished', {'status': 'finished'})

    thread = threading.Thread(target=extract)
    thread.start()

def get_sd_disks():
    output = subprocess.check_output(['lsblk', '-dn', '-o', 'NAME']).decode()
    disks = [line.strip()[:3] for line in output.splitlines() if line.startswith('sd')]
    return disks

if __name__ == '__main__':
    socketio.run(app, debug=True)
