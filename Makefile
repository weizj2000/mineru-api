# ---------------------------
# 配置参数
# ---------------------------
IMAGE_NAME ?= weizhanjun/mineru-api
TAG ?= 1.3.12
DOCKERFILE ?= docker/Dockerfile-cuda
PLATFORM ?= linux/amd64

# ---------------------------
# 构建镜像
# ---------------------------
build-docker:
	@echo "开始构建 Docker 镜像（平台: $(PLATFORM)）"
	docker build \
		--platform $(PLATFORM) \
		-t $(IMAGE_NAME):$(TAG) \
		-f $(DOCKERFILE) \
		.
	@echo "镜像构建完成: $(IMAGE_NAME):$(TAG)"

# ---------------------------
# 推送镜像到仓库
# ---------------------------
push-docker: build-docker
	@echo "开始推送镜像到仓库"
	docker push $(IMAGE_NAME):$(TAG)
	@echo "镜像推送完成"

# ---------------------------
# 清理镜像
# ---------------------------
clean:
	@echo "清理镜像"
	docker rmi -f $(IMAGE_NAME):$(TAG) 2>/dev/null || true
	@echo "镜像清理完成"

# ---------------------------
# 帮助信息
# ---------------------------
help:
	@echo "可用命令:"
	@echo "  make build-docker      构建Docker镜像（默认平台: $(PLATFORM）"
	@echo "  make push-docker       推送镜像到仓库（需先构建）"
	@echo "  make clean             清理本地镜像"
	@echo "参数覆盖示例:"
	@echo "  make build-docker IMAGE_NAME=myapp TAG=v1.0.0"