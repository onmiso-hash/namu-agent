#!/bin/sh
# 개발 클론당 1회 실행: core.hooksPath를 .githooks로 설정해 pre-push 버전 드리프트 가드를 활성화한다.

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT" || exit 1

# 클론 후 실행권한이 유실될 수 있으므로 재부여
chmod +x .githooks/pre-push

git config core.hooksPath .githooks

echo "개발 훅 활성화됨: core.hooksPath=.githooks"
