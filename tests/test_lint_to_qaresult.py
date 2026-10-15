"""
lint -> QAResult: what a run found, as data.

The first of four suites over one shared input (tests/data/reporters.ttl). This one pins
what the checks decided; the other three pin how that same result is reported, as Markdown,
CTRF and DQV. Keeping them on one input means a change in a check shows up in all four, and
the three reporters can be read against this one.
"""

import rdflib

from scripts.ontology_qa import CHECKLIST

EX = "https://example.org/reporters#"

# What the fixture is built to fail, and by how much. Everything else must pass.
EXPECTED_FAILURES = {
    "Class without label": 1,
    "Class without description": 2,
    "Property without description": 1,
    "Classes with the same label": 1,
    "Isolated classes": 1,
    "Property without domain": 1,
    "Property without range": 1,
}


def test_every_check_in_the_checklist_ran(reporters_result):
    assert len(reporters_result.checks) == len(CHECKLIST)


def test_the_expected_checks_failed_and_no_others(reporters_result):
    assert {c.name: c.count for c in reporters_result.failures} == EXPECTED_FAILURES


def test_the_run_did_not_pass(reporters_result):
    assert not reporters_result.passed


def test_each_failure_names_the_offending_resource(reporters_result):
    assert reporters_result.get("Class without label").elements == f"{EX}Cat"
    assert reporters_result.get("Property without domain").elements == f"{EX}hasName"
    assert f"{EX}Mineral" in reporters_result.get("Isolated classes").elements


def test_a_duplicate_label_names_both_classes(reporters_result):
    elements = reporters_result.get("Classes with the same label").elements
    assert f"{EX}Dog" in elements and f"{EX}Hound" in elements


def test_failures_carry_structured_violations_for_the_rdf_report(reporters_result):
    # The DQV report is built from these, not from the rendered elements string.
    for check in reporters_result.failures:
        assert check.violations, f"{check.name} has no violation records"


def test_passing_checks_carry_no_violations(reporters_result):
    assert all(not c.violations for c in reporters_result.checks if c.passed)


def test_a_deprecated_class_is_skipped_by_the_annotation_checks(reporters_result):
    # :Beast has neither label nor description, and is owl:deprecated.
    for name in ("Class without label", "Class without description"):
        assert f"{EX}Beast" not in reporters_result.get(name).elements


def test_profiling_counts_the_input(reporters_result):
    profiling = reporters_result.profiling
    assert int(profiling["classCount"]) == 5     # Beast is deprecated, counted separately
    assert int(profiling["propertyCount"]) == 2
    assert int(profiling["instances"]) == 1
    assert int(profiling["deprecatedClasses"]) == 1
    assert profiling["filesProcessed"] == ["reporters.ttl"]


def test_profiling_counts_arrive_as_rdf_literals(reporters_result):
    # They come straight from the counting queries, so they are typed literals rather than
    # ints. Worth knowing before comparing one to a number; converting them would be a
    # deliberate change, not a tidy-up.
    assert isinstance(reporters_result.profiling["classCount"], rdflib.Literal)


def test_the_result_is_computed_on_the_declared_ontology(reporters_result):
    assert [d.iri for d in reporters_result.datasets] == [EX]


def test_the_configuration_that_ran_is_recorded(reporters_result):
    # Every check that ran is recorded with whether it was enabled, for the DQV report.
    checks = [s for s in reporters_result.settings if s.key == 'checks']
    assert len(checks) == len(CHECKLIST)
    assert all(s.enabled for s in checks)
