"""
QAResult -> CTRF, from the QAResult stored in tests/data/reporters_qaresult.py.

CTRF is a projection: one test case per executed check, plus the run's summary. These
assertions are about that mapping alone — `build_ctrf_report` returns the report, so
nothing here runs a check or reads a file.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from scripts.ontology_qa import build_ctrf_report, write_ctrf_report

@pytest.fixture(autouse=True)
def _pinned(pinned_clock):
    """Every test here builds at the epoch the stored report was built at."""


def _build(result):
    return build_ctrf_report(result)


@pytest.fixture
def ctrf(stored_qa_result):
    """The CTRF projection of the stored QAResult."""
    return _build(stored_qa_result)['results']


STORED_CTRF = Path(__file__).parent / 'data' / 'reporters_ctrf.json'


def test_it_builds_the_stored_report(stored_qa_result, stored_ctrf):
    """The projection, whole. Everything below says which part of it must hold, and why."""
    report = _build(stored_qa_result)
    if os.environ.get('UPDATE_GOLDEN'):
        STORED_CTRF.write_text(json.dumps(report, indent=4) + "\n", encoding='utf-8')
        pytest.skip(f"updated {STORED_CTRF.name}")

    assert report == stored_ctrf, (
        "the built report and tests/data/reporters_ctrf.json differ; regenerate with "
        "UPDATE_GOLDEN=1 poetry run pytest tests/test_qaresult_to_ctrf.py")


def test_one_entry_per_executed_check(ctrf, stored_qa_result):
    assert len(ctrf['tests']) == len(stored_qa_result.checks)
    assert {t['name'] for t in ctrf['tests']} == {c.name for c in stored_qa_result.checks}


def test_each_status_matches_the_check(ctrf, stored_qa_result):
    expected = {c.name: ('passed' if c.passed else 'failed') for c in stored_qa_result.checks}

    assert {t['name']: t['status'] for t in ctrf['tests']} == expected


def test_the_summary_counts_the_failures(ctrf, stored_qa_result):
    summary = ctrf['summary']

    assert summary['failed'] == len(stored_qa_result.failures)
    assert summary['passed'] == len(stored_qa_result.checks) - len(stored_qa_result.failures)
    assert summary['tests'] == len(stored_qa_result.checks)


def test_a_failed_entry_carries_the_offending_elements(ctrf, stored_qa_result):
    entry = next(t for t in ctrf['tests'] if t['name'] == "Class without label")

    assert entry['status'] == 'failed'
    assert entry['failure']['elements'] == stored_qa_result.get("Class without label").elements
    assert entry['failure']['violations'] == stored_qa_result.get("Class without label").count


def test_a_passing_entry_carries_no_failure(ctrf):
    passing = [t for t in ctrf['tests'] if t['status'] == 'passed']

    assert passing, "the stored result is meant to have passing checks too"
    assert all('failure' not in t for t in passing)


def test_the_input_is_recorded(ctrf):
    assert ctrf['filesProcessed'] == ['reporters.ttl']


def test_the_report_names_the_tool(ctrf):
    assert ctrf['tool']['name']


def test_the_report_carries_the_time_it_was_built(ctrf):
    assert ctrf['timestamp'] == "2026-10-15 09:30:00"


def test_two_builds_of_the_same_result_are_equal(stored_qa_result):
    assert _build(stored_qa_result) == _build(stored_qa_result)


def test_the_clock_defaults_to_now(stored_qa_result, monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    before = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    assert build_ctrf_report(stored_qa_result)['results']['timestamp'] >= before


def test_source_date_epoch_pins_the_timestamp(stored_qa_result, monkeypatch):
    # Pinned, the date can be asserted outright rather than bounded, which is what makes a
    # CTRF file comparable against an expected one. 1792056600 is 2026-10-15 09:30:00Z.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1792056600")

    assert build_ctrf_report(stored_qa_result)['results']['timestamp'] == "2026-10-15 09:30:00"


def test_two_builds_under_source_date_epoch_are_byte_identical(stored_qa_result, monkeypatch):
    # The whole point: with the clock pinned nothing else in the report varies, so the
    # serialised file is stable and a diff of two runs is empty.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1792056600")

    first = json.dumps(build_ctrf_report(stored_qa_result), indent=4)
    second = json.dumps(build_ctrf_report(stored_qa_result), indent=4)

    assert first == second


def test_writing_puts_the_given_report_on_disk(stored_qa_result, tmp_path):
    # The other half of the split: write takes the built report and only writes it.
    report = _build(stored_qa_result)

    log = write_ctrf_report(report, str(tmp_path), 'report.json')

    assert json.loads((tmp_path / 'report.json').read_text()) == report
    assert 'report.json' in log


def test_writing_falls_back_to_a_generated_filename(stored_qa_result, tmp_path):
    write_ctrf_report(_build(stored_qa_result), str(tmp_path), None)

    assert len(list(tmp_path.glob('*.json'))) == 1
