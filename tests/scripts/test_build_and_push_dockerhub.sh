#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/build-and-push-dockerhub.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TMP_DIR/bin"
cat > "$TMP_DIR/bin/docker" <<'DOCKER'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == buildx && "${2:-}" == version ]]; then
    echo "github.com/docker/buildx v0.0.0"
    exit 0
fi
printf '%s\n' "$*" >> "$DOCKER_CALLS"
DOCKER
chmod +x "$TMP_DIR/bin/docker"

export DOCKER_CALLS="$TMP_DIR/docker-calls"
export PATH="$TMP_DIR/bin:$PATH"

DOCKERHUB_REPOSITORY=example/storyteller "$SCRIPT" release-test
grep -Fq 'buildx build --platform linux/amd64,linux/arm64 --tag example/storyteller:release-test --push ' "$DOCKER_CALLS"

: > "$DOCKER_CALLS"
"$SCRIPT"
grep -Fq 'buildx build --platform linux/amd64,linux/arm64 --tag lizhe2004/audio-story-generator:latest --push ' "$DOCKER_CALLS"

: > "$DOCKER_CALLS"
if "$SCRIPT" 'bad tag' >/dev/null 2>&1; then
    echo "invalid tag unexpectedly succeeded" >&2
    exit 1
fi
if [[ -s "$DOCKER_CALLS" ]]; then
    echo "Docker was called for an invalid tag" >&2
    exit 1
fi

echo "build-and-push script checks passed"
