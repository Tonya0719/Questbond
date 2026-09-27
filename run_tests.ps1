<#
    运行全部测试并把结果记录到 test-results\ 目录。

    用法（在项目根目录打开 PowerShell）：
        .\run_tests.ps1

    可选参数：
        .\run_tests.ps1 -TestPath tests\test_intake_clarification.py   # 只跑某个文件
        .\run_tests.ps1 -PythonExe "D:\software\anaconda3\envs\hackathon\python.exe"  # 指定解释器

    每次运行会在 test-results\ 下按时间戳生成三份文件：
        <时间戳>_full.txt      完整日志（每个用例 + 失败详情）
        <时间戳>_junit.xml     JUnit XML（机器可读，可供 CI/工具解析）
        <时间戳>_summary.md    Markdown 总结（通过/失败数量一目了然）
#>
param(
    [string]$TestPath  = "tests",
    [string]$PythonExe = "D:\software\anaconda3\envs\hackathon\python.exe"
)

$ErrorActionPreference = "Stop"

# 切到 UTF-8 代码页并设置编码，避免中文乱码
try { chcp 65001 > $null } catch {}
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path $PythonExe)) {
    Write-Host "找不到 Python 解释器：$PythonExe" -ForegroundColor Red
    Write-Host "请用 -PythonExe 参数指定 hackathon 环境的 python.exe 路径。" -ForegroundColor Red
    exit 1
}

# 结果目录
$resultsDir = Join-Path $PSScriptRoot "test-results"
if (-not (Test-Path $resultsDir)) {
    New-Item -ItemType Directory -Path $resultsDir | Out-Null
}

# 带时间戳的文件名
$stamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$txtFile = Join-Path $resultsDir "${stamp}_full.txt"
$xmlFile = Join-Path $resultsDir "${stamp}_junit.xml"
$mdFile  = Join-Path $resultsDir "${stamp}_summary.md"

$env:LLM_BACKEND = "mock"

Write-Host "使用解释器：$PythonExe" -ForegroundColor Cyan
Write-Host "运行测试：$TestPath" -ForegroundColor Cyan
Write-Host "结果保存到：$resultsDir`n" -ForegroundColor Cyan

# 直接调用 hackathon 环境的 python.exe。输出经管道由 Tee-Object 同时写屏和写文件。
& $PythonExe -m pytest $TestPath -v --tb=short --junitxml="$xmlFile" 2>&1 | Tee-Object -FilePath $txtFile
$exitCode = $LASTEXITCODE

# 统计（若日志文件因故未生成则用空串兜底）
if (Test-Path $txtFile) { $content = Get-Content $txtFile -Raw } else { $content = "" }
if ($null -eq $content) { $content = "" }
$passed  = ([regex]::Matches($content, " PASSED")).Count
$failed  = ([regex]::Matches($content, " FAILED")).Count
$errored = ([regex]::Matches($content, " ERROR ")).Count
$skipped = ([regex]::Matches($content, " SKIPPED")).Count

# 提取 pytest 末尾汇总行
$summaryLine = "(无汇总行)"
if (Test-Path $txtFile) {
    $matched = Select-String -Path $txtFile -Pattern "passed|failed|error"
    if ($matched) { $summaryLine = $matched[-1].Line.Trim() }
}

# 写 Markdown 总结
$verdict = if ($exitCode -eq 0) { "PASS - 全部通过" } else { "FAIL - 存在失败/错误" }
$runTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$lines = @(
    "# 测试结果总结"
    ""
    "- 运行时间：$runTime"
    "- 测试范围：$TestPath"
    "- 结论：$verdict"
    ""
    "## 数量统计"
    ""
    "| 状态 | 数量 |"
    "|------|------|"
    "| 通过 PASSED  | $passed |"
    "| 失败 FAILED  | $failed |"
    "| 错误 ERROR   | $errored |"
    "| 跳过 SKIPPED | $skipped |"
    ""
    "pytest 汇总行：$summaryLine"
    ""
    "## 关联文件"
    "- 完整日志：$(Split-Path $txtFile -Leaf)"
    "- JUnit XML：$(Split-Path $xmlFile -Leaf)"
)
Set-Content -Path $mdFile -Value $lines -Encoding UTF8

Write-Host "`n---------------------------------------------" -ForegroundColor Green
Write-Host "结果已保存：" -ForegroundColor Green
Write-Host "  完整日志: $txtFile"
Write-Host "  JUnit XML: $xmlFile"
Write-Host "  总结:     $mdFile"
Write-Host "  统计: 通过 $passed / 失败 $failed / 错误 $errored / 跳过 $skipped" -ForegroundColor Green

exit $exitCode
