#!/usr/bin/env bash
# NAMU 원격 MCP 클라우드 컨테이너 entrypoint (namu-45, docs/remote_mcp_design.md §7-2).
#
# 1) NAMU_SYNC_REMOTE(토큰 내장 HTTPS remote URL)로 ~/.namu를 clone, 이미 있으면 pull.
# 2) git identity(user.email/user.name)가 비어 있으면 기본값을 채운다 — python:3.12-slim
#    이미지에는 git identity가 없어, 이후 sync_setup의 초기 커밋이 "Author identity
#    unknown"으로 실패하는 실배포 갭이 실측됐다(namu-45 docker 실검증).
# 3) deploy/namu_cloud_sync_setup.py(memory_sync.sync_setup() wrapper)로 .namu_sync
#    마커 / .gitattributes union 라인 / git remote origin을 wiring한다 — 새로 짜지
#    않고 기존 함수를 그대로 재사용한다.
# 4) http_server.py를 exec로 기동한다(PID 1 시그널을 그대로 전달하기 위해 exec 사용).
#
# 실패를 조용히 삼키지 않는다 — 각 단계는 실패 시 원인을 stderr에 남기고 즉시
# 비정상 종료(exit != 0)한다("완료" 오출력 금지, namu-43 교훈).
set -euo pipefail

NAMU_HOME="${HOME:-/root}/.namu"
NAMU_PLUGIN_DIR="/app/namu-plugin"
SYNC_SETUP_SCRIPT="/app/deploy/namu_cloud_sync_setup.py"

if [ -z "${NAMU_SYNC_REMOTE:-}" ]; then
  echo "[namu-entrypoint] ERROR: NAMU_SYNC_REMOTE 환경변수가 설정되지 않았습니다." >&2
  echo "  예: NAMU_SYNC_REMOTE=https://x-access-token:<PAT>@github.com/<user>/<repo>.git" >&2
  echo "  (docs/remote_mcp_design.md §7-2 참조 — 클라우드 컨테이너는 이 원격에서" >&2
  echo "   ~/.namu(교훈 저장소)를 clone/pull합니다. 인증(NAMU_HTTP_TOKEN 등)은" >&2
  echo "   별도 환경변수이며 http_server.py가 자체적으로 기동을 거부합니다.)" >&2
  exit 1
fi

if [ -d "${NAMU_HOME}/.git" ]; then
  echo "[namu-entrypoint] 기존 ~/.namu 발견 — git pull"
  if ! git -C "${NAMU_HOME}" pull --no-rebase --no-edit; then
    echo "[namu-entrypoint] ERROR: ~/.namu git pull 실패 (원격/자격증명을 확인하세요)" >&2
    exit 1
  fi
else
  echo "[namu-entrypoint] ~/.namu 없음 — clone: ${NAMU_HOME}"
  if ! git clone "${NAMU_SYNC_REMOTE}" "${NAMU_HOME}"; then
    echo "[namu-entrypoint] ERROR: ~/.namu git clone 실패 (NAMU_SYNC_REMOTE/토큰을 확인하세요)" >&2
    exit 1
  fi
fi

# git identity 기본값 채우기 — python:3.12-slim에는 user.email/user.name이 없어
# sync_setup의 초기 커밋이 "Author identity unknown"으로 실패한다(namu-45 docker
# 실검증). 이미 설정돼 있으면(이미지를 확장해 사용자가 직접 넣은 경우 등) 절대
# 덮어쓰지 않는다 — email/name을 각각 독립적으로 부재 시에만 채운다.
if ! git config --global --get user.email > /dev/null 2>&1; then
  GIT_EMAIL="${NAMU_GIT_EMAIL:-namu@container}"
  git config --global user.email "${GIT_EMAIL}"
  echo "[namu-entrypoint] git identity: user.email 미설정 — 기본값 적용(${GIT_EMAIL})"
fi
if ! git config --global --get user.name > /dev/null 2>&1; then
  GIT_NAME="${NAMU_GIT_NAME:-namu-${NAMU_MACHINE:-web}}"
  git config --global user.name "${GIT_NAME}"
  echo "[namu-entrypoint] git identity: user.name 미설정 — 기본값 적용(${GIT_NAME})"
fi

echo "[namu-entrypoint] sync wiring (.namu_sync 마커 / .gitattributes / remote origin)"
if ! uv run --script "${SYNC_SETUP_SCRIPT}" "${NAMU_SYNC_REMOTE}"; then
  echo "[namu-entrypoint] ERROR: sync wiring 실패 (위 memory_sync.sync_setup 출력 참조)" >&2
  exit 1
fi

echo "[namu-entrypoint] http_server.py 기동 (machine=${NAMU_MACHINE:-unset} host=${NAMU_HTTP_HOST:-unset} port=${NAMU_HTTP_PORT:-unset})"
exec uv run --script "${NAMU_PLUGIN_DIR}/http_server.py"
