FROM ubuntu:latest

# 安装必要的工具
RUN apt-get update && apt-get install -y \
    live-build \
    xorriso \
    coreutils

# 创建工作目录
WORKDIR /live

# 初始化 live-build 配置
RUN lb config \
    --architectures amd64 \
    --linux-flavours generic \
    --binary-images iso-hybrid \
    --iso-application "Ubuntu Live" \
    --iso-preparer "Live Build" \
    --iso-publisher "Your Name" \
    --iso-volume "Ubuntu Live Volume" \
    --debian-installer live

# 构建 LiveCD 镜像
RUN lb build
