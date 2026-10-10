"""
Note templates: what the summary model is asked to write for a recording.

A template is a small text file:

    name = SOAP note
    description = Subjective, Objective, Assessment and Plan for a clinical visit
    output = file                 (file = its own note beside the transcript; summary = the
                                   Summary block at the top of the transcript)
    instructions:
    <everything below this line is the instruction to the model>

Built-in templates ship in the program's templates/ folder. Anything a user saves goes to
<data dir>/templates/ (edited in the window's Note templates page). A user file with the same
name as a built-in one replaces it; deleting the user file brings the built-in back.
"""

import os
import re

import sysglue

FIELDS = ("name", "description", "output")
DEFAULT_NAME = "Meeting summary"


def user_dir():
    return os.path.join(sysglue.data_dir(), "templates")


def builtin_dir(bundle_dir, app_dir):
    for d in (os.path.join(bundle_dir, "templates"), os.path.join(app_dir, "templates")):
        if os.path.isdir(d):
            return d
    return os.path.join(app_dir, "templates")


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "template"


def parse(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError:
        return None
    head, sep, body = text.partition("\ninstructions:")
    if not sep:
        head, sep, body = text.partition("instructions:")
    t = {"name": "", "description": "", "output": "summary", "instructions": body.strip("\n").strip(), "path": path}
    for ln in head.splitlines():
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, _, v = ln.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k in FIELDS:
                t[k] = v
    if t["output"] not in ("summary", "file"):
        t["output"] = "summary"
    if not t["name"]:
        t["name"] = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
    return t if t["instructions"] else None


def load_all(bundle_dir, app_dir):
    """All templates by name: built-in first, then the user's (which replace same-named ones)."""
    found = {}
    for folder, builtin in ((builtin_dir(bundle_dir, app_dir), True), (user_dir(), False)):
        if not os.path.isdir(folder):
            continue
        for fn in sorted(os.listdir(folder)):
            if not fn.lower().endswith(".txt"):
                continue
            t = parse(os.path.join(folder, fn))
            if t:
                t["builtin"] = builtin
                t["overrides_builtin"] = (not builtin) and t["name"] in found and found[t["name"]]["builtin"]
                found[t["name"]] = t
    order = sorted(found.values(), key=lambda t: (t["name"] != DEFAULT_NAME, t["name"].lower()))
    return order


def get(name, bundle_dir, app_dir):
    all_t = load_all(bundle_dir, app_dir)
    for t in all_t:
        if t["name"].lower() == (name or "").strip().lower():
            return t
    return all_t[0] if all_t else None


def save(t):
    """Write a template to the user folder (built-in ones are never changed in place)."""
    os.makedirs(user_dir(), exist_ok=True)
    name = t["name"].strip()
    if not name:
        raise ValueError("the template needs a name")
    if not t["instructions"].strip():
        raise ValueError("the instructions cannot be empty")
    path = t.get("path") if t.get("path") and os.path.dirname(t["path"]) == user_dir() else None
    if path is None:
        path = os.path.join(user_dir(), _slug(name) + ".txt")
    text = (f"name = {name}\n"
            f"description = {t.get('description', '').strip()}\n"
            f"output = {t.get('output', 'summary')}\n"
            f"instructions:\n{t['instructions'].strip()}\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def delete(t):
    """Remove a user template (a built-in one cannot be deleted; its user copy can)."""
    if t.get("path") and os.path.dirname(t["path"]) == user_dir():
        os.remove(t["path"])
        return True
    return False
