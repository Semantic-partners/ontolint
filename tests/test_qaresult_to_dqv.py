"""
QAResult -> DQV, from the same result as tests/test_lint_to_qaresult.py.

The DQV report is the structured form of a run: a measurement per failed check, each
violation a sh:ValidationResult naming the resource, and a conformance roll-up per dataset.
Unlike Markdown and CTRF it describes the whole run rather than one result, which is why
set-level findings can only live here.

tests/test_dqv.py covers the vocabulary and minting rules; this is about the projection.
"""

import os
from pathlib import Path

import pytest
import rdflib
from rdflib.compare import graph_diff

from scripts.dqv import build_dqv_graph, DQV_METRICS, DQV, OLQ, DEFAULT_BASE_URI

EX = "https://example.org/reporters#"
ROLLUP = rdflib.URIRef(f"{DEFAULT_BASE_URI}metric-ontolint-conformance")


def _metric(check_key):
    return rdflib.URIRef(f"{DEFAULT_BASE_URI}metric-{DQV_METRICS[check_key][0]}")


def _measured(graph):
    """{metric slug: value} for every check measurement, excluding the roll-up."""
    return {
        str(graph.value(m, DQV.isMeasurementOf)).rsplit('metric-', 1)[-1]:
            graph.value(m, DQV.value).toPython()
        for m in graph.subjects(rdflib.RDF.type, DQV.QualityMeasurement)
        if graph.value(m, DQV.isMeasurementOf) != ROLLUP
    }


@pytest.fixture(autouse=True)
def _pinned(pinned_clock):
    """Every test here builds at the epoch the stored report was built at."""


STORED_DQV = Path(__file__).parent / 'data' / 'reporters_dqv.ttl'


def test_it_builds_the_stored_report(stored_qa_result, stored_dqv):
    """The projection, whole. Everything below says which part of it must hold, and why."""
    graph = build_dqv_graph([stored_qa_result])
    if os.environ.get('UPDATE_GOLDEN'):
        STORED_DQV.write_text(graph.serialize(format='turtle'), encoding='utf-8')
        pytest.skip(f"updated {STORED_DQV.name}")

    in_report, in_stored = graph_diff(graph, stored_dqv)[1:]
    assert not list(in_report) and not list(in_stored), _diff_message(in_report, in_stored)


def _diff_message(in_report, in_stored):
    def lines(label, triples):
        shown = sorted(f"    {s} {p} {o}" for s, p, o in triples)[:10]
        return f"  {label} ({len(triples)}):\n" + "\n".join(shown) if len(triples) else ""
    return ("the built report and tests/data/reporters_dqv.ttl differ\n"
            + lines("only in the built report", in_report)
            + lines("only in the stored report", in_stored)
            + "\n  regenerate with: UPDATE_GOLDEN=1 poetry run pytest tests/test_qaresult_to_dqv.py")


def test_a_measurement_per_failed_check_and_no_others(stored_qa_result):
    graph = build_dqv_graph([stored_qa_result])
    expected = {DQV_METRICS[c.key][0]: c.count for c in stored_qa_result.failures}

    assert _measured(graph) == expected


def test_a_passing_check_is_measured_only_by_the_rollup(stored_qa_result):
    # Taken from the result rather than named, so extending the fixture to make a check
    # fail does not quietly leave this asserting nothing.
    passing = [c for c in stored_qa_result.checks if c.passed]
    assert passing, "the fixture is meant to leave some checks clean"
    graph = build_dqv_graph([stored_qa_result])

    for check in passing:
        assert not list(graph.subjects(DQV.isMeasurementOf, _metric(check.key))), (
            f"{check.name} passed but was measured")


def test_every_executed_check_is_declared_as_a_metric(stored_qa_result):
    # Including the ones that passed, so a consumer can tell "ran and was clean" from
    # "never ran".
    graph = build_dqv_graph([stored_qa_result])

    for check in stored_qa_result.checks:
        assert (_metric(check.key), rdflib.RDF.type, DQV.Metric) in graph


def test_measurements_are_computed_on_the_declared_ontology(stored_qa_result):
    graph = build_dqv_graph([stored_qa_result])

    assert {str(o) for o in graph.objects(None, DQV.computedOn)} == {EX}


def test_each_violation_names_the_offending_resource(stored_qa_result):
    graph = build_dqv_graph([stored_qa_result])
    [measurement] = list(graph.subjects(DQV.isMeasurementOf, _metric('missingClassLabel')))

    focus = {str(graph.value(v, rdflib.SH.focusNode)) for v in graph.objects(measurement, OLQ.violation)}
    assert focus == {f"{EX}Cat"}


def test_a_violation_is_a_shacl_validation_result(stored_qa_result):
    graph = build_dqv_graph([stored_qa_result])
    [measurement] = list(graph.subjects(DQV.isMeasurementOf, _metric('isolatedClasses')))
    [violation] = list(graph.objects(measurement, OLQ.violation))

    assert (violation, rdflib.RDF.type, rdflib.SH.ValidationResult) in graph
    assert graph.value(violation, rdflib.SH.resultSeverity)


def test_the_rollup_counts_the_failed_checks(stored_qa_result):
    graph = build_dqv_graph([stored_qa_result])
    [rollup] = list(graph.subjects(DQV.isMeasurementOf, ROLLUP))

    assert graph.value(rollup, DQV.value).toPython() == len(stored_qa_result.failures)
    assert graph.value(rollup, OLQ.conforms).toPython() is False


def test_the_configuration_that_ran_is_recorded(stored_qa_result):
    graph = build_dqv_graph([stored_qa_result])

    [configuration] = list(graph.subjects(rdflib.RDF.type, OLQ.Configuration))
    assert list(graph.objects(configuration, OLQ.setting))


def test_the_graph_has_no_blank_nodes(stored_qa_result):
    # Every node is minted or skolemized, so a report can be merged with another without
    # its blank nodes colliding.
    graph = build_dqv_graph([stored_qa_result])

    assert not [t for triple in graph for t in triple if isinstance(t, rdflib.BNode)]
