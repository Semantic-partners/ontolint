"""
End-to-end DQV tests: ontology Turtle in, DQV Turtle out, both committed to the repo.

Each directory under tests/dqv/ is a case:

    tests/dqv/<case>/
        *.ttl           input ontologies (every .ttl except expected.ttl)
        .rdf-lint.yml   optional lint config (auto-detected, as in a real run)
        args.txt        optional extra CLI arguments, e.g. --per-file
        expected.ttl    the DQV report ontolint must produce

The test runs ontolint's CLI (main()) from inside the case directory, so input paths and
config resolution match a real run, and compares the report with expected.ttl as RDF graphs.
The report timestamp is pinned with SOURCE_DATE_EPOCH, so minted IRIs are reproducible.

After an intentional change to the report, regenerate the expected files and review the diff:

    UPDATE_GOLDEN=1 poetry run pytest tests/test_dqv_e2e.py
"""
import os
import shlex
from pathlib import Path
from unittest.mock import patch

import pytest
import rdflib

from scripts.ontology_qa import main

CASES_DIR = Path(__file__).parent / 'dqv'
CASES = sorted(p.name for p in CASES_DIR.iterdir() if p.is_dir())
BASE_URI = 'https://example.org/qa#'
EPOCH = '1790000000'  # 2026-09-21T14:13:20Z


def test_cases_exist():
    # An empty parameter list makes pytest skip the golden test rather than fail, so a
    # missing or empty tests/dqv/ would otherwise pass silently.
    assert CASES, f"no DQV cases found in {CASES_DIR}"
    for case in CASES:
        assert (CASES_DIR / case / 'expected.ttl').exists(), f"{case} has no expected.ttl"


def _run_case(case_dir, out_dir):
    inputs = sorted(p.name for p in case_dir.glob('*.ttl') if p.name != 'expected.ttl')
    assert inputs, f"no input .ttl files in {case_dir}"
    extra = shlex.split((case_dir / 'args.txt').read_text()) if (case_dir / 'args.txt').exists() else []
    argv = ['ontology_qa.py', *inputs, *extra,
            '--ctrf-dir', str(out_dir / 'ctrf'),
            '--dqv-dir', str(out_dir), '--dqv-filename', 'actual.ttl',
            '--base-uri', BASE_URI]
    cwd = os.getcwd()
    os.chdir(case_dir)
    try:
        with patch('sys.argv', argv), patch.dict(os.environ, {'SOURCE_DATE_EPOCH': EPOCH}):
            main()
    finally:
        os.chdir(cwd)
    return out_dir / 'actual.ttl'


def _ntriples(g):
    return sorted(line for line in g.serialize(format='nt').splitlines() if line.strip())


@pytest.mark.parametrize('case', CASES)
def test_dqv_report_matches_expected(case, tmp_path):
    case_dir = CASES_DIR / case
    expected_path = case_dir / 'expected.ttl'
    actual_path = _run_case(case_dir, tmp_path)

    if os.environ.get('UPDATE_GOLDEN'):
        expected_path.write_text(actual_path.read_text())
        pytest.skip(f"updated {expected_path.relative_to(CASES_DIR.parent.parent)}")

    assert expected_path.exists(), (
        f"missing {expected_path}; run UPDATE_GOLDEN=1 poetry run pytest tests/test_dqv_e2e.py")
    actual = rdflib.Graph().parse(actual_path, format='turtle')
    expected = rdflib.Graph().parse(expected_path, format='turtle')
    missing = sorted(set(_ntriples(expected)) - set(_ntriples(actual)))
    unexpected = sorted(set(_ntriples(actual)) - set(_ntriples(expected)))
    assert not missing and not unexpected, (
        f"DQV report for '{case}' differs from expected.ttl\n"
        + "".join(f"- {t}\n" for t in missing)
        + "".join(f"+ {t}\n" for t in unexpected)
        + "If the change is intended: UPDATE_GOLDEN=1 poetry run pytest tests/test_dqv_e2e.py")
