"""The programmatic API: lint in-memory graphs, get a DQV graph back (issue #92)."""

import rdflib
import pytest

from ontolint import Config, lint, lint_results
from scripts.ontology_qa import CHECKLIST, deepcopy_list, run_qa
from scripts.dqv import DQV, OLQ, DEFAULT_BASE_URI, dataset_iri

OWL = "http://www.w3.org/2002/07/owl#"
# undefined-terms reads the ontology IRI that owl-declaration records, to tell a local
# namespace from one it has to resolve.
UNDEFINED_TERMS = ["owl-declaration", "undefined-terms"]
EXTERNAL = "http://external.example.org#"


def _ttl(body, prefix="http://example.org/core#"):
    return (
        f"@prefix : <{prefix}> .\n"
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        f"{body}\n"
    )


def _graph(body, prefix="http://example.org/core#"):
    return rdflib.Graph().parse(data=_ttl(body, prefix), format="turtle")


def _computed_on(report):
    return {str(o) for o in report.objects(None, DQV.computedOn)}


def _focus_nodes(report, slug, base=DEFAULT_BASE_URI):
    """The resources reported as violating the given metric."""
    metric = rdflib.URIRef(f"{base}metric-{slug}")
    return {
        str(report.value(v, rdflib.SH.focusNode))
        for m in report.subjects(DQV.isMeasurementOf, metric)
        for v in report.objects(m, OLQ.violation)
    }


# ── the basic contract ────────────────────────────────────────────────────────

