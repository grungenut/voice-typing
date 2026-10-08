# PyInstaller spec for Voice Typing. Run from the project folder via build\build_exe.ps1:
#     .\.build-venv\Scripts\pyinstaller.exe build\voice_typing.spec --noconfirm
# Produces dist\Voice Typing\Voice Typing.exe (a one-folder build; the installer wraps it).

import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, ".."))
models = os.path.join(root, "build", "models")

datas = [
    (os.path.join(root, "assets", "voice_typing.ico"), "assets"),
    (os.path.join(root, "LICENSE"), "."),
    (os.path.join(root, "THIRD-PARTY-NOTICES.md"), "."),
    (models, "models"),
]
datas += collect_data_files("whisper")                 # mel filters + tokenizer files
datas += collect_data_files("sherpa_onnx")
binaries = collect_dynamic_libs("sherpa_onnx")         # onnxruntime.dll, sherpa-onnx-c-api.dll, ...
hiddenimports = collect_submodules("sherpa_onnx") + ["tiktoken_ext", "tiktoken_ext.openai_public"]

a = Analysis(
    [os.path.join(root, "voice_typing.py")],
    pathex=[root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "PIL", "IPython", "pytest", "setuptools", "pip"],
    noarchive=False,
)
# PyInstaller picked up a 2022-era msvcp140.dll (14.34) from the Python install while torch's
# DLLs need the current runtime; c10.dll then fails with WinError 1114. Ship the machine's
# up-to-date Visual C++ runtime files instead (Microsoft permits redistributing these).
_vc = {"msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140_atomic_wait.dll",
       "vcomp140.dll", "concrt140.dll", "msvcp140_codecvt_ids.dll"}
_sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
a.binaries = [b for b in a.binaries if os.path.basename(b[0]).lower() not in _vc]
for _name in sorted(_vc):
    _src = os.path.join(_sys32, _name)
    if os.path.exists(_src):
        a.binaries.append((_name, _src, "BINARY"))

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Voice Typing",
    icon=os.path.join(root, "assets", "voice_typing.ico"),
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Voice Typing")
