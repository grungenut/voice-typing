# Voice Typing installer. Run it by double-clicking Install.cmd (which bypasses the
# PowerShell script policy for this one file). Safe to run again: it only redoes what is missing.
#
# What it does
#   1. Finds Python 3.10 or newer, or installs Python 3.12 (per-user, no admin) with winget.
#   2. Creates a private copy of Python in .venv\ next to this script.
#   3. Installs PyTorch - the NVIDIA (CUDA) build if an NVIDIA card is present, else the CPU build.
#   4. Installs the other libraries from requirements.txt.
#   5. Downloads the two speaker-labeling models (33 MB) into models\.
#   6. Downloads the Whisper speech model so the first start is not slow.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Say($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }

function Get-PythonMinor($exe, $extra) {
    try {
        $out = & $exe @($extra + @("-c", "import sys; print(sys.version_info.minor if sys.version_info.major == 3 else 0)")) 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return [int]($out | Select-Object -Last 1) }
    } catch {}
    return 0
}

# --- 1. Python --------------------------------------------------------------------------
Say "Looking for Python 3.10 or newer"
$py = $null
foreach ($cand in @(@("py", @("-3")), @("python", @()), @("python3", @()))) {
    if (Get-Command $cand[0] -ErrorAction SilentlyContinue) {
        $minor = Get-PythonMinor $cand[0] $cand[1]
        if ($minor -ge 10) { $py = $cand; Write-Host "   found $($cand[0]) (Python 3.$minor)"; break }
    }
}
if (-not $py) {
    Say "No suitable Python found - installing Python 3.12 for this user with winget"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is not available. Install Python 3.12 from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'), then run Install.cmd again."
    }
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    $exe = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (-not (Test-Path $exe)) { throw "Python was installed but not found at $exe. Open a new window and run Install.cmd again." }
    $py = @($exe, @())
}

# --- 2. Virtual environment -------------------------------------------------------------
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Say "Creating a private Python environment in .venv"
    & $py[0] @($py[1] + @("-m", "venv", ".venv"))
    if ($LASTEXITCODE -ne 0) { throw "Could not create .venv" }
} else { Say "Private Python environment already exists (.venv)" }
& $venvPy -m pip install --quiet --upgrade pip

# --- 3. PyTorch -------------------------------------------------------------------------
$hasNvidia = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
if ($hasNvidia) {
    Say "NVIDIA card found - installing the GPU build of PyTorch (about 2.5 GB, be patient)"
    & $venvPy -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cu128
} else {
    Say "No NVIDIA card - installing the CPU build of PyTorch"
    & $venvPy -m pip install --quiet torch
}
if ($LASTEXITCODE -ne 0) { throw "PyTorch did not install" }

# --- 4. Everything else -----------------------------------------------------------------
Say "Installing the speech and audio libraries"
& $venvPy -m pip install --quiet -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "requirements.txt did not install" }

# --- 5. Speaker-labeling models ---------------------------------------------------------
$models = Join-Path $root "models"
New-Item -ItemType Directory -Force $models | Out-Null
$seg = Join-Path $models "pyannote-segmentation-3-0.onnx"
$emb = Join-Path $models "3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not (Test-Path $seg)) {
    Say "Downloading the speaker segmentation model"
    $tmp = Join-Path $env:TEMP "vt-seg"
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $tmp | Out-Null
    $tar = Join-Path $tmp "seg.tar.bz2"
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2" -OutFile $tar
    tar -xjf $tar -C $tmp
    Copy-Item (Join-Path $tmp "sherpa-onnx-pyannote-segmentation-3-0\model.onnx") $seg
    Copy-Item (Join-Path $tmp "sherpa-onnx-pyannote-segmentation-3-0\LICENSE") (Join-Path $models "pyannote-segmentation-3-0.LICENSE")
    Remove-Item -Recurse -Force $tmp
}
if (-not (Test-Path $emb)) {
    Say "Downloading the speaker embedding model (26 MB)"
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx" -OutFile $emb
}

# --- 6. Whisper model -------------------------------------------------------------------
Say "Downloading the Whisper speech model (1.5 GB with an NVIDIA card, 140 MB without)"
& $venvPy -c "import torch, whisper; name = 'turbo' if torch.cuda.is_available() else 'base.en'; whisper.load_model(name); print('   Whisper model ready:', name, '| GPU:', torch.cuda.is_available())"
if ($LASTEXITCODE -ne 0) { throw "Whisper model download failed" }

Say "Done. Double-click 'Start Voice Typing.cmd' to run it, or 'Add to Startup.cmd' to run it at every login."
