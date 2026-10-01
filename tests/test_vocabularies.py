"""Bundled vocabularies (vocabularies/): integrity, coverage, and offline term validation."""
import inspect
import os
from pathlib import Path

import pytest
import rdflib
import yaml
from rdflib import namespace as N

import scripts.ontology_qa as qa
from scripts.ontology_qa import VOCAB_DIR, bundled_vocabularies, iri_key, run_qa

MANIFEST = yaml.safe_load(open(VOCAB_DIR / 'manifest.yml', encoding='utf-8'))
UNDEFINED = "Undefined terms"
IMPORTS = "Unresolvable imports"


class _NoNetwork:
    """uri_parser that records every namespace the check tries to fetch, then fails."""
    def __init__(self):
        self.fetched = []

    def __call__(self, uri):
        self.fetched.append(uri)
        raise Exception(f"no network in tests: {uri}")


def _undefined(make_graph, ttl, **kwargs):
    fetch = _NoNetwork()
    prefixes = "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    check = run_qa(make_graph(prefixes + ": a owl:Ontology .\n" + ttl), uri_parser=fetch, **kwargs).get(UNDEFINED)
    return check, fetch


# ── the bundle itself ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("entry", MANIFEST, ids=lambda e: e['file'])
def test_manifest_entry_parses_and_defines_terms_in_its_namespace(entry):
    path = VOCAB_DIR / entry['file']
    assert path.exists(), path
    g = rdflib.Graph().parse(path)
    ns = entry['namespace']
    terms = {s for s in g.subjects() if isinstance(s, rdflib.URIRef) and str(s).startswith(ns) and str(s) != ns}
    assert terms, f"{entry['file']} defines no terms in {ns}"


def test_every_vocabulary_file_is_in_the_manifest_and_readme():
    files = {p.name for p in VOCAB_DIR.glob('*.ttl')}
    assert files == {e['file'] for e in MANIFEST}
    readme = (VOCAB_DIR / 'README.md').read_text(encoding='utf-8')
    for f in files:
        assert f"`{f}`" in readme, f"{f} is not documented in vocabularies/README.md"


# rdflib's built-in term lists, for the vocabularies it has them for. Every term rdflib
# knows must be in our file, or a valid term would be reported as undefined.
RDFLIB_LISTS = {
    'rdf.ttl': N.RDF, 'rdfs.ttl': N.RDFS, 'owl.ttl': N.OWL, 'xsd.ttl': N.XSD, 'shacl.ttl': N.SH,
    'skos.ttl': N.SKOS, 'dcterms.ttl': N.DCTERMS, 'dc.ttl': N.DC, 'dcam.ttl': N.DCAM,
    'dctype.ttl': N.DCMITYPE, 'foaf.ttl': N.FOAF, 'vann.ttl': N.VANN, 'prov.ttl': N.PROV,
    'org.ttl': N.ORG, 'dcat3.ttl': N.DCAT,
}


@pytest.mark.parametrize("filename", sorted(RDFLIB_LISTS))
def test_bundled_file_covers_rdflib_term_list(filename):
    ns = RDFLIB_LISTS[filename]
    base = str(ns)
    known = {base + name for name in inspect.get_annotations(ns) if not name.startswith('_')}
    g = rdflib.Graph().parse(VOCAB_DIR / filename)
    defined = {str(s) for s in g.subjects() if isinstance(s, rdflib.URIRef)}
    missing = sorted(t[len(base):] for t in known - defined)
    assert not missing, f"{filename} lacks terms rdflib defines: {missing}"


def test_rdf_includes_rdf_1_2_terms():
    g = rdflib.Graph().parse(VOCAB_DIR / 'rdf.ttl')
    for name in ["reifies", "dirLangString", "PropositionForm",
                 "propositionFormSubject", "propositionFormPredicate", "propositionFormObject"]:
        # Built as a plain IRI: rdflib's closed RDF namespace doesn't know these RDF 1.2 terms.
        assert (rdflib.URIRef(str(rdflib.RDF) + name), None, None) in g, name


# ── offline validation of core-vocabulary terms ───────────────────────────────

