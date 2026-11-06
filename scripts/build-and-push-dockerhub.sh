#!/usr/bin/env bash
set -euo pipefail

readonly DEFAULT_REPOSITORY="lizhe2004/audio-story-generator"
readonly PLATFORMS="linux/amd64,linux/arm64"

usage() {
    cat <<'USAGE'
Usage: scripts/build-and-push-dockerhub.sh [tag]

Build and push a multi-platform image to Docker Hub.
Platforms: linux/amd64, linux/arm64

Environment:
  DOCKERHUB_REPOSITORY  Image repository (default: lizhe2004/audio-story-generator)

The script uses the Docker login already configured on this machine.
USAGE
}

if [[ "${1:-}" == -h || "${1:-}" == --help ]]; then
    usage
    exit 0
fi

if [[ "$#" -gt 1 ]]; then
    usage >&2
    exit 2
fi

tag="${1:-latest}"
if [[ ! "$tag" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]; then
    echo "Error: invalid Docker image tag: $tag" >&2
    exit 2
fi

repository="${DOCKERHUB_REPOSITORY:-$DEFAULT_REPOSITORY}"
if [[ ! "$repository" =~ ^[a-z0-9]+([._-][a-z0-9]+)*(\/[a-z0-9]+([._-][a-z0-9]+)*)+$ ]]; then
    echo "Error: invalid Docker Hub repository: $repository" >&2
    exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Error: Docker CLI is not installed or not on PATH." >&2
    exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
    echo "Error: Docker Buildx is unavailable. Install or enable Docker Buildx first." >&2
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"
image="${repository}:${tag}"

echo "Building and pushing ${image} for ${PLATFORMS}"
docker buildx build \
    --platform "$PLATFORMS" \
    --tag "$image" \
    --push \
    "$project_root"
