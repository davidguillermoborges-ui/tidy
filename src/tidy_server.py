"""
Tidy - lets Claude look at, move, rename and organize folders on this PC.

Safety nets:
  * every move/rename/new-folder is logged as a "job" and can be undone (undo_job)
  * nothing is ever overwritten - a taken name gets " (2)", " (3)" ...
  * deleting only sends to the Recycle Bin (Mac: Trash), and only after a Yes/No box on the computer
  * system folders (Windows, Program Files, AppData / Mac: System, Library, Applications) can be read
    but never changed
Runs on Windows and macOS.
Long operations run in the background; if a call takes more than ~40 s it returns
a task_id and Claude checks back with task_status.
"""
from __future__ import annotations

import csv
import ctypes
import subprocess
import datetime as _dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import string
import sys
import threading
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except Exception:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server

def _version():
    base = getattr(sys, "_MEIPASS", None) or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    try:
        with open(os.path.join(base, "tidy.json"), encoding="utf-8") as f:
            return json.load(f)["version"]
    except Exception:
        return "dev"


VERSION = _version()
MAC = sys.platform == "darwin"
TRASH = "Trash" if MAC else "Recycle Bin"
INSTRUCTIONS = """Tidy organizes folders on the user's computer (Windows or Mac). Workflow when they say 'tidy <folder>':
1) scan_folder (and list_folder / find_duplicates where useful).
2) Reply in chat with a SIMPLE plan: the new folder layout, what moves where, renames (with an
   example or two), anything to delete (suggest only), and anything you can't place - ask about those.
3) Wait for the user to approve in chat. Do not move, rename or recycle before they say yes.
4) Apply with move / rename_pattern / make_folders / remove_empty_folders, then report briefly
   with the job_id (so 'undo' works) and mention that moved media may need relinking in
   Resolve/Blender (the job's relink_list has old -> new paths).
To see what photos show (to sort by character, project or kind), use photo_sheets on the folder, then look at
the sheet JPGs (stage them) instead of the originals; clear_photo_sheets afterwards. Group characters by matching
them across pictures and name them from folder/file names or what the user says, never by recognizing a real person.
Never rename files inside software projects/code or camera-card folders unless asked.
Deletes: only via recycle, only for items the user agreed to in chat."""
try:
    mcp = _Server("tidy", instructions=INSTRUCTIONS)
except TypeError:
    mcp = _Server("tidy")

# ----------------------------------------------------------------- paths/safety
HOME = Path(os.path.expanduser("~"))
if os.environ.get("LOCALAPPDATA"):
    DATA = Path(os.environ["LOCALAPPDATA"]) / "Tidy"
elif MAC:
    DATA = HOME / "Library" / "Application Support" / "Tidy"
else:
    DATA = HOME / "AppData" / "Local" / "Tidy"
JOBS = DATA / "jobs"
RULES_FILE = DATA / "rename_rules.json"
JOBS.mkdir(parents=True, exist_ok=True)
LOG_FILE = DATA / "tidy_log.txt"


def _log(msg: str):
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2_000_000:
            LOG_FILE.replace(LOG_FILE.with_suffix(".old.txt"))
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except Exception:
        pass


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p))).rstrip("\\/")


_PROTECTED = []
for _env, _sub in [("SystemRoot", ""), ("ProgramFiles", ""), ("ProgramFiles(x86)", ""),
                   ("ProgramW6432", ""), ("ProgramData", ""), ("APPDATA", ""), ("LOCALAPPDATA", "")]:
    _v = os.environ.get(_env)
    if _v:
        _PROTECTED.append(_norm(_v))
if MAC:
    _PROTECTED += [_norm(p) for p in ("/System", "/Library", "/Applications", "/usr", "/bin", "/sbin",
                                      "/opt", "/cores", HOME / "Library")]
else:
    _PROTECTED.append(_norm(HOME / "AppData"))
_PROTECTED.append(_norm(DATA))
_PROTECTED = sorted(set(_PROTECTED))


def _is_protected(p) -> bool:
    n = _norm(p)
    for root in _PROTECTED:
        if n == root or n.startswith(root + os.sep):
            return True
    # drive roots and the home folder itself can't be moved/deleted
    if re.fullmatch(r"[a-z]:", n) or n == _norm(HOME) or n in ("", "/"):
        return True
    if MAC and n.startswith("/Volumes/") and n.count("/") == 2:   # a whole disk
        return True
    return False


def _check_writable(*paths):
    for p in paths:
        if _is_protected(p):
            raise PermissionError(f"Protected location, Tidy won't change it: {p}")