def test_typos_in_core_vocabularies_are_reported_offline(make_graph):
    check, fetch = _undefined(make_graph, """
    :Foo a owl:Class ; skos:scopNote "x" ; dcterms:licence "MIT" .
    :p a owl:DatatypeProperty ; rdfs:range xsd:strin .
    """)
    for typo in ["skos/core#scopNote", "dc/terms/licence", "XMLSchema#strin"]:
        assert typo in check.elements, typo
    assert "fetch failure" not in check.elements
    assert fetch.fetched == []


def test_valid_core_and_rdf_1_2_terms_pass_offline(make_graph):
    check, fetch = _undefined(make_graph, """
    :Foo a owl:Class ; skos:scopeNote "x" ; rdfs:label "Foo" .
    :p a owl:DatatypeProperty ; rdfs:range xsd:dateTimeStamp .
    :q a owl:DatatypeProperty ; rdfs:range owl:real .
    :standIn a rdf:PropositionForm ; rdf:reifies :Foo .
    :list rdf:_3 :Foo .
    """)
    assert check.passed, check.elements
    assert fetch.fetched == []


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_schema_org_terms_validated_for_http_and_https(make_graph, scheme):
    check, fetch = _undefined(make_graph, f"""
    :Foo a owl:Class ; <{scheme}://schema.org/name> "Foo" ; <{scheme}://schema.org/nmae> "Foo" .
    """)
    assert f"{scheme}://schema.org/nmae" in check.elements
    assert f"{scheme}://schema.org/name" not in check.elements
    assert fetch.fetched == []


def test_owl_imports_of_bundled_ontology_resolves_offline(make_graph):
    g = make_graph("""
    : a owl:Ontology ; owl:imports <http://www.w3.org/2004/02/skos/core> , <http://www.w3.org/ns/shacl#> .
    """)
    check = run_qa(g, uri_parser=_NoNetwork()).get(IMPORTS)
    assert check.passed, check.elements


def test_project_local_import_overrides_bundled_file(make_graph, tmp_path):
    skos_override = tmp_path / "skos-custom.ttl"
    skos_override.write_text("""
    @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
    skos:customNote a <http://www.w3.org/2002/07/owl#AnnotationProperty> .
    """)
    # Configured with the ontology IRI form (no '#'): still overrides the namespace.
    check, _ = _undefined(make_graph, """
    :Foo a owl:Class ; skos:customNote "x" ; skos:scopeNote "y" .
    """, local_imports={"http://www.w3.org/2004/02/skos/core": str(skos_override)})
    assert "customNote" not in check.elements
    assert "scopeNote" in check.elements  # not in the override file


# ── trust via imports.ignore, in either key form ──────────────────────────────

@pytest.mark.parametrize("form", ["http://example.org/vendor/ns#", "http://example.org/vendor/ns"])
def test_ignored_namespace_is_trusted_in_either_form(make_graph, form):
    g = make_graph("""
    : a owl:Ontology ; owl:imports <http://example.org/vendor/ns> .
    :Foo a owl:Class ; rdfs:subClassOf <http://example.org/vendor/ns#Thing> .
    """)
    fetch = _NoNetwork()
    result = run_qa(g, uri_parser=fetch, ignore_imports=[form])
    assert result.get(UNDEFINED).passed, result.get(UNDEFINED).elements
    assert fetch.fetched == []
    # The owl:imports of that ontology is ignored too, so nothing is left to resolve.
    assert "vendor" not in result.get(IMPORTS).elements


def test_trusted_namespaces_constant_is_removed():
    assert not hasattr(qa, "TRUSTED_NAMESPACES")


def test_iri_key_matches_namespace_and_ontology_forms():
    assert iri_key("http://www.w3.org/2004/02/skos/core#") == iri_key("http://www.w3.org/2004/02/skos/core")
    assert iri_key("http://purl.org/dc/terms/") == iri_key("http://purl.org/dc/terms")


# ── location ──────────────────────────────────────────────────────────────────

def test_bundled_vocabularies_found_from_any_working_directory(make_graph, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert all(Path(p).is_absolute() and os.path.exists(p) for p in bundled_vocabularies().values())
    check, _ = _undefined(make_graph, ":Foo a owl:Class ; skos:scopNote \"x\" .")
    assert "scopNote" in check.elements
