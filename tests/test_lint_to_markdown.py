"""
lint -> Markdown, over the same input as tests/test_lint_to_qaresult.py.

Markdown is not a projection of QAResult today: the per-check text is rendered inside each
check as it runs and collected into `result.logs`, and the load and config logs never reach
QAResult at all (see design.md). So the only boundary that exists is argv -> stdout, and
that is what this pins — including that the two agree about what failed.

When Markdown does become a projection, these assertions should survive the move unchanged.
"""

import re
from unittest.mock import patch

import pytest

from scripts.ontology_qa import main

EX = "https://example.org/reporters#"
# An rdflib blank node identifier: invented per parse, so it must never reach the report.
RAW_BNODE = re.compile(r'\bn[0-9a-f]{32}b\d+\b')


def _report(reporters_ttl, tmp_path, capsys, *args):
    with patch('sys.argv', ['ontology_qa.py', str(reporters_ttl), '--ctrf-dir', str(tmp_path), *args]):
        main()
    return capsys.readouterr().out


@pytest.fixture
def markdown(reporters_ttl, tmp_path, capsys):
    return _report(reporters_ttl, tmp_path, capsys)


def test_the_report_has_its_sections(markdown):
    for heading in ("# Ontology Quality Assurance",
                    "## Profiling Details",
                    "## Quality Assurance Checks"):
        assert heading in markdown


def test_the_input_is_named(markdown):
    assert "reporters.ttl" in markdown


def test_every_failing_check_is_reported_as_a_violation(markdown, reporters_result):
    # The same run, reported two ways: whatever the QAResult says failed must appear here.
    for check in reporters_result.failures:
        assert check.name in markdown, f"{check.name} failed but is not in the report"


def test_a_violation_names_the_offending_resource(markdown):
    assert f"{EX}Cat" in markdown      # class without a label
    assert f"{EX}hasName" in markdown  # property without domain or range


def test_a_passing_check_is_not_reported_as_a_violation(markdown):
    # :Animal is complete, so it should appear in no violation list.
    violations = [line for line in markdown.splitlines() if line.startswith("VIOLATION")]
    assert violations, "the fixture is meant to fail some checks"
    assert not any(f"{EX}Animal" in line for line in violations)


def test_both_profiling_and_qa_tables_are_rendered(markdown):
    assert "| Number of triples |" in markdown
    assert "| Ontology not declared |" in markdown


def test_no_blank_node_identifier_reaches_the_report(markdown):
    # They differ on every parse, so printing one makes the report vary run to run.
    assert not RAW_BNODE.search(markdown), "a raw blank node identifier reached the report"


def test_the_report_is_the_same_on_every_run(reporters_ttl, tmp_path, capsys):
    # Without this the output cannot be compared against an expected one, and diffs between
    # runs are unreadable.
    assert _report(reporters_ttl, tmp_path, capsys) == _report(reporters_ttl, tmp_path, capsys)


def test_the_counts_in_the_report_match_the_result(markdown, reporters_result):
    # Compared without depending on any check's wording: the numbers the report states
    # must be the numbers the run produced, one VIOLATION line per failing check.
    reported = sorted(int(n) for n in re.findall(r'^VIOLATION - Found (\d+)', markdown, re.M))

    assert reported == sorted(c.count for c in reporters_result.failures)