def _unique(dest: Path) -> Path:
    if not os.path.lexists(dest):
        return dest
    stem, suf = (dest.stem, dest.suffix) if dest.suffix and not dest.is_dir() else (dest.name, "")
    if os.path.isdir(dest):
        stem, suf = dest.name, ""
    n = 2
    while True:
        cand = dest.with_name(f"{stem} ({n}){suf}")
        if not os.path.lexists(cand):
            return cand
        n += 1


def _human(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def _ext(name: str) -> str:
    e = os.path.splitext(name)[1].lower()
    return e if e else "(none)"


# ----------------------------------------------------------------- background tasks
_TASKS: dict[str, dict] = {}
_WAIT = 40  # seconds a call waits before handing back a task_id


def _run(label: str, fn, *args, **kwargs):
    tid = uuid.uuid4().hex[:8]
    rec = {"task_id": tid, "label": label, "status": "running", "started": time.time(),
           "progress": "", "result": None, "error": None}
    _TASKS[tid] = rec

    def worker():
        try:
            rec["result"] = fn(rec, *args, **kwargs)
            rec["status"] = "done"
        except Exception as e:  # noqa
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["status"] = "error"

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(_WAIT)
    if rec["status"] == "done":
        return rec["result"]
    if rec["status"] == "error":
        return {"error": rec["error"]}
    return {"task_id": tid, "status": "running", "progress": rec["progress"],
            "note": "Still working. Call task_status with this task_id to get the result."}


@mcp.tool()
def task_status(task_id: str) -> dict:
    """Check on a long-running Tidy task (returned when a call took longer than ~40 s)."""
    rec = _TASKS.get(task_id)
    if not rec:
        return {"error": "Unknown task_id (Tidy may have restarted)."}
    out = {"task_id": task_id, "label": rec["label"], "status": rec["status"],
           "seconds": round(time.time() - rec["started"])}
    if rec["status"] == "running":
        out["progress"] = rec["progress"]
    elif rec["status"] == "done":
        out["result"] = rec["result"]
    else:
        out["error"] = rec["error"]
    return out


# ----------------------------------------------------------------- jobs (undo log)
class _Job:
    def __init__(self, name: str, kind: str):
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^\w\- ]+", "", name).strip()[:50] or kind
        self.id = f"{stamp}_{uuid.uuid4().hex[:4]}"
        self.file = JOBS / f"{self.id} {safe}.json"
        self.data = {"id": self.id, "name": name, "kind": kind,
                     "created": _dt.datetime.now().isoformat(timespec="seconds"),
                     "undone": False, "ops": []}

    def add(self, op: dict):
        self.data["ops"].append(op)
        if len(self.data["ops"]) % 200 == 0:
            self.save()

    def save(self):
        if not self.data["ops"]:
            return
        _log(f"job {self.id} '{self.data['name']}': {dict(Counter(o['op'] for o in self.data['ops']))}")
        self.file.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        with open(self.file.with_suffix(".csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Action", "Old path", "New path"])
            for o in self.data["ops"]:
                w.writerow([o["op"], o.get("from", o.get("path", "")), o.get("to", "")])


def _mkdirs(path: Path, job: _Job):
    missing = []
    p = path
    while not p.exists():
        missing.append(p)
        if p.parent == p:
            break
        p = p.parent
    for d in reversed(missing):
        _check_writable(d)
        d.mkdir()
        job.add({"op": "mkdir", "path": str(d)})


def _do_moves(rec, items, job_name):
    job = _Job(job_name, "move")
    results = []
    total = len(items)
    for i, it in enumerate(items, 1):
        rec["progress"] = f"{i}/{total}"
        src = Path(os.path.expanduser(it["from"]))
        dst = Path(os.path.expanduser(it["to"]))
        try:
            if not os.path.lexists(src):
                results.append({"from": str(src), "status": "skipped - not found"})
                continue
            _check_writable(src, dst)
            if dst.exists() and dst.is_dir() and it.get("into", False):
                dst = dst / src.name
            if _norm(dst).startswith(_norm(src) + os.sep):
                raise ValueError("Can't move a folder inside itself")
            _mkdirs(dst.parent, job)
            final = dst
            if os.path.lexists(dst) and _norm(dst) != _norm(src):
                final = _unique(dst)
            if _norm(dst) == _norm(src) and str(dst) != str(src):
                # case-only rename on Windows
                tmp = src.with_name(src.name + ".tidytmp")
                os.rename(src, tmp)
                os.rename(tmp, dst)
            else:
                shutil.move(str(src), str(final))
            job.add({"op": "move", "from": str(src), "to": str(final)})
            r = {"from": str(src), "to": str(final), "status": "moved"}
            if final != dst:
                r["note"] = "name was taken, added a number"
            results.append(r)
        except Exception as e:  # noqa
            results.append({"from": str(src), "to": str(dst), "status": f"error: {e}"})
    job.save()
    moved = sum(1 for r in results if r["status"] == "moved")
    out = {"job_id": job.id if job.data["ops"] else None, "moved": moved,
           "skipped_or_failed": total - moved,
           "relink_list": str(job.file.with_suffix(".csv")) if job.data["ops"] else None}
    problems = [r for r in results if r["status"] != "moved"]
    out["problems"] = problems[:200]
    if total <= 300:
        out["results"] = [r for r in results if r["status"] == "moved"]
    return out


