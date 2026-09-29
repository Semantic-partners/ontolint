import os
from datetime import datetime, timezone

import rdflib
from rdflib import RDF, RDFS, SKOS, URIRef, Literal

from scripts.ontology_qa import (
    run_qa, build_dqv_graph, write_dqv_report, file_iri,
    CHECKLIST, DQV_METRICS, DQV, OLQ, PROV, DEFAULT_BASE_URI,
)

EX = rdflib.Namespace("http://example.org#")
TS = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
MISSING_IMPORT = "http://example.org/missing-import"


def _no_fetch(uri):
    raise Exception(f"no network in tests: {uri}")


def _qa(graph, **kwargs):
    kwargs.setdefault("uri_parser", _no_fetch)
    return run_qa(graph, **kwargs)


def _metric(slug, base=DEFAULT_BASE_URI):
    return URIRef(f"{base}metric-{slug}")


def _measurement(g, slug, dataset=None):
    """The single measurement of the given metric (optionally on the given dataset)."""
    found = [
        m for m in g.subjects(DQV.isMeasurementOf, _metric(slug))
        if dataset is None or (m, DQV.computedOn, URIRef(dataset)) in g
    ]
    assert len(found) == 1, f"expected one {slug} measurement, found {len(found)}"
    return found[0]


def _violation_resources(g, measurement):
    return {str(g.value(v, OLQ.resource)) for v in g.objects(measurement, OLQ.violation)}


# ── metric catalogue ──────────────────────────────────────────────────────────

def test_every_check_has_dqv_metric_metadata():
    assert {key for *_, key in CHECKLIST} == set(DQV_METRICS)


def test_metric_slugs_are_unique():
    slugs = [slug for slug, *_ in DQV_METRICS.values()]
    assert len(slugs) == len(set(slugs))


def test_metrics_and_dimensions_are_declared(make_graph):
    g = build_dqv_graph([_qa(make_graph(": a owl:Ontology . :Dog a owl:Class .")), ], timestamp=TS)
    m = _metric("properties-same-label")
    assert (m, RDF.type, DQV.Metric) in g
    assert g.value(m, SKOS.prefLabel) == Literal("Properties with the same label")
    assert g.value(m, RDFS.label) == Literal("Properties with the same label")
    assert g.value(m, SKOS.definition) is not None
    assert g.value(m, OLQ.severity) == Literal("error")
    dim = g.value(m, DQV.inDimension)
    assert (dim, RDF.type, DQV.Dimension) in g
    assert g.value(dim, RDFS.label) is not None


# ── measurements ──────────────────────────────────────────────────────────────

def test_violations_attributed_to_check_and_dataset(make_graph):
    # The worked example from the spec: same-label properties and an unresolvable import,
    # each reported under its own check with exactly its offending resources.
    g = make_graph(f"""
    : a owl:Ontology ; owl:imports <{MISSING_IMPORT}> .
    :assignedTo a owl:ObjectProperty ; rdfs:label "assigned to" .
    :delegatedTo a owl:ObjectProperty ; rdfs:label "assigned to" .
    """)
    result = _qa(g, local_imports={MISSING_IMPORT: "/nonexistent/import.ttl"})
    dqv = build_dqv_graph([result], timestamp=TS)

    same_label = _measurement(dqv, "properties-same-label", "http://example.org#")
    assert (same_label, RDF.type, DQV.QualityMeasurement) in dqv
    assert dqv.value(same_label, DQV.value) == Literal(1)
    assert dqv.value(same_label, OLQ.conforms) == Literal(False)
    assert dqv.value(same_label, OLQ.severity) == Literal("error")
    assert _violation_resources(dqv, same_label) == {str(EX.assignedTo), str(EX.delegatedTo)}

    imports = _measurement(dqv, "unresolvable-imports", "http://example.org#")
    assert dqv.value(imports, DQV.value) == Literal(1)
    assert _violation_resources(dqv, imports) == {MISSING_IMPORT}


