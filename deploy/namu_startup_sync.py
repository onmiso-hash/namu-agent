# /// script
# requires-python = ">=3.12"
# dependencies = ["python-dotenv>=1.0.0", "tzdata>=2024.1"]
# ///
"""클라우드 컨테이너 entrypoint 전용 얇은 wrapper — 시작 동기화
(namu-entrypoint-pull-resilience).

`startup_sync.main()`을 그대로 부른다. 로직은 `namu-plugin/startup_sync.py`에 있다 —
그래야 pytest가 실제 임시 git 저장소로 잠금·미커밋·충돌 시나리오를 재현할 수 있고,
셸 스크립트 안에 검사 불가능한 로직이 쌓이지 않는다.

exit code: 0=받아오기 성공, 3=실패(그래도 entrypoint는 서버를 띄운다), 2=인자 오류.
`namu_cloud_sync_setup.py`와 달리 실패가 곧 기동 중단이 아니라는 점이 이 파일의 요지다.

의존성이 dotenv/tzdata 둘뿐인 이유는 `namu_cloud_sync_setup.py`와 같다 —
`startup_sync`/`memory_sync`는 stdlib만 쓰지만 `import config as cfg`가 dotenv를
요구하고, 실패 시각을 `cfg.now()`(기준 시간대 Asia/Seoul)로 찍으므로 slim 이미지에
없는 tz 데이터가 필요하다. tzdata가 없으면 시각이 UTC로 찍혀 사람이 다른 기기 기록과
비교할 수 없다(config.py `cfg.now()` 규약).
"""
import sys
from pathlib import Path

# namu-plugin/은 이 파일 기준 ../namu-plugin (Dockerfile: /app/deploy/, /app/namu-plugin/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "namu-plugin"))

import startup_sync  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(startup_sync.main())
