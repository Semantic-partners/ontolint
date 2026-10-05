"""Bundled vocabularies (vocabularies/): integrity, coverage, and offline term validation."""
import hashlib
import inspect
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest
import rdflib
from rdflib import namespace as N

import scripts.ontology_qa as qa
from scripts.ontology_qa import VOCAB_CATALOG, bundled_vocabularies, iri_key, run_qa

CATALOG = VOCAB_CATALOG
VOCAB_DIR = VOCAB_CATALOG.parent  # repo layout: the catalogued files live next to it
VOCABULARIES = sorted(bundled_vocabularies().items(), key=lambda item: item[1])
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

@pytest.mark.parametrize("ns, path", VOCABULARIES, ids=[Path(p).name for _, p in VOCABULARIES])
def test_catalog_entry_parses_and_defines_terms_in_its_namespace(ns, path):
    assert Path(path).parent == VOCAB_DIR, path
    assert os.path.exists(path), path
    g = rdflib.Graph().parse(path)
    terms = {s for s in g.subjects() if isinstance(s, rdflib.URIRef) and str(s).startswith(ns) and str(s) != ns}
    assert terms, f"{Path(path).name} defines no terms in {ns}"


def test_every_vocabulary_file_is_in_the_catalog_and_readme():
    files = {p.name for p in VOCAB_DIR.glob('*.ttl')} - {CATALOG.name}
    assert files == {Path(p).name for _, p in VOCABULARIES}
    readme = (VOCAB_DIR / 'README.md').read_text(encoding='utf-8')
    for f in files:
        assert f"`{f}`" in readme, f"{f} is not documented in vocabularies/README.md"


def test_discovery_starts_from_the_catalog(make_graph, tmp_path, monkeypatch):
    # Which vocabularies exist and where their files are comes only from the catalog: a
    # catalog elsewhere, whose distribution points at a file in another directory, is honoured.
    vocab = tmp_path / "files" / "example.ttl"
    vocab.parent.mkdir()
    vocab.write_text("""
    @prefix ex: <http://example.org/vocab#> .
    ex:known a <http://www.w3.org/2000/01/rdf-schema#Class> .
    """)
    catalog = tmp_path / "catalogs" / "catalog.ttl"
    catalog.parent.mkdir()
    catalog.write_text("""
    @prefix dcat: <http://www.w3.org/ns/dcat#> .
    @prefix vann: <http://purl.org/vocab/vann/> .
    <https://ontolint.org/test-catalog> a dcat:Catalog ; dcat:dataset <https://ontolint.org/test-example> .
    <https://ontolint.org/test-example> a dcat:Dataset ;
        vann:preferredNamespaceUri "http://example.org/vocab#" ;
        dcat:distribution [ a dcat:Distribution ; dcat:downloadURL <../files/example.ttl> ] .
    """)
    monkeypatch.setattr(qa, "VOCAB_CATALOG", catalog)
    bundled_vocabularies.cache_clear()
    try:
        assert bundled_vocabularies() == {"http://example.org/vocab#": str(vocab.resolve())}
        assert qa._is_bundled(vocab)
        check, fetch = _undefined(make_graph, """
        :Foo a owl:Class ; rdfs:subClassOf <http://example.org/vocab#known>, <http://example.org/vocab#unknown> .
        """)
        reported = {str(v.resource) for v in check.violations}
        assert "http://example.org/vocab#unknown" in reported
        assert "http://example.org/vocab#known" not in reported
        assert "http://example.org/vocab#" not in fetch.fetched
    finally:
        bundled_vocabularies.cache_clear()


