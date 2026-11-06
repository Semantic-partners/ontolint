"""
Reading and writing RDF terms: namespaces, CURIEs, and how a term is shown to a reader.

The bottom of the stack — nothing here knows what a check is, what a report looks like or
how a run is configured, so everything else may depend on it and it depends on nothing but
rdflib.
"""
import rdflib

def get_namespace(uri):
    """Extract namespace from a URIRef."""
    if '#' in uri:
        base = uri.rsplit('#', 1)[0]
        if len(base) >= 8:
            return base + '#'
    elif '/' in uri:
        base = uri.rsplit('/', 1)[0]
        if len(base) >= 8:
            return base + '/'
    return uri  # fallback


def iri_key(iri):
    """
    The form imports.ignore / imports.local entries are matched by: the IRI without one
    trailing '#' or '/'. So an ontology IRI (…/skos/core) and its namespace (…/skos/core#)
    match the same entry, whichever form was configured.
    """
    iri = str(iri)
    return iri[:-1] if iri.endswith(('#', '/')) else iri


def _term_from_string(value):
    """An absolute IRI string as a URIRef; anything else is an rdflib blank-node id."""
    return rdflib.URIRef(value) if ':' in value else rdflib.BNode(value)


def term_text(term):
    """
    A term as it appears in a text report.

    A blank node's rdflib identifier is invented at parse time and differs on every run, so
    printing it makes the report vary run to run while telling a reader nothing they can
    act on or look up. Anything that needs stable identity has it in the DQV report, where
    blank nodes are skolemized under the report's base.
    """
    return "[anonymous]" if isinstance(term, rdflib.BNode) else term


# Prefixes accepted in compact IRIs in the lint config (e.g. `rdf:PropositionForm`).
CONFIG_PREFIXES = {
    'rdf': str(rdflib.RDF),
    'rdfs': str(rdflib.RDFS),
    'owl': str(rdflib.OWL),
    'xsd': str(rdflib.XSD),
    'skos': str(rdflib.SKOS),
    'sh': str(rdflib.SH),
    'dcterms': str(rdflib.DCTERMS),
    'foaf': str(rdflib.FOAF),
    'schema': 'https://schema.org/',
    'vs': 'http://www.w3.org/2003/06/sw-vocab-status/ns#',
}


def expand_curie(value, allow_wildcard=False):
    """
    Expand a compact IRI using CONFIG_PREFIXES; full IRIs are returned unchanged. With
    allow_wildcard, a trailing `*` (e.g. `vs:*`) is kept, to match a whole namespace.
    """
    if value.endswith('*') and not allow_wildcard:
        raise ValueError(f"Wildcards are not supported here: '{value}'")
    if value.startswith(('http://', 'https://', 'urn:')):
        return value
    prefix, sep, local = value.partition(':')
    if sep and prefix in CONFIG_PREFIXES:
        return CONFIG_PREFIXES[prefix] + local
    raise ValueError(f"Cannot expand '{value}': use a full IRI or one of the prefixes {', '.join(CONFIG_PREFIXES)}")
