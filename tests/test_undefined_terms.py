import pytest
import rdflib
from scripts.ontology_qa import DEFAULT_SKIP_OBJECT_OF, expand_curie, run_qa

CHECK_NAME = "Undefined terms"


def _no_fetch(uri):
    raise Exception(f"no network in tests: {uri}")


# ── Local namespace ───────────────────────────────────────────────────────────

def test_no_external_passes(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog a owl:Class .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_local_undefined_term_fails(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf :Mammal .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


def test_version_iri_is_not_an_undefined_term(make_graph):
    # owl:versionIRI names a version of the ontology document, not a term to resolve.
    g = make_graph("""
    : a owl:Ontology ; owl:versionIRI <http://example.org/1.0.0> .
    :Dog a owl:Class .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_version_iri_skip_does_not_hide_other_uses(make_graph):
    # The same IRI used as an ordinary term elsewhere is still checked.
    g = make_graph("""
    : a owl:Ontology ; owl:versionIRI :v1 .
    :Dog a owl:Class ; rdfs:subClassOf :v1 .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert "v1" in check.elements


def test_local_predicate_not_declared_fails(make_graph):
    # :livesIn is used as a predicate but never declared as a subject
    g = make_graph("""
    : a owl:Ontology .
    :Dog :livesIn :Kennel .
    :Dog a owl:Class .
    :Kennel a owl:Class .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


def test_local_predicate_declared_passes(make_graph):
    # :livesIn is used as a predicate and also declared as a subject
    g = make_graph("""
    : a owl:Ontology .
    :Dog :livesIn :Kennel .
    :Dog a owl:Class .
    :Kennel a owl:Class .
    :livesIn a owl:ObjectProperty .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_multiple_local_undefined_terms_count(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf :Mammal .
    :Cat rdfs:subClassOf :Reptile .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 2


def test_mix_of_defined_and_undefined_local_terms(make_graph):
    # :Mammal is declared so it passes; :Reptile is not so it is flagged
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf :Mammal .
    :Mammal a owl:Class .
    :Cat rdfs:subClassOf :Reptile .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


# ── Remote namespace ──────────────────────────────────────────────────────────

def test_remote_term_found_passes(make_graph):
    def fake_parser(uri):
        g = rdflib.Graph()
        if uri == "http://remote.example.org#":
            g.add((
                rdflib.URIRef("http://remote.example.org#Mammal"),
                rdflib.RDF.type,
                rdflib.OWL.Class,
            ))
        else:
            raise Exception(f"no network in tests: {uri}")
        return g

    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://remote.example.org#Mammal> .
    """)
    check = run_qa(g, uri_parser=fake_parser).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_remote_namespace_resolves_but_term_absent_fails(make_graph):
    def fake_parser(uri):
        if uri == "http://remote.example.org#":
            return rdflib.Graph()
        raise Exception(f"no network in tests: {uri}")

    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://remote.example.org#Mammal> .
    """)
    check = run_qa(g, uri_parser=fake_parser).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


def test_unresolvable_remote_namespace_flagged_as_fetch_failure(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://remote.example.org#Mammal> .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1
    assert "http://remote.example.org#Mammal (fetch failure)" in check.elements


def test_ignored_namespace_not_flagged(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://remote.example.org#Mammal> .
    """)
    check = run_qa(
        g,
        uri_parser=_no_fetch,
        ignore_imports=["http://remote.example.org#"],
    ).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_https_remote_term_found_passes(make_graph):
    def fake_parser(uri):
        g = rdflib.Graph()
        if uri == "https://remote.example.org#":
            g.add((
                rdflib.URIRef("https://remote.example.org#Mammal"),
                rdflib.RDF.type,
                rdflib.OWL.Class,
            ))
        else:
            raise Exception(f"no network in tests: {uri}")
        return g

    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <https://remote.example.org#Mammal> .
    """)
    check = run_qa(g, uri_parser=fake_parser).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_multiple_remote_namespaces_partial_resolution(make_graph):
    # Namespace A resolves with term found — passes
    # Namespace B resolves but term is absent — flagged
    def fake_parser(uri):
        g = rdflib.Graph()
        if uri == "http://a.example.org#":
            g.add((
                rdflib.URIRef("http://a.example.org#Mammal"),
                rdflib.RDF.type,
                rdflib.OWL.Class,
            ))
        elif uri == "http://b.example.org#":
            pass  # resolves but returns empty graph
        else:
            raise Exception(f"no network in tests: {uri}")
        return g

    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://a.example.org#Mammal> .
    :Gecko rdfs:subClassOf <http://b.example.org#Reptile> .
    """)
    check = run_qa(g, uri_parser=fake_parser).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_no_ontology_declaration_remote_term_flagged_as_fetch_failure(make_graph):
    # Without owl:Ontology the local namespace is unknown, so neither :Dog nor
    # :Mammal can be identified as local — both fall through to an unresolvable
    # remote namespace and are flagged as (fetch failure).
    g = make_graph("""
    :Dog a owl:Class .
    :Dog rdfs:subClassOf :Mammal .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 2
    assert "fetch failure" in check.elements


def test_violation_elements_lists_undefined_uri(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf :Mammal .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert "http://example.org#Mammal" in check.elements


# ── local_imports substitution ────────────────────────────────────────────────

def test_local_imports_substitutes_namespace_fetch(make_graph, tmp_path):
    local_file = tmp_path / "remote_ns.ttl"
    local_file.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<http://remote.example.org#Mammal> a owl:Class .\n"
    )
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://remote.example.org#Mammal> .
    """)
    check = run_qa(
        g, local_imports={"http://remote.example.org#": str(local_file)}
    ).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_local_imports_term_absent_in_local_file_fails(make_graph, tmp_path):
    local_file = tmp_path / "remote_ns.ttl"
    local_file.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<http://remote.example.org#Other> a owl:Class .\n"
    )
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://remote.example.org#Mammal> .
    """)
    check = run_qa(
        g, local_imports={"http://remote.example.org#": str(local_file)}
    ).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


# ── Reference properties (skip-object-of) ─────────────────────────────────────

WIKI = "https://en.wikipedia.org/wiki/Interval_algebra"
LICENSE = "https://example.com/legal/license.md"


class _RecordingFetch:
    """uri_parser that records every namespace the check tries to fetch, then fails."""
    def __init__(self):
        self.fetched = []

    def __call__(self, uri):
        self.fetched.append(uri)
        raise Exception(f"no network in tests: {uri}")


def test_reference_property_objects_are_not_reported_or_fetched(make_graph):
    # The ticket's example: document links are not term uses.
    g = make_graph(f"""
    : a owl:Ontology .
    :Foo a owl:Class ;
        rdfs:seeAlso <{WIKI}> ;
        dcterms:license <{LICENSE}> .
    """)
    fetch = _RecordingFetch()
    check = run_qa(g, uri_parser=fetch).get(CHECK_NAME)
    assert check.passed, check.elements
    assert fetch.fetched == []


def test_genuine_undefined_reference_still_fails(make_graph):
    g = make_graph(f"""
    : a owl:Ontology .
    :Foo a owl:Class ; rdfs:seeAlso <{WIKI}> ; rdfs:subClassOf :Undefined .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert "Undefined" in check.elements
    assert "wikipedia" not in check.elements


def test_reference_target_also_used_as_term_is_still_checked(make_graph):
    # The same IRI as a real term (object of a non-reference property) is still checked,
    # so its namespace is fetched and the failure reported.
    g = make_graph(f"""
    : a owl:Ontology .
    :Foo a owl:Class ; rdfs:seeAlso <{WIKI}> ; rdfs:subClassOf <{WIKI}> .
    """)
    fetch = _RecordingFetch()
    check = run_qa(g, uri_parser=fetch).get(CHECK_NAME)
    assert not check.passed
    assert WIKI in check.elements
    assert fetch.fetched == ["https://en.wikipedia.org/wiki/"]


def test_reference_target_used_as_subject_is_still_checked(make_graph):
    g = make_graph(f"""
    : a owl:Ontology .
    :Foo a owl:Class ; rdfs:seeAlso <{WIKI}> .
    <{WIKI}> rdfs:comment "A page." .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert WIKI in check.elements


@pytest.mark.parametrize("prop", [p for p in DEFAULT_SKIP_OBJECT_OF if not p.endswith("*")])
def test_every_default_reference_property_is_skipped(make_graph, prop):
    g = make_graph(f"""
    : a owl:Ontology .
    :Foo a owl:Class ; <{expand_curie(prop)}> <{LICENSE}> .
    """)
    fetch = _RecordingFetch()
    check = run_qa(g, uri_parser=fetch).get(CHECK_NAME)
    # Only the object is skipped; the predicate itself is in a trusted or fetched namespace.
    assert LICENSE not in check.elements
    assert "https://example.com/legal/" not in fetch.fetched


def test_namespace_wildcard_default_skips_vocab_status_terms(make_graph):
    g = make_graph(f"""
    : a owl:Ontology .
    :Foo a owl:Class ; <http://www.w3.org/2003/06/sw-vocab-status/ns#userdocs> <{LICENSE}> .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert LICENSE not in check.elements


def test_skip_object_of_overrides_defaults(make_graph):
    # A configured list replaces the defaults: seeAlso is checked again, the custom
    # property is skipped.
    g = make_graph(f"""
    : a owl:Ontology .
    :docs a owl:AnnotationProperty .
    :Foo a owl:Class ; rdfs:seeAlso <{WIKI}> ; :docs <{LICENSE}> .
    """)
    check = run_qa(g, uri_parser=_no_fetch, skip_object_of=["http://example.org#docs"]).get(CHECK_NAME)
    assert WIKI in check.elements
    assert LICENSE not in check.elements


def test_empty_skip_object_of_checks_every_object(make_graph):
    g = make_graph(f"""
    : a owl:Ontology ; owl:versionIRI <http://example.org/1.0> .
    :Foo a owl:Class ; rdfs:seeAlso <{WIKI}> .
    """)
    check = run_qa(g, uri_parser=_no_fetch, skip_object_of=[]).get(CHECK_NAME)
    assert WIKI in check.elements
    assert "http://example.org/1.0" in check.elements

