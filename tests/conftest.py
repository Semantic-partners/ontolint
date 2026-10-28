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

DATA = Path(__file__).parent / 'data'
REPORTERS_TTL = DATA / 'reporters.ttl'

# The reporter suites run over three cases, because several checks answer differently
# depending only on how the inputs were batched — which is the whole of #96. Linted alone,
# the fragment is the only way to see the two ontology-metadata checks fail; linted beside
# reporters.ttl it changes the declaration check's answer again, and puts its own terms
# outside the one declared namespace.
CASES = {
    'reporters': ['reporters.ttl'],
    'fragment': ['fragment.ttl'],
    'merged': ['reporters.ttl', 'fragment.ttl'],
}

def _offline(uri):
    raise OSError(f"the reporter fixture must not need the network: {uri}")


def case_graph(case):
    """A fresh parse each time: the checks remove instance data from the graph they run on."""
    graph = rdflib.Graph()
    for name in CASES[case]:
        graph.parse(DATA / name, format='turtle')
    return graph


# What each input is reported as. Without these, a check that names its source mints
# file:///<cwd>/<name>, so the stored expectation would embed the checkout path and match
# only the machine that generated it. source_iris exists for exactly this.
SOURCE_IRI = 'https://example.org/input/'


def lint_case(case):
    """The QAResult linting a case produces — what test_pipeline_lint_to_qaresult.py checks."""
    from scripts.ontology_qa import Config, lint_graph
    names = list(CASES[case])
    return lint_graph(case_graph(case), names, Config(uri_parser=_offline),
                      source_iris=[SOURCE_IRI + name for name in names])


def stored_qa_result_for(case):
    """
    The QAResult written out under tests/data/, and the input to the reporter suites.

    They take the stored instance rather than a freshly linted one, so they test the
    projection alone: a change to what a check finds cannot break them, and a change to a
    reporter cannot be blamed on the checks. test_pipeline_lint_to_qaresult.py is what keeps the
    stored instance honest — it asserts linting the input still produces it.
    """
    import importlib
    return importlib.import_module(f'tests.data.{case}_qaresult').EXPECTED


def stored_markdown_for(case):
    """The Markdown stored under tests/data/, which linting the case should still render."""
    return (DATA / f'{case}_report.md').read_text()


def stored_ctrf_for(case):
    """The CTRF report stored under tests/data/, as the dict build_ctrf_report returns."""
    import json
    return json.loads((DATA / f'{case}_ctrf.json').read_text())


def stored_dqv_for(case):
    """
    The DQV report stored under tests/data/, parsed back into a graph.

    One per case, as for the other reporters. A report covering several results is not the
    union of their individual ones — a measurement IRI hashes the assessment node it hangs
    from, so every one of them differs — so multi-result runs are pinned end-to-end in
    tests/dqv/ instead, where `per-file/` and `merged/` already cover both shapes.
    """
    return rdflib.Graph().parse(DATA / f'{case}_dqv.ttl', format='turtle')


@pytest.fixture
def reporters_ttl():
    """The path to the main input, for the suites that run the CLI over it."""
    return REPORTERS_TTL


@pytest.fixture
def reporters_graph():
    return case_graph('reporters')


@pytest.fixture
def reporters_result():
    return lint_case('reporters')


@pytest.fixture
def stored_qa_result():
    """The stored QAResult for the main case, for assertions written against its content."""
    return stored_qa_result_for('reporters')


@pytest.fixture
def stored_markdown():
    return stored_markdown_for('reporters')


@pytest.fixture
def stored_ctrf():
    return stored_ctrf_for('reporters')


@pytest.fixture
def stored_dqv():
    return stored_dqv_for('reporters')


def render_case(case):
    """
    Render the Markdown for a fresh lint of a case.

    Taken from `_process_loaded_graph`, the seam that turns a run into report text. `main()`
    wraps it with the heading, the load log and the config log — run context rather than
    anything the checks produced, and carrying input paths, so test_e2e_cli.py covers
    those. Each call reparses, because blank node identifiers and SPARQL row order both
    differ between parses and that is what makes a rendering unstable.
    """
    from types import SimpleNamespace
    from scripts.ontology_qa import CHECKLIST, Config, _process_loaded_graph, deepcopy_list
    log, _ = _process_loaded_graph(
        case_graph(case), list(CASES[case]),
        SimpleNamespace(verbose=False, profile_only=False),
        Config(uri_parser=_offline), deepcopy_list(CHECKLIST), None)
    return log


@pytest.fixture
def render_markdown():
    """Render the main case's Markdown, as many times as asked."""
    return lambda: render_case('reporters')


@pytest.fixture
def rendered_markdown(render_markdown):
    """The Markdown a lint of the input renders."""
    return render_markdown()
