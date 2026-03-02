#!/usr/bin/env python3
"""ctx-watch: warns when source files change without their .ctx companion being updated."""

import os
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
    def __init__(self, tracker: ChangeTracker, extensions: set[str], skip_dirs: set[str]) -> None:
        self.tracker = tracker
        self.extensions = extensions
        self.skip_dirs = skip_dirs

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
    tracker = ChangeTracker(grace)
    handler = CtxWatchHandler(tracker, extensions, skip_dirs)

    observer = Observer()
    observer.schedule(handler, path, recursive=True)
    observer.start()

    ext_display = ",".join(sorted(extensions))
    click.echo(
        f"{c.c}{c.b}ctx-watch{c.rst}: watching {Path(path).resolve()} "
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
@click.option("--no-color", is_flag=True, help="Disable ANSI color output.")
def status(
    path: str,
    since: int,
    changed_files: str | None,
    ext: str | None,
    ignore_dir: tuple[str, ...],
    reverse: bool,
    no_color: bool,
) -> None:
    """One-shot scan of PATH for source files modified without a .ctx update."""
    extensions = set(ext.split(",")) if ext else DEFAULT_EXTENSIONS
    skip_dirs = SKIP_DIRS | set(ignore_dir)
    c = _C(no_color)
    root = Path(path).resolve()
    drift: list[tuple[Path, str]] = []

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

    if changed_files is not None:
        # CI mode: check an explicit file list, no mtime filter
        raw = sys.stdin.read() if changed_files == "-" else changed_files
        file_list = raw.split()
        checked = 0
        for fpath_str in file_list:
            fpath = Path(fpath_str)
            if not fpath.is_absolute():
                fpath = root / fpath
            if not fpath.exists() or fpath.suffix.lstrip(".") not in extensions:
                continue
            checked += 1
            try:
                src_mtime = fpath.stat().st_mtime
            except OSError:
                continue
            ctx = _ctx_of(fpath)
            if not ctx.exists():
                drift.append((fpath, "no .ctx file"))
            elif ctx.stat().st_mtime < src_mtime:
                lag = src_mtime - ctx.stat().st_mtime
                drift.append((fpath, f".ctx is {_fmt_elapsed(lag)} older than source"))
        summary_ok = f"No drift detected in {checked} changed file(s)."
    else:
        # mtime-based walk
        cutoff = time.time() - since
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lstrip(".") not in extensions:
                    continue
                try:
                    src_mtime = fpath.stat().st_mtime
                except OSError:
                    continue
                if src_mtime < cutoff:
                    continue
                ctx = _ctx_of(fpath)
                if not ctx.exists():
                    drift.append((fpath, "no .ctx file"))
                elif ctx.stat().st_mtime < src_mtime:
                    lag = src_mtime - ctx.stat().st_mtime
                    drift.append((fpath, f".ctx is {_fmt_elapsed(lag)} older than source"))
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
