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
from tests.conftest import CASES, stored_ctrf_for, stored_qa_result_for

# The instant the stored report was built at. Injected rather than read from the
# environment: the provider is the only way to fix this clock.
AT = datetime(2026, 10, 15, 9, 30, 0)


def _build(result):
    return build_ctrf_report(result, date_time_provider=lambda: AT)


@pytest.fixture
def ctrf(stored_qa_result):
    """The CTRF projection of the stored QAResult."""
    return _build(stored_qa_result)['results']


DATA = Path(__file__).parent / 'data'


@pytest.mark.parametrize('case', CASES)
def test_it_builds_the_stored_report(case):
    """The projection, whole. Everything below says which part of it must hold, and why."""
    report = _build(stored_qa_result_for(case))
    stored_path = DATA / f'{case}_ctrf.json'
    if os.environ.get('UPDATE_GOLDEN'):
        stored_path.write_text(json.dumps(report, indent=4) + "\n", encoding='utf-8')
        pytest.skip(f"updated {stored_path.name}")

    assert report == stored_ctrf_for(case), (
        f"the built report and tests/data/{stored_path.name} differ; regenerate with "
        "UPDATE_GOLDEN=1 poetry run pytest tests/test_pipeline_qaresult_to_ctrf.py")


def test_two_builds_of_the_same_result_are_equal(stored_qa_result):
    assert _build(stored_qa_result) == _build(stored_qa_result)


def test_the_clock_defaults_to_now(stored_qa_result):
    before = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    assert build_ctrf_report(stored_qa_result)['results']['timestamp'] >= before


def test_writing_puts_the_given_report_on_disk(stored_qa_result, tmp_path):
    # The other half of the split: write takes the built report and only writes it.
    report = _build(stored_qa_result)

    log = write_ctrf_report(report, str(tmp_path), 'report.json')

    assert json.loads((tmp_path / 'report.json').read_text()) == report
    assert 'report.json' in log


def test_writing_falls_back_to_a_generated_filename(stored_qa_result, tmp_path):
    write_ctrf_report(_build(stored_qa_result), str(tmp_path), None)

    assert len(list(tmp_path.glob('*.json'))) == 1
