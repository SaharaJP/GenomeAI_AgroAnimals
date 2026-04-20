from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_installer_scripts_present() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "installers" / "linux" / "install.sh").exists()
    assert (root / "installers" / "linux" / "uninstall.sh").exists()
    assert (root / "installers" / "windows" / "GenomeAI_AgroAnimals_Setup.ps1").exists()
    assert (root / "installers" / "windows" / "GenomeAI_AgroAnimals_Uninstall.ps1").exists()


def test_launcher_dry_run() -> None:
    # The launcher must be testable without any removed legacy UI installed.
    cmd = [sys.executable, "-m", "genomeai.app_launcher", "--dry-run"]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "DRY_RUN" in out
    assert "PRIMARY_ENTRY:" in out
    assert "PRIMARY_ENTRY:" in out
    assert "WEB_URL:" in out
    assert "BACKEND:" in out