@mcp.tool()
def move(items: list[dict], job_name: str = "move") -> dict:
    """Move and/or rename files and folders (renaming = moving to a new name in the same folder).
    items: [{"from": "C:\\full\\old\\path", "to": "C:\\full\\new\\path"}, ...]
    Add "into": true to drop the item inside an existing folder 'to' keeping its name.
    Missing parent folders are created. Existing names are never overwritten (adds " (2)").
    Everything is logged as one job that undo_job can reverse. Works across drives."""
    if not items:
        return {"error": "No items given"}
    return _run(f"move: {job_name}", _do_moves, items, job_name)


@mcp.tool()
def make_folders(paths: list[str], job_name: str = "new folders") -> dict:
    """Create folders (and any missing parents). Logged so undo_job removes them if still empty."""
    job = _Job(job_name, "mkdir")
    made, errors = [], []
    for p in paths:
        try:
            before = len(job.data["ops"])
            _mkdirs(Path(os.path.expanduser(p)), job)
            if len(job.data["ops"]) > before:
                made.append(p)
        except Exception as e:  # noqa
            errors.append({"path": p, "error": str(e)})
    job.save()
    return {"job_id": job.id if job.data["ops"] else None, "created": made, "errors": errors}


def _do_undo(rec, job_id):
    files = sorted(JOBS.glob(f"{job_id}*.json"))
    if not files:
        return {"error": f"No job {job_id}"}
    jf = files[0]
    data = json.loads(jf.read_text(encoding="utf-8"))
    if data.get("undone"):
        return {"error": "That job was already undone."}
    restored, problems = 0, []
    ops = data["ops"]
    for i, op in enumerate(reversed(ops), 1):
        rec["progress"] = f"{i}/{len(ops)}"
        try:
            if op["op"] == "move":
                if not os.path.lexists(op["to"]):
                    problems.append(f"missing now: {op['to']}")
                    continue
                if os.path.lexists(op["from"]):
                    problems.append(f"something new is already at {op['from']} - left {op['to']} where it is")
                    continue
                os.makedirs(os.path.dirname(op["from"]), exist_ok=True)
                shutil.move(op["to"], op["from"])
                restored += 1
            elif op["op"] == "mkdir":
                p = op["path"]
                if os.path.isdir(p) and not os.listdir(p):
                    os.rmdir(p)
            elif op["op"] == "rmdir":
                os.makedirs(op["path"], exist_ok=True)
        except Exception as e:  # noqa
            problems.append(f"{op}: {e}")
    data["undone"] = True
    jf.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return {"job_id": job_id, "items_put_back": restored, "problems": problems[:200]}


@mcp.tool()
def undo_job(job_id: str) -> dict:
    """Reverse a Tidy job: moves everything back and removes folders it created (if empty)."""
    return _run(f"undo {job_id}", _do_undo, job_id)


@mcp.tool()
def list_jobs(limit: int = 20) -> list[dict]:
    """Recent Tidy jobs, newest first (id, name, when, how many changes, undone or not)."""
    out = []
    for f in sorted(JOBS.glob("*.json"), reverse=True)[:limit]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            c = Counter(o["op"] for o in d["ops"])
            out.append({"job_id": d["id"], "name": d["name"], "created": d["created"],
                        "changes": dict(c), "undone": d.get("undone", False),
                        "relink_list": str(f.with_suffix(".csv"))})
        except Exception:  # noqa
            pass
    return out


# ----------------------------------------------------------------- looking
def _drive_roots():
    if MAC:   # the startup disk is "/", other disks are in /Volumes ("Macintosh HD" there is just "/")
        roots = ["/"]
        try:
            for n in sorted(os.listdir("/Volumes")):
                v = os.path.join("/Volumes", n)
                if os.path.isdir(v) and os.path.realpath(v) != "/":
                    roots.append(v)
        except OSError:
            pass
        return roots
    return [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]


