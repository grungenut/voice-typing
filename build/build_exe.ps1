# Builds the Voice Typing installer: dist\VoiceTyping-Setup-<version>.exe
#
#   powershell -ExecutionPolicy Bypass -File build\build_exe.ps1
#
# Steps
#   1. A build-only Python environment in %LOCALAPPDATA%\VoiceTyping\build-venv with the CPU
#      build of PyTorch (the exe is CPU-only so it works on every PC and stays well under
#      GitHub's 2 GB release limit; NVIDIA users use Install.cmd from source instead).
#   2. The two speaker models into build\models (copied from the installed app data if present,
#      else downloaded).
#   2b. FFmpeg (LGPL shared build) into build\ffmpeg, bundled so MP3/MP4 files can be transcribed.
#   3. THIRD-PARTY-NOTICES.md regenerated from the build environment.
#   4. PyInstaller -> dist\Voice Typing\  (one folder, no console)
#   5. Inno Setup  -> dist\VoiceTyping-Setup-<version>.exe
#
# Needs: Python 3.10+ on PATH (py launcher) and Inno Setup 6 (ISCC.exe).

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
function Say($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host ""; Write-Host "!! $m" -ForegroundColor Red; exit 1 }

$version = (Select-String -Path "$root\voice_typing.py" -Pattern '^__version__ = "([^"]+)"').Matches[0].Groups[1].Value
if (-not $version) { Fail "Could not read __version__ from voice_typing.py" }
Say "Building Voice Typing $version"

# --- 1. build environment ---------------------------------------------------------------
$venv = Join-Path $env:LOCALAPPDATA "VoiceTyping\build-venv"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    Say "Creating the build environment in $venv"
    py -3 -m venv $venv
    if (-not (Test-Path $py)) { Fail "Could not create the build environment (is Python 3.10+ installed?)" }
}
& $py -m pip install --quiet --upgrade pip
Say "Installing CPU PyTorch and the libraries into the build environment"
& $py -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { Fail "torch (CPU) did not install" }
& $py -m pip install --quiet -r "$root\requirements.txt" pyinstaller
if ($LASTEXITCODE -ne 0) { Fail "requirements did not install" }
$gpu = & $py -c "import torch; print(torch.version.cuda or 'none')"
if ($gpu -ne "none") { Fail "The build environment has a CUDA torch ($gpu); it must be the CPU build. Delete $venv and rerun." }

# --- 2. speaker models ------------------------------------------------------------------
$models = Join-Path $root "build\models"
New-Item -ItemType Directory -Force $models | Out-Null
$installed = Join-Path $env:LOCALAPPDATA "VoiceTyping\models"
foreach ($f in @("pyannote-segmentation-3-0.onnx", "pyannote-segmentation-3-0.LICENSE", "3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx")) {
    $dst = Join-Path $models $f
    if (-not (Test-Path $dst)) {
        $src = Join-Path $installed $f
        if (Test-Path $src) { Copy-Item $src $dst }
    }
}
if (-not (Test-Path (Join-Path $models "3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx")) -or
    -not (Test-Path (Join-Path $models "pyannote-segmentation-3-0.onnx"))) {
    Say "Downloading the speaker models"
    $ProgressPreference = "SilentlyContinue"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $tmp = Join-Path $env:TEMP "vt-seg"; Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force $tmp | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2" -OutFile "$tmp\seg.tar.bz2"
    tar -xjf "$tmp\seg.tar.bz2" -C $tmp
    Copy-Item "$tmp\sherpa-onnx-pyannote-segmentation-3-0\model.onnx" (Join-Path $models "pyannote-segmentation-3-0.onnx")
    Copy-Item "$tmp\sherpa-onnx-pyannote-segmentation-3-0\LICENSE" (Join-Path $models "pyannote-segmentation-3-0.LICENSE")
    Remove-Item -Recurse -Force $tmp
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx" -OutFile (Join-Path $models "3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx")
}

# --- 2b. FFmpeg -------------------------------------------------------------------------
$ff = Join-Path $root "build\ffmpeg"
if (-not (Test-Path (Join-Path $ff "ffmpeg.exe"))) {
    $installedFf = Join-Path $env:LOCALAPPDATA "VoiceTyping\ffmpeg"
    if (Test-Path (Join-Path $installedFf "ffmpeg.exe")) {
        Say "Copying FFmpeg from the installed app data"
        New-Item -ItemType Directory -Force $ff | Out-Null
        Copy-Item (Join-Path $installedFf "*") $ff -Force
    } else {
        Say "Downloading FFmpeg (LGPL shared build)"
        $ProgressPreference = "SilentlyContinue"
        New-Item -ItemType Directory -Force $ff | Out-Null
        $zip = Join-Path $env:TEMP "vt-ffmpeg.zip"
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-win64-lgpl-shared-8.1.zip" -OutFile $zip
        $tmp = Join-Path $env:TEMP "vt-ffmpeg"; Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
        Copy-Item (Join-Path $inner.FullName "bin\*") $ff -Force
        Get-ChildItem $inner.FullName -File -Filter "LICENSE*" | Copy-Item -Destination $ff -Force
        Remove-Item -Recurse -Force $tmp, $zip -ErrorAction SilentlyContinue
    }
}
if (-not (Test-Path (Join-Path $ff "ffmpeg.exe"))) { Fail "build\ffmpeg\ffmpeg.exe is missing" }
# Only ffmpeg.exe and its DLLs are shipped (not ffplay/ffprobe).
Get-ChildItem $ff -File | Where-Object { $_.Name -in @("ffplay.exe", "ffprobe.exe") } | Remove-Item -Force

# --- 3. third-party notices -------------------------------------------------------------
Say "Writing THIRD-PARTY-NOTICES.md"
& $py "$root\build\collect_licenses.py" "$root\THIRD-PARTY-NOTICES.md"
if ($LASTEXITCODE -ne 0) { Fail "collect_licenses.py failed" }

# --- 4. PyInstaller ---------------------------------------------------------------------
Say "Running PyInstaller (this takes a few minutes)"
Remove-Item -Recurse -Force "$root\dist\Voice Typing" -ErrorAction SilentlyContinue
& (Join-Path $venv "Scripts\pyinstaller.exe") "$root\build\voice_typing.spec" --noconfirm --distpath "$root\dist" --workpath "$root\build\work" --log-level WARN
if ($LASTEXITCODE -ne 0 -or -not (Test-Path "$root\dist\Voice Typing\Voice Typing.exe")) { Fail "PyInstaller failed" }
$size = [Math]::Round((Get-ChildItem "$root\dist\Voice Typing" -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "   dist\Voice Typing\ is $size MB"

# --- 5. Inno Setup ----------------------------------------------------------------------
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { Fail "Inno Setup 6 not found (https://jrsoftware.org/isdl.php). dist\Voice Typing\ is built; only the Setup.exe is missing." }
Say "Compiling the installer with Inno Setup"
& $iscc /Q "/DAppVersion=$version" "$root\build\installer.iss"
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup failed" }
$setup = "$root\dist\VoiceTyping-Setup-$version.exe"
Write-Host ("   {0}  ({1} MB)" -f $setup, [Math]::Round((Get-Item $setup).Length / 1MB))
Say "Done."
exit 0
