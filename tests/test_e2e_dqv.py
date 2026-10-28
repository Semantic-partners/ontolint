"""
End-to-end DQV tests: ontology Turtle in, DQV Turtle out, both committed to the repo.

Each directory under tests/dqv/ is a case:

    tests/dqv/<case>/
        *.ttl           input ontologies (every .ttl except expected.ttl)
        .rdf-lint.yml   optional lint config (auto-detected, as in a real run)
        args.txt        optional extra CLI arguments, e.g. --per-file
        expected.ttl    the DQV report ontolint must produce

The effective configuration (olq:Configuration and its olq:Settings) is left out of every
case's report except CONFIG_CASE: an ontology with one failure and a .rdf-lint.yml that
exercises each kind of setting. The other reports show only the results.

The test runs ontolint's CLI (main()) from inside the case directory, so input paths and
config resolution match a real run, and compares the report with expected.ttl as RDF graphs.
main() takes no clock, so dqv.utc_now is patched to pin the report timestamp, and with it
every minted IRI.

After an intentional change to the report, regenerate the expected files and review the diff:

    UPDATE_GOLDEN=1 poetry run pytest tests/test_e2e_dqv.py
"""
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import rdflib

from scripts import dqv
from scripts.ontology_qa import main

CASES_DIR = Path(__file__).parent / 'dqv'
CASES = sorted(p.name for p in CASES_DIR.iterdir() if p.is_dir())
BASE_URI = 'https://example.org/qa#'
AT = datetime(2026, 9, 21, 14, 13, 20, tzinfo=timezone.utc)
CONFIG_CASE = 'configuration'
OLQ = rdflib.Namespace('https://ontolint.org/ns#')


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
        with patch('sys.argv', argv), patch.object(dqv, 'utc_now', lambda: AT):
            main()
    finally:
        os.chdir(cwd)
    return out_dir / 'actual.ttl'


def _without_configuration(g):
    """The report minus its effective configuration (see CONFIG_CASE)."""
    nodes = set(g.subjects(rdflib.RDF.type, OLQ.Configuration)) | set(g.subjects(rdflib.RDF.type, OLQ.Setting))
    for node in nodes:
        g.remove((node, None, None))
        g.remove((None, None, node))
    return g


CASE_PREFIX = 'file:///case/'


def _portable(g, case_dir):
    """Rewrite file: IRIs under the case directory to a fixed prefix.

    A report that names one of its input files names it by absolute path, so a golden
    written on one machine could only ever match that machine — green locally, red in CI.
    Nothing else in a report depends on where the checkout lives.
    """
    nt = g.serialize(format='nt')
    rewritten = nt.replace(case_dir.resolve().as_uri().rstrip('/') + '/', CASE_PREFIX)
    if rewritten == nt:
        return g
    out = rdflib.Graph()
    out.parse(data=rewritten, format='nt')
    return out


def _report(case, path, case_dir):
    g = rdflib.Graph().parse(path, format='turtle')
    g = _portable(g, case_dir)
    return g if case == CONFIG_CASE else _without_configuration(g)


def test_configuration_case_exists():
    assert CONFIG_CASE in CASES


def _ntriples(g):
    return sorted(line for line in g.serialize(format='nt').splitlines() if line.strip())


@pytest.mark.parametrize('case', CASES)
def test_dqv_report_matches_expected(case, tmp_path):
    case_dir = CASES_DIR / case
    expected_path = case_dir / 'expected.ttl'
    actual_path = _run_case(case_dir, tmp_path)

    actual = _report(case, actual_path, case_dir)
    if os.environ.get('UPDATE_GOLDEN'):
        expected_path.write_text(actual.serialize(format='turtle'), encoding='utf-8')
        pytest.skip(f"updated {expected_path.relative_to(CASES_DIR.parent.parent)}")

    assert expected_path.exists(), (
        f"missing {expected_path}; run UPDATE_GOLDEN=1 poetry run pytest tests/test_e2e_dqv.py")
    expected = rdflib.Graph().parse(expected_path, format='turtle')
    missing = sorted(set(_ntriples(expected)) - set(_ntriples(actual)))
    unexpected = sorted(set(_ntriples(actual)) - set(_ntriples(expected)))
    assert not missing and not unexpected, (
        f"DQV report for '{case}' differs from expected.ttl\n"
        + "".join(f"- {t}\n" for t in missing)
        + "".join(f"+ {t}\n" for t in unexpected)
        + "If the change is intended: UPDATE_GOLDEN=1 poetry run pytest tests/test_e2e_dqv.py")
