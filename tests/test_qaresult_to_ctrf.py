"""
QAResult -> CTRF, from the QAResult stored in tests/data/reporters_qaresult.py.

CTRF is a projection: one test case per executed check, plus the run's summary. These
assertions are about that mapping alone — `build_ctrf_report` returns the report, so
nothing here runs a check or reads a file.
"""

import json

import pytest

from scripts.ontology_qa import build_ctrf_report, write_ctrf_report


@pytest.fixture
def ctrf(stored_result):
    """The CTRF projection of the stored QAResult."""
    return build_ctrf_report(stored_result)['results']


def test_one_entry_per_executed_check(ctrf, stored_result):
    assert len(ctrf['tests']) == len(stored_result.checks)
    assert {t['name'] for t in ctrf['tests']} == {c.name for c in stored_result.checks}


def test_each_status_matches_the_check(ctrf, stored_result):
    expected = {c.name: ('passed' if c.passed else 'failed') for c in stored_result.checks}

    assert {t['name']: t['status'] for t in ctrf['tests']} == expected


def test_the_summary_counts_the_failures(ctrf, stored_result):
    summary = ctrf['summary']

    assert summary['failed'] == len(stored_result.failures)
    assert summary['passed'] == len(stored_result.checks) - len(stored_result.failures)
    assert summary['tests'] == len(stored_result.checks)


def test_a_failed_entry_carries_the_offending_elements(ctrf, stored_result):
    entry = next(t for t in ctrf['tests'] if t['name'] == "Class without label")

    assert entry['status'] == 'failed'
    assert entry['failure']['elements'] == stored_result.get("Class without label").elements
    assert entry['failure']['violations'] == stored_result.get("Class without label").count


def test_a_passing_entry_carries_no_failure(ctrf):
    passing = [t for t in ctrf['tests'] if t['status'] == 'passed']

    assert passing, "the stored result is meant to have passing checks too"
    assert all('failure' not in t for t in passing)


def test_the_input_is_recorded(ctrf):
    assert ctrf['filesProcessed'] == ['reporters.ttl']


def test_the_report_names_the_tool(ctrf):
    assert ctrf['tool']['name']


def test_the_report_is_timestamped(ctrf):
    assert ctrf['timestamp']


def test_writing_puts_the_given_report_on_disk(stored_result, tmp_path):
    # The other half of the split: write takes the built report and only writes it.
    report = build_ctrf_report(stored_result)

    log = write_ctrf_report(report, str(tmp_path), 'report.json')

    assert json.loads((tmp_path / 'report.json').read_text()) == report
    assert 'report.json' in log


def test_writing_falls_back_to_a_generated_filename(stored_result, tmp_path):
    write_ctrf_report(build_ctrf_report(stored_result), str(tmp_path), None)

    assert len(list(tmp_path.glob('*.json'))) == 1
