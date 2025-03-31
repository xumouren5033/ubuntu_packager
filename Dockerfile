# 基于 Debian 镜像
FROM debian:latest

# 安装 live-build
RUN apt-get update && apt-get install -y live-build

# 设置工作目录
WORKDIR /live-build

# 创建 live-build 配置目录
RUN mkdir -p /live-build/config

# 运行 lb config 生成配置文件
RUN lb config

# 运行 live-build 构建
CMD ["lb", "build"]