@mcp.tool()
def drives() -> list[dict]:
    """List drives / disks with total and free space."""
    out = []
    for root in _drive_roots():
        if os.path.exists(root):
            try:
                u = shutil.disk_usage(root)
                out.append({"drive": root, "total": _human(u.total), "free": _human(u.free)})
            except Exception:  # noqa
                out.append({"drive": root, "total": "?", "free": "?"})
    return out


@mcp.tool()
def list_folder(path: str, recursive: bool = False, pattern: str = "*",
                offset: int = 0, limit: int = 500) -> dict:
    """List a folder's contents (name, type, size, modified). Paged with offset/limit.
    recursive walks everything below; pattern is a filename glob like '*.mov'."""
    root = Path(os.path.expanduser(path))
    if not root.is_dir():
        return {"error": f"Not a folder: {root}"}
    entries = []
    if recursive:
        for dp, dns, fns in os.walk(root, onerror=lambda e: None):
            dns.sort(); fns.sort()
            for d in dns:
                if fnmatch.fnmatch(d.lower(), pattern.lower()):
                    entries.append((os.path.relpath(os.path.join(dp, d), root), "dir", None, None))
            for f in fns:
                if fnmatch.fnmatch(f.lower(), pattern.lower()):
                    fp = os.path.join(dp, f)
                    try:
                        st = os.stat(fp)
                        entries.append((os.path.relpath(fp, root), "file", st.st_size, st.st_mtime))
                    except OSError:
                        entries.append((os.path.relpath(fp, root), "file", None, None))
    else:
        with os.scandir(root) as it:
            for e in sorted(it, key=lambda e: (not e.is_dir(), e.name.lower())):
                if not fnmatch.fnmatch(e.name.lower(), pattern.lower()):
                    continue
                try:
                    st = e.stat()
                    entries.append((e.name, "dir" if e.is_dir() else "file",
                                    None if e.is_dir() else st.st_size, st.st_mtime))
                except OSError:
                    entries.append((e.name, "dir" if e.is_dir() else "file", None, None))
    page = entries[offset:offset + limit]
    return {"path": str(root), "total": len(entries), "offset": offset,
            "more": offset + limit < len(entries),
            "entries": [{"name": n, "type": t, **({"size": _human(s)} if s is not None else {}),
                         **({"modified": _dt.datetime.fromtimestamp(m).strftime("%Y-%m-%d")} if m else {})}
                        for n, t, s, m in page]}


_MESSY = [
    (re.compile(r"^hf_\d{8}_\d{6}_"), "Higgsfield auto-name"),
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "random ID in name"),
    (re.compile(r"^[0-9a-f]{32}\.", re.I), "random ID name"),
    (re.compile(r"^untitled", re.I), "Untitled"),
    (re.compile(r"^new folder", re.I), "New folder"),
    (re.compile(r"\(\d+\)(\.\w+)?$"), "numbered copy (1)"),
    (re.compile(r" - copy", re.I), "'- Copy'"),
    (re.compile(r"^WhatsApp (Image|Video)", re.I), "WhatsApp export"),
    (re.compile(r"^(IMG|VID|DSC|MVI|PXL)_?\d+", re.I), "camera name"),
]


