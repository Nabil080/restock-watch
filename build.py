"""Builds dist/RestockWatch-<version>.zip: the one-file exe in a RestockWatch folder.

    python build.py           version taken from the git tag (v1.0.0 -> 1.0.0)
    python build.py 1.0.0
"""

import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent


def version() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    tag = subprocess.run(["git", "describe", "--tags", "--abbrev=0"], capture_output=True, text=True, cwd=ROOT)
    return tag.stdout.strip().removeprefix("v") or "dev"


def main() -> None:
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "restock_watch.py",
        "--onefile", "--console", "--noconfirm", "--clean",
        "--name", "RestockWatch",
        "--add-data", "extract_offers.js;.",
        "--add-data", "config.example.json;.",
    ], check=True, cwd=ROOT)

    zip_path = ROOT / "dist" / f"RestockWatch-{version()}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "dist" / "RestockWatch.exe", "RestockWatch/RestockWatch.exe")
    print(f"Built {zip_path}")


if __name__ == "__main__":
    main()
