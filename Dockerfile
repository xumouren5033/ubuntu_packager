# 使用官方的 Ubuntu 基础镜像
FROM ubuntu:latest

# 设置环境变量，避免交互式配置
ENV DEBIAN_FRONTEND=noninteractive

# 安装 live-build 工具
RUN apt-get update && apt-get install -y live-build xorriso

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

# 添加自定义软件包（可选）
# RUN echo "vim git curl" > config/package-lists/custom.list.chroot

# 构建 LiveCD 镜像
RUN lb build

# 将生成的 ISO 文件输出到宿主机
VOLUME ["/live/binary.hybrid.iso"]