def _do_scan(rec, path, show_files):
    root = Path(os.path.expanduser(path))
    if not root.is_dir():
        return {"error": f"Not a folder: {root}"}
    per = defaultdict(lambda: {"files": 0, "bytes": 0, "types": Counter(), "newest": 0.0})
    tot_files = tot_bytes = 0
    types = Counter()
    type_bytes = Counter()
    biggest = []
    empty_dirs = []
    messy = defaultdict(list)
    messy_count = Counter()
    loose = []
    n = 0
    for dp, dns, fns in os.walk(root, onerror=lambda e: None):
        if not dns and not fns and _norm(dp) != _norm(root):
            empty_dirs.append(os.path.relpath(dp, root))
        rel = os.path.relpath(dp, root)
        top = None if rel == "." else rel.split(os.sep)[0]
        for f in fns:
            n += 1
            if n % 2000 == 0:
                rec["progress"] = f"{n} files read"
            fp = os.path.join(dp, f)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            sz = st.st_size
            tot_files += 1; tot_bytes += sz
            e = _ext(f); types[e] += 1; type_bytes[e] += sz
            biggest.append((sz, os.path.relpath(fp, root)))
            if len(biggest) > 200:
                biggest.sort(reverse=True); del biggest[25:]
            if top is None:
                loose.append({"name": f, "size": _human(sz)})
            else:
                p = per[top]; p["files"] += 1; p["bytes"] += sz; p["types"][e] += 1
                p["newest"] = max(p["newest"], st.st_mtime)
            for rx, label in _MESSY:
                if rx.search(f):
                    messy_count[label] += 1
                    if len(messy[label]) < 8:
                        messy[label].append(os.path.relpath(fp, root))
                    break
    biggest.sort(reverse=True)
    top_level = []
    with os.scandir(root) as it:
        for e in sorted(it, key=lambda e: e.name.lower()):
            if e.is_dir():
                p = per.get(e.name, {"files": 0, "bytes": 0, "types": Counter(), "newest": 0})
                top_level.append({"folder": e.name, "files": p["files"], "size": _human(p["bytes"]),
                                  "main_types": dict(p["types"].most_common(5)),
                                  "last_changed": _dt.datetime.fromtimestamp(p["newest"]).strftime("%Y-%m-%d") if p["newest"] else None})
    out = {"path": str(root), "total_files": tot_files, "total_size": _human(tot_bytes),
           "subfolders": top_level, "loose_files": loose[:300],
           "types": {k: {"count": v, "size": _human(type_bytes[k])} for k, v in types.most_common(30)},
           "biggest_files": [{"file": p, "size": _human(s)} for s, p in biggest[:25]],
           "empty_folders": empty_dirs[:100],
           "messy_names": {k: {"count": messy_count[k], "examples": v} for k, v in messy.items()}}
    if show_files:
        out["note"] = "Use list_folder on a subfolder to see every file."
    return out


@mcp.tool()
def scan_folder(path: str) -> dict:
    """Summary of a folder of any size: totals, each subfolder's file count/size/main file types/
    last change, loose files, file types, 25 biggest files, empty folders and samples of messy names
    (Higgsfield auto-names, random IDs, Untitled, (1) copies, WhatsApp exports...).
    Start here, then use list_folder on parts you need in detail."""
    return _run(f"scan {path}", _do_scan, path, True)


_SKIP_DIRS = {"_tidy sheets", "node_modules", ".git", "__pycache__", "$recycle.bin", "system volume information",
              ".trash", ".trashes", ".spotlight-v100", ".fseventsd",
              "appdata", "windows", "program files", "program files (x86)", "programdata"}


def _default_roots():
    roots = [HOME / d for d in ["Desktop", "Documents", "Downloads", "Videos", "Pictures", "Music"]
             if (HOME / d).exists()]
    for r in _drive_roots():
        if r not in ("/", "C:\\"):
            roots.append(Path(r))
    return roots


def _do_where(rec, query, roots, limit):
    q = query.lower()
    words = q.split()
    use_glob = any(c in q for c in "*?")
    hits = []
    n = 0
    for root in roots:
        for dp, dns, fns in os.walk(root, onerror=lambda e: None):
            dns[:] = [d for d in dns if d.lower() not in _SKIP_DIRS]
            for name in dns + fns:
                n += 1
                if n % 5000 == 0:
                    rec["progress"] = f"{n} items checked, {len(hits)} found"
                nl = name.lower()
                ok = fnmatch.fnmatch(nl, q) if use_glob else all(w in nl for w in words)
                if ok:
                    fp = os.path.join(dp, name)
                    hits.append({"path": fp, "type": "dir" if name in dns else "file"})
                    if len(hits) >= limit:
                        return {"query": query, "found": hits, "stopped_at_limit": True}
    return {"query": query, "found": hits, "searched": [str(r) for r in roots]}


@mcp.tool()
def where_is(query: str, roots: list[str] | None = None, limit: int = 100) -> dict:
    """Find files or folders by name. query: words that must all be in the name ('bella proposal')
    or a glob ('*.r3d'). Default search: Desktop, Documents, Downloads, Videos, Pictures, Music
    and every drive other than C: (Mac: other disks in /Volumes). Pass roots to search specific places."""
    rs = [Path(os.path.expanduser(r)) for r in roots] if roots else _default_roots()
    return _run(f"where_is {query}", _do_where, query, rs, limit)


