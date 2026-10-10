"""
Reading and rewriting the header of a transcript file.

A transcript written by Voice Typing 1.4 or later starts like this:

    <title>
    Recorded: Friday, October 10, 2026 at 2:31 PM        (a file transcript says Source: and Transcribed:)
    Length: 00:12:34 - 2 speakers detected
    Recording: C:\\...\\Meeting 2026-10-10 14-31.wav

    Summary:                                             (only once a summary has been made)
    - ...

    [00:00] Speaker 1: ...

Older transcripts (1.0 - 1.3) have a looser header: the title line, a "Length ..." line and an
"Audio:" or "Recording:" line. parse() reads both; write_summary() upgrades the header when it
adds a summary. The spoken part of the file - everything from the first "[hh:mm]" line - is
never touched.
"""

import datetime
import os
import re

TIMESTAMP_LINE = re.compile(r"^\[\d{2}:\d{2}(:\d{2})?\] ")
FILE_STAMP = re.compile(r"Meeting (\d{4}-\d{2}-\d{2} \d{2}-\d{2})")
DATE_FORMATS = ("%A, %B %d, %Y at %I:%M %p", "%A, %B %d, %Y, %I:%M %p")


def _parse_date(text):
    text = text.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def parse(path, with_body=False):
    """Header fields of a transcript. Returns None if the file does not look like one."""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        return None
    if any(ln.startswith("Note:") for ln in lines[1:3]):
        return None                                   # a note written from a transcript, not one itself
    body_at = next((i for i, ln in enumerate(lines) if TIMESTAMP_LINE.match(ln)), None)
    if body_at is None and not any(ln.startswith("Length") for ln in lines[:8]):
        return None                                   # some other text file
    head = lines[:body_at] if body_at is not None else lines[:40]
    info = {"path": path, "title": lines[0].strip(), "recorded": None, "length": "", "speakers": "",
            "recording": "", "source": "", "summary": "", "legacy": True, "body_at": body_at}
    in_summary, summary = False, []
    for ln in head[1:]:
        s = ln.strip()
        if in_summary:
            if s or summary:
                summary.append(s)
            continue
        if s.startswith("Summary:"):
            in_summary = True
            rest = s[len("Summary:"):].strip()
            if rest:
                summary.append(rest)
        elif s.startswith("Recorded:"):
            info["recorded"] = _parse_date(s[len("Recorded:"):])
            info["legacy"] = False
        elif s.startswith("Transcribed:"):
            info["recorded"] = _parse_date(s[len("Transcribed:"):])
            info["legacy"] = False
        elif s.startswith("Source:"):
            info["source"] = s[len("Source:"):].strip()
        elif s.startswith("Length"):
            m = re.match(r"Length:?\s*(\S+)\s*-\s*(\d+) speaker", s)
            if m:
                info["length"], info["speakers"] = m.group(1), m.group(2)
            else:
                info["length"] = s.split(":", 1)[-1].strip() if ":" in s else s
        elif s.startswith("Recording:") or s.startswith("Audio:"):
            info["recording"] = s.split(":", 1)[1].strip()
    info["summary"] = "\n".join(summary).strip()
    if info["recorded"] is None:
        # Older files: "Meeting transcript - Friday, October 09, 2026, 02:31 PM" or the file name.
        m = re.search(r" - (.+)$", info["title"])
        if m:
            info["recorded"] = _parse_date(m.group(1))
        if info["recorded"] is None:
            m = FILE_STAMP.search(os.path.basename(path))
            if m:
                info["recorded"] = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H-%M")
        if info["recorded"] is None:
            info["recorded"] = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    if not info["recording"] and info["source"]:
        info["recording"] = info["source"]
    if info["recording"] and not os.path.isabs(info["recording"]):
        info["recording"] = os.path.join(os.path.dirname(path), info["recording"])
    if with_body:
        info["body"] = "\n".join(lines[body_at:]) if body_at is not None else ""
    return info


def body_text(path):
    """The spoken lines only, for summarizing."""
    info = parse(path, with_body=True)
    return info["body"] if info else ""


def header_lines(title, recorded, length_text, n_speakers, labels_ok, recording_path, source=None):
    """The header a new transcript gets (list of lines, without the trailing blank line)."""
    when = recorded.strftime("%A, %B %d, %Y at %I:%M %p").replace(" 0", " ")
    lines = [title]
    if source:
        lines.append(f"Source: {source}")
        lines.append(f"Transcribed: {when}")
    else:
        lines.append(f"Recorded: {when}")
    lines.append(f"Length: {length_text} - {n_speakers} speaker{'s' if n_speakers != 1 else ''} detected"
                 + ("" if labels_ok else " (labels unavailable)"))
    if recording_path and not source:
        lines.append(f"Recording: {os.path.abspath(recording_path)}")
    return lines


def write_summary(path, title, summary):
    """Put a title and summary into an existing transcript, keeping the spoken part untouched.
    An old-style header is rewritten in the new form."""
    info = parse(path, with_body=True)
    if info is None:
        raise ValueError("not a transcript file")
    labels_ok = "labels unavailable" not in open(path, encoding="utf-8-sig", errors="replace").read(600)
    n_spk = int(info["speakers"]) if info["speakers"].isdigit() else 0
    lines = header_lines(title.strip() or info["title"], info["recorded"], info["length"] or "?", n_spk, labels_ok,
                         info["recording"], info["source"] or None)
    summary = summary.strip()
    if summary:
        lines += ["", "Summary:"] + summary.splitlines()
    text = "\n".join(lines) + "\n\n" + (info["body"].rstrip("\n") + "\n" if info["body"] else "")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def notes_for(path):
    """Note files written from this transcript: '<name> - <template>.txt' beside it."""
    base = os.path.splitext(os.path.basename(path))[0] + " - "
    folder = os.path.dirname(os.path.abspath(path))
    out = []
    try:
        for fn in sorted(os.listdir(folder)):
            if fn.startswith(base) and fn.lower().endswith(".txt"):
                out.append(os.path.join(folder, fn))
    except OSError:
        pass
    return out


def find_transcripts(folders, depth=2):
    """All transcript files under the folders (a few levels deep), newest first."""
    seen, found = set(), []
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        base_depth = folder.rstrip("\\/").count(os.sep)
        for root, dirs, files in os.walk(folder):
            if root.count(os.sep) - base_depth >= depth:
                dirs[:] = []
            for name in files:
                if not name.lower().endswith(".txt") or name.lower().endswith(".live.txt"):
                    continue
                full = os.path.normcase(os.path.join(root, name))
                if full in seen:
                    continue
                seen.add(full)
                info = parse(os.path.join(root, name))
                if info:
                    found.append(info)
    found.sort(key=lambda i: i["recorded"] or datetime.datetime.min, reverse=True)
    return found
