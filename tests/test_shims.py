"""The deprecated scripts/ shims: they run the installed commands, or say how to install them."""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SHIMS = [("ontology_qa.py", "ontolint"), ("generate_custom_report.py", "ontolint-report")]


@pytest.mark.parametrize("script, command", SHIMS)
def test_a_shim_runs_the_installed_command(script, command):
    run = subprocess.run([sys.executable, str(SCRIPTS / script), "--help"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "usage:" in run.stdout


@pytest.mark.parametrize("script, command", SHIMS)
def test_a_shim_says_how_to_install_ontolint_when_it_is_missing(script, command):
    # -S leaves site-packages off sys.path: an interpreter where ontolint was never installed.
    run = subprocess.run([sys.executable, "-S", str(SCRIPTS / script), "--help"],
                         capture_output=True, text=True)
    assert run.returncode == 2
    assert "Traceback" not in run.stderr
    assert "ontolint is not installed" in run.stderr
    assert f"pip install {SCRIPTS.parent}" in run.stderr
    assert f"run `{command}` instead" in run.stderr
