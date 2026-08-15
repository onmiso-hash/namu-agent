#!/usr/bin/env python3
"""안내 문서의 공용 스타일(`docs/assets/namu-docs.css`)을 나무 클라우드 홈페이지에서 다시 뽑는다.

안내서(docs/*.html)와 홈페이지(namu-cloud.onnamu.kr)는 서로 오가는 한 동선이라 같은
옷을 입어야 한다. 그런데 두 곳은 저장소가 다르므로(홈페이지는 namu-cloud-routing),
색·글자·부품 정의를 손으로 베끼면 반드시 어긋난다 — 그래서 홈페이지의 `ui.SITE_CSS`를
원본으로 삼고 이 스크립트로 복사해 온다.

홈페이지 저장소가 옆에 없으면(=이 repo만 clone한 사람) 아무것도 하지 않고 그대로
끝낸다. 기존 CSS 파일이 이미 저장돼 있으므로 문서는 문제없이 열린다.

사용법:
    python3 scripts/sync_docs_css.py            # 기본 경로(../namu-cloud-routing)에서 찾는다
    python3 scripts/sync_docs_css.py <경로>     # 홈페이지 저장소 경로를 직접 준다
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = REPO_ROOT / "docs" / "assets" / "namu-docs.css"
DEFAULT_SITE_REPO = REPO_ROOT.parent / "namu-cloud-routing"

HEADER = """/* NAMU 안내 문서 공용 스타일.
   나무 클라우드 홈페이지(namu-cloud-routing/src/ui.py SITE_CSS)에서 그대로 뽑아온 것이다.
   안내서와 홈페이지를 오가는 동선이라 두 곳이 같은 옷을 입어야 한다.
   홈페이지 디자인이 바뀌면 scripts/sync_docs_css.py로 다시 뽑는다. */
"""

# 안내 문서에만 있고 홈페이지에는 없는 부품 — 목차, 비교표, 짚고 넘어가는 칸.
EXTRA = """
/* ── 안내 문서 전용 추가분 ── */
.toc{background:var(--bg-soft);border:1px solid var(--border);border-radius:var(--radius);padding:18px 22px;margin:24px 0;}
.toc h2{margin:0 0 .5em;font-size:1rem;letter-spacing:.02em;color:var(--fg-faint);text-transform:uppercase;}
.toc ol{margin:0;padding-left:1.4em;}
.toc li{margin:.35em 0;}
.toc a{color:var(--fg);text-decoration:none;font-weight:600;}
.toc a:hover{color:var(--accent-deep);text-decoration:underline;}
.cmp{overflow-x:auto;margin:1.2em 0;}
.cmp table{min-width:640px;margin:0;}
.cmp td.no{color:var(--fg-faint);}
.tip{border-left:3px solid var(--accent);background:var(--accent-soft);padding:14px 18px;border-radius:0 var(--radius-sm) var(--radius-sm) 0;margin:18px 0;}
.tip>:first-child{margin-top:0;} .tip>:last-child{margin-bottom:0;}
.warnbox{border-left:3px solid var(--warn);background:var(--bg-soft);padding:14px 18px;border-radius:0 var(--radius-sm) var(--radius-sm) 0;margin:18px 0;}
.warnbox>:first-child{margin-top:0;} .warnbox>:last-child{margin-bottom:0;}
.docfoot{margin-top:3em;padding-top:1.4em;border-top:1px solid var(--border);color:var(--fg-soft);font-size:.9rem;}
h2[id],h3[id]{scroll-margin-top:70px;}
"""


def main() -> int:
    site_repo = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SITE_REPO
    ui_py = site_repo / "src" / "ui.py"
    if not ui_py.exists():
        print(f"홈페이지 저장소를 찾지 못했습니다: {ui_py}")
        print("건너뜁니다 — 이미 저장된 CSS가 그대로 쓰입니다.")
        return 0

    sys.path.insert(0, str(site_repo / "src"))
    import ui  # type: ignore[import-not-found]

    CSS_PATH.parent.mkdir(parents=True, exist_ok=True)
    css = _bring_the_fonts_along(ui, site_repo)
    CSS_PATH.write_text(HEADER + css + EXTRA, encoding="utf-8")
    print(f"갱신 완료: {CSS_PATH} ({CSS_PATH.stat().st_size:,}바이트)")
    return 0


def _bring_the_fonts_along(ui, site_repo: Path) -> str:
    """글꼴 파일을 안내서 쪽으로 복사하고, CSS의 주소를 상대 경로로 바꾼다.

    홈페이지는 글꼴을 `/asset/…`이라는 **절대 주소**로 부른다 — 화면마다 주소가
    달라(`/`, `/start`, …) 상대 경로를 쓸 수 없기 때문이다. 그런데 안내서는
    다른 서버(GitHub Pages)에 올라가므로 그 절대 주소는 그 서버의 없는 자리를
    가리켜 404가 된다. 화면은 시스템 글꼴로 멀쩡히 떠서 아무도 눈치채지 못한다.

    안내서 쪽은 CSS가 파일 하나(`assets/namu-docs.css`)라 그 파일 옆을 가리키는
    상대 경로가 항상 맞는다. 그래서 파일을 같은 폴더로 옮기고 주소만 바꾼다 —
    남의 서버에서 우리 서버로 글꼴을 받아가게 만들지 않는 것이 요점이다.
    """
    css = ui.SITE_CSS
    src_dir = site_repo / "src" / "assets" / "fonts"
    for path in getattr(ui, "ASSET_PATHS", ()):
        name = Path(path).name
        src = src_dir / name
        if not src.exists():
            print(f"  경고: 글꼴 파일이 없습니다 — {src}")
            continue
        (CSS_PATH.parent / name).write_bytes(src.read_bytes())
        css = css.replace(f"url({path})", f"url({name})")
        print(f"  글꼴 복사: {name} ({src.stat().st_size:,}바이트)")
    return css


if __name__ == "__main__":
    raise SystemExit(main())
