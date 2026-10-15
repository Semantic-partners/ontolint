"""The programmatic API: lint in-memory graphs, get a DQV graph back (issue #92)."""

from dataclasses import fields
from pathlib import Path

import rdflib
import pytest

import ontolint

from ontolint import Config, lint
from scripts.ontology_qa import CHECKLIST, deepcopy_list, lint_graph, run_qa
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


def _results(datasets, config=None):
    """The same run lint() performs, one dataset at a time, keeping the QAResults.

    `lint()` hands back only the DQV graph, so a test that is about what a check decided
    goes through `lint_graph` — the entry point `lint()` and the CLI both call.
    """
    return [lint_graph(graph, [name], config) for name, graph in datasets.items()]


def _conforms(report, base=DEFAULT_BASE_URI):
    """{dataset: whether every executed check passed}, as a consumer would read it."""
    rollup = rdflib.URIRef(f"{base}metric-ontolint-conformance")
    return {
        str(report.value(m, DQV.computedOn)): report.value(m, OLQ.conforms).toPython()
        for m in report.subjects(DQV.isMeasurementOf, rollup)
    }


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


# ── the public surface ────────────────────────────────────────────────────────

# Every setting a run takes, and what it defaults to. Adding a field is a promise to
# keep, so it should mean updating this list, the readme table and the Config docstring.
CONFIG_DEFAULTS = {
    "per_file": False,
    "imports": {},
    "ignore_imports": (),
    "exclude_types": (),
    "skip_object_of": None,
    "checks": None,
    "base_iri": None,
    "inference": False,
    "uri_parser": None,
}

README = Path(__file__).parent.parent / "readme.md"


def test_the_package_exports_exactly_config_and_lint():
    assert sorted(ontolint.__all__) == ["Config", "lint"]
    assert sorted(n for n in vars(ontolint) if not n.startswith("_")) == ["Config", "api", "lint"]


def test_config_is_the_documented_set_of_settings():
    assert {f.name for f in fields(Config)} == set(CONFIG_DEFAULTS)
    assert {name: getattr(Config(), name) for name in CONFIG_DEFAULTS} == CONFIG_DEFAULTS


def test_config_is_published_as_ontolints_own():
    # Otherwise help(), pickle and generated docs name an implementation module.
    assert Config.__module__ == "ontolint"


def test_every_setting_is_documented():
    readme = README.read_text()
    assert [f.name for f in fields(Config) if f"`{f.name}`" not in readme] == []
    assert [f.name for f in fields(Config) if f"{f.name}:" not in (Config.__doc__ or "")] == []


# ── the basic contract ────────────────────────────────────────────────────────

