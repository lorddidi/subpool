# publish.ps1 — subpool 国内视角验证发布（计划任务每 6 小时调用）
# 流程：本地跑 merge.py（TCP+TLS 连通性验证，视角=家庭网络）→ 以远端为基线提交 sub/ → 推送
# 电脑关机时由 GitHub Actions 的海外视角验证兜底，不会断更。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Administrator\Documents\kimi\workspace\subpool'
$safe = '-c safe.directory=C:/Users/Administrator/Documents/kimi/workspace/subpool'
Set-Location $repo
$env:PYTHONUTF8 = '1'

python merge.py
if ($LASTEXITCODE -ne 0) { Write-Output 'merge.py failed'; exit 1 }

& git $safe fetch origin
& git $safe reset --soft origin/main
& git $safe add sub
& git $safe diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm'
    & git $safe commit -m "verified(CN): $ts"
    & git $safe push origin main
    Write-Output "pushed at $ts"
} else {
    Write-Output 'no change'
}