def _hash(fp, chunk=1 << 20, partial=False):
    h = hashlib.blake2b(digest_size=20)
    with open(fp, "rb") as f:
        if partial:
            h.update(f.read(chunk))
            size = os.fstat(f.fileno()).st_size
            if size > 2 * chunk:
                f.seek(size // 2); h.update(f.read(chunk))
                f.seek(-chunk, 2); h.update(f.read(chunk))
        else:
            while True:
                b = f.read(chunk * 8)
                if not b:
                    break
                h.update(b)
    return h.hexdigest()


def _do_dups(rec, paths, min_mb):
    by_size = defaultdict(list)
    for p in paths:
        for dp, dns, fns in os.walk(os.path.expanduser(p), onerror=lambda e: None):
            for f in fns:
                fp = os.path.join(dp, f)
                try:
                    s = os.path.getsize(fp)
                except OSError:
                    continue
                if s >= min_mb * 1024 * 1024 and s > 0:
                    by_size[s].append(fp)
    cands = {s: fs for s, fs in by_size.items() if len(fs) > 1}
    groups = []
    done = 0
    total = sum(len(v) for v in cands.values())
    for s, fs in cands.items():
        part = defaultdict(list)
        for fp in fs:
            done += 1
            rec["progress"] = f"checking {done}/{total} same-size files"
            try:
                part[_hash(fp, partial=True)].append(fp)
            except OSError:
                pass
        for fs2 in part.values():
            if len(fs2) < 2:
                continue
            full = defaultdict(list)
            for fp in fs2:
                try:
                    full[_hash(fp)].append(fp)
                except OSError:
                    pass
            for g in full.values():
                if len(g) > 1:
                    groups.append({"size_each": _human(s), "wasted": _human(s * (len(g) - 1)),
                                   "bytes_wasted": s * (len(g) - 1), "files": sorted(g)})
    groups.sort(key=lambda g: -g["bytes_wasted"])
    wasted = sum(g.pop("bytes_wasted") for g in groups)
    return {"duplicate_groups": len(groups), "space_you_could_free": _human(wasted),
            "groups": groups[:200]}


@mcp.tool()
def find_duplicates(paths: list[str], min_size_mb: float = 1.0) -> dict:
    """Find files that are exact byte-for-byte copies (checked by content, not name) across one or
    more folders. Ignores files smaller than min_size_mb. Biggest wasted space first."""
    return _run("find duplicates", _do_dups, paths, min_size_mb)


# ----------------------------------------------------------------- renaming by pattern
@mcp.tool()
def rename_pattern(folder: str, find_regex: str, replace_with: str, recursive: bool = False,
                   include_folders: bool = False, apply: bool = False,
                   job_name: str = "pattern rename") -> dict:
    """Rename many items at once with a regular expression on the name (Python re; use \\1 or
    \\g<1> for groups). With apply=False (default) it only shows a preview of old -> new.
    With apply=True it renames and logs a job (undoable)."""
    root = Path(os.path.expanduser(folder))
    rx = re.compile(find_regex)
    items = []
    walker = os.walk(root, onerror=lambda e: None) if recursive else [(str(root), [d.name for d in root.iterdir() if d.is_dir()], [f.name for f in root.iterdir() if f.is_file()])]
    for dp, dns, fns in walker:
        names = list(fns) + (list(dns) if include_folders else [])
        for name in names:
            if rx.search(name):
                new = rx.sub(replace_with, name)
                if new and new != name:
                    items.append({"from": os.path.join(dp, name), "to": os.path.join(dp, new)})
    if include_folders:  # rename deepest first so paths stay valid
        items.sort(key=lambda i: -i["from"].count(os.sep))
    if not apply:
        return {"matches": len(items),
                "preview": [{"old": os.path.relpath(i["from"], root), "new": os.path.basename(i["to"])}
                            for i in items[:300]]}
    return _run(f"rename {folder}", _do_moves, items, job_name)


@mcp.tool()
def rename_rules(action: str = "list", name: str = "", find_regex: str = "",
                 replace_with: str = "") -> dict:
    """Saved rename rules the user wants applied again later (e.g. Higgsfield hf_ names).
    action: 'list', 'save' (name + find_regex + replace_with) or 'delete' (name).
    To use one, pass its regex/replacement to rename_pattern."""
    rules = json.loads(RULES_FILE.read_text(encoding="utf-8")) if RULES_FILE.exists() else {
        "Higgsfield": {"find_regex": r"^hf_(\d{4})(\d{2})(\d{2})_(\d{6})_[^.]*(\.\w+)$",
                       "replace_with": r"Higgsfield \1-\2-\3 \4\5"}}
    if action == "save":
        rules[name] = {"find_regex": find_regex, "replace_with": replace_with}
    elif action == "delete":
        rules.pop(name, None)
    if action in ("save", "delete") or not RULES_FILE.exists():
        RULES_FILE.write_text(json.dumps(rules, indent=1), encoding="utf-8")
    return rules


# ----------------------------------------------------------------- cleanup
def _do_rm_empty(rec, path):
    root = Path(os.path.expanduser(path))
    job = _Job(f"remove empty folders in {root.name}", "rmdir")
    removed = []
    for dp, dns, fns in os.walk(root, topdown=False, onerror=lambda e: None):
        if _norm(dp) == _norm(root):
            continue
        try:
            if not os.listdir(dp) and not _is_protected(dp):
                os.rmdir(dp)
                job.add({"op": "rmdir", "path": dp})
                removed.append(os.path.relpath(dp, root))
        except OSError:
            pass
    job.save()
    return {"job_id": job.id if removed else None, "removed": removed[:300], "count": len(removed)}


@mcp.tool()
def remove_empty_folders(path: str) -> dict:
    """Remove folders that are completely empty under path (bottom-up). Undoable."""
    return _run("remove empty folders", _do_rm_empty, path)


_MAC_DIALOG = """on run argv
    with timeout of 86400 seconds
        activate
        set r to display dialog (item 1 of argv) with title (item 2 of argv) buttons {"No", "Yes"} default button "No" cancel button "No" with icon caution
    end timeout
    return button returned of r
end run"""


def _confirm_box(title: str, text: str) -> bool:
    if MAC:
        try:
            r = subprocess.run(["osascript", "-e", _MAC_DIALOG, text, title], capture_output=True, text=True)
            return r.returncode == 0 and r.stdout.strip() == "Yes"
        except Exception:
            return False
    try:
        MB_YESNO, MB_ICONWARNING, MB_TOPMOST, MB_SETFOREGROUND, IDYES = 0x4, 0x30, 0x40000, 0x10000, 6
        r = ctypes.windll.user32.MessageBoxW(None, text, title,
                                             MB_YESNO | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND)
        return r == IDYES
    except Exception:  # not Windows
        return False


def _do_recycle(rec, paths, reason):
    from send2trash import send2trash
    items = []
    for p in paths:
        p = os.path.expanduser(p)
        if not os.path.lexists(p):
            continue
        _check_writable(p)
        if os.path.isdir(p):
            size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(p) for f in fs
                       if os.path.exists(os.path.join(dp, f)))
        else:
            size = os.path.getsize(p)
        items.append((p, size))
    if not items:
        return {"error": "Nothing to recycle (paths not found)."}
    total = sum(s for _, s in items)
    lines = "\n".join(f"  {os.path.basename(p)}  ({_human(s)})" for p, s in items[:15])
    more = f"\n  ...and {len(items) - 15} more" if len(items) > 15 else ""
    listfile = DATA / "last_recycle_request.txt"
    listfile.write_text("\n".join(f"{p}\t{_human(s)}" for p, s in items), encoding="utf-8")
    rec["progress"] = "waiting for the user to click Yes or No in the Tidy box on the computer (it may be behind other windows)"
    msg = (f"Claude wants to move {len(items)} item(s), {_human(total)}, to the {TRASH}.\n\n"
           f"Why: {reason}\n\n{lines}{more}\n\nFull list: {listfile}\n\nMove them to the {TRASH}?")
    if not _confirm_box("Tidy - OK to delete?" if MAC else "Tidy - OK to recycle?", msg):
        return {"status": "The user clicked No - nothing was removed."}
    job = _Job("recycle", "recycle")
    done, errs = [], []
    for p, s in items:
        try:
            send2trash(p)
            job.add({"op": "recycled", "path": p})
            done.append(p)
        except Exception as e:  # noqa
            errs.append({"path": p, "error": str(e)})
    job.save()
    return {"status": "recycled", "count": len(done), "freed": _human(sum(s for p, s in items if p in done)),
            "errors": errs, "note": f"Restore from the {TRASH} if needed."}


