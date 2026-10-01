"""The olq: vocabulary in ontology/olq.ttl must match the terms the DQV report uses."""
import os

import rdflib
from rdflib import OWL, RDF, RDFS

from scripts.dqv import OLQ, build_dqv_graph
from scripts.ontology_qa import CHECKLIST, deepcopy_list, lint_selection, parse_lint_config, run_qa

REPO = os.path.join(os.path.dirname(__file__), '..')
VOCAB = os.path.join(REPO, 'ontology', 'olq.ttl')
VOCAB_CONFIG = os.path.join(REPO, 'ontology', '.rdf-lint.yml')
MISSING_IMPORT = "http://example.org/missing-import"


def _vocab():
    return rdflib.Graph().parse(VOCAB, format='turtle')


def _olq_terms(g):
    """Every olq: IRI appearing in the graph, other than the namespace (ontology) itself."""
    return {t for triple in g for t in triple
            if isinstance(t, rdflib.URIRef) and str(t).startswith(str(OLQ)) and t != OLQ[""]}


def _defined_terms(vocab):
    return {s for s in vocab.subjects(RDFS.isDefinedBy, OLQ[""])}


def _sample_report(make_graph):
    # Exercises every olq: term: failing checks, a clean roll-up, and a same-label
    # clash plus an unresolvable import (both produce olq:relatedResource).
    g = make_graph(f"""
    : a owl:Ontology ; owl:imports <{MISSING_IMPORT}> .
    :a a owl:ObjectProperty ; rdfs:label "x" .
    :b a owl:ObjectProperty ; rdfs:label "x" .
    """)
    # A config that disables owl-declaration, which the owl-description check depends on, so
    # the rule re-enables it: the configuration then has settings of every origin (config
    # file, default, bundled, rule) while every other check still runs.
    rule_reasons = {}
    lint_config = {"disable": ["check_owl_declaration"]}
    checklist, _ = lint_selection(lint_config, deepcopy_list(CHECKLIST), rule_reasons)
    result = run_qa(g, uri_parser=lambda u: (_ for _ in ()).throw(Exception(u)),
                    local_imports={MISSING_IMPORT: "/nonexistent/import.ttl"},
                    checklist=checklist, lint_config=lint_config, rule_reasons=rule_reasons,
                    config_file=".rdf-lint.yml")
    return build_dqv_graph([result])


def test_vocabulary_declares_ontology():
    vocab = _vocab()
    assert (OLQ[""], RDF.type, OWL.Ontology) in vocab


def test_every_term_used_in_report_is_defined(make_graph):
    used = _olq_terms(_sample_report(make_graph))
    assert used, "sample report uses no olq: terms"
    assert used <= _defined_terms(_vocab()), used - _defined_terms(_vocab())


def test_every_defined_term_is_used_in_report(make_graph):
    vocab = _vocab()
    # Classes only used to type other olq: terms (e.g. olq:SettingOrigin for olq:ConfigFile)
    # never appear in a report themselves.
    type_only = {o for s in _defined_terms(vocab) for o in vocab.objects(s, RDF.type) if o in _defined_terms(vocab)}
    unused = _defined_terms(vocab) - _olq_terms(_sample_report(make_graph)) - type_only
    assert not unused, f"defined in olq.ttl but never emitted: {unused}"


def test_every_term_is_labelled_and_described():
    vocab = _vocab()
    for term in _defined_terms(vocab):
        assert vocab.value(term, RDFS.label) is not None, term
        assert vocab.value(term, RDFS.comment) is not None, term


def test_vocabulary_passes_ontolint():
    # Offline: the vocabulary's own config ignores link targets; DQV and SHACL terms are
    # external vocabularies we don't fetch in tests.
    _, ignore_imports, _, _, _ = parse_lint_config(VOCAB_CONFIG)
    ignore_imports += ["http://www.w3.org/ns/dqv#"]
    result = run_qa(_vocab(), files_processed=[VOCAB], ignore_imports=ignore_imports,
                    uri_parser=lambda u: (_ for _ in ()).throw(Exception(u)))
    assert result.passed, [(c.name, c.elements) for c in result.failures]
