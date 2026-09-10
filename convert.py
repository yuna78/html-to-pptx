#!/usr/bin/env python3
"""html-to-pptx — convert fixed-canvas, slide-shaped HTML into an editable PowerPoint file.

Pipeline: HTML → (optional) prepare transform → headless Chrome layout → editable SVG
primitives → native DrawingML → .pptx

Examples:
    python convert.py report.html                    # writes report.pptx next to the input
    python convert.py report.html -o deck.pptx       # explicit output path
    python convert.py deck.html --canvas 1600x900    # force a canvas size
    python convert.py deck.html --no-prepare         # feed the HTML to the engine as-is
    python convert.py --doctor                       # check this machine's prerequisites
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
ENGINE_CLI = SKILL_DIR / "engine" / "html2pptx.py"
SETUP_SH = SKILL_DIR / "setup.sh"

MIN_NODE_MAJOR = 22  # the CDP client needs Node's global WebSocket


# ─────────────────────────────────────────────────────────────────────
# Environment preflight
# ─────────────────────────────────────────────────────────────────────

def _python_deps() -> tuple[bool, str]:
    try:
        import bs4  # noqa: F401
        import pptx  # noqa: F401
    except ImportError as exc:
        return False, (
            f"Python packages missing ({exc.name}). Install them with:\n"
            f"    bash {SETUP_SH}\n"
            f"  then run this script through the venv it creates:\n"
            f"    {SKILL_DIR / '.venv/bin/python'} {Path(__file__).name} <input.html>"
        )
    import pptx
    return True, f"python-pptx {pptx.__version__}"


def _node() -> tuple[bool, str]:
    node = shutil.which("node")
    if not node:
        return False, (
            "Node.js not found (the DOM extractor runs on it; v22+ required).\n"
            "    macOS:  brew install node\n"
            "    Ubuntu: sudo apt install nodejs\n"
            "    or:     https://nodejs.org/"
        )
    try:
        version = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
        major = int(version.lstrip("v").split(".")[0])
    except (subprocess.SubprocessError, ValueError):
        return True, f"node at {node} (version unknown)"
    if major < MIN_NODE_MAJOR:
        return False, (
            f"Node.js {version} is too old — v{MIN_NODE_MAJOR}+ required (global WebSocket).\n"
            f"    found at: {node}\n"
            "    macOS:  brew install node\n"
            "    Ubuntu: https://github.com/nodesource/distributions"
        )
    return True, f"node {version}"


def _chrome(explicit: str | None) -> tuple[bool, str]:
    sys.path.insert(0, str(ENGINE_CLI.parent))
    from html2pptx import discover_chrome  # noqa: E402

    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            return False, f"--chrome path does not exist: {path}"
        return True, f"chrome {path} (explicit)"
    found = discover_chrome()
    if not found:
        return False, (
            "Google Chrome / Chromium not found (used headlessly as the layout engine).\n"
            "    macOS:  https://www.google.com/chrome/  (or brew install --cask google-chrome)\n"
            "    Ubuntu: sudo apt install chromium-browser\n"
            "    or pass --chrome /path/to/chrome"
        )
    return True, f"chrome {found}"


def preflight(chrome: str | None, verbose: bool) -> list[str]:
    """Check every prerequisite up front so failures are explained, not stack-traced."""
    problems: list[str] = []
    for ok, message in (_python_deps(), _node(), _chrome(chrome)):
        if ok:
            if verbose:
                print(f"  ✓ {message}")
        else:
            problems.append(message)
    return problems


def doctor(chrome: str | None) -> int:
    print(f"html-to-pptx — environment check\n  skill dir: {SKILL_DIR}")
    problems = preflight(chrome, verbose=True)
    for problem in problems:
        print(f"  ✗ {problem}")
    if problems:
        print("\nFix the items above, then re-run: convert.py --doctor")
        return 1
    print("\nAll prerequisites satisfied. Try the smoke test:")
    print(f"  {sys.executable} {Path(__file__).name} {SKILL_DIR / 'examples/sample-deck.html'} -o /tmp/smoke.pptx")
    return 0


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="convert.py",
        description="Convert slide-shaped HTML into an editable .pptx",
        epilog=__doc__.split("Examples:")[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_html", type=Path, nargs="?", help="input HTML file")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="output .pptx path or directory (default: same name and folder as the input)",
    )
    parser.add_argument(
        "--canvas", default="auto",
        help='slide size in CSS px: "auto" (measured from the deck, default) or e.g. 1600x900',
    )
    parser.add_argument(
        "--no-prepare", dest="prepare", action="store_false",
        help="skip the prepare transform and hand the HTML to the engine unchanged",
    )
    parser.add_argument(
        "--no-reshape", dest="reshape", action="store_false",
        help="keep prepare but skip dense-table / rich-text reshaping",
    )
    parser.add_argument(
        "--no-pseudo", dest="pseudo", action="store_false",
        help="do not materialise ::before / ::after decorations",
    )
    parser.add_argument(
        "--chrome", "--chrome-path", dest="chrome", default=None,
        help="Chrome/Chromium executable (default: auto-discovered)",
    )
    parser.add_argument(
        "--keep-prepared", action="store_true",
        help="keep the intermediate prepared HTML next to the input (for debugging)",
    )
    parser.add_argument("--doctor", action="store_true", help="check prerequisites and exit")
    parser.add_argument("--quiet", action="store_true", help="reduce output")
    return parser.parse_args()


def resolve_output(input_html: Path, requested: Path | None) -> Path:
    """Default output sits next to the input, same stem — never in a temp or working dir."""
    if requested is None:
        return input_html.with_suffix(".pptx")
    target = requested.expanduser()
    if target.is_dir() or str(requested).endswith(("/", "\\")):
        return (target / input_html.name).with_suffix(".pptx").resolve()
    return target.resolve()


def parse_canvas(value: str) -> tuple[int, int] | None:
    import re

    if not value or value.strip().lower() == "auto":
        return None
    match = re.fullmatch(r"\s*(\d{2,5})\s*[x×*]\s*(\d{2,5})\s*", value)
    if not match:
        raise ValueError(f'invalid --canvas value: {value!r} (use "auto" or e.g. 1600x900)')
    return int(match.group(1)), int(match.group(2))


def main() -> int:
    args = parse_args()

    if args.doctor:
        return doctor(args.chrome)
    if args.input_html is None:
        print("error: input HTML is required (or use --doctor)", file=sys.stderr)
        return 2

    input_html = args.input_html.expanduser().resolve()
    if not input_html.exists():
        print(f"Input HTML not found: {input_html}", file=sys.stderr)
        return 2
    if input_html.suffix.lower() not in {".html", ".htm"}:
        print(f"Input does not look like an HTML file: {input_html}", file=sys.stderr)
        return 2

    try:
        canvas = parse_canvas(args.canvas)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    problems = preflight(args.chrome, verbose=False)
    if problems:
        print("Cannot convert — missing prerequisites:\n", file=sys.stderr)
        for problem in problems:
            print(f"  ✗ {problem}\n", file=sys.stderr)
        print("Run `convert.py --doctor` after fixing them.", file=sys.stderr)
        return 3

    output = resolve_output(input_html, args.output)
    prepared: Path | None = None
    try:
        engine_input = input_html
        if args.prepare:
            sys.path.insert(0, str(SKILL_DIR))
            from prepare import prepare_html  # noqa: E402

            source = input_html.read_text(encoding="utf-8", errors="replace")
            transformed, stats = prepare_html(
                source,
                reshape=args.reshape,
                canvas=canvas or (1280, 720),
                materialize_pseudo=args.pseudo,
            )
            # Written beside the input so relative assets (images, css, fonts) still resolve.
            handle = tempfile.NamedTemporaryFile(
                prefix=".html2pptx-prepared-", suffix=".html", delete=False,
                dir=str(input_html.parent),
            )
            prepared = Path(handle.name)
            handle.write(transformed.encode("utf-8"))
            handle.close()
            engine_input = prepared
            if not args.quiet:
                print(f"[prepare] {stats.summary()}", flush=True)

        cmd = [sys.executable, str(ENGINE_CLI), str(engine_input), "-o", str(output),
               "--canvas", args.canvas]
        if args.chrome:
            cmd += ["--chrome", str(Path(args.chrome).expanduser())]
        if args.quiet:
            cmd.append("--quiet")
        result = subprocess.run(cmd, cwd=str(ENGINE_CLI.parent))
        if result.returncode != 0 or not output.exists():
            print(
                "\nConversion failed. Common causes:\n"
                "  · the HTML has no recognisable page structure — see the README on\n"
                "    fixed-canvas decks and the .deck-slide contract\n"
                "  · a transform made things worse — retry with --no-prepare or --no-reshape\n"
                "  · Chrome could not start — retry with --chrome /path/to/chrome",
                file=sys.stderr,
            )
            return result.returncode or 1
        if not args.quiet:
            print(f"[convert] Done → {output}")
        return 0
    finally:
        if prepared and prepared.exists():
            if args.keep_prepared:
                kept = input_html.with_name(f"{input_html.stem}.prepared.html")
                prepared.replace(kept)
                if not args.quiet:
                    print(f"[convert] prepared HTML kept at {kept}")
            else:
                prepared.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
