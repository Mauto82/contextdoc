#!/usr/bin/env python3
"""ctx-watch: warns when source files change without their .ctx companion being updated."""

import fnmatch
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── constants ─────────────────────────────────────────────────────────────────

DEFAULT_EXTENSIONS = {"py", "js", "ts", "go", "rb", "java", "rs", "php"}
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache"}

YELLOW = "\033[33m"
RED    = "\033[31m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
    h, rem = divmod(int(seconds), 3600)
    return f"{h}h {rem // 60}m"


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _should_skip(path: Path, skip_dirs: set[str]) -> bool:
    return any(part in skip_dirs for part in path.parts)


def _ctx_of(source: Path) -> Path:
    return source.parent / (source.name + ".ctx")


def _load_ignore_patterns(root: Path) -> list[str]:
    ignore_file = root / ".ctxignore"
    if not ignore_file.exists():
        return []
    patterns = []
    for line in ignore_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _is_ignored(path: Path, root: Path, patterns: list[str]) -> bool:
    if not patterns:
        return False
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)
    name = path.name
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern):
            return True
        if "/" not in pattern and fnmatch.fnmatch(name, pattern):
            return True
    return False


# ── git-based drift ───────────────────────────────────────────────────────────

class GitHistory:
    """Drift from git history instead of mtimes, which a clone, checkout or rebase makes meaningless.

    A source drifts when commits after the last commit that touched its .ctx changed it, or when
    it has uncommitted changes and its .ctx doesn't. Built from one `git log` and one `git status`.
    """

    def __init__(self, toplevel: Path, commits_by_file: dict[str, list[int]], dirty: set[str]) -> None:
        self.toplevel = toplevel
        self.commits_by_file = commits_by_file  # repo-relative path -> commit indices, 0 = newest
        self.dirty = dirty                      # repo-relative paths: staged, unstaged or untracked

    @classmethod
    def load(cls, path: Path) -> "GitHistory | None":
        """The history of the repository containing PATH, or None outside git."""
        def git(*args: str) -> str | None:
            try:
                out = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, check=True)
            except (OSError, subprocess.CalledProcessError):
                return None
            return out.stdout

        top = git("rev-parse", "--show-toplevel")
        if top is None:
            return None
        commits_by_file: dict[str, list[int]] = {}
        log = git("log", "--topo-order", "--no-renames", "--name-only", "--format=%x00%H") or ""
        for index, block in enumerate(b for b in log.split("\x00") if b.strip()):
            for name in block.splitlines()[1:]:
                if name:
                    commits_by_file.setdefault(name, []).append(index)
        dirty: set[str] = set()
        status_out = git("status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all") or ""
        for entry in status_out.split("\x00"):
            if len(entry) > 3:
                dirty.add(entry[3:])
        return cls(Path(top.strip()).resolve(), commits_by_file, dirty)

    def _rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.toplevel).as_posix()

    def is_dirty(self, path: Path) -> bool:
        return self._rel(path) in self.dirty

    def drift(self, source: Path, ctx: Path) -> str | None:
        """Why SOURCE drifted from its existing CTX, or None if it didn't."""
        if self.is_dirty(ctx):
            return None  # the .ctx is being updated alongside
        if self.is_dirty(source):
            return "source has uncommitted changes, .ctx doesn't"
        ctx_commits = self.commits_by_file.get(self._rel(ctx))
        if not ctx_commits:
            return None
        newer = [i for i in self.commits_by_file.get(self._rel(source), []) if i < ctx_commits[0]]
        if newer:
            return f".ctx not updated in {len(newer)} commit(s) that changed the source"
        return None

    def changed_since(self, base: str) -> list[Path] | None:
        """Files changed between BASE and HEAD (merge-base diff), plus uncommitted ones."""
        try:
            out = subprocess.run(["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
                                 cwd=self.toplevel, capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            return None
        names = {n for n in out.splitlines() if n} | self.dirty
        return [self.toplevel / n for n in sorted(names)]


# ── change tracker ────────────────────────────────────────────────────────────

class ChangeTracker:
    """Tracks source file changes and .ctx update state within a watch session."""

    def __init__(self, grace_period: int) -> None:
        self.grace_period = grace_period
        self._source_changes: dict[str, float] = {}   # path -> monotonic time
        self._ctx_updated: set[str] = set()            # source paths with updated .ctx
        self._intents: set[str] = set()                # source paths with .ctx but no source yet

    def record_source(self, path: str) -> None:
        self._source_changes[path] = time.monotonic()
        self._ctx_updated.discard(path)
        self._intents.discard(path)        # source was created: clear any pending intent

    def record_ctx(self, source_path: str) -> None:
        self._ctx_updated.add(source_path)

    def record_intent(self, source_path: str) -> None:
        """Called when a .ctx is saved but its source file does not exist."""
        self._intents.add(source_path)

    def changed_at(self, path: str) -> float:
        return self._source_changes.get(path, -1.0)

    def drift_files(self):
        """Yield (source_path, elapsed_seconds) for files past the grace period without a .ctx update."""
        now = time.monotonic()
        for path, changed_at in list(self._source_changes.items()):
            elapsed = now - changed_at
            if elapsed >= self.grace_period and path not in self._ctx_updated:
                yield path, elapsed

    def intent_files(self):
        """Yield source paths where a .ctx spec exists but the source has not been created."""
        for path in list(self._intents):
            if Path(path).exists():
                self._intents.discard(path)   # source appeared in the meantime
            else:
                yield path


# ── watchdog handler ──────────────────────────────────────────────────────────

class CtxWatchHandler(FileSystemEventHandler):
    def __init__(
        self,
        tracker: ChangeTracker,
        extensions: set[str],
        skip_dirs: set[str],
        ignore_patterns: list[str],
        root: Path,
    ) -> None:
        self.tracker = tracker
        self.extensions = extensions
        self.skip_dirs = skip_dirs
        self.ignore_patterns = ignore_patterns
        self.root = root

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_created(self, event) -> None:
        # Editors that write via tmp+rename trigger created, not modified
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def _handle(self, path: Path) -> None:
        if _should_skip(path, self.skip_dirs):
            return
        if _is_ignored(path, self.root, self.ignore_patterns):
            return
        name = path.name
        if name.endswith(".ctx"):
            source = path.parent / name[:-4]   # strip trailing .ctx
            self.tracker.record_ctx(str(source))
            if not source.exists():
                self.tracker.record_intent(str(source))
            return
        ext = path.suffix.lstrip(".")
        if ext in self.extensions:
            self.tracker.record_source(str(path))


# ── color helper ──────────────────────────────────────────────────────────────

class _C:
    def __init__(self, disabled: bool) -> None:
        if disabled:
            self.y = self.r = self.g = self.c = self.b = self.rst = ""
        else:
            self.y   = YELLOW
            self.r   = RED
            self.g   = GREEN
            self.c   = CYAN
            self.b   = BOLD
            self.rst = RESET


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """ctx-watch: monitor .ctx companions for source file drift."""


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--grace", default=300, show_default=True,
              help="Seconds before reporting drift.")
@click.option("--ext", default=None,
              help="Comma-separated extensions to watch (default: py,js,ts,go,rb,java,rs,php).")
@click.option("--ignore-dir", multiple=True, metavar="DIR",
              help="Additional directory name to skip (repeatable, e.g. --ignore-dir dist).")
@click.option("--no-color", is_flag=True, help="Disable ANSI color output.")
def watch(path: str, grace: int, ext: str | None, ignore_dir: tuple[str, ...], no_color: bool) -> None:
    """Watch PATH for source changes without .ctx updates. Blocking (Ctrl+C to stop)."""
    extensions = set(ext.split(",")) if ext else DEFAULT_EXTENSIONS
    skip_dirs = SKIP_DIRS | set(ignore_dir)
    c = _C(no_color)
    root_path = Path(path).resolve()
    ignore_patterns = _load_ignore_patterns(root_path)
    tracker = ChangeTracker(grace)
    handler = CtxWatchHandler(tracker, extensions, skip_dirs, ignore_patterns, root_path)

    observer = Observer()
    observer.schedule(handler, path, recursive=True)
    observer.start()

    ext_display = ",".join(sorted(extensions))
    click.echo(
        f"{c.c}{c.b}ctx-watch{c.rst}: watching {root_path} "
        f"(grace: {grace}s, extensions: {ext_display})"
    )

    # Maps source_path -> monotonic time when last reported.
    # A file re-triggers if its source was modified after the last report.
    reported: dict[str, float] = {}
    intent_reported: set[str] = set()

    try:
        while True:
            time.sleep(5)
            for source_path, elapsed in tracker.drift_files():
                changed_at = tracker.changed_at(source_path)
                if changed_at <= reported.get(source_path, -1.0):
                    continue  # already reported for this modification cycle
                reported[source_path] = time.monotonic()
                ctx = _ctx_of(Path(source_path))
                if ctx.exists():
                    detail = f"{source_path}.ctx not updated ({_fmt_elapsed(elapsed)} ago)"
                else:
                    detail = f"{source_path}.ctx does not exist"
                click.echo(f"[{_timestamp()}] {c.y}⚠{c.rst}  {source_path} — {detail}")
            for source_path in tracker.intent_files():
                if source_path in intent_reported:
                    continue
                intent_reported.add(source_path)
                click.echo(
                    f"[{_timestamp()}] {c.c}→{c.rst}  {source_path} — "
                    f".ctx spec exists, source not yet implemented"
                )
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

    still_drifting = sum(1 for _ in tracker.drift_files())
    still_intent = sum(1 for _ in tracker.intent_files())
    parts = []
    if still_drifting:
        parts.append(f"{still_drifting} file(s) with stale context")
    if still_intent:
        parts.append(f"{still_intent} spec(s) without implementation")
    if parts:
        click.echo(f"\n{c.y}ctx-watch: stopped. {', '.join(parts)}.{c.rst}")
    else:
        click.echo(f"\n{c.g}ctx-watch: stopped. All .ctx companions up to date.{c.rst}")


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--since", default=3600, show_default=True,
              help="Look back N seconds for recently modified files (ignored when --changed-files is set).")
