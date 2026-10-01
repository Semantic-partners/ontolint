"""
Design comparison: can .rdf-lint.yml become RDF by direct JSON-LD mapping, without
changing the YAML format? All files are in tests/config-jsonld/:

    rdf-lint.yml          sample config using every feature
    context.jsonld        JSON-LD 1.1 context applied to the YAML as-is
    expected-jsonld.ttl   the RDF the context produces (direct mapping)
    expected-model.ttl    the same settings in the report's model (olq:Configuration /
                          olq:Setting), config-file settings only, for side-by-side review
    model-rdf-lint.yml    expected-model.ttl written back as YAML: what an input file would
    model-context.jsonld  have to contain for plain JSON-LD to produce the model directly

Both TTL files are generated, so after changing the YAML or the context, regenerate and
review the diff:   UPDATE_GOLDEN=1 poetry run pytest tests/test_config_jsonld.py
"""
import json
import os
from pathlib import Path

import pytest
import rdflib
import yaml

from scripts import dqv
from scripts.ontology_qa import (CHECKLIST, deepcopy_list, describe_configuration,
                                 lint_selection, parse_lint_config)

DIR = Path(__file__).parent / 'config-jsonld'
CONFIG = DIR / 'rdf-lint.yml'
CONTEXT = DIR / 'context.jsonld'
# Fixed IRIs so the output doesn't depend on where the repo is checked out.
CONFIG_IRI = 'https://example.org/project/.rdf-lint.yml'
REPORT_BASE = 'https://example.org/qa#'


def _jsonld_graph():
    """Lift the YAML with the context: the loader only adds the node's identity and type."""
    config = yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    context = json.loads(CONTEXT.read_text(encoding='utf-8'))['@context']
    doc = {'@context': context, '@id': '', '@type': 'olq:Configuration', **config}
    g = rdflib.Graph().parse(data=json.dumps(doc), format='json-ld', base=CONFIG_IRI)
    for prefix in ('olq', 'check', 'rdf', 'rdfs', 'skos', 'dcterms', 'vs'):
        g.bind(prefix, context[prefix])
    return g


def _model_graph(monkeypatch):
    """The config-file settings as this branch's DQV report records them."""
    monkeypatch.chdir(DIR)
    lint_config, ignore, local, exclude, skip = parse_lint_config(CONFIG.name)
    rule_reasons = {}
    checklist, _ = lint_selection(lint_config, deepcopy_list(CHECKLIST), rule_reasons)
    settings = describe_configuration(checklist, lint_config, rule_reasons, ignore, local,
                                      exclude, skip, config_file=CONFIG.name)
    from_file = [s for s in settings if s.origin == 'config']
    g = rdflib.Graph()
    for prefix, ns in [('olq', dqv.OLQ), ('dqv', dqv.DQV), ('prov', dqv.PROV), ('sh', dqv.SH),
                       ('skos', rdflib.SKOS), ('rdfs', rdflib.RDFS), ('xsd', rdflib.XSD)]:
        g.bind(prefix, ns)
    dqv._add_configuration(g, REPORT_BASE, from_file, CONFIG.name)
    return g


def _check(g, expected_path):
    if os.environ.get('UPDATE_GOLDEN'):
        expected_path.write_text(g.serialize(format='turtle'), encoding='utf-8')
        pytest.skip(f"updated {expected_path.name}")
    expected = rdflib.Graph().parse(expected_path, format='turtle')
    missing = sorted(set(expected) - set(g), key=str)
    unexpected = sorted(set(g) - set(expected), key=str)
    assert not missing and not unexpected, (
        f"{expected_path.name} differs:\n"
        + "".join(f"- {' '.join(t.n3() for t in triple)}\n" for triple in missing)
        + "".join(f"+ {' '.join(t.n3() for t in triple)}\n" for triple in unexpected)
        + "If intended: UPDATE_GOLDEN=1 poetry run pytest tests/test_config_jsonld.py")


def test_sample_config_still_loads_with_the_existing_parser():
    # The JSON-LD route must not need any change to the YAML format.
    lint_config, ignore, local, exclude, skip = parse_lint_config(str(CONFIG))
    assert lint_config == {'disable': ['check_owl_declaration', 'check_hijacking', 'check_property_missing_domain']}
    assert ignore and local and exclude and skip


def test_direct_jsonld_mapping_matches_expected():
    g = _jsonld_graph()
    assert not any(isinstance(t, rdflib.BNode) for triple in g for t in triple)
    _check(g, DIR / 'expected-jsonld.ttl')


def test_report_model_matches_expected(monkeypatch):
    _check(_model_graph(monkeypatch), DIR / 'expected-model.ttl')


def test_model_yaml_with_model_context_reproduces_expected_model():
    # Plain JSON-LD, no ontolint code: the loader adds only the context.
    config = yaml.safe_load((DIR / 'model-rdf-lint.yml').read_text(encoding='utf-8'))
    context = json.loads((DIR / 'model-context.jsonld').read_text(encoding='utf-8'))['@context']
    g = rdflib.Graph().parse(data=json.dumps({'@context': context, **config}), format='json-ld')
    expected = rdflib.Graph().parse(DIR / 'expected-model.ttl', format='turtle')
    missing = sorted(set(expected) - set(g), key=str)
    unexpected = sorted(set(g) - set(expected), key=str)
    assert not missing and not unexpected, (
        "model-rdf-lint.yml + model-context.jsonld != expected-model.ttl\n"
        + "".join(f"- {' '.join(t.n3() for t in triple)}\n" for triple in missing)
        + "".join(f"+ {' '.join(t.n3() for t in triple)}\n" for triple in unexpected))

