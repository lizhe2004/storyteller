#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${DOCKER_IMAGE:-lizhe2004/audio-story-generator}"
PLATFORMS="${DOCKER_PLATFORMS:-linux/amd64,linux/arm64}"
BUILDER="${DOCKER_BUILDER:-storyteller-multiarch}"
LATEST_TAG="${DOCKER_LATEST_TAG:-latest}"

if ! command -v docker >/dev/null 2>&1; then
  echo "错误：未找到 docker 命令。" >&2
  exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
  echo "错误：当前 Docker 不支持 buildx。请升级 Docker Engine 或 Docker Desktop。" >&2
  exit 1
fi

if [[ ! -f "${ROOT_DIR}/Dockerfile" ]]; then
  echo "错误：未找到 ${ROOT_DIR}/Dockerfile。" >&2
  exit 1
fi

if ! docker buildx inspect "${BUILDER}" >/dev/null 2>&1; then
  echo "创建 Buildx builder：${BUILDER}"
  docker buildx create \
    --name "${BUILDER}" \
    --driver docker-container \
    --use
else
  docker buildx use "${BUILDER}"
fi

docker buildx inspect "${BUILDER}" --bootstrap >/dev/null

if [[ -n "${DOCKER_VERSION_TAG:-}" ]]; then
  VERSION_TAG="${DOCKER_VERSION_TAG}"
else
  GIT_SHA="$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || true)"
  if [[ -z "${GIT_SHA}" ]]; then
    echo "错误：无法获取 Git commit；请设置 DOCKER_VERSION_TAG。" >&2
    exit 1
  fi
  BRANCH="$(git -C "${ROOT_DIR}" branch --show-current 2>/dev/null || true)"
  BRANCH="${BRANCH:-detached}"
  BRANCH="${BRANCH//\//-}"
  VERSION_TAG="${BRANCH}-${GIT_SHA}"
fi

echo "构建并推送多架构镜像："
echo "  image:     ${IMAGE}"
echo "  platforms: ${PLATFORMS}"
echo "  tags:      ${LATEST_TAG}, ${VERSION_TAG}"
echo "  builder:   ${BUILDER}"

docker buildx build \
  --builder "${BUILDER}" \
  --platform "${PLATFORMS}" \
  --provenance=false \
  --tag "${IMAGE}:${LATEST_TAG}" \
  --tag "${IMAGE}:${VERSION_TAG}" \
  --push \
  "${ROOT_DIR}"

echo "校验 Docker Hub manifest：${IMAGE}:${LATEST_TAG}"
docker buildx imagetools inspect "${IMAGE}:${LATEST_TAG}"

echo "校验 Docker Hub manifest：${IMAGE}:${VERSION_TAG}"
docker buildx imagetools inspect "${IMAGE}:${VERSION_TAG}"

echo "完成：${IMAGE}:${LATEST_TAG} 和 ${IMAGE}:${VERSION_TAG}"
