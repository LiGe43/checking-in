$ErrorActionPreference = 'Continue'
$target = 'nokey@localhost.run'

while ($true) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 正在连接公网隧道..."
    ssh -o StrictHostKeyChecking=accept-new `
        -o TCPKeepAlive=yes `
        -o ServerAliveInterval=30 `
        -o ServerAliveCountMax=3 `
        -o ExitOnForwardFailure=yes `
        -R 80:127.0.0.1:5173 $target

    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 隧道已断开，5 秒后自动重连..."
    Start-Sleep -Seconds 5
}