def test_same_label_violations_are_structured(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :assignedTo a owl:ObjectProperty ; rdfs:label "assigned to"@en .
    :delegatedTo a owl:ObjectProperty ; rdfs:label "assigned to"@en .
    """)
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    m = _measurement(dqv, "properties-same-label")
    node = next(v for v in dqv.objects(m, OLQ.violation) if dqv.value(v, OLQ.resource) == EX.assignedTo)
    assert (node, RDF.type, OLQ.Violation) in dqv
    assert dqv.value(node, OLQ.value) == Literal("assigned to", lang="en")
    assert dqv.value(node, OLQ.relatedResource) == EX.delegatedTo
    assert "delegatedTo" in str(dqv.value(node, RDFS.comment))


def test_import_violation_related_to_importing_ontology(make_graph):
    g = make_graph(f": a owl:Ontology ; owl:imports <{MISSING_IMPORT}> . :Dog a owl:Class .")
    dqv = build_dqv_graph([_qa(g, local_imports={MISSING_IMPORT: "/nonexistent/import.ttl"})], timestamp=TS)
    node = dqv.value(_measurement(dqv, "unresolvable-imports"), OLQ.violation)
    assert dqv.value(node, OLQ.relatedResource) == URIRef("http://example.org#")


def test_passing_checks_have_no_measurement(make_graph):
    g = make_graph(": a owl:Ontology . :Dog a owl:Class .")
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    assert not list(dqv.subjects(DQV.isMeasurementOf, _metric("properties-same-label")))


def test_rollup_measurement_for_clean_dataset(make_graph):
    g = make_graph("""
    : a owl:Ontology ; rdfs:comment "Clean." .
    """)
    result = _qa(g)
    assert result.passed, [c.name for c in result.failures]
    dqv = build_dqv_graph([result], timestamp=TS)
    rollup = _measurement(dqv, "ontolint-conformance", "http://example.org#")
    assert dqv.value(rollup, DQV.value) == Literal(0)
    assert dqv.value(rollup, OLQ.conforms) == Literal(True)
    # Only the roll-up measurement is emitted for a clean dataset.
    assert set(dqv.subjects(RDF.type, DQV.QualityMeasurement)) == {rollup}


def test_rollup_counts_failed_checks(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog a owl:Class .
    """)
    result = _qa(g)
    assert result.failures
    dqv = build_dqv_graph([result], timestamp=TS)
    rollup = _measurement(dqv, "ontolint-conformance")
    assert dqv.value(rollup, DQV.value) == Literal(len(result.failures))
    assert dqv.value(rollup, OLQ.conforms) == Literal(False)


# ── datasets ──────────────────────────────────────────────────────────────────

def test_dataset_labelled_from_ontology(make_graph):
    g = make_graph(': a owl:Ontology ; rdfs:label "Activities" .')
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    assert dqv.value(URIRef("http://example.org#"), RDFS.label) == Literal("Activities")


def test_dataset_falls_back_to_file_iri_without_ontology(make_graph, tmp_path):
    path = str(tmp_path / "no-ontology.ttl")
    g = make_graph(":Dog a owl:Class .")
    dqv = build_dqv_graph([_qa(g, files_processed=[path])], timestamp=TS)
    rollup = _measurement(dqv, "ontolint-conformance")
    assert dqv.value(rollup, DQV.computedOn) == URIRef(file_iri(path))
    assert file_iri(path).startswith("file://")


def test_same_ontology_iri_in_two_runs_gives_distinct_measurements(make_graph):
    g = make_graph(": a owl:Ontology . :Dog a owl:Class .")
    r1 = _qa(g, files_processed=["a.ttl"])
    r2 = _qa(g, files_processed=["b.ttl"])
    dqv = build_dqv_graph([r1, r2], timestamp=TS)
    assert len(list(dqv.subjects(DQV.isMeasurementOf, _metric("ontolint-conformance")))) == 2


# ── IRIs ──────────────────────────────────────────────────────────────────────

