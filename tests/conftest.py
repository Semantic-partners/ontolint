import os

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
