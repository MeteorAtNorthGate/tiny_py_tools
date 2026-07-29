$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location $PSScriptRoot
$startTime = Get-Date
$monitor = $null

Write-Host "=== Windows CUDA / PyTorch / VRAM Acceptance Test ===" -ForegroundColor Cyan
Write-Host "Requirements: NVIDIA driver and Python >= 3.12 x64 installed."
Write-Host "Close browsers, games, screen recording, remote streaming and other GPU programs during the test."
Write-Host ""

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    throw "nvidia-smi not found. Please install NVIDIA driver first."
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher (py) not found. Please install Python >= 3.12 x64 and check the py launcher option."
}

& python -c "import sys; print(sys.version)"
if ($LASTEXITCODE -ne 0) {
    throw "Python is not available."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating isolated Python environment..."
    & python -m venv .venv
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "Upgrading pip..."
& $python -m pip install --upgrade pip

Write-Host "Installing NumPy: $NumpyRequirement ..."
& $python -m pip install "numpy>=1.26,<3"


Write-Host "Installing PyTorch 2.12.1 + CUDA 13.0 wheel via Aliyun mirror..."

# 显示当前 Python 环境，方便发现版本或位数不匹配
& $python -c "import sys, struct; print('Python:', sys.version); print('Executable:', sys.executable); print('Bits:', struct.calcsize('P') * 8)"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to check Python environment."
}

# cu130 wheel 目录是平铺目录，因此使用 --find-links；
# 普通依赖包继续使用阿里云 PyPI 镜像。
& $python -m pip install `
    --no-cache-dir `
    --timeout 600 `
    --retries 8 `
    --prefer-binary `
    --index-url "https://mirrors.aliyun.com/pypi/simple/" `
    --find-links "https://mirrors.aliyun.com/pytorch-wheels/cu130/" `
    "torch==2.12.1+cu130"

if ($LASTEXITCODE -ne 0) {
    throw "PyTorch 2.12.1+cu130 installation failed."
}

Write-Host "Saving pre-test device information..."
& nvidia-smi -q | Out-File -Encoding utf8 "nvidia-smi-before.txt"
& nvidia-smi -L | Out-File -Encoding utf8 "nvidia-smi-list.txt"

$monitorArgs = @(
    "--query-gpu=timestamp,name,driver_version,pstate,temperature.gpu,power.draw,clocks.sm,clocks.mem,memory.used,memory.total,utilization.gpu,utilization.memory",
    "--format=csv",
    "-l", "2"
)

Write-Host "Starting GPU status logging..."
$monitor = Start-Process -FilePath "nvidia-smi.exe" `
    -ArgumentList $monitorArgs `
    -RedirectStandardOutput "gpu-monitor.csv" `
    -RedirectStandardError "gpu-monitor-error.txt" `
    -PassThru -WindowStyle Hidden

try {
    Write-Host ""
    Write-Host "Starting Python test; default ~80% VRAM usage with 10 minutes of sustained computation." -ForegroundColor Yellow
    # Windows PowerShell 5.1 会把 Python 写入 stderr 的普通 warning
    # 包装成 NativeCommandError；在 ErrorActionPreference=Stop 下会误终止。
    # 这里只临时允许 stderr 继续输出，最终仍按 Python 的退出码判定成功或失败。
    $savedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $python ".\gpu_acceptance_test.py" `
            --stress-minutes 10 `
            --vram-fraction 0.80 `
            --vram-rounds 2 `
            --chunk-mib 256 `
            --reserve-gib 1.75 `
            --matrix-size 8192 2>&1 |
            Tee-Object -FilePath "gpu-test-output.txt"
        $testCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
}
finally {
    if ($monitor -and -not $monitor.HasExited) {
        Stop-Process -Id $monitor.Id -Force -ErrorAction SilentlyContinue
    }
    & nvidia-smi -q | Out-File -Encoding utf8 "nvidia-smi-after.txt"

    Write-Host "Exporting NVIDIA/WHEA system logs during test period..."
    try {
        Get-WinEvent -FilterHashtable @{
            LogName = "System"
            StartTime = $startTime
        } -ErrorAction Stop |
        Where-Object {
            $_.ProviderName -match "nvlddmkm|Display|WHEA" -or
            $_.Id -in 17,18,19,20,4101
        } |
        Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message |
        Format-List |
        Out-File -Encoding utf8 "windows-gpu-events.txt"
    }
    catch {
        "Failed to export event log: $($_.Exception.Message)" |
            Out-File -Encoding utf8 "windows-gpu-events.txt"
    }
}

Write-Host ""
if ($testCode -eq 0) {
    Write-Host "Python test PASSED. Please continue with OCCT as described in README." -ForegroundColor Green
} else {
    Write-Host "Python test FAILED, exit code: $testCode. Do not ship; troubleshoot first." -ForegroundColor Red
}
Write-Host "Package the entire folder (especially txt/csv files) for the buyer."
Read-Host "Press Enter to exit"
exit $testCode
