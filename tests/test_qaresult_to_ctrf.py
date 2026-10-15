"""
QAResult -> CTRF, from the same result as tests/test_lint_to_qaresult.py.

CTRF is a projection of the QAResult: one test entry per executed check, with the run's
summary. Nothing is re-derived from the graph here, so these assertions are about the
mapping alone.
"""

import json

from scripts.ontology_qa import write_ctrf_report


def _ctrf(result, tmp_path):
    report, _ = write_ctrf_report(result, str(tmp_path), 'report.json')
    assert json.loads((tmp_path / 'report.json').read_text()) == report, "file and return differ"
    return report['results']


def test_one_entry_per_executed_check(reporters_result, tmp_path):
    results = _ctrf(reporters_result, tmp_path)

    assert len(results['tests']) == len(reporters_result.checks)
    assert {t['name'] for t in results['tests']} == {c.name for c in reporters_result.checks}


def test_each_status_matches_the_check(reporters_result, tmp_path):
    results = _ctrf(reporters_result, tmp_path)
    expected = {c.name: ('passed' if c.passed else 'failed') for c in reporters_result.checks}

    assert {t['name']: t['status'] for t in results['tests']} == expected


def test_the_summary_counts_the_failures(reporters_result, tmp_path):
    results = _ctrf(reporters_result, tmp_path)
    summary = results['summary']

    assert summary['failed'] == len(reporters_result.failures)
    assert summary['passed'] == len(reporters_result.checks) - len(reporters_result.failures)
    assert summary['tests'] == len(reporters_result.checks)


def test_a_failed_entry_carries_the_offending_elements(reporters_result, tmp_path):
    results = _ctrf(reporters_result, tmp_path)
    entry = next(t for t in results['tests'] if t['name'] == "Class without label")

    assert entry['status'] == 'failed'
    assert reporters_result.get("Class without label").elements in json.dumps(entry)


def test_the_input_is_recorded(reporters_result, tmp_path):
    results = _ctrf(reporters_result, tmp_path)

    assert results['filesProcessed'] == ['reporters.ttl']


def test_the_report_names_the_tool(reporters_result, tmp_path):
    results = _ctrf(reporters_result, tmp_path)

    assert results['tool']['name']


def test_the_report_is_timestamped(reporters_result, tmp_path):
    results = _ctrf(reporters_result, tmp_path)

    assert results['timestamp']