@click.option("--changed-files", default=None, metavar="FILES",
              help="Whitespace-separated list of files to check. Pass '-' to read from stdin. "
                   "Skips mtime filter — use in CI: --changed-files \"$(git diff --name-only HEAD~1)\".")
@click.option("--ext", default=None,
              help="Comma-separated extensions to check.")
@click.option("--ignore-dir", multiple=True, metavar="DIR",
              help="Additional directory name to skip (repeatable).")
@click.option("--reverse", is_flag=True,
              help="Intent-first mode: find .ctx specs without a corresponding source file.")
@click.option("--base", default=None, metavar="REF",
              help="Git only: check the files changed since REF (merge base) plus uncommitted ones, e.g. --base origin/main in CI.")
@click.option("--mtime", "use_mtime", is_flag=True,
              help="Use file modification times even inside a git repository (the pre-git behavior).")
@click.option("--no-color", is_flag=True, help="Disable ANSI color output.")
def status(
    path: str,
    since: int,
    changed_files: str | None,
    ext: str | None,
    ignore_dir: tuple[str, ...],
    reverse: bool,
    base: str | None,
    use_mtime: bool,
    no_color: bool,
) -> None:
    """One-shot scan of PATH for source files modified without a .ctx update.

    Inside a git repository drift comes from the history: a source drifts when commits after the
    last .ctx commit changed it, or when it has uncommitted changes and its .ctx doesn't. Outside
    git (or with --mtime) it comes from file modification times, limited to --since.
    """
    extensions = set(ext.split(",")) if ext else DEFAULT_EXTENSIONS
    skip_dirs = SKIP_DIRS | set(ignore_dir)
    c = _C(no_color)
    root = Path(path).resolve()
    ignore_patterns = _load_ignore_patterns(root)
    drift: list[tuple[Path, str]] = []
    history = None if (use_mtime or reverse) else GitHistory.load(root)
    if base is not None and history is None:
        click.echo(f"{c.r}--base needs a git repository (and no --mtime).{c.rst}")
        sys.exit(2)

    if reverse:
        # Intent-first mode: find .ctx specs with missing or lagging source
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fname in filenames:
                if not fname.endswith(".ctx"):
                    continue
                source_name = fname[:-4]                           # e.g. "auth.py"
                source_ext = Path(source_name).suffix.lstrip(".")  # e.g. "py"
                if source_ext not in extensions:
                    continue                                        # skip project.ctx etc.
                ctx_path = Path(dirpath) / fname
                source = ctx_path.parent / source_name
                if _is_ignored(source, root, ignore_patterns):
                    continue
                try:
                    ctx_mtime = ctx_path.stat().st_mtime
                except OSError:
                    continue
                if not source.exists():
                    drift.append((source, "source file does not exist"))
                elif source.stat().st_mtime < ctx_mtime:
                    lead = ctx_mtime - source.stat().st_mtime
                    drift.append((source, f"spec is {_fmt_elapsed(lead)} ahead of source"))
        if not drift:
            click.echo(f"{c.g}✓{c.rst}  No unimplemented specs found.")
            sys.exit(0)
        click.echo(f"{c.c}{len(drift)} spec(s) without implementation:{c.rst}")
        for fpath, reason in sorted(drift):
            rel = fpath.relative_to(root) if fpath.is_relative_to(root) else fpath
            click.echo(f"  {c.c}→{c.rst}  {rel}  ({reason})")
        sys.exit(1)

    def check(fpath: Path, report_missing: bool) -> None:
        """Drift of one watched source file, by git history when available, else by mtime."""
        ctx = _ctx_of(fpath)
        if not ctx.exists():
            if report_missing:
                drift.append((fpath, "no .ctx file"))
            return
        if history is not None:
            reason = history.drift(fpath, ctx)
            if reason:
                drift.append((fpath, reason))
            return
        try:
            src_mtime = fpath.stat().st_mtime
        except OSError:
            return
        if ctx.stat().st_mtime < src_mtime:
            lag = src_mtime - ctx.stat().st_mtime
            drift.append((fpath, f".ctx is {_fmt_elapsed(lag)} older than source"))

    def watched(fpath: Path) -> bool:
        return (fpath.exists() and fpath.suffix.lstrip(".") in extensions
                and not _should_skip(fpath.relative_to(root) if fpath.is_relative_to(root) else fpath, skip_dirs)
                and not _is_ignored(fpath, root, ignore_patterns))

    if changed_files is not None or base is not None:
        # explicit list (CI): every listed source is checked, a missing .ctx included
        if base is not None:
            file_list = [p for p in (history.changed_since(base) or []) if p.is_relative_to(root)]
        else:
            raw = sys.stdin.read() if changed_files == "-" else changed_files
            file_list = [Path(f) if Path(f).is_absolute() else root / f for f in raw.split()]
        checked = 0
        for fpath in file_list:
            if not watched(fpath):
                continue
            checked += 1
            check(fpath, report_missing=True)
        summary_ok = f"No drift detected in {checked} changed file(s)."
    elif history is not None:
        # git: the state of the whole tree, no time window. A missing .ctx is not reported here:
        # ContextDoc expects a .ctx only where it adds value (use --base or --changed-files for that).
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lstrip(".") not in extensions or _is_ignored(fpath, root, ignore_patterns):
                    continue
                check(fpath, report_missing=False)
        summary_ok = "No drift detected (git history)."
    else:
        # mtime-based walk, limited to files modified in the last --since seconds
        cutoff = time.time() - since
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lstrip(".") not in extensions:
                    continue
                if _is_ignored(fpath, root, ignore_patterns):
                    continue
                try:
                    if fpath.stat().st_mtime < cutoff:
                        continue
                except OSError:
                    continue
                check(fpath, report_missing=True)
        summary_ok = f"No drift detected in the last {_fmt_elapsed(since)}."

    if not drift:
        click.echo(f"{c.g}✓{c.rst}  {summary_ok}")
        sys.exit(0)

    click.echo(f"{c.y}{len(drift)} file(s) with stale context:{c.rst}")
    for fpath, reason in sorted(drift):
        rel = fpath.relative_to(root) if fpath.is_relative_to(root) else fpath
        click.echo(f"  {c.y}⚠{c.rst}  {rel}  ({reason})")
    sys.exit(1)


if __name__ == "__main__":
    cli()
