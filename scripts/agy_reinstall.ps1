<#
.SYNOPSIS
    agy용 namu 플러그인 재설치 일괄 스크립트 (uninstall -> install -> heal).

.DESCRIPTION
    agy `plugin install`은 비파괴 병합이라 소스에서 삭제한 파일이 설치본에 잔존한다.
    또한 설치 직후 세션은 PreInvocation 훅이 아직 한 번도 돌지 않아 mcp_config.json이
    상대경로 상태로 남아있을 수 있다 (#22). 이 스크립트는:
      1) uninstall
      2) install
      3) 설치본 훅의 --heal 모드로 mcp_config.json을 즉시 절대경로로 교정
    을 순서대로 실행해, 재설치 직후 첫 세션부터 MCP가 정상 동작하도록 한다.

.PARAMETER PluginSource
    설치할 namu-plugin 소스 경로. 기본값은 이 스크립트의 상위 폴더(repo root) 밑의 namu-plugin.

.NOTES
    Windows PowerShell 5.1 호환. 삼항연산자·`&&` 체이닝 미사용.
#>
param(
    [string]$PluginSource = (Join-Path (Split-Path $PSScriptRoot -Parent) "namu-plugin")
)

$ErrorActionPreference = "Stop"

# ---- 단계 1: uninstall (미설치 상태여도 계속 진행) ----
Write-Host "[1/3] agy plugin uninstall namu ..."
agy plugin uninstall namu
if ($LASTEXITCODE -ne 0) {
    Write-Host "  -> uninstall 실패 또는 미설치 상태 (무시하고 계속 진행)"
} else {
    Write-Host "  -> uninstall 완료"
}

# ---- 단계 2: install (실패 시 즉시 중단) ----
Write-Host "[2/3] agy plugin install `"$PluginSource`" ..."
agy plugin install $PluginSource
if ($LASTEXITCODE -ne 0) {
    Write-Host "  -> install 실패. 중단합니다." -ForegroundColor Red
    exit 1
}
Write-Host "  -> install 완료"

# ---- 단계 3: 설치본 훅으로 mcp_config.json 즉시 교정 ----
$installed = Join-Path $HOME ".gemini\config\plugins\namu"
$healScript = Join-Path $installed "hooks\session_inject.py"

Write-Host "[3/3] mcp_config.json 절대경로 즉시 교정 ($healScript --heal) ..."

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    python $healScript --heal
} else {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        py -3 $healScript --heal
    } else {
        Write-Host "  -> python/py 실행 파일을 찾을 수 없습니다. 중단합니다." -ForegroundColor Red
        exit 1
    }
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "  -> heal 실패. 중단합니다." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "재설치 완료 — 첫 세션부터 /mcp 정상" -ForegroundColor Green
