#!/usr/bin/env bash
#
# Run ontolint the way a user does: installed from a built wheel, from a directory
# that is not this repo.
#
# Why this exists. Every other CI step runs against the source tree (poetry installs
# ontolint editable), so package data missing from the wheel, or a path that only
# resolves inside the checkout, would pass CI and fail for everyone who installs it.
# Ontolint is more exposed than most: its SPARQL is read at import time, so missing
# package data is an immediate error, not a late one.
#
# Two properties do the work here, and both are easy to lose:
#   1. A REAL wheel install, not editable.
#   2. Run from a temp directory OUTSIDE the repo, so nothing can resolve back into the
#      source tree and quietly work.
#
# Usage: scripts/consumer_smoke.sh
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work" "$repo_root/dist-smoke"' EXIT

echo "==> Building a wheel"
rm -rf "$repo_root/dist-smoke"
poetry build -f wheel -o "$repo_root/dist-smoke"
wheel="$(ls "$repo_root"/dist-smoke/*.whl | head -1)"
echo "    $(basename "$wheel")"

echo "==> Installing it into a clean venv (not editable, no repo on the path)"
python -m venv "$work/venv"
if [ -d "$work/venv/bin" ]; then venv_bin="$work/venv/bin"; else venv_bin="$work/venv/Scripts"; fi
"$venv_bin/python" -m pip install --quiet --upgrade pip
"$venv_bin/python" -m pip install --quiet "$wheel"

echo "==> Copying a fixture out of the repo"
mkdir -p "$work/project"
cp "$repo_root/tests/example_failure.ttl" "$work/project/ontology.ttl"
cd "$work/project"

echo "==> Checking it is the INSTALLED ontolint, carrying its own data"
# Run from the fixture dir, never the repo: python prepends the working directory to
# sys.path, so `import ontolint` beside the source tree imports the source tree and this
# script silently tests nothing. The first assertion is what stops that regressing.
ONTOLINT_VENV="$work/venv" "$venv_bin/python" - <<'PY'
import os
from importlib.metadata import requires
from pathlib import Path

import rdflib

import ontolint
from ontolint import Config, lint
from ontolint.resolution import bundled_vocabularies

root = Path(ontolint.__file__).resolve().parent
venv = Path(os.environ["ONTOLINT_VENV"]).resolve()
assert venv in root.parents, (
    f"imported ontolint from {root}, not from the venv at {venv} — this script is "
    "testing the source tree, not the wheel")

queries = list((root / "sparql").glob("*.sparql"))
assert queries, "wheel is missing sparql/*.sparql"
vocabularies = bundled_vocabularies()
missing = [f for f in vocabularies.values() if not Path(f).is_file()]
assert vocabularies and not missing, f"wheel is missing bundled vocabularies: {missing}"
assert (root / "report" / "templates" / "ctrf-report.hbs").is_file(), "wheel is missing the CTRF template"

# The stdlib-named PyPI packages a published release must never pull in.
shadowing = [r for r in requires("ontolint") or [] if r.split()[0].lower() in ("argparse", "datetime")]
assert not shadowing, f"published metadata requires stdlib-shadowing packages: {shadowing}"

graph = rdflib.Graph().parse("ontology.ttl")
report = lint(graph, Config(uri_parser=lambda iri: rdflib.Graph()))
assert len(report) > 0, "lint() returned an empty report"
print(f"    ok: {root}")
print(f"    ok: {len(queries)} queries, {len(vocabularies)} bundled vocabularies, "
      f"lint() returned {len(report)} triples")
PY

echo "==> Running the ontolint command, from $work/project"
"$venv_bin/ontolint" ontology.ttl --ctrf-dir ctrf --dqv-dir dqv > report.md
ls ctrf/*.json >/dev/null 2>&1 || { echo "ontolint wrote no CTRF report"; exit 1; }
test -s dqv/ontolint-dqv.ttl || { echo "ontolint wrote no DQV report"; exit 1; }
test -s report.md || { echo "ontolint printed no Markdown report"; exit 1; }
echo "    ok: CTRF, DQV and $(wc -l < report.md) lines of Markdown"

echo "==> Running ontolint-report with its bundled template"
"$venv_bin/ontolint-report" --ctrf-dir ctrf --output-path summary.md >/dev/null
test -s summary.md || { echo "ontolint-report produced no summary"; exit 1; }
echo "    ok: $(wc -l < summary.md) lines of summary"

"$venv_bin/python" -m ontolint --help >/dev/null

echo
echo "PASS: ontolint works when installed."
