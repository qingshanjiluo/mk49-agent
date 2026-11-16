param([string]$Action = "status")
# mk49-agent 控制脚本：status / stop / start / restart / open
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Get-AgentProcs {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^(python|cmd)' -and
        $_.CommandLine -and
        $_.CommandLine -match 'run\.py (loop|dashboard)'
    })
}

function Test-Port([int]$Port, [int]$Ms = 800) {
    $c = New-Object Net.Sockets.TcpClient
    try {
        $ok = $c.ConnectAsync("127.0.0.1", $Port).Wait($Ms)
        $c.Close()
        return $ok
    } catch { return $false }
}

function Test-Site([string]$H, [int]$Port = 443, [int]$Ms = 3000) {
    $c = New-Object Net.Sockets.TcpClient
    try {
        $ok = $c.ConnectAsync($H, $Port).Wait($Ms)
        $c.Close()
        return $ok
    } catch { return $false }
}

function Show-Status {
    Write-Host "================ mk49-agent 状态 ================"
    $procs = Get-AgentProcs
    $loop = @($procs | Where-Object {
        $_.CommandLine -match 'run\.py loop' -and $_.Name -match 'python'
    })
    $dash = @($procs | Where-Object {
        $_.CommandLine -match 'run\.py dashboard' -and $_.Name -match 'python'
    })
    if ($loop) {
        Write-Host ("循环 loop       : 运行中  PID " + ($loop[0].ProcessId))
    } else {
        Write-Host "循环 loop       : 未运行"
    }
    if ($dash) {
        Write-Host ("仪表盘 dashboard: 运行中  PID " + ($dash[0].ProcessId))
    } else {
        Write-Host "仪表盘 dashboard: 未运行"
    }
    $p = Test-Port 8899
    if ($p) {
        Write-Host "面板端口 8899   : 可访问  http://127.0.0.1:8899"
    } else {
        Write-Host "面板端口 8899   : 无监听"
    }
    try {
        $st = Get-Content "state\agent_state.json" -Raw -Encoding UTF8 | ConvertFrom-Json
        $k = Get-Date -Format "yyyy-MM-dd"
        $prop = $st.daily.PSObject.Properties[$k]
        if ($prop -and $prop.Value) {
            $day = $prop.Value
            $slotStr = ""
            if ($day.slots) {
                $slotStr = (@($day.slots.PSObject.Properties | ForEach-Object {
                    "$($_.Name)=$($_.Value)"
                }) -join "  ")
            }
            Write-Host ("今日 $k    : 学习 $($day.learn)  槽位 $slotStr")
        } else {
            Write-Host "今日 $k   : 无活动记录"
        }
        if ($st.stats) {
            $s = $st.stats
            Write-Host ("累计            : 循环 $($s.cycles)  评论 $($s.comments)  点赞 $($s.likes)  发帖 $($s.threads)  速览 $($s.digest)")
        }
    } catch {
        Write-Host "状态文件        : 读取失败 $_"
    }
    $h = (Get-Date).Hour
    if ($h -ge 23 -or $h -lt 8) {
        Write-Host "静默时段        : 是（23:00-08:00 禁写）"
    } else {
        Write-Host "静默时段        : 否"
    }
    if (Test-Site "forum.mk49.top") {
        Write-Host "论坛 forum.mk49 : 连通 OK"
    } else {
        Write-Host "论坛 forum.mk49 : 不通（站点或线路故障）"
    }
    if (Test-Site "ai.furry.vg") {
        Write-Host "LLM 网关        : 连通 OK"
    } else {
        Write-Host "LLM 网关        : 不通"
    }
    if (Test-Path "state\loop.log") {
        Write-Host "--------- 日志尾部（state\loop.log）---------"
        Get-Content "state\loop.log" -Tail 5 -Encoding UTF8 | ForEach-Object {
            Write-Host ("  " + $_)
        }
    }
    Write-Host "=============================================="
}

function Stop-Agent {
    $procs = Get-AgentProcs
    if (-not $procs -or $procs.Count -eq 0) {
        Write-Host "没有正在运行的 agent 进程，无需停止。"
        return
    }
    $ordered = $procs | Sort-Object -Property @{
        Expression = { if ($_.Name -match 'python') { 0 } else { 1 } }
    }
    foreach ($p in $ordered) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host ("已停止 PID " + $p.ProcessId + "  (" + $p.Name + ")")
    }
    Start-Sleep -Milliseconds 800
    $left = Get-AgentProcs
    if (-not $left -or $left.Count -eq 0) {
        Write-Host "全部停止完成。"
    } else {
        Write-Host ("仍有残留 PID: " + (($left | ForEach-Object { $_.ProcessId }) -join ","))
    }
}

function Start-Part([string]$cmdName) {
    $cmd = "cd /d `"$root`" && python -u run.py $cmdName >> state\$cmdName.log 2>&1"
    Start-Process -FilePath $env:ComSpec -ArgumentList "/c", $cmd -WindowStyle Hidden
    Write-Host ("已启动 run.py $cmdName")
}

function Start-Agent {
    $procs = Get-AgentProcs
    $hasLoop = @($procs | Where-Object {
        $_.CommandLine -match 'run\.py loop' -and $_.Name -match 'python'
    }).Count -gt 0
    $hasDash = @($procs | Where-Object {
        $_.CommandLine -match 'run\.py dashboard' -and $_.Name -match 'python'
    }).Count -gt 0
    if (-not $hasLoop) { Start-Part "loop" }
    else { Write-Host "loop 已在运行，跳过。" }
    if (-not $hasDash) { Start-Part "dashboard" }
    else { Write-Host "dashboard 已在运行，跳过。" }
    Start-Sleep -Seconds 2
}

switch ($Action) {
    "stop"    { Stop-Agent }
    "start"   {
        Start-Agent
        Show-Status
    }
    "restart" {
        Stop-Agent
        Start-Sleep -Seconds 1
        Start-Part "loop"
        Start-Part "dashboard"
        Start-Sleep -Seconds 2
        Show-Status
    }
    "open"    {
        Start-Process "http://127.0.0.1:8899"
        Write-Host "已在浏览器打开面板。"
    }
    default   { Show-Status }
}
