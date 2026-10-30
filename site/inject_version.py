#!/usr/bin/env python3
"""Stamp site/*.html asset query strings with the current git short SHA."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

SITE = Path(__file__).resolve().parent


def git_short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=SITE.parent,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "dev"


def inject(html: str, sha: str) -> str:
    def css_repl(match: re.Match[str]) -> str:
        path = match.group(1)
        return f'href="{path}?v={sha}"'

    def src_repl(match: re.Match[str]) -> str:
        path = match.group(1)
        return f'src="{path}?v={sha}"'

    html = re.sub(r'href="([^"?]+\.css)"', css_repl, html)
    html = re.sub(r'src="([^"?]+\.(?:png|svg|js))"', src_repl, html)
    return html


def main() -> None:
    sha = git_short_sha()
    src = SITE / "index.template.html"
    dst = SITE / "index.html"
    text = src.read_text(encoding="utf-8")
    dst.write_text(inject(text, sha), encoding="utf-8")
    print(f"Wrote {dst} (v={sha})")


if __name__ == "__main__":
    main()
