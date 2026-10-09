r"""
Writes THIRD-PARTY-NOTICES.md: every library that ends up inside the Voice Typing exe, with
its license name and the full license text, plus the speech and speaker models, Python
itself and Tcl/Tk. Run it from the build environment (the one PyInstaller bundles from):

    python build\collect_licenses.py  >  THIRD-PARTY-NOTICES.md

build_exe.ps1 does this automatically. The file is shipped inside the installer and kept in
the repo so the notices are visible on GitHub too.
"""

import importlib.metadata as md
import os
import re
import sys
import sysconfig

# Build-only tools that are not inside the finished program.
EXCLUDE = {"pip", "setuptools", "wheel", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph",
           "pefile", "pywin32-ctypes", "packaging", "pillow", "pip-licenses"}

MODELS = [
    ("Whisper (speech recognition model and code)", "OpenAI", "MIT",
     "https://github.com/openai/whisper", "Downloaded to %USERPROFILE%\\.cache\\whisper on first run."),
    ("pyannote segmentation-3.0 (speaker segmentation model)", "CNRS / Hervé Bredin", "MIT",
     "https://huggingface.co/pyannote/segmentation-3.0 (ONNX export from https://github.com/k2-fsa/sherpa-onnx)",
     "Bundled as models\\pyannote-segmentation-3-0.onnx."),
    ("3D-Speaker ERes2Net VoxCeleb (speaker embedding model)", "Alibaba DAMO Academy, 3D-Speaker project", "Apache-2.0",
     "https://github.com/modelscope/3D-Speaker (ONNX export from https://github.com/k2-fsa/sherpa-onnx)",
     "Bundled as models\\3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx."),
    ("FFmpeg (audio/video decoding for 'Transcribe a file')", "FFmpeg developers", "LGPL-2.1-or-later (LGPL build, no GPL components)",
     "https://ffmpeg.org - build from https://github.com/BtbN/FFmpeg-Builds",
     "Bundled as ffmpeg\\ffmpeg.exe and its DLLs, run as a separate program; the source install downloads the same build on first use. "
     "Source code for this build: https://github.com/BtbN/FFmpeg-Builds (the LGPL license text is below)."),
    ("ONNX Runtime", "Microsoft", "MIT", "https://github.com/microsoft/onnxruntime",
     "Bundled inside sherpa-onnx as onnxruntime.dll."),
    ("PortAudio", "PortAudio community", "MIT", "http://www.portaudio.com",
     "Bundled inside python-sounddevice as libportaudio64bit.dll."),
    ("Python", "Python Software Foundation", "PSF-2.0", "https://www.python.org",
     "The interpreter and standard library are embedded in the exe."),
    ("Tcl/Tk", "Tcl Core Team and contributors", "Tcl/Tk license (BSD-style)", "https://www.tcl.tk",
     "Used for the on-screen status pill (tkinter)."),
    ("PyInstaller bootloader", "PyInstaller Development Team", "GPL-2.0 with the PyInstaller bootloader exception",
     "https://pyinstaller.org", "The exe's bootloader. The exception allows bundled programs to carry any license."),
]


def license_text(dist):
    texts = []
    for f in dist.files or []:
        if re.match(r"(?i)^(LICENSE|LICENCE|COPYING|NOTICE)", f.name) and ".dist-info" in str(f):
            try:
                with open(f.locate(), encoding="utf-8", errors="replace") as fh:
                    texts.append((f.name, fh.read().strip()))
            except Exception as e:
                print(f"warning: could not read {f}: {e}", file=sys.stderr)
    if not texts:
        body = (dist.metadata.get("License") or "").strip()
        if len(body) > 200:
            texts.append(("License (from package metadata)", body))
    return texts


def license_name(m):
    lic = (m.get("License-Expression") or "").strip()
    if lic:
        return lic
    cls = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License ::")]
    if cls:
        return "; ".join(cls)
    body = (m.get("License") or "").strip()
    return body.splitlines()[0][:80] if body else "see license text"


def main():
    out = open(sys.argv[1], "w", encoding="utf-8", newline="\n") if len(sys.argv) > 1 else sys.stdout
    print("# Third-party notices for Voice Typing\n", file=out)
    print("Voice Typing itself is MIT-licensed (see LICENSE). It is built from the open-source components "
          "below, which are included in the installed program. Each one's license is reproduced here as "
          "its authors require.\n", file=out)

    print("## Models and runtime components\n", file=out)
    print("| Component | Author | License | Source |\n|---|---|---|---|", file=out)
    for name, author, lic, url, note in MODELS:
        print(f"| {name} | {author} | {lic} | {url} |", file=out)
    print("", file=out)
    for name, author, lic, url, note in MODELS:
        print(f"- **{name}** - {note}", file=out)

    dists = sorted((d for d in md.distributions() if d.metadata["Name"].lower() not in EXCLUDE),
                   key=lambda d: d.metadata["Name"].lower())
    print("\n## Python libraries\n", file=out)
    print("| Library | Version | License |\n|---|---|---|", file=out)
    for d in dists:
        print(f"| {d.metadata['Name']} | {d.metadata['Version']} | {license_name(d.metadata)} |", file=out)

    print("\n## License texts\n", file=out)
    # Python's own license file.
    py_lic = os.path.join(sysconfig.get_paths()["data"], "LICENSE.txt")
    if not os.path.exists(py_lic):
        py_lic = os.path.join(os.path.dirname(sys.executable), "LICENSE.txt")
    if os.path.exists(py_lic):
        print("### Python\n\n```\n" + open(py_lic, encoding="utf-8", errors="replace").read().strip() + "\n```\n", file=out)
    for d in dists:
        for fname, text in license_text(d):
            print(f"### {d.metadata['Name']} {d.metadata['Version']} - {fname}\n\n```\n{text}\n```\n", file=out)
    # FFmpeg: the LGPL 2.1 text (kept in build/licenses) and the build's own license file if present.
    here = os.path.dirname(os.path.abspath(__file__))
    for label, path in (("FFmpeg - GNU Lesser General Public License 2.1", os.path.join(here, "licenses", "LGPL-2.1.txt")),
                        ("FFmpeg build - LICENSE.txt", os.path.join(here, "ffmpeg", "LICENSE.txt"))):
        if os.path.exists(path):
            print(f"### {label}\n\n```\n" + open(path, encoding="utf-8", errors="replace").read().strip() + "\n```\n", file=out)
    if out is not sys.stdout:
        out.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