def test_lint_returns_a_dqv_graph_of_the_violations():
    report = lint({"core": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    assert isinstance(report, rdflib.Graph)
    assert _focus_nodes(report, "classes-missing-label") == {"http://example.org/core#Thing"}


def test_lint_results_gives_the_checks_directly():
    [result] = lint_results({"core": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    assert not result.passed
    assert [c.name for c in result.failures] == ["Class without label"]
    assert result.get("Class without label").count == 1


def test_a_clean_dataset_passes():
    graph = _graph("""
    : a owl:Ontology ; rdfs:label "Core" ; rdfs:comment "A core ontology" .
    :Thing a owl:Class ; rdfs:label "Thing" ; rdfs:comment "Anything at all" .
    """)
    [result] = lint_results({"core": graph}, Config(checks=["class-missing-label", "class-missing-comment"]))

    assert result.passed


def test_every_check_runs_by_default():
    [result] = lint_results({"core": _graph(":Thing a owl:Class .")})

    assert len(result.checks) == len(CHECKLIST)


# ── the caller's graphs are left alone ────────────────────────────────────────

def test_the_callers_graph_is_not_modified():
    # The checks drop instance data from the graph they run on, so a shared graph would
    # come back shorter than the caller left it.
    graph = _graph(":Thing a owl:Class . :fido a :Thing .")
    before = set(graph)

    lint({"core": graph})

    assert set(graph) == before


INSTANCE_OF_A_SUBCLASS = """
:A rdfs:subClassOf :B . :A a owl:Class . :B a owl:Class .
:fido a :A .
"""


def test_inference_does_not_modify_the_callers_graph():
    graph = _graph(INSTANCE_OF_A_SUBCLASS)
    before = set(graph)

    lint({"core": graph}, Config(inference=True, checks=["class-missing-label"]))

    assert set(graph) == before


def test_inference_adds_the_entailed_triples():
    plain = lint_results({"core": _graph(INSTANCE_OF_A_SUBCLASS)},
                         Config(checks=["class-missing-label"]))[0]
    inferred = lint_results({"core": _graph(INSTANCE_OF_A_SUBCLASS)},
                            Config(inference=True, checks=["class-missing-label"]))[0]

    assert inferred.profiling["triples"] > plain.profiling["triples"]


# ── naming the datasets ───────────────────────────────────────────────────────

def test_a_dataset_without_an_ontology_declaration_is_named_after_its_key():
    report = lint({"activities": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    assert _computed_on(report) == {f"{DEFAULT_BASE_URI}dataset-activities"}


def test_a_declared_ontology_iri_names_the_dataset():
    graph = _graph(": a owl:Ontology . :Thing a owl:Class .")
    report = lint({"activities": graph}, Config(checks=["class-missing-label"]))

    assert _computed_on(report) == {"http://example.org/core#"}


def test_the_dataset_iri_is_stable_across_runs():
    first = lint({"activities": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))
    second = lint({"activities": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    assert _computed_on(first) == _computed_on(second)


def test_an_iri_name_is_used_as_the_dataset_iri():
    # Keying by the ontology IRI identifies the dataset the same way in every report.
    report = lint({"https://example.org/parties": _graph(":Thing a owl:Class .")},
                  Config(checks=["class-missing-label"]))

    assert _computed_on(report) == {"https://example.org/parties"}


def test_an_iri_name_is_not_minted_under_the_base():
    report = lint({"https://example.org/parties": _graph(":Thing a owl:Class .")},
                  Config(checks=["class-missing-label"], base_iri="https://example.org/reports/run-1-"))

    assert _computed_on(report) == {"https://example.org/parties"}


def test_iri_names_keep_per_file_datasets_apart():
    report = lint(
        {"https://example.org/activities": _graph(":Activity a owl:Class .", "http://example.org/act#"),
         "https://example.org/parties": _graph(":Party a owl:Class .", "http://example.org/party#")},
        Config(per_file=True, checks=["class-missing-label"]),
    )

    assert _computed_on(report) == {"https://example.org/activities", "https://example.org/parties"}


def test_a_declared_ontology_iri_wins_over_the_name():
    # The graph says what it is; the name is only how the caller referred to it.
    graph = _graph(": a owl:Ontology . :Thing a owl:Class .")
    report = lint({"https://example.org/parties": graph}, Config(checks=["class-missing-label"]))

    assert _computed_on(report) == {"http://example.org/core#"}


def test_a_name_that_is_not_iri_safe_is_still_one_iri():
    report = lint({"my datasets/core": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    assert _computed_on(report) == {f"{DEFAULT_BASE_URI}dataset-my%20datasets%2Fcore"}


def test_base_iri_is_used_for_minted_iris():
    # As with the CLI's --base-uri, a base that ends in no separator gets a '/'.
    base = "https://example.org/reports/run-123-/"
    report = lint({"activities": _graph(":Thing a owl:Class .")},
                  Config(checks=["class-missing-label"], base_iri="https://example.org/reports/run-123-"))

    assert _computed_on(report) == {f"{base}dataset-activities"}
    assert _focus_nodes(report, "classes-missing-label", base) == {"http://example.org/core#Thing"}


def test_a_relative_base_iri_is_rejected():
    with pytest.raises(ValueError, match="Config.base_iri"):
        lint({"core": _graph(":Thing a owl:Class .")}, Config(base_iri="reports/"))


# ── per-dataset versus merged ─────────────────────────────────────────────────

def test_per_file_attributes_each_violation_to_its_own_dataset():
    report = lint(
        {"activities": _graph(":Activity a owl:Class .", "http://example.org/act#"),
         "parties": _graph(":Party a owl:Class .", "http://example.org/party#")},
        Config(per_file=True, checks=["class-missing-label"]),
    )

    metric = rdflib.URIRef(f"{DEFAULT_BASE_URI}metric-classes-missing-label")
    by_dataset = {
        str(report.value(m, DQV.computedOn)): {
            str(report.value(v, rdflib.SH.focusNode)) for v in report.objects(m, OLQ.violation)
        }
        for m in report.subjects(DQV.isMeasurementOf, metric)
    }
    assert by_dataset == {
        f"{DEFAULT_BASE_URI}dataset-activities": {"http://example.org/act#Activity"},
        f"{DEFAULT_BASE_URI}dataset-parties": {"http://example.org/party#Party"},
    }


def test_per_file_gives_one_result_per_dataset():
    results = lint_results(
        {"activities": _graph(":Activity a owl:Class .", "http://example.org/act#"),
         "parties": _graph(":Party a owl:Class .", "http://example.org/party#")},
        Config(per_file=True, checks=["class-missing-label"]),
    )

    assert len(results) == 2


def test_merged_is_the_default_and_reports_one_aggregate_dataset():
    report = lint(
        {"activities": _graph(":Activity a owl:Class .", "http://example.org/act#"),
         "parties": _graph(":Party a owl:Class .", "http://example.org/party#")},
        Config(checks=["class-missing-label"]),
    )

    [aggregate] = list(report.subjects(rdflib.RDF.type, rdflib.DCAT.Dataset))
    assert set(report.objects(aggregate, rdflib.DCTERMS.hasPart)) == {
        rdflib.URIRef(f"{DEFAULT_BASE_URI}dataset-activities"),
        rdflib.URIRef(f"{DEFAULT_BASE_URI}dataset-parties"),
    }
    assert _focus_nodes(report, "classes-missing-label") == {
        "http://example.org/act#Activity", "http://example.org/party#Party",
    }


def test_merged_sees_terms_defined_in_another_dataset():
    # :Activity is only connected to the hierarchy through the other dataset.
    results = lint_results(
        {"activities": _graph(":Activity rdfs:subClassOf <http://example.org/party#Party> . :Activity a owl:Class .",
                              "http://example.org/act#"),
         "parties": _graph(":Party a owl:Class .", "http://example.org/party#")},
        Config(checks=["isolated-classes"]),
    )

    assert len(results) == 1
    assert results[0].get("Isolated classes").count == 0


# ── dependency vocabularies as graphs ─────────────────────────────────────────

def test_imports_resolve_from_a_supplied_graph_without_touching_the_network():
    # The no_network fixture makes any fetch fail, so this can only pass from the graph.
    external = rdflib.Graph().parse(
        data=f"@prefix owl: <{OWL}> .\n<{EXTERNAL}Thing> a owl:Class .\n", format="turtle")
    graph = _graph(f"""
    : a owl:Ontology .
    :Local rdfs:subClassOf <{EXTERNAL}Thing> ; a owl:Class .
    """)

    [result] = lint_results({"core": graph},
                            Config(checks=UNDEFINED_TERMS, imports={EXTERNAL: external}))

    assert result.get("Undefined terms").passed


def test_a_term_missing_from_the_supplied_graph_is_still_reported():
    external = rdflib.Graph().parse(
        data=f"@prefix owl: <{OWL}> .\n<{EXTERNAL}Thing> a owl:Class .\n", format="turtle")
    graph = _graph(f"""
    : a owl:Ontology .
    :Local rdfs:subClassOf <{EXTERNAL}Missing> ; a owl:Class .
    """)

    [result] = lint_results({"core": graph},
                            Config(checks=UNDEFINED_TERMS, imports={EXTERNAL: external}))

    check = result.get("Undefined terms")
    assert not check.passed
    assert check.count == 1
    assert f"{EXTERNAL}Missing" in check.elements


def test_an_owl_import_resolves_from_a_supplied_graph():
    external = rdflib.Graph().parse(
        data=f"@prefix owl: <{OWL}> .\n<{EXTERNAL}> a owl:Ontology .\n", format="turtle")
    graph = _graph(f"""
    : a owl:Ontology ; owl:imports <{EXTERNAL}> .
    """)

    [result] = lint_results({"core": graph},
                            Config(checks=["owl-imports"], imports={EXTERNAL: external}))

    assert result.get("Unresolvable imports").passed


def test_a_supplied_graph_is_recorded_in_the_configuration_without_a_file():
    external = rdflib.Graph().parse(data=f"@prefix owl: <{OWL}> .\n<{EXTERNAL}Thing> a owl:Class .\n",
                                    format="turtle")
    report = lint({"core": _graph(":Thing a owl:Class .")},
                  Config(checks=["class-missing-label"], imports={EXTERNAL: external}))

    [setting] = [s for s in report.subjects(OLQ.key, rdflib.Literal("imports.local"))
                 if (s, OLQ.value, rdflib.URIRef(EXTERNAL)) in report]
    assert report.value(setting, OLQ.origin) == OLQ.CallerArgument
    assert report.value(setting, OLQ.localFile) is None


def test_imports_may_still_be_a_file_path(tmp_path):
    vocabulary = tmp_path / "external.ttl"
    vocabulary.write_text(f"@prefix owl: <{OWL}> .\n<{EXTERNAL}Thing> a owl:Class .\n")
    graph = _graph(f"""
    : a owl:Ontology .
    :Local rdfs:subClassOf <{EXTERNAL}Thing> ; a owl:Class .
    """)

    [result] = lint_results({"core": graph},
                            Config(checks=UNDEFINED_TERMS, imports={EXTERNAL: str(vocabulary)}))

    assert result.get("Undefined terms").passed


def test_uri_parser_decides_how_a_namespace_outside_imports_is_fetched():
    fetched = []

    def parser(uri):
        fetched.append(str(uri))
        return rdflib.Graph().parse(
            data=f"@prefix owl: <{OWL}> .\n<{EXTERNAL}Thing> a owl:Class .\n", format="turtle")

    graph = _graph(f"""
    : a owl:Ontology .
    :Local rdfs:subClassOf <{EXTERNAL}Thing> ; a owl:Class .
    """)

    [result] = lint_results({"core": graph}, Config(checks=UNDEFINED_TERMS, uri_parser=parser))

    assert result.get("Undefined terms").passed
    assert fetched == [EXTERNAL]


def test_ignore_imports_trusts_a_namespace():
    graph = _graph(f"""
    : a owl:Ontology .
    :Local rdfs:subClassOf <{EXTERNAL}Thing> ; a owl:Class .
    """)

    [result] = lint_results({"core": graph},
                            Config(checks=UNDEFINED_TERMS, ignore_imports=[EXTERNAL]))

    assert result.get("Undefined terms").passed


# ── choosing what runs ────────────────────────────────────────────────────────

def test_checks_selects_what_runs():
    [result] = lint_results({"core": _graph(":Thing a owl:Class .")},
                            Config(checks=["class-missing-label"]))

    assert [c.name for c in result.checks] == ["Class without label"]


def test_check_names_may_be_given_in_either_form():
    [result] = lint_results({"core": _graph(":Thing a owl:Class .")},
                            Config(checks=["check_class_missing_label"]))

    assert [c.name for c in result.checks] == ["Class without label"]


def test_an_unknown_check_is_an_error_rather_than_a_silent_no_op():
    with pytest.raises(ValueError, match="class-missing-description"):
        lint({"core": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-description"]))


def test_a_check_that_depends_on_another_pulls_it_in():
    # Same rule as the CLI's: the description check needs the declaration check.
    [result] = lint_results({"core": _graph(":Thing a owl:Class .")},
                            Config(checks=["owl-description"]))

    assert "Ontology without declaration" in [c.name for c in result.checks]


def test_exclude_types_skips_instances_of_that_type():
    body = ":Thing a owl:Class, rdf:PropositionForm ."
    reported = lint_results({"core": _graph(body)}, Config(checks=["class-missing-label"]))[0]
    skipped = lint_results({"core": _graph(body)},
                           Config(checks=["class-missing-label"],
                                  exclude_types=["rdf:PropositionForm"]))[0]

    assert reported.get("Class without label").count == 1
    assert skipped.get("Class without label").passed


def test_skip_object_of_is_honoured():
    graph = _graph(f"""
    : a owl:Ontology .
    :Thing a owl:Class ; rdfs:seeAlso <{EXTERNAL}Elsewhere> .
    """)
    checked = lint_results({"core": graph},
                           Config(checks=UNDEFINED_TERMS, skip_object_of=[]))[0]
    skipped = lint_results({"core": graph},
                           Config(checks=UNDEFINED_TERMS, skip_object_of=["rdfs:seeAlso"]))[0]

    assert not checked.get("Undefined terms").passed
    assert skipped.get("Undefined terms").passed


# ── what callers can pass ─────────────────────────────────────────────────────

def test_a_turtle_string_is_parsed_for_the_caller():
    report = lint({"core": _ttl(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    assert _focus_nodes(report, "classes-missing-label") == {"http://example.org/core#Thing"}


def test_an_empty_mapping_is_rejected():
    with pytest.raises(ValueError, match="nothing to lint"):
        lint({})


def test_something_that_is_not_a_graph_is_rejected():
    with pytest.raises(TypeError, match="rdflib.Graph"):
        lint({"core": 42})


def test_datasets_must_be_a_mapping():
    with pytest.raises(TypeError, match="mapping"):
        lint([_graph(":Thing a owl:Class .")])


def test_prefixes_survive_the_copy():
    # Prefixes are a profiling input, and `+=` copies triples but not bindings.
    body = ':Thing a owl:Class ; rdfs:label "Thing" .'
    only_labels = [c for c in deepcopy_list(CHECKLIST) if c[3] == "missingClassLabel"]
    direct = run_qa(_graph(body), checklist=only_labels)

    [through_api] = lint_results({"core": _graph(body)}, Config(checks=["class-missing-label"]))

    assert through_api.profiling["vocabulariesUsed"] == direct.profiling["vocabulariesUsed"] > 0


def test_the_configuration_records_the_caller_as_the_origin():
    report = lint({"core": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    [configuration] = list(report.subjects(rdflib.RDF.type, OLQ.Configuration))
    assert report.value(configuration, OLQ.configurationFile) is None


def test_dataset_iri_helper_matches_what_the_report_mints():
    report = lint({"activities": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    assert _computed_on(report) == {str(dataset_iri(None, "activities"))}
