import os
from pathlib import Path

# Must run before scripts.ontology_qa is imported so module-level SPARQL loading
# resolves the sparql/ directory correctly regardless of where pytest is invoked from.
os.environ.setdefault(
    'QA_SPARQL_DIR',
    os.path.join(os.path.dirname(__file__), '..', 'sparql')
)

import socket

import rdflib
import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Keep tests offline: a fetch fails at once, as on a machine with no network.

    Without this, tests using the shared http://example.org# prefix fetch example.org
    for the undefined-terms check, which made CI slow and network-dependent.
    """
    def blocked(*args, **kwargs):
        raise OSError("network access is blocked in tests")
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)

PREFIXES = """
@prefix : <http://example.org#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
"""


@pytest.fixture
def make_graph():
    def _make(ttl: str) -> rdflib.Graph:
        g = rdflib.Graph()
        g.parse(data=PREFIXES + ttl, format='turtle')
        return g
    return _make


# ── the shared reporter fixture ───────────────────────────────────────────────
#
# One input behind four suites — lint -> QAResult, lint -> Markdown, QAResult -> CTRF and
# QAResult -> DQV — so they all describe the same run and can be read against each other.
# See tests/data/reporters.ttl.

REPORTERS_TTL = Path(__file__).parent / 'data' / 'reporters.ttl'


def _offline(uri):
    raise OSError(f"the reporter fixture must not need the network: {uri}")


@pytest.fixture
def reporters_ttl():
    """The path to the shared input, for the suites that run the CLI over it."""
    return REPORTERS_TTL


@pytest.fixture
def reporters_graph():
    """A fresh parse each time: the checks remove instance data from the graph they run on."""
    return rdflib.Graph().parse(REPORTERS_TTL, format='turtle')


@pytest.fixture
def reporters_result(reporters_graph):
    """The QAResult produced by linting the input — what test_lint_to_qaresult.py checks."""
    from scripts.ontology_qa import Config, lint_graph
    return lint_graph(reporters_graph, ['reporters.ttl'], Config(uri_parser=_offline))


@pytest.fixture
def stored_result():
    """
    The QAResult written out under tests/data/, and the input to the reporter suites.

    They take the stored instance rather than a freshly linted one, so they test the
    projection alone: a change to what a check finds cannot break them, and a change to a
    reporter cannot be blamed on the checks. test_lint_to_qaresult.py is what keeps the
    stored instance honest — it asserts linting the input still produces it.
    """
    from tests.data.reporters_qaresult import EXPECTED
    return EXPECTED


@pytest.fixture
def stored_markdown():
    """The Markdown stored under tests/data/, which linting the input should still render."""
    from tests.data.reporters_markdown import EXPECTED
    return EXPECTED


@pytest.fixture
def render_markdown():
    """
    Render the Markdown for a fresh lint of the input, as many times as asked.

    Taken from `_process_loaded_graph`, the seam that turns a run into report text. `main()`
    wraps it with the heading, the load log and the config log — run context rather than
    anything the checks produced, and carrying input paths, so test_integration.py covers
    those. Each call reparses, because blank node identifiers and SPARQL row order both
    differ between parses and that is what makes a rendering unstable.
    """
    from types import SimpleNamespace
    from scripts.ontology_qa import CHECKLIST, Config, _process_loaded_graph, deepcopy_list

    def render():
        log, _ = _process_loaded_graph(
            rdflib.Graph().parse(REPORTERS_TTL, format='turtle'), ['reporters.ttl'],
            SimpleNamespace(verbose=False, profile_only=False),
            Config(uri_parser=_offline), deepcopy_list(CHECKLIST), None)
        return log

    return render


@pytest.fixture
def rendered_markdown(render_markdown):
    """The Markdown a lint of the input renders."""
    return render_markdown()