def test_catalog_entry_without_namespace_is_rejected(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.ttl"
    catalog.write_text("""
    @prefix dcat: <http://www.w3.org/ns/dcat#> .
    <https://ontolint.org/test-broken> a dcat:Dataset .
    """)
    monkeypatch.setattr(qa, "VOCAB_CATALOG", catalog)
    bundled_vocabularies.cache_clear()
    try:
        with pytest.raises(ValueError):
            bundled_vocabularies()
    finally:
        bundled_vocabularies.cache_clear()


def test_catalog_describes_every_dataset():
    g = rdflib.Graph().parse(CATALOG)
    catalog = next(g.subjects(rdflib.RDF.type, rdflib.DCAT.Catalog))
    datasets = set(g.subjects(rdflib.RDF.type, rdflib.DCAT.Dataset))
    assert set(g.objects(catalog, rdflib.DCAT.dataset)) == datasets
    for ds in datasets:
        for p in (rdflib.DCTERMS.title, rdflib.DCTERMS.source, rdflib.DCTERMS.license,
                  rdflib.VANN.preferredNamespacePrefix):
            assert g.value(ds, p) is not None, f"{ds} has no {p}"


def test_catalog_uses_only_defined_terms(make_graph):
    # The catalog is RDF too: its DCAT, Dublin Core, VANN and SKOS terms resolve from the
    # bundle. Trusted: the catalog's own https://ontolint.org/ IRIs (it declares no
    # owl:Ontology to make that namespace local), IANA media types (not published as RDF)
    # and SPDX (checksum terms, not bundled).
    g = rdflib.Graph().parse(CATALOG)
    check = run_qa(g, uri_parser=_NoNetwork(),
                   ignore_imports=["https://ontolint.org/",
                                   "https://www.iana.org/assignments/media-types/text/",
                                   "http://spdx.org/rdf/terms#"]).get(UNDEFINED)
    assert check.passed, check.elements


def test_distribution_checksums_match_files():
    # Pins each bundled file to the exact bytes recorded in the catalog (provenance).
    g = rdflib.Graph().parse(CATALOG)
    SPDX = rdflib.Namespace("http://spdx.org/rdf/terms#")
    for dist in g.subjects(rdflib.RDF.type, rdflib.DCAT.Distribution):
        path = Path(url2pathname(urlparse(str(g.value(dist, rdflib.DCAT.downloadURL))).path))
        recorded = str(g.value(g.value(dist, SPDX.checksum), SPDX.checksumValue))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == recorded, (
            f"{path.name} changed: update its checksum, source and change note in catalog.ttl")


# rdflib's built-in term lists, for the vocabularies it has them for. Every term rdflib
# knows must be in our file, or a valid term would be reported as undefined.
RDFLIB_LISTS = {
    'rdf.ttl': N.RDF, 'rdfs.ttl': N.RDFS, 'owl.ttl': N.OWL, 'shacl.ttl': N.SH,
    'skos.ttl': N.SKOS, 'dcterms.ttl': N.DCTERMS, 'dc.ttl': N.DC, 'dcam.ttl': N.DCAM,
    'dctype.ttl': N.DCMITYPE, 'foaf.ttl': N.FOAF, 'vann.ttl': N.VANN, 'prov.ttl': N.PROV,
    'org.ttl': N.ORG, 'dcat3.ttl': N.DCAT, 'time.ttl': N.TIME, 'odrl.ttl': N.ODRL2,
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
    :Short a rdfs:Datatype ; owl:withRestrictions ( [ xsd:assertions "true" ] ) .
    :q a owl:DatatypeProperty ; rdfs:range owl:real .
    :standIn a rdf:PropositionForm ; rdf:reifies :Foo .
    :list rdf:_3 :Foo .
    """)
    assert check.passed, check.elements
    assert fetch.fetched == []


@pytest.mark.parametrize("namespace, valid, typo", [
    ("http://www.w3.org/ns/dqv#", "hasQualityMeasurement", "hasQualityMeasurment"),
    ("http://www.w3.org/2006/time#", "hasBeginning", "hasBegining"),
    ("http://www.w3.org/ns/odrl/2/", "hasPolicy", "hasPolicies"),
    ("http://datashapes.org/dash#", "editor", "editr"),
])
def test_dqv_time_odrl_dash_terms_validated_offline(make_graph, namespace, valid, typo):
    check, fetch = _undefined(make_graph, f"""
    :Foo a owl:Class ; <{namespace}{valid}> :Bar ; <{namespace}{typo}> :Bar .
    """)
    assert namespace + typo in check.elements
    assert namespace + valid not in check.elements
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
