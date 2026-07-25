#!/usr/bin/env bash
set -euo pipefail

image="${1:-llmwho:ci}"
container_name="llmwho-smoke-${GITHUB_RUN_ID:-local}-$$"
collector_token="llmwho-container-smoke-token"

cleanup() {
  docker rm --force "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

configured_user="$(docker image inspect --format '{{.Config.User}}' "$image")"
if [[ "$configured_user" != "10001:10001" ]]; then
  echo "Expected image user 10001:10001; found $configured_user" >&2
  exit 1
fi

docker run \
  --detach \
  --name "$container_name" \
  --env "LLMWHO_COLLECTOR_TOKEN=$collector_token" \
  "$image" >/dev/null

ready=false
for _ in {1..30}; do
  if docker exec "$container_name" python -c \
    "from urllib.request import urlopen; urlopen('http://127.0.0.1:7734/api/health', timeout=1).read()" \
    >/dev/null 2>&1; then
    ready=true
    break
  fi
  if [[ "$(docker inspect --format '{{.State.Running}}' "$container_name")" != "true" ]]; then
    docker logs "$container_name" >&2
    exit 1
  fi
  sleep 1
done

if [[ "$ready" != "true" ]]; then
  docker logs "$container_name" >&2
  echo "Collector container did not become ready" >&2
  exit 1
fi

if [[ "$(docker exec "$container_name" id -u)" != "10001" ]]; then
  echo "Collector process is not running as UID 10001" >&2
  exit 1
fi

docker exec \
  --interactive \
  --env "LLMWHO_COLLECTOR_TOKEN=$collector_token" \
  "$container_name" \
  python - <<'PY'
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = "http://127.0.0.1:7734"
with urlopen(f"{base}/api/health", timeout=2) as response:
    health = json.load(response)
assert health["status"] == "ok"
assert health["schema_version"] == "2"

try:
    urlopen(f"{base}/api/summary", timeout=2)
except HTTPError as error:
    assert error.code == 401
    error.close()
else:
    raise AssertionError("unauthenticated data API request was accepted")

request = Request(
    f"{base}/api/summary",
    headers={"Authorization": f"Bearer {os.environ['LLMWHO_COLLECTOR_TOKEN']}"},
)
with urlopen(request, timeout=2) as response:
    summary = json.load(response)
assert summary["events"] == 0
assert summary["scope"]["since"]
assert summary["scope"]["until"]
PY
