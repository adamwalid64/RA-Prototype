#!/usr/bin/env python3
"""
Single entrypoint to build a native distributable for the current OS.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def build_windows() -> None:
    run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "build_windows_package.ps1"),
        ]
    )
    print("\nWindows artifact:")
    print(f"  {ROOT / 'release' / 'RA-Launcher-windows.zip'}")


def build_macos() -> None:
    run(["bash", str(ROOT / "build_macos_package.sh")])
    print("\nmacOS artifact:")
    print(f"  {ROOT / 'release-macos' / 'RA-Launcher-macOS.zip'}")


def main() -> int:
    os_name = platform.system().lower()
    if os_name == "windows":
        build_windows()
        return 0
    if os_name == "darwin":
        build_macos()
        return 0

    print(
        "Unsupported OS for desktop packaging on this machine.\n"
        "Use Windows to build Windows .exe zips, and macOS to build Mac .app zips."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
