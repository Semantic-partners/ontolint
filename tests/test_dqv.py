from datetime import datetime, timezone

import rdflib
from rdflib import RDF, RDFS, SKOS, URIRef, Literal

import pytest

from scripts.ontology_qa import run_qa, _same_label_records, CHECKLIST
from scripts.dqv import (
    build_dqv_graph, write_dqv_report, file_iri, check_dqv_filename,
    DQV_METRICS, DQV, OLQ, PROV, SH, DEFAULT_BASE_URI,
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


def _measurement(g, slug, dataset=None, base=DEFAULT_BASE_URI):
    """The single measurement of the given metric (optionally on the given dataset)."""
    found = [
        m for m in g.subjects(DQV.isMeasurementOf, _metric(slug, base))
        if dataset is None or (m, DQV.computedOn, URIRef(dataset)) in g
    ]
    assert len(found) == 1, f"expected one {slug} measurement, found {len(found)}"
    return found[0]


def _violation_resources(g, measurement):
    return {str(g.value(v, SH.focusNode)) for v in g.objects(measurement, OLQ.violation)}


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
    assert g.value(m, OLQ.severity) == SH.Violation
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
    assert dqv.value(same_label, OLQ.severity) == SH.Violation
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
    node = next(v for v in dqv.objects(m, OLQ.violation) if dqv.value(v, SH.focusNode) == EX.assignedTo)
    assert (node, RDF.type, SH.ValidationResult) in dqv
    assert dqv.value(node, SH.value) == Literal("assigned to", lang="en")
    assert dqv.value(node, OLQ.relatedResource) == EX.delegatedTo
    assert "delegatedTo" in str(dqv.value(node, SH.resultMessage))
    assert dqv.value(node, SH.resultSeverity) == SH.Violation
    assert dqv.value(node, SH.sourceConstraintComponent) == SH.SPARQLConstraintComponent


def test_same_label_in_two_languages_gives_distinct_violations(make_graph):
    # "x"@en and "x"@fr are separate same-label clashes; hashing only the lexical form
    # would merge them into one node with two sh:value.
    g = make_graph("""
    : a owl:Ontology .
    :a a owl:ObjectProperty ; rdfs:label "x"@en, "x"@fr .
    :b a owl:ObjectProperty ; rdfs:label "x"@en, "x"@fr .
    """)
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    nodes = list(dqv.objects(_measurement(dqv, "properties-same-label"), OLQ.violation))
    assert len(nodes) == 4
    for node in nodes:
        assert len(list(dqv.objects(node, SH.value))) == 1
    values = {(dqv.value(n, SH.focusNode), dqv.value(n, SH.value)) for n in nodes}
    assert values == {(p, Literal("x", lang=lang)) for p in (EX.a, EX.b) for lang in ("en", "fr")}


def test_same_label_with_different_datatypes_gives_distinct_violations(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :a a owl:ObjectProperty ; rdfs:label "1", "1"^^<http://www.w3.org/2001/XMLSchema#integer> .
    :b a owl:ObjectProperty ; rdfs:label "1", "1"^^<http://www.w3.org/2001/XMLSchema#integer> .
    """)
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    nodes = list(dqv.objects(_measurement(dqv, "properties-same-label"), OLQ.violation))
    assert len(nodes) == 4
    assert all(len(list(dqv.objects(n, SH.value))) == 1 for n in nodes)


def test_import_violation_related_to_importing_ontology(make_graph):
    g = make_graph(f": a owl:Ontology ; owl:imports <{MISSING_IMPORT}> . :Dog a owl:Class .")
    dqv = build_dqv_graph([_qa(g, local_imports={MISSING_IMPORT: "/nonexistent/import.ttl"})], timestamp=TS)
    node = dqv.value(_measurement(dqv, "unresolvable-imports"), OLQ.violation)
    assert dqv.value(node, OLQ.relatedResource) == URIRef("http://example.org#")


def test_warning_severity_uses_shacl_warning(make_graph):
    g = make_graph(": a owl:Ontology . :Dog a owl:Class ; rdfs:label \"Dog\" .")
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    m = _measurement(dqv, "classes-missing-description")
    assert dqv.value(m, OLQ.severity) == SH.Warning
    assert dqv.value(dqv.value(m, OLQ.violation), SH.resultSeverity) == SH.Warning


def test_same_failing_import_from_two_ontologies_gives_two_violations(make_graph):
    g = make_graph(f"""
    : a owl:Ontology ; owl:imports <{MISSING_IMPORT}> .
    <http://example.org/two#> a owl:Ontology ; owl:imports <{MISSING_IMPORT}> .
    """)
    result = _qa(g, local_imports={MISSING_IMPORT: "/nonexistent/import.ttl"})
    assert result.get("Unresolvable imports").count == 2
    dqv = build_dqv_graph([result], timestamp=TS)
    nodes = list(dqv.objects(_measurement(dqv, "unresolvable-imports"), OLQ.violation))
    assert len(nodes) == 2
    assert {dqv.value(n, SH.focusNode) for n in nodes} == {URIRef(MISSING_IMPORT)}
    assert {dqv.value(n, OLQ.relatedResource) for n in nodes} == {
        URIRef("http://example.org#"), URIRef("http://example.org/two#")}


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


def test_merged_run_uses_aggregate_dataset(make_graph):
    # Two ontologies in one merged graph: violations can't be attributed to either, so
    # results are computed on one aggregate dataset, not asserted on each ontology.
    g = make_graph("""
    : a owl:Ontology ; rdfs:label "One" .
    <http://example.org/two#> a owl:Ontology ; rdfs:label "Two" .
    :Dog a owl:Class .
    """)
    dqv = build_dqv_graph([_qa(g, files_processed=["one.ttl", "two.ttl"])], timestamp=TS)
    computed_on = set(dqv.objects(None, DQV.computedOn))
    assert len(computed_on) == 1
    aggregate = computed_on.pop()
    assert (aggregate, RDF.type, rdflib.DCAT.Dataset) in dqv
    assert set(dqv.objects(aggregate, rdflib.DCTERMS.hasPart)) == {
        URIRef("http://example.org#"), URIRef("http://example.org/two#")}
    assert "One" in str(dqv.value(aggregate, RDFS.label))
    assert len(list(dqv.subjects(DQV.isMeasurementOf, _metric("ontolint-conformance")))) == 1


def test_aggregate_dataset_iri_is_stable_across_runs(make_graph):
    g = make_graph(": a owl:Ontology . <http://example.org/two#> a owl:Ontology .")
    result = _qa(g, files_processed=["one.ttl", "two.ttl"])
    first = set(build_dqv_graph([result], timestamp=TS).objects(None, DQV.computedOn))
    later = set(build_dqv_graph([result], timestamp=TS.replace(hour=11)).objects(None, DQV.computedOn))
    assert first == later


def test_single_ontology_is_computed_on_directly(make_graph):
    g = make_graph(": a owl:Ontology . :Dog a owl:Class .")
    dqv = build_dqv_graph([_qa(g)], timestamp=TS)
    assert set(dqv.objects(None, DQV.computedOn)) == {URIRef("http://example.org#")}
    assert not list(dqv.subjects(RDF.type, rdflib.DCAT.Dataset))


# ── blank nodes ───────────────────────────────────────────────────────────────

SHAPES = """
: a owl:Ontology .
:DogShape a sh:NodeShape ; rdfs:label "Dog shape" ; rdfs:comment "Dogs." ; sh:targetClass :Dog ;
    sh:property [ a sh:PropertyShape ; sh:path :name ; rdfs:label "same" ] ,
                [ a sh:PropertyShape ; sh:path :age ; rdfs:label "same" ] ,
                [ a sh:PropertyShape ; sh:path :tail ] .
"""


def _shape_report(make_graph):
    return build_dqv_graph([_qa(make_graph(SHAPES))], base_uri="https://kh.example/qa#", timestamp=TS)


def test_blank_node_resources_are_skolemized_under_base(make_graph):
    dqv = _shape_report(make_graph)
    shapes = {o for o in dqv.objects(None, SH.focusNode) if "bnode-" in str(o)}
    assert len(shapes) == 3  # three anonymous property shapes
    assert all(str(o).startswith("https://kh.example/qa#bnode-") for o in shapes)
    # No relative IRIs (the old bug: a bare blank-node id emitted as <n0123...>).
    for term in [o for t in dqv for o in t if isinstance(o, URIRef)]:
        assert ":" in str(term), term


def test_blank_node_skolem_iris_are_stable_across_parses(make_graph):
    # Blank-node ids differ on every parse; the report must not.
    assert set(_shape_report(make_graph)) == set(_shape_report(make_graph))


def test_identical_blank_nodes_get_distinct_skolem_iris(make_graph):
    # Two structurally identical anonymous shapes under the same parent are still two
    # violations; a local content key would give them one skolem IRI and one result.
    ttl = """
    : a owl:Ontology .
    :DogShape a sh:NodeShape ; rdfs:label "Dog shape" ; rdfs:comment "Dogs." ;
        sh:property [ a sh:PropertyShape ] , [ a sh:PropertyShape ] .
    """
    reports = [build_dqv_graph([_qa(make_graph(ttl))], timestamp=TS) for _ in range(2)]
    m = _measurement(reports[0], "property-shapes-missing-label")
    assert reports[0].value(m, DQV.value) == Literal(2)
    nodes = list(reports[0].objects(m, OLQ.violation))
    assert len(nodes) == 2
    assert len({reports[0].value(n, SH.focusNode) for n in nodes}) == 2
    assert set(reports[0]) == set(reports[1])  # still stable across parses


def test_blank_node_related_resources_are_skolemized(make_graph):
    dqv = _shape_report(make_graph)
    m = _measurement(dqv, "property-shapes-same-label", base="https://kh.example/qa#")
    nodes = list(dqv.objects(m, OLQ.violation))
    assert len(nodes) == 2
    focus = {dqv.value(n, SH.focusNode) for n in nodes}
    related = {dqv.value(n, OLQ.relatedResource) for n in nodes}
    assert focus == related  # each shape is related to the other
    assert all("a blank node" in str(dqv.value(n, SH.resultMessage)) for n in nodes)


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
    for v in dqv.subjects(RDF.type, SH.ValidationResult):
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


@pytest.mark.parametrize("bad", ["qa", "qa/", "/qa/", "//example.org/qa/", "https://ex ample.org/",
                                 "https://example.org/<qa>/", "1http://x/"])
def test_relative_or_malformed_base_uri_rejected(make_graph, bad):
    g = make_graph(": a owl:Ontology .")
    with pytest.raises(ValueError):
        build_dqv_graph([_qa(g)], base_uri=bad, timestamp=TS)


@pytest.mark.parametrize("good", ["https://example.org/qa#", "urn:ontolint:", "http://x", "tag:example.org,2026:qa/"])
def test_absolute_base_uri_accepted(make_graph, good):
    g = make_graph(": a owl:Ontology .")
    build_dqv_graph([_qa(g)], base_uri=good, timestamp=TS)


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


@pytest.mark.parametrize("bad", ["../escape.ttl", "/tmp/abs.ttl", "sub/report.ttl", "..", ".", "",
                                 "../../important-file", "report.ttl\ninjected=1", "a\rb.ttl", "a\x00b.ttl"])
def test_dqv_filename_must_be_plain_name(bad):
    with pytest.raises(ValueError):
        check_dqv_filename(bad)


def test_write_dqv_report_does_not_escape_directory(make_graph, tmp_path):
    g = make_graph(": a owl:Ontology .")
    with pytest.raises(ValueError):
        write_dqv_report([_qa(g)], str(tmp_path / "out"), "../escape.ttl", timestamp=TS)
    assert not (tmp_path / "escape.ttl").exists()


# ── reproducibility of GROUP_CONCAT-derived records ──────────────────────────

def test_same_label_records_independent_of_group_concat_order():
    a = "http://example.org#a"
    b = "http://example.org#b"
    first = _same_label_records(Literal("x"), f"{a}, {b}")
    second = _same_label_records(Literal("x"), f"{b}, {a}")
    assert first == second


def test_non_unique_identifier_comment_is_sorted(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Thing a owl:Class, owl:ObjectProperty, owl:DatatypeProperty .
    """)
    check = _qa(g).get("Non-unique identifiers")
    comment = check.violations[0].comment
    declared = comment.removeprefix("declared as ").split(", ")
    assert declared == sorted(declared)

