param([ValidateSet('all','docling','paddle')][string]$Backend = 'all')
$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$toolsPath = Join-Path $projectPath 'workbench-data/tools'
New-Item -ItemType Directory -Path $toolsPath -Force | Out-Null
$pythonPath = Join-Path $projectPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = (Get-Command python -ErrorAction Stop).Source }
Push-Location $projectPath
try {
    if ($Backend -in @('all','docling')) {
        $tesseractCommand = Join-Path $env:ProgramFiles 'Tesseract-OCR/tesseract.exe'
        if (-not (Test-Path -LiteralPath $tesseractCommand)) {
            $installerPath = Join-Path $toolsPath 'tesseract-5.4.0-installer.exe'
            Invoke-WebRequest 'https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe' -OutFile $installerPath
            if ((Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash -ne 'C885FFF6998E0608BA4BB8AB51436E1C6775C2BAFC2559A19B423E18678B60C9') { throw 'Tesseract 安装包校验不符' }
            # The UB Mannheim build installs the native CLI in its standard directory.
            $installed = Start-Process -FilePath $installerPath -ArgumentList '/S' -WindowStyle Hidden -Wait -PassThru
            if ($installed.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $tesseractCommand)) { throw 'Tesseract 未安装完成' }
        }
        $languagePath = Join-Path $toolsPath 'tesseract/tessdata'
        New-Item -ItemType Directory -Path $languagePath -Force | Out-Null
        $configPath = Join-Path $languagePath 'configs'
        New-Item -ItemType Directory -Path $configPath -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $configPath 'tsv') -Value 'tessedit_create_tsv 1' -Encoding ascii
        $englishModel = Join-Path $languagePath 'eng.traineddata'
        $expectedModelHash = '8280AED0782FE27257A68EA10FE7EF324CA0F8D85BD2FD145D1C2B560BCB66BA'
        if (-not (Test-Path -LiteralPath $englishModel) -or (Get-FileHash -LiteralPath $englishModel).Hash -ne $expectedModelHash) {
            Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/e12c65a915945e4c28e237a9b52bc4a8f39a0cec/eng.traineddata' -OutFile $englishModel
        }
        if ((Get-FileHash -LiteralPath $englishModel).Hash -ne $expectedModelHash) { throw '英文模型校验不符' }
    }
    $backends = if ($Backend -eq 'all') { @('docling','paddle') } else { @($Backend) }
    foreach ($choice in $backends) {
        $environmentPath = Join-Path $toolsPath $choice
        $environmentPython = Join-Path $environmentPath 'Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $environmentPython)) {
            & $pythonPath -m venv $environmentPath
            if ($LASTEXITCODE -ne 0) { throw "无法创建 $choice 独立环境" }
        }
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            & uv pip install --python $environmentPython -r (Join-Path $projectPath "workbench/requirements-$choice.txt")
        } else {
            & $environmentPython -m ensurepip --upgrade
            & $environmentPython -m pip install -r (Join-Path $projectPath "workbench/requirements-$choice.txt")
        }
        if ($LASTEXITCODE -ne 0) { throw "$choice 依赖安装未完成" }
        & $environmentPython -X utf8 (Join-Path $projectPath 'scripts/parser_environment.py') $choice
        if ($LASTEXITCODE -ne 0) { throw "$choice 环境检查未通过" }
    }
    Write-Output '组件安装完成。重启工作台，在“选择与编辑 → 英文材料解析”切换；首次使用会下载对应的公开模型。'
} finally { Pop-Location }
