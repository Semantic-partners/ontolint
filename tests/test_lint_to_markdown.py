"""
lint -> Markdown: linting `tests/data/reporters.ttl` renders the Markdown stored in
`tests/data/reporters_markdown.py`.

The stored text is the expectation, exactly as the stored QAResult is for the checks. The
assertions after it are not a second expectation — they say *why* parts of it must hold, so
a failure explains itself instead of handing over a 189-line diff.

Markdown is the one reporter that is not a projection of QAResult: the per-check text is
rendered inside each check as it runs (see design.md). When that moves, the stored text
stays as it is and only the way it is produced changes — which is how the move gets checked.
"""

import re

# An rdflib blank node identifier: invented per parse, so it must never reach the report.
RAW_BNODE = re.compile(r'\bn[0-9a-f]{32}b\d+\b')


def test_a_lint_renders_the_stored_markdown(rendered_markdown, stored_markdown):
    assert rendered_markdown == stored_markdown


def test_it_renders_the_same_text_every_time(render_markdown):
    # Each call reparses: blank node identifiers and SPARQL row order differ between
    # parses, and without this the stored text could not be an expectation at all.
    assert render_markdown() == render_markdown()


def test_every_failing_check_is_reported_as_a_violation(stored_markdown, stored_result):
    # The stored Markdown and the stored QAResult describe the same run, so they must agree
    # about what failed.
    for check in stored_result.failures:
        assert check.name in stored_markdown, f"{check.name} failed but is not in the report"


def test_the_counts_in_the_report_match_the_result(stored_markdown, stored_result):
    reported = sorted(int(n) for n in re.findall(r'^VIOLATION - Found (\d+)', stored_markdown, re.M))

    assert reported == sorted(c.count for c in stored_result.failures)


def test_a_violation_names_the_offending_resource(stored_markdown, stored_result):
    for element in stored_result.get("Class without label").elements.split(",<br> "):
        assert element in stored_markdown


def test_a_passing_check_is_not_reported_as_a_violation(stored_markdown):
    violations = [line for line in stored_markdown.splitlines() if line.startswith("VIOLATION")]

    assert violations, "the fixture is meant to fail some checks"
    assert not any("https://example.org/reporters#Animal" in line for line in violations)


def test_no_blank_node_identifier_reaches_the_report(stored_markdown):
    assert not RAW_BNODE.search(stored_markdown), "a raw blank node identifier reached the report"


def test_the_report_has_its_sections(stored_markdown):
    assert "## Profiling Details" in stored_markdown
    assert "## Quality Assurance Checks" in stored_markdown
    assert "| Number of triples |" in stored_markdown
    assert "| Ontology not declared |" in stored_markdown