def test_no_blank_nodes_and_turtle_round_trips(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :a a owl:ObjectProperty ; rdfs:label "x" .
    :b a owl:ObjectProperty ; rdfs:label "x" .
    :Dog rdfs:subClassOf :Undeclared .
    """)
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    assert not any(isinstance(t, rdflib.BNode) for triple in dqv for t in triple)
    reparsed = rdflib.Graph().parse(data=dqv.serialize(format="turtle"), format="turtle")
    assert len(reparsed) == len(dqv)


def test_instance_iris_minted_under_base_uri(make_graph):
    g = make_graph(": a owl:Ontology . :Dog a owl:Class .")
    dqv = build_dqv_graph([_qa(g)], base_uri="https://kh.example/qa/", timestamp=TS)
    assessment = dqv.value(predicate=RDF.type, object=DQV.QualityMetadata, any=False)
    assert str(assessment).startswith("https://kh.example/qa/assessment-")
    for m in dqv.subjects(RDF.type, DQV.QualityMeasurement):
        assert str(m).startswith("https://kh.example/qa/measurement-")
    for v in dqv.subjects(RDF.type, OLQ.Violation):
        assert str(v).startswith("https://kh.example/qa/violation-")
    # Metrics and dimensions are minted under the base URI too, by slug.
    metric = _metric("classes-missing-label", "https://kh.example/qa/")
    assert (metric, RDF.type, DQV.Metric) in dqv
    assert str(dqv.value(metric, DQV.inDimension)).startswith("https://kh.example/qa/dimension-")


def test_olq_namespace_holds_no_instance_data(make_graph):
    g = make_graph(": a owl:Ontology . :Dog a owl:Class .")
    dqv = build_dqv_graph([_qa(g)], base_uri="https://kh.example/qa/", timestamp=TS)
    subjects = {str(s) for s in dqv.subjects()}
    assert not any(s.startswith(str(OLQ)) for s in subjects)


def test_default_base_uri(make_graph):
    g = make_graph(": a owl:Ontology .")
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    assessment = dqv.value(predicate=RDF.type, object=DQV.QualityMetadata, any=False)
    assert str(assessment).startswith(DEFAULT_BASE_URI)


def test_base_uri_without_separator_gets_slash(make_graph):
    g = make_graph(": a owl:Ontology .")
    dqv = build_dqv_graph([_qa(g)], base_uri="https://kh.example/qa", timestamp=TS)
    assessment = dqv.value(predicate=RDF.type, object=DQV.QualityMetadata, any=False)
    assert str(assessment).startswith("https://kh.example/qa/assessment-")


def test_iris_are_deterministic_per_run_and_unique_across_runs(make_graph):
    g = make_graph(": a owl:Ontology . :Dog a owl:Class .")
    result = _qa(g)
    first = set(build_dqv_graph([result], timestamp=TS).subjects(RDF.type, DQV.QualityMeasurement))
    again = set(build_dqv_graph([result], timestamp=TS).subjects(RDF.type, DQV.QualityMeasurement))
    later = set(build_dqv_graph([result], timestamp=TS.replace(hour=11)).subjects(RDF.type, DQV.QualityMeasurement))
    assert first == again
    assert first.isdisjoint(later)


def test_assessment_links_all_measurements(make_graph):
    g = make_graph(": a owl:Ontology . :Dog a owl:Class .")
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    assessment = dqv.value(predicate=RDF.type, object=DQV.QualityMetadata, any=False)
    assert dqv.value(assessment, PROV.generatedAtTime).toPython() == TS
    linked = set(dqv.objects(assessment, DQV.hasQualityMeasurement))
    assert linked == set(dqv.subjects(RDF.type, DQV.QualityMeasurement))


def test_write_dqv_report(make_graph, tmp_path):
    g = make_graph(": a owl:Ontology .")
    _, log = write_dqv_report([_qa(g)], str(tmp_path), "out.ttl", timestamp=TS)
    out = tmp_path / "out.ttl"
    assert out.exists()
    assert str(out) in log
    rdflib.Graph().parse(str(out), format="turtle")