def test_lint_returns_a_dqv_graph_of_the_violations():
    report = lint({"core": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    assert isinstance(report, rdflib.Graph)
    assert _focus_nodes(report, "classes-missing-label") == {"http://example.org/core#Thing"}


def test_conformance_is_readable_from_the_returned_graph():
    failing = lint({"bad": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))
    clean = lint({"good": _graph(':Thing a owl:Class ; rdfs:label "Thing" .')},
                 Config(checks=["class-missing-label"]))

    assert _conforms(failing) == {f"{DEFAULT_BASE_URI}dataset-bad": False}
    assert _conforms(clean) == {f"{DEFAULT_BASE_URI}dataset-good": True}


def test_the_failed_check_count_is_on_the_conformance_measurement():
    report = lint({"bad": _graph(":Thing a owl:Class .")},
                  Config(checks=["class-missing-label", "class-missing-comment"]))

    rollup = rdflib.URIRef(f"{DEFAULT_BASE_URI}metric-ontolint-conformance")
    [measurement] = list(report.subjects(DQV.isMeasurementOf, rollup))
    assert report.value(measurement, DQV.value).toPython() == 2


def test_a_clean_dataset_passes():
    graph = _graph("""
    : a owl:Ontology ; rdfs:label "Core" ; rdfs:comment "A core ontology" .
    :Thing a owl:Class ; rdfs:label "Thing" ; rdfs:comment "Anything at all" .
    """)
    [result] = _results({"core": graph}, Config(checks=["class-missing-label", "class-missing-comment"]))

    assert result.passed


def test_every_check_runs_by_default():
    [result] = _results({"core": _graph(":Thing a owl:Class .")})

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
    plain = _results({"core": _graph(INSTANCE_OF_A_SUBCLASS)},
                         Config(checks=["class-missing-label"]))[0]
    inferred = _results({"core": _graph(INSTANCE_OF_A_SUBCLASS)},
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
    # A prefix-style base is used as given: no separator is inserted after the hyphen.
    base = "https://example.org/reports/run-123-"
    report = lint({"activities": _graph(":Thing a owl:Class .")},
                  Config(checks=["class-missing-label"], base_iri=base))

    assert _computed_on(report) == {f"{base}dataset-activities"}
    assert _focus_nodes(report, "classes-missing-label", base) == {"http://example.org/core#Thing"}


def test_a_relative_base_iri_is_rejected():
    with pytest.raises(ValueError, match="Config.base_iri"):
        lint({"core": _graph(":Thing a owl:Class .")}, Config(base_iri="reports/"))


# ── passing graphs without naming them ────────────────────────────────────────

def test_a_single_graph_needs_no_container():
    report = lint(_graph(": a owl:Ontology . :Thing a owl:Class ."), Config(checks=["class-missing-label"]))

    assert _computed_on(report) == {"http://example.org/core#"}


def test_unnamed_graphs_are_reported_under_the_ontology_they_declare():
    # The point of the unkeyed form: the caller doesn't extract what ontolint reads anyway.
    report = lint(
        [_graph(": a owl:Ontology . :Activity a owl:Class .", "http://example.org/act#"),
         _graph(": a owl:Ontology . :Party a owl:Class .", "http://example.org/party#")],
        Config(per_file=True, checks=["class-missing-label"]),
    )

    assert _computed_on(report) == {"http://example.org/act#", "http://example.org/party#"}


def test_naming_is_only_needed_when_no_ontology_is_declared():
    report = lint(
        [_graph(":Activity a owl:Class .", "http://example.org/act#"),
         _graph(":Party a owl:Class .", "http://example.org/party#")],
        Config(per_file=True, checks=["class-missing-label"]),
    )

    assert _computed_on(report) == {f"{DEFAULT_BASE_URI}dataset-unnamed-1",
                                    f"{DEFAULT_BASE_URI}dataset-unnamed-2"}


# ── one file, one ontology ────────────────────────────────────────────────────

DUPLICATE_METRIC = rdflib.URIRef(f"{DEFAULT_BASE_URI}metric-duplicate-ontology-iri")


def _duplicate_findings(report):
    """{ontology IRI: the inputs that declared it}, as the report states it."""
    return {
        str(report.value(v, rdflib.SH.focusNode)):
            sorted(str(r) for r in report.objects(v, OLQ.relatedResource))
        for m in report.subjects(DQV.isMeasurementOf, DUPLICATE_METRIC)
        for v in report.objects(m, OLQ.violation)
    }


def test_two_inputs_declaring_the_same_ontology_are_reported_not_refused():
    same = ": a owl:Ontology . :Thing a owl:Class ."

    report = lint([_graph(same), _graph(same)], Config(per_file=True, checks=["class-missing-label"]))

    assert _duplicate_findings(report) == {
        "http://example.org/core#": [f"{DEFAULT_BASE_URI}dataset-unnamed-1",
                                     f"{DEFAULT_BASE_URI}dataset-unnamed-2"],
    }


def test_the_other_checks_still_run_for_a_duplicated_ontology():
    # The point of reporting rather than refusing: a duplicate must not mask everything else.
    report = lint([_graph(": a owl:Ontology . :Alpha a owl:Class ."),
                   _graph(": a owl:Ontology . :Beta a owl:Class .")],
                  Config(per_file=True, checks=["class-missing-label"]))

    assert _focus_nodes(report, "classes-missing-label") == {
        "http://example.org/core#Alpha", "http://example.org/core#Beta",
    }


def test_the_duplicate_finding_names_the_inputs_the_caller_named():
    same = ": a owl:Ontology . :Thing a owl:Class ."

    report = lint({"file-a": _graph(same), "file-b": _graph(same)},
                  Config(per_file=True, checks=["class-missing-label"]))

    assert _duplicate_findings(report) == {
        "http://example.org/core#": [f"{DEFAULT_BASE_URI}dataset-file-a",
                                     f"{DEFAULT_BASE_URI}dataset-file-b"],
    }


def test_distinct_names_do_not_hide_a_duplicated_ontology():
    # Naming them apart was the old workaround; it never gave them separate identities,
    # since the report keys on the declared IRI either way.
    same = ": a owl:Ontology . :Thing a owl:Class ."

    report = lint({"a": _graph(same), "b": _graph(same)},
                  Config(per_file=True, checks=["class-missing-label"]))

    assert _computed_on(report) == {"http://example.org/core#"}
    assert _duplicate_findings(report)


def test_a_duplicated_ontology_is_reported_in_merged_runs_too():
    # Merging the graphs first would hide it: two identical declarations are one triple.
    same = ": a owl:Ontology . :Thing a owl:Class ."

    report = lint([_graph(same), _graph(same)], Config(checks=["class-missing-label"]))

    assert _duplicate_findings(report)


def test_distinct_ontologies_raise_no_duplicate_finding():
    report = lint([_graph(": a owl:Ontology .", "http://example.org/act#"),
                   _graph(": a owl:Ontology .", "http://example.org/party#")],
                  Config(per_file=True, checks=["class-missing-label"]))

    assert _duplicate_findings(report) == {}


def test_an_unnamed_turtle_string_is_accepted_too():
    report = lint([_ttl(": a owl:Ontology . :Thing a owl:Class .")],
                  Config(checks=["class-missing-label"]))

    assert _computed_on(report) == {"http://example.org/core#"}


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
    # :Party is only connected to anything by the subClassOf in the other dataset, so
    # checking the two separately reports it as isolated and merging them does not.
    datasets = {
        "activities": _graph(":Activity rdfs:subClassOf <http://example.org/party#Party> . :Activity a owl:Class .",
                             "http://example.org/act#"),
        "parties": _graph(":Party a owl:Class .", "http://example.org/party#"),
    }

    merged = lint(datasets, Config(checks=["isolated-classes"]))
    separately = lint(datasets, Config(checks=["isolated-classes"], per_file=True))

    assert _focus_nodes(merged, "isolated-classes") == set()
    assert _focus_nodes(separately, "isolated-classes") == {"http://example.org/party#Party"}


# ── dependency vocabularies as graphs ─────────────────────────────────────────

def test_imports_resolve_from_a_supplied_graph_without_touching_the_network():
    # The no_network fixture makes any fetch fail, so this can only pass from the graph.
    external = rdflib.Graph().parse(
        data=f"@prefix owl: <{OWL}> .\n<{EXTERNAL}Thing> a owl:Class .\n", format="turtle")
    graph = _graph(f"""
    : a owl:Ontology .
    :Local rdfs:subClassOf <{EXTERNAL}Thing> ; a owl:Class .
    """)

    [result] = _results({"core": graph},
                            Config(checks=UNDEFINED_TERMS, imports={EXTERNAL: external}))

    assert result.get("Undefined terms").passed


@pytest.mark.parametrize("key", [
    "http://vocab.example.org/core#",   # the namespace the terms live in
    "http://vocab.example.org/core",    # the owl:Ontology IRI, as a hash vocabulary writes it
    "http://vocab.example.org/core/",   # a trailing slash instead
])
def test_an_imports_key_matches_however_the_namespace_is_written(key):
    # Documented in the readme so callers don't derive a vocabulary's "real" namespace.
    vocabulary = rdflib.Graph().parse(data=f"""
    @prefix owl: <{OWL}> .
    <http://vocab.example.org/core> a owl:Ontology .
    <http://vocab.example.org/core#Thing> a owl:Class .
    """, format="turtle")
    graph = _graph("""
    : a owl:Ontology .
    :Local a owl:Class ; rdfs:subClassOf <http://vocab.example.org/core#Thing> .
    """)

    [result] = _results({"core": graph}, Config(checks=UNDEFINED_TERMS, imports={key: vocabulary}))

    assert result.get("Undefined terms").passed


def test_one_imports_entry_covers_every_namespace_that_graph_defines():
    # So a vocabulary spanning namespaces needs one entry, not one per namespace.
    vocabulary = rdflib.Graph().parse(data=f"""
    @prefix owl: <{OWL}> .
    <http://a.example.org/v#Thing> a owl:Class .
    <http://b.example.org/v#Other> a owl:Class .
    """, format="turtle")
    graph = _graph("""
    : a owl:Ontology .
    :Local a owl:Class ;
        rdfs:subClassOf <http://a.example.org/v#Thing>, <http://b.example.org/v#Other> .
    """)

    [result] = _results({"core": graph},
                        Config(checks=UNDEFINED_TERMS, imports={"http://a.example.org/v#": vocabulary}))

    assert result.get("Undefined terms").passed


def test_imports_may_be_given_without_keys():
    vocabulary = rdflib.Graph().parse(data=f"""
    @prefix owl: <{OWL}> .
    <http://vocab.example.org/core> a owl:Ontology .
    <http://vocab.example.org/core#Thing> a owl:Class .
    """, format="turtle")
    graph = _graph("""
    : a owl:Ontology .
    :Local a owl:Class ; rdfs:subClassOf <http://vocab.example.org/core#Thing> .
    """)

    [result] = _results({"core": graph}, Config(checks=UNDEFINED_TERMS, imports=[vocabulary]))

    assert result.get("Undefined terms").passed


def test_an_unkeyed_vocabulary_covers_every_namespace_it_defines():
    vocabulary = rdflib.Graph().parse(data=f"""
    @prefix owl: <{OWL}> .
    <http://a.example.org/v#Thing> a owl:Class .
    <http://b.example.org/v#Other> a owl:Class .
    """, format="turtle")
    graph = _graph("""
    : a owl:Ontology .
    :Local a owl:Class ;
        rdfs:subClassOf <http://a.example.org/v#Thing>, <http://b.example.org/v#Other> .
    """)

    [result] = _results({"core": graph}, Config(checks=UNDEFINED_TERMS, imports=[vocabulary]))

    assert result.get("Undefined terms").passed


def test_an_unkeyed_vocabulary_does_not_claim_its_siblings():
    # <.../core> sits in <.../>, and claiming that namespace would make every unrelated
    # term beside it look resolved rather than fetched.
    vocabulary = rdflib.Graph().parse(data=f"""
    @prefix owl: <{OWL}> .
    <http://vocab.example.org/core> a owl:Ontology .
    <http://vocab.example.org/core#Thing> a owl:Class .
    """, format="turtle")
    graph = _graph("""
    : a owl:Ontology .
    :Local a owl:Class ; rdfs:subClassOf <http://vocab.example.org/unrelated#Gone> .
    """)

    [result] = _results({"core": graph}, Config(checks=UNDEFINED_TERMS, imports=[vocabulary]))

    assert not result.get("Undefined terms").passed


def test_a_term_missing_from_the_supplied_graph_is_still_reported():
    external = rdflib.Graph().parse(
        data=f"@prefix owl: <{OWL}> .\n<{EXTERNAL}Thing> a owl:Class .\n", format="turtle")
    graph = _graph(f"""
    : a owl:Ontology .
    :Local rdfs:subClassOf <{EXTERNAL}Missing> ; a owl:Class .
    """)

    [result] = _results({"core": graph},
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

    [result] = _results({"core": graph},
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

    [result] = _results({"core": graph},
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

    [result] = _results({"core": graph}, Config(checks=UNDEFINED_TERMS, uri_parser=parser))

    assert result.get("Undefined terms").passed
    assert fetched == [EXTERNAL]


def test_ignore_imports_trusts_a_namespace():
    graph = _graph(f"""
    : a owl:Ontology .
    :Local rdfs:subClassOf <{EXTERNAL}Thing> ; a owl:Class .
    """)

    [result] = _results({"core": graph},
                            Config(checks=UNDEFINED_TERMS, ignore_imports=[EXTERNAL]))

    assert result.get("Undefined terms").passed


# ── choosing what runs ────────────────────────────────────────────────────────

def test_checks_selects_what_runs():
    [result] = _results({"core": _graph(":Thing a owl:Class .")},
                            Config(checks=["class-missing-label"]))

    assert [c.name for c in result.checks] == ["Class without label"]


def test_check_names_may_be_given_in_either_form():
    [result] = _results({"core": _graph(":Thing a owl:Class .")},
                            Config(checks=["check_class_missing_label"]))

    assert [c.name for c in result.checks] == ["Class without label"]


def test_an_unknown_check_is_an_error_rather_than_a_silent_no_op():
    with pytest.raises(ValueError, match="class-missing-description"):
        lint({"core": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-description"]))


def test_a_check_that_depends_on_another_pulls_it_in():
    # Same rule as the CLI's: the description check needs the declaration check.
    [result] = _results({"core": _graph(":Thing a owl:Class .")},
                            Config(checks=["owl-description"]))

    assert "Ontology without declaration" in [c.name for c in result.checks]


def test_exclude_types_skips_instances_of_that_type():
    body = ":Thing a owl:Class, rdf:PropositionForm ."
    reported = _results({"core": _graph(body)}, Config(checks=["class-missing-label"]))[0]
    skipped = _results({"core": _graph(body)},
                           Config(checks=["class-missing-label"],
                                  exclude_types=["rdf:PropositionForm"]))[0]

    assert reported.get("Class without label").count == 1
    assert skipped.get("Class without label").passed


def test_skip_object_of_is_honoured():
    graph = _graph(f"""
    : a owl:Ontology .
    :Thing a owl:Class ; rdfs:seeAlso <{EXTERNAL}Elsewhere> .
    """)
    checked = _results({"core": graph},
                           Config(checks=UNDEFINED_TERMS, skip_object_of=[]))[0]
    skipped = _results({"core": graph},
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


def test_datasets_must_be_graphs_however_they_are_passed():
    with pytest.raises(TypeError, match="mapping of name to graph"):
        lint(42)


def test_prefixes_survive_the_copy():
    # Prefixes are a profiling input, and `+=` copies triples but not bindings.
    body = ':Thing a owl:Class ; rdfs:label "Thing" .'
    only_labels = [c for c in deepcopy_list(CHECKLIST) if c[3] == "missingClassLabel"]
    direct = run_qa(_graph(body), checklist=only_labels)

    [through_api] = _results({"core": _graph(body)}, Config(checks=["class-missing-label"]))

    assert through_api.profiling["vocabulariesUsed"] == direct.profiling["vocabulariesUsed"] > 0


def test_the_configuration_records_the_caller_as_the_origin():
    report = lint({"core": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    [configuration] = list(report.subjects(rdflib.RDF.type, OLQ.Configuration))
    assert report.value(configuration, OLQ.configurationFile) is None


def test_dataset_iri_helper_matches_what_the_report_mints():
    report = lint({"activities": _graph(":Thing a owl:Class .")}, Config(checks=["class-missing-label"]))

    assert _computed_on(report) == {str(dataset_iri(None, "activities"))}
