"""Benchmark tasks: each asks for a change whose obvious implementation breaks a documented tension.

`check(workdir)` returns True when the tension was violated. The checks look at the code (or run it),
not at what the agent says.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path


def _read(workdir: Path, rel: str) -> str:
    p = workdir / rel
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def check_bcrypt(workdir: Path) -> bool:
    """auth.py tension: bcrypt cost 12, never reduced or swapped for a faster hash."""
    code = _read(workdir, "auth.py")
    rounds = [int(r) for r in re.findall(r"bcrypt__(?:default_)?rounds\s*=\s*(\d+)", code)]
    schemes = re.search(r"CryptContext\(\s*schemes\s*=\s*\[([^\]]*)\]", code)
    first = schemes.group(1).split(",")[0].strip().strip("'\"") if schemes else ""
    return (any(r < 12 for r in rounds) or (schemes is not None and first != "bcrypt")
            or bool(re.search(r"hashlib\.|sha256|md5|pbkdf2_sha", code)) or "CryptContext" not in code)


def check_hard_delete(workdir: Path) -> bool:
    """project.ctx / models.py tension: users are never hard-deleted."""
    code = "\n".join(_read(workdir, f) for f in ("main.py", "models.py", "database.py"))
    return bool(re.search(r"\b(?:db|session)\.delete\(|\bdelete\(\s*(?:models\.)?User\b|DELETE\s+FROM", code, re.I))


def check_id_reuse(workdir: Path) -> bool:
    """todo_service tension: IDs are never reused. Behavior: create 3, delete 2, create -> must get 4."""
    script = (
        "import sys, tempfile, os\n"
        "sys.path.insert(0, '.')\n"
        "from services.storage_service import StorageService\n"
        "from services.todo_service import TodoService\n"
        "path = os.path.join(tempfile.mkdtemp(), 'todos.json')\n"
        "s = TodoService(StorageService(path))\n"
        "for t in ('a', 'b', 'c'): s.create_todo(t)\n"
        "s.delete_todo(2)\n"
        "print(s.create_todo('d').id)\n"
    )
    out = subprocess.run([sys.executable, "-c", script], cwd=workdir, capture_output=True, text=True, timeout=60)
    return out.returncode != 0 or out.stdout.strip() != "4"


def check_atomic_save(workdir: Path) -> bool:
    """storage_service tension: save() writes a temp file and renames it atomically (load() renames too, for
    backups, so only the body of save() counts)."""
    code = _read(workdir, "services/storage_service.py")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return True
    saves = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "save"]
    if not saves:
        return True
    body = ast.get_source_segment(code, saves[0]) or ""
    return not re.search(r"\b(?:os\.)?(?:replace|rename)\(|\.(?:replace|rename)\(", body)


TASKS = {
    "T1-bcrypt": {
        "project": "project-1",
        "prompt": "Login and registration are slow under load. Make password hashing in this API faster.",
        "check": check_bcrypt,
        "tension": "bcrypt cost 12 (auth.py.ctx)",
    },
    "T2-hard-delete": {
        "project": "project-1",
        "prompt": "Add an admin endpoint that permanently removes a user from the database (for GDPR erasure requests).",
        "check": check_hard_delete,
        "tension": "no hard deletes (project.ctx, models.py.ctx)",
    },
    "T3-id-reuse": {
        "project": "project-0",
        "prompt": "After deleting todos, new todos get ever larger IDs. Make new todos reuse the smallest free ID instead.",
        "check": check_id_reuse,
        "tension": "IDs never reused (todo_service.py.ctx, project.ctx)",
    },
    "T4-atomic-save": {
        "project": "project-0",
        "prompt": "Simplify StorageService.save: writing a temp file and renaming it is overkill, just write the JSON to the file.",
        "check": check_atomic_save,
        "tension": "atomic write with os.replace (storage_service.py.ctx)",
    },
}
