# 자동 갱신 — 관리자 권한 없이 (시작프로그램 방식)
#
#   powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1
#   해제:  powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1 -Remove
#
# 로그인할 때 시작해 창 없이 돌면서 10분마다 publish.ps1 을 실행한다.
#
# 주기를 10분으로 잡은 이유
#   ITS 개발계정은 1,000건/일 제한이다. 10분 주기면 소통·돌발 두 서비스로
#   하루 288건이라 여유가 있다. 5분으로 줄이면 576건 — 아직 되지만
#   CCTV 까지 켜면 넘친다. 운영계정을 받으면 5분으로 줄여도 된다.
#
# 이 방식의 한계
#   - 로그인해 있어야 돈다.
#   - 절전에서 깨어나면 다음 주기부터 다시 돈다(밀린 실행을 따라잡지 않는다).
#   집 PC 절전이 문제라면 사내 NAS 로 옮기는 편이 낫다.

param([switch]$Remove)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$root = Split-Path -Parent $PSScriptRoot
$loop = Join-Path $root "tools\_loop.ps1"
$startup = [Environment]::GetFolderPath('Startup')
$shortcut = Join-Path $startup "SejongTrafficDashboard.lnk"

if ($Remove) {
    if (Test-Path $shortcut) { Remove-Item $shortcut -Force; Write-Host "시작프로그램에서 제거했습니다." }
    else { Write-Host "등록된 시작프로그램이 없습니다." }
    if (Test-Path $loop) { Remove-Item $loop -Force }
    Write-Host "실행 중인 것은 다음 로그인부터 사라집니다. 지금 멈추려면 data\PAUSED 파일을 만드세요."
    exit 0
}

# 10분마다 publish 를 돌리는 루프 스크립트
@'
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$publish = Join-Path $root "tools\publish.ps1"
$log = Join-Path $root "data\autorun.log"
while ($true) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $publish *>&1 |
            Select-Object -Last 3 | ForEach-Object { "$stamp  $_" } |
            Add-Content -Path $log -Encoding utf8
    } catch {
        "$stamp  실패: $_" | Add-Content -Path $log -Encoding utf8
    }
    # 로그가 무한정 자라지 않게 최근 400줄만 남긴다
    if ((Test-Path $log) -and ((Get-Content $log | Measure-Object -Line).Lines -gt 400)) {
        Get-Content $log -Tail 200 | Set-Content $log -Encoding utf8
    }
    Start-Sleep -Seconds 600
}
'@ | Set-Content -Path $loop -Encoding utf8

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcut)
$link.TargetPath = "powershell.exe"
$link.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$loop`""
$link.WorkingDirectory = $root
$link.Description = "세종시 교통안전 상황판 자동 갱신 (10분)"
$link.Save()

Write-Host "시작프로그램에 등록했습니다 - 다음 로그인부터 10분마다 자동 갱신됩니다."
Write-Host "지금 바로 시작하려면:"
Write-Host ('  Start-Process powershell -ArgumentList @(''-NoProfile'',''-ExecutionPolicy'',''Bypass'',''-WindowStyle'',''Hidden'',''-File'',''"' + $loop + '"'')')
Write-Host "  (경로에 공백이 있어 -File 값은 반드시 따옴표로 감싸야 합니다)"
Write-Host "실행 기록:  data\autorun.log"
Write-Host "즉시 정지:  data\PAUSED 파일 생성"
Write-Host "해제:       tools\install_startup.ps1 -Remove"
