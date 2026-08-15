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
TOKENS_PATH = CSS_PATH.parent / "namu-docs-tokens.css"
JS_PATH = CSS_PATH.parent / "namu-theme.js"
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
    css = _keep_our_own_colors(ui, css)
    CSS_PATH.write_text(HEADER + css + EXTRA, encoding="utf-8")
    print(f"갱신 완료: {CSS_PATH} ({CSS_PATH.stat().st_size:,}바이트)")
    _bring_the_theme_button_along(ui)
    return 0


def _bring_the_theme_button_along(ui) -> None:
    """밝게/어둡게 단추의 동작을 홈페이지에서 뽑아 파일 한 장으로 만든다.

    홈페이지는 이 조각을 화면 HTML 안에 통째로 박아 넣지만(화면이 서버에서
    만들어지므로 그럴 수 있다), 안내서는 정적 파일 다섯 장이라 그럴 수 없다 —
    다섯 장에 같은 조각을 박아 넣으면 한 장만 고치고 넘어가는 날이 온다.
    그래서 파일 한 장으로 뽑고 다섯 장이 그것을 부른다.

    단추를 켜는 부분은 <head>에서 도는데 그때는 아직 단추가 없으므로,
    화면이 다 그려진 뒤로 미룬다. 반대로 고른 색을 입히는 부분은 미루면
    안 된다 — 밝은 화면이 한 번 번쩍인다.
    """
    inner = _script_body(ui._THEME_BOOT_SCRIPT)
    later = _script_body(ui._THEME_TOGGLE_SCRIPT)
    js = (
        "/* 밝게/어둡게 단추. namu-cloud-routing/src/ui.py에서 뽑아온 것이다 —\n"
        "   손대지 말고 scripts/sync_docs_css.py로 다시 뽑을 것. */\n"
        + inner
        + "\ndocument.addEventListener('DOMContentLoaded',function(){"
        + later
        + "});\n"
    )
    JS_PATH.write_text(js, encoding="utf-8")
    print(f"  단추 동작: {JS_PATH.name} ({JS_PATH.stat().st_size:,}바이트)")


def _script_body(tag: str) -> str:
    """`<script>…</script>`에서 알맹이만 꺼낸다."""
    start, end = tag.index(">") + 1, tag.rindex("</script>")
    return tag[start:end]


def _keep_our_own_colors(ui, css: str) -> str:
    """색만 안내서 것으로 바꾼다 — 나머지는 홈페이지에서 따라온다.

    안내서는 첫 나무의 그림이라 청록이고, 나무 클라우드는 그 나무의 열매라
    자주다. 사용자가 두 곳의 색을 일부러 갈랐다(2026-08-15).

    색만 가르고 글꼴·부품·여백은 계속 홈페이지를 따라간다 — 그래야 부품이
    새로 생기거나 여백이 바뀌어도 안내서가 저절로 따라온다. 손으로 베끼면
    반드시 어긋난다는 것이 이 스크립트가 있는 이유이고, 그 이유는 색을
    가른 뒤에도 그대로다.

    바꿔 넣을 자리는 `ui._TOKENS_CSS` 한 덩어리다. 글자를 찾아 자르지 않고
    그 변수를 그대로 대조하므로, 홈페이지가 물감통 모양을 바꾸면 조용히
    비껴가는 게 아니라 여기서 멈춘다.
    """
    if not TOKENS_PATH.exists():
        print(f"  안내서 전용 색 파일이 없습니다 — {TOKENS_PATH}")
        print("  홈페이지 색을 그대로 씁니다.")
        return css

    tokens = getattr(ui, "_TOKENS_CSS", None)
    if not tokens or css.count(tokens) != 1:
        raise SystemExit(
            "홈페이지의 물감통(_TOKENS_CSS)을 CSS 안에서 정확히 한 번 찾지 못했습니다.\n"
            "홈페이지 쪽 구조가 바뀐 것이니 이 스크립트를 함께 고쳐야 합니다."
        )

    ours = TOKENS_PATH.read_text(encoding="utf-8")
    print(f"  색 갈아 끼움: {TOKENS_PATH.name} (안내서는 청록을 유지한다)")
    return css.replace(tokens, ours)


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
