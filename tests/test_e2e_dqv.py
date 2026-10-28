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
main() takes no clock and no path resolver, so two things are pinned at the point they are
made: dqv.utc_now, which fixes the report timestamp and with it every minted IRI, and
dqv.file_iri, which names an input relative to the case directory instead of to this
checkout. Both are hashed into minted IRIs, so neither can be corrected after the fact.
dqv.mint_id is replaced too, so a node is named after what it is about rather than after
the run — see design.md for what that leaves these reports testing.

After an intentional change to the report, regenerate the expected files and review the diff:

    UPDATE_GOLDEN=1 poetry run pytest tests/test_e2e_dqv.py
"""
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import rdflib

from scripts import dqv
from scripts.ontology_qa import main
from tests.golden import stable_mint_id

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


CASE_PREFIX = 'file:///case/'


def _case_file_iri(path):
    """
    The IRI naming an input, relative to the case directory rather than the checkout.

    A report that names one of its input files names it by file: IRI, which is an absolute
    path — and the violation IRI minted from it *hashes* that path, so a golden written
    here would match only this machine. Rewriting the report afterwards does not help: the
    hash is taken before anyone can rewrite anything. So the IRI is pinned where it is
    made, the same way the clock is pinned with dqv.utc_now.

    _run_case has chdir'd into the case directory, so a path under the working directory
    is one of the case's own files; anything else keeps its real IRI.
    """
    resolved = Path(path).resolve()
    try:
        return CASE_PREFIX + resolved.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return resolved.as_uri()


def _run_case(case_dir, out_dir, mint=stable_mint_id):
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
        with patch('sys.argv', argv), patch.object(dqv, 'utc_now', lambda: AT), \
             patch.object(dqv, 'file_iri', _case_file_iri), \
             patch.object(dqv, 'mint_id', mint):
            main()
    finally:
        os.chdir(cwd)
    return out_dir / 'actual.ttl'


REAL_NAME = re.compile(r'#(assessment|measurement|violation|dataset|configuration|setting|bnode)-[0-9a-f]{16}$')


def test_a_real_run_mints_hashed_iris(tmp_path):
    """
    The goldens replace dqv.mint_id, so nothing else here runs the real one end to end.

    Without this the naming could stop being wired into a CLI run — or stay replaced by
    accident — and every stored report would still match. It asserts the shape production
    emits, not any particular name.
    """
    report = _run_case(CASES_DIR / 'clean', tmp_path, mint=dqv.mint_id)
    g = rdflib.Graph().parse(report, format='turtle')
    minted = [str(s) for s in set(g.subjects()) if str(s).startswith(BASE_URI)
              and not str(s).startswith(f"{BASE_URI}metric-")
              and not str(s).startswith(f"{BASE_URI}dimension-")]
    assert minted, "a report with no minted instance IRIs at all"
    assert all(REAL_NAME.search(name) for name in minted), sorted(minted)[:5]

    # And the substitute really is substituting: the golden's names are not these.
    stored = rdflib.Graph().parse(CASES_DIR / 'clean' / 'expected.ttl', format='turtle')
    assert not (set(minted) & {str(s) for s in stored.subjects()})


def _without_configuration(g):
    """The report minus its effective configuration (see CONFIG_CASE)."""
    nodes = set(g.subjects(rdflib.RDF.type, OLQ.Configuration)) | set(g.subjects(rdflib.RDF.type, OLQ.Setting))
    for node in nodes:
        g.remove((node, None, None))
        g.remove((None, None, node))
    return g


def _report(case, path):
    g = rdflib.Graph().parse(path, format='turtle')
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

    actual = _report(case, actual_path)
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