@mcp.tool()
def recycle(paths: list[str], reason: str) -> dict:
    """Send files/folders to the Recycle Bin (Mac: Trash; never permanent). A Yes/No box pops up on
    the computer listing what and why; nothing happens unless the user clicks Yes. Only call after you
    and the user agreed in chat on what to remove."""
    return _run("recycle", _do_recycle, paths, reason)


# ----------------------------------------------------------------- photo sheets (so Claude can see photos)
SHEETS_DIR = "_Tidy sheets"
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".jfif"}


def _do_sheets(rec, folder, recursive, per_sheet, thumb):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    root = Path(os.path.expanduser(folder))
    if not root.is_dir():
        return {"error": f"Not a folder: {root}"}
    photos, skipped = [], Counter()
    walker = os.walk(root, onerror=lambda e: None) if recursive else [(str(root), [], sorted(os.listdir(root)))]
    for dp, dns, fns in walker:
        dns[:] = sorted(d for d in dns if d != SHEETS_DIR)
        for f in sorted(fns):
            fp = os.path.join(dp, f)
            if not os.path.isfile(fp):
                continue
            e = _ext(f)
            if e in PHOTO_EXT:
                photos.append(fp)
            elif e in {".dng", ".nef", ".cr2", ".cr3", ".arw", ".r3d", ".heic"}:
                skipped[e] += 1
    out = root / SHEETS_DIR
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    (out / ".tidy-sheets").write_text("made by Tidy; safe to delete", encoding="utf-8")
    try:
        font = ImageFont.load_default(size=max(14, thumb // 12))
        small = ImageFont.load_default(size=max(11, thumb // 18))
    except TypeError:
        font = small = ImageFont.load_default()
    cols = 8 if per_sheet >= 32 else 6
    cell_w, cell_h = thumb + 8, thumb + 30
    index, sheets, unreadable = {}, [], []
    for s_i in range(0, len(photos), per_sheet):
        chunk = photos[s_i:s_i + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w + 8, rows * cell_h + 8), (24, 26, 28))
        draw = ImageDraw.Draw(sheet)
        for j, fp in enumerate(chunk):
            n = s_i + j + 1
            rec["progress"] = f"{n}/{len(photos)} photos"
            x, y = 8 + (j % cols) * cell_w, 8 + (j // cols) * cell_h
            try:
                with Image.open(fp) as im:
                    im.draft("RGB", (thumb * 2, thumb * 2))
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    im.thumbnail((thumb, thumb))
                    sheet.paste(im, (x + (thumb - im.width) // 2, y + (thumb - im.height) // 2))
            except Exception:
                unreadable.append(os.path.relpath(fp, root))
                draw.rectangle([x, y, x + thumb, y + thumb], outline=(120, 40, 40))
            draw.rectangle([x, y, x + thumb // 4, y + thumb // 9], fill=(22, 163, 124))
            draw.text((x + 4, y + 1), str(n), fill=(255, 255, 255), font=font)
            name = os.path.basename(fp)
            draw.text((x, y + thumb + 4), name if len(name) <= 30 else name[:27] + "...", fill=(190, 198, 196), font=small)
            index[n] = os.path.relpath(fp, root)
        p = out / f"sheet_{len(sheets) + 1:02d}.jpg"
        sheet.save(p, quality=80)
        sheets.append(str(p))
    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return {"folder": str(root), "photos": len(photos), "sheets": sheets, "numbers_to_files": str(out / "index.json"),
            "index": index if len(index) <= 600 else "too long here, read numbers_to_files",
            "not_photos_skipped": dict(skipped), "unreadable": unreadable[:50],
            "note": f"Each sheet shows {per_sheet} numbered thumbnails. Delete with clear_photo_sheets when done."}


@mcp.tool()
def photo_sheets(folder: str, recursive: bool = False, per_sheet: int = 48, thumb: int = 220) -> dict:
    """Make numbered contact sheets (small thumbnail grids, JPG) of the photos in a folder, so Claude can look at
    many photos quickly without copying the originals. Saved in '<folder>\\_Tidy sheets' with index.json
    (number -> file). Raw camera files are counted but not drawn. Remove with clear_photo_sheets."""
    per_sheet = max(6, min(int(per_sheet), 96))
    thumb = max(96, min(int(thumb), 400))
    return _run(f"photo sheets {folder}", _do_sheets, folder, recursive, per_sheet, thumb)


@mcp.tool()
def clear_photo_sheets(folder: str) -> dict:
    """Delete the '_Tidy sheets' folder that photo_sheets made in this folder (only a folder Tidy made)."""
    out = Path(os.path.expanduser(folder)) / SHEETS_DIR
    if not out.exists():
        return {"status": "nothing to clear"}
    if not (out / ".tidy-sheets").exists():
        return {"error": "That _Tidy sheets folder wasn't made by Tidy, so it was left alone."}
    shutil.rmtree(out)
    return {"status": "cleared", "folder": str(out)}


@mcp.tool()
def tidy_info() -> dict:
    """Tidy version, where logs live, and which locations are protected."""
    return {"version": VERSION, "jobs_folder": str(JOBS), "protected": _PROTECTED,
            "python": sys.version.split()[0]}


if __name__ == "__main__":
    if "--check" in sys.argv:
        print(f"Tidy {VERSION} OK")
    else:
        _log(f"Tidy {VERSION} started for Claude")
        mcp.run()
