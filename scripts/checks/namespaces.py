"""
The checks that ask *"is this term in my declared namespace?"* — untyped classes and
properties, namespace hijacking, and undefined terms. They are the only checks whose
answer depends on what a unit is, which is #96.
"""
import re

import rdflib

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv
    from scripts.model import (AS_LIST, decided, EMPTY_POPULATION, not_assessed, note,
                               records_key, violation_formatting)
    from scripts.queries import exec_sparql
    from scripts.resolution import _describe_local, _parse_local
    from scripts.terms import expand_curie, get_namespace, iri_key, ontology_iris
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    from model import (AS_LIST, decided, EMPTY_POPULATION, not_assessed, note, records_key,
                       violation_formatting)
    from queries import exec_sparql
    from resolution import _describe_local, _parse_local
    from terms import expand_curie, get_namespace, iri_key, ontology_iris


# rdf:_1, rdf:_2, ... (container membership properties) are defined by RDF but can't be listed.
_CONTAINER_MEMBERSHIP = re.compile(re.escape(str(rdflib.RDF)) + r'_[1-9][0-9]*')


def check_untyped_class(in_metrics, graph, check, status, verbose, exclude_types=None):
    """
    QA test counting classes in the current namespace without owl:Class or rdfs:Class declaration
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        check (str): Dictionary key of the QA check being carried out.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
        exclude_types (list): Type IRIs whose instances are skipped by this check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = exec_sparql(graph, 'untyped_class', exclude_types)
    metrics[check] = 0 # 'untypedClasses'
    violations[check] = ""
    num_files = len(in_metrics['filesProcessed'])

    if not ontology_iris(graph):
        # Without a declared namespace, a term of the ontology's own cannot be told from an
        # external vocabulary's, so the query reports nothing. PASS would imply it had looked.
        decided(violations, check, "WARNING - Ontology namespace undefined, invalid metric. No way to confirm if a class is defined in the ontology or an external vocabulary.")
        not_assessed(violations, check, 'ontologyNotDeclared')

    elif not results and int(in_metrics['classCount']) > 0:
        decided(violations, check, "PASS - No violations found.")

    elif not results and int(in_metrics['classCount']) == 0:
        decided(violations, check, "WARNING - No classes defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} classes without `owl:Class` or `rdfs:Class` declaration:", AS_LIST)
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[records_key(check)] = [dqv.Violation(row.c) for row in results]
        violations[check] = string

    if ('ontologyNotDeclared' in in_metrics
            and 0 < in_metrics['ontologyNotDeclared'] < num_files and metrics[check] > 0):
        note(violations, check, "WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.")
    
    return metrics, violations, status


def check_untyped_property(in_metrics, graph, check, status, verbose):
    """
    QA test counting properties in the current namespace without rdf:Property, owl:ObjectProperty or owl:DatatypeProperty declaration.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        check (str): Dictionary key of the QA check being carried out.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = exec_sparql(graph, 'untyped_property')
    metrics[check] = 0 # 'untypedProperties'
    violations[check] = ""
    num_files = len(in_metrics['filesProcessed'])

    if not ontology_iris(graph):
        # Without a declared namespace, a term of the ontology's own cannot be told from an
        # external vocabulary's, so the query reports nothing. PASS would imply it had looked.
        decided(violations, check, "WARNING - Ontology namespace undefined, invalid metric. No way to confirm if a property is defined in the ontology or an external vocabulary.")
        not_assessed(violations, check, 'ontologyNotDeclared')

    elif not results and int(in_metrics['propertyCount']) > 0:
        decided(violations, check, "PASS - No violations found.")
              
    elif not results and int(in_metrics['propertyCount']) == 0:
        decided(violations, check, "WARNING - No properties defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} property without `rdf:Property`, `owl:ObjectProperty`, or `owl:DatatypeProperty` declaration:", AS_LIST)
        status += 1
        string = violation_formatting([row.property for row in results])
        violations[records_key(check)] = [dqv.Violation(row.property) for row in results]
        violations[check] = string
    
    if ('ontologyNotDeclared' in in_metrics
            and 0 < in_metrics['ontologyNotDeclared'] < num_files and metrics[check] > 0):
        note(violations, check, "WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.")
    
    return metrics, violations, status


def check_hijacking(in_metrics, graph, check, status, verbose):
    """
    QA test counting instances of hijacking, that is, resources defined in the current namespace but using a URI from an external vocabulary.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        check (str): Dictionary key of the QA check being carried out.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    num_files = len(in_metrics['filesProcessed'])
    fallback = False
    ontology_check = False
    if 'ontologyNotDeclared' in in_metrics:
        if in_metrics['ontologyNotDeclared'] > 0 and num_files == 1: fallback = True
        ontology_check = True
    
    if fallback:
        # TO DO: check if the fallback makes sense for graphs where more ontologies are loaded, say one defines the
        # namespace, and one extends it by defining additional resources.
        results = exec_sparql(graph, 'hijacking_fallback')
    else:
        results = exec_sparql(graph, 'hijacking')
    metrics[check] = 0 # 'hijacking'
    violations[check] = ""

    if not results:
        decided(violations, check, "PASS - No violations found.")

    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} resources defined using an external vocabulary prefix:", AS_LIST)
        string = violation_formatting([row.resource for row in results])
        violations[records_key(check)] = [dqv.Violation(row.resource) for row in results]
        violations[check] = string
    
    if ontology_check:
        if (in_metrics['ontologyNotDeclared'] > 0 and num_files == 1) or in_metrics['ontologyNotDeclared'] == num_files:
            note(violations, check, "WARNING - Ontology namespace undefined. The reported violations may be incorrect.")
        elif in_metrics['ontologyNotDeclared'] > 0 and in_metrics['ontologyNotDeclared'] < num_files and metrics[check] > 0:
            note(violations, check, "WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.")
    else:
        note(violations, check, "WARNING - Ontology namespace not checked. The reported violations may be incorrect.")
    
    return metrics, violations, status


def _reference_predicate_matcher(predicates):
    """A predicate test for skip-object-of: exact IRIs, or `<namespace>*` wildcards."""
    exact = {p for p in predicates if not p.endswith('*')}
    namespaces = tuple(p[:-1] for p in predicates if p.endswith('*'))
    return lambda p: str(p) in exact or (bool(namespaces) and str(p).startswith(namespaces))


def check_undefined_terms(in_metrics, graph, check, status, verbose,
                           uri_parser=lambda uri: rdflib.Graph().parse(uri),
                           local_imports=None, ignore_imports=None, skip_object_of=None):
    """
    QA test finding terms used in the ontology that are not defined locally (as a subject
    in the graph file) nor in their namespace's vocabulary: a bundled or imports.local file, or
    the namespace fetched from the web.

    Note that the URI parser defaults to the standard rdflib parse function unless specified.
    In a non networked env (see this repo's tests), you can override the URI parser to fetch 
    from elsewhere. 
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        check (str): Dictionary key of the QA check being carried out.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.

    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    metrics[check] = 0  # 'undefinedTerms'
    violations[check] = ""
    
    # Identify the local namespace(s) from declared owl:Ontology URIs.
    # For local namespaces we already hold the full graph — no remote fetch needed.
    local_namespaces = set()
    for ont_uri in in_metrics.get('ontologyURI', []):
        local_namespaces.add(get_namespace(str(ont_uri)))

    # Collect all URIRefs that appear anywhere in the graph and those used as subjects
    used_terms = set()
    local_subjects = set()
    is_reference = _reference_predicate_matcher(
        skip_object_of if skip_object_of is not None
        else [expand_curie(t, allow_wildcard=True) for t in DEFAULT_SKIP_OBJECT_OF])
    for s, p, o in graph.triples((None, None, None)):
        # Objects of reference properties (rdfs:seeAlso, dcterms:license, owl:versionIRI, ...)
        # link to documents, not terms, so they are neither reported nor fetched. The same
        # IRI used elsewhere as a term is still collected from that other triple.
        terms = (s, p) if is_reference(p) else (s, p, o)
        for term in terms:
            if isinstance(term, rdflib.URIRef):
                used_terms.add(str(term))

        # prevents namespace hijacking
        if isinstance(s, rdflib.URIRef) and get_namespace(s) in local_namespaces:
            local_subjects.add(str(s))

    if not used_terms:
        decided(violations, check, "WARNING - No terms to check.")
        return metrics, violations, status

    # Collect every HTTP namespace used that falls outside the local namespace(s) and isn't
    # ignored (trusted) by configuration. Bundled vocabularies resolve from imports.local.
    ignored = {iri_key(i) for i in (ignore_imports or [])}
    def is_ignored(uri, ns):
        return iri_key(uri) in ignored or iri_key(ns) in ignored
    remote_namespaces = set()
    for uri in used_terms:
        ns = get_namespace(uri)
        if (ns.startswith(('http://', 'https://'))
                and ns not in local_namespaces
                and not is_ignored(uri, ns)):
            remote_namespaces.add(ns)

    # Fetch each remote namespace (or read its local/bundled file) and collect its subjects
    local_map = {iri_key(k): v for k, v in (local_imports or {}).items()}
    remote_subjects = set()
    remote_subjects_by_ns = {}
    fetch_failures = set()
    applied_subs = []
    for ns_uri in remote_namespaces:
        try:
            local = local_map.get(iri_key(ns_uri))
            if local:
                remote_g = _parse_local(local)
                applied_subs.append((ns_uri, local))
            else:
                remote_g = uri_parser(ns_uri)
            subjects = {str(s) for s, _, _ in remote_g if isinstance(s, rdflib.URIRef)}
            remote_subjects_by_ns[ns_uri] = subjects
            remote_subjects.update(subjects)
        except Exception:
            fetch_failures.add(ns_uri)

    known_terms = local_subjects | remote_subjects

    # A term is undefined if it is used but:
    # - not in known_terms, AND
    # - its namespace is either local (we have the full graph) or was successfully fetched.
    # Terms from namespaces that failed to fetch are included as (fetch failure) violations.
    undefined_terms = []
    fetch_failure_terms = []
    for uri in sorted(used_terms):
        if uri in known_terms or _CONTAINER_MEMBERSHIP.fullmatch(uri):
            continue
        ns = get_namespace(uri)
        if not ns.startswith(('http://', 'https://')):
            continue
        if is_ignored(uri, ns):
            continue
        elif ns in local_namespaces:
            undefined_terms.append(uri)
        elif ns in fetch_failures:
            fetch_failure_terms.append(uri)
        else:
            undefined_terms.append(uri)

    all_violations = undefined_terms + [f"{uri} (fetch failure)" for uri in fetch_failure_terms]

    applied_subs_map = {ns: path for ns, path in applied_subs}
    metrics['fetchActivity'] = {
        'local': applied_subs_map,
        'fetched': {
            ns: len(remote_subjects_by_ns.get(ns, set()))
            for ns in remote_namespaces
            if ns not in fetch_failures and ns not in applied_subs_map
        },
        'failed': sorted(fetch_failures),
    }

    if not all_violations:
        decided(violations, check, "PASS - All used terms are defined locally or in their respective remote ontologies.")
        if verbose:
            note(violations, check, f"\nChecked {len(used_terms)} term(s) across {len(remote_namespaces)} remote namespace(s).")
    else:
        metrics[check] = len(all_violations)
        status += 1
        string = violation_formatting(all_violations)
        violations[check] = string
        violations[records_key(check)] = [dqv.Violation(uri) for uri in undefined_terms] + [
            dqv.Violation(uri, comment=f"namespace {get_namespace(uri)} could not be fetched")
            for uri in fetch_failure_terms
        ]
        decided(violations, check, f"VIOLATION - Found {metrics[check]} term(s) used but not defined locally or in their vocabulary (bundled, local or fetched):", AS_LIST)
    if remote_namespaces:
        applied_subs_map = {ns: path for ns, path in applied_subs}
        note(violations, check, f"\n> **Remote namespace activity** — {len(remote_namespaces)} checked:")
        for ns in sorted(remote_namespaces):
            if ns in applied_subs_map:
                note(violations, check, f">   - {chr(9989)} `{ns}` — {_describe_local(applied_subs_map[ns])}")
            elif ns in fetch_failures:
                note(violations, check, f">   - {chr(10060)} `{ns}` — fetch failed")
            else:
                count = len(remote_subjects_by_ns.get(ns, set()))
                note(violations, check, f">   - {chr(9989)} `{ns}` — fetched ({count} subject(s))")

    if not local_namespaces:
        note(violations, check, "\nWARNING - No owl:Ontology declared; local namespace is unknown. Local dangling references may not be detected.")

    return metrics, violations, status


# Reference/documentation properties whose objects are links to documents, not term uses:
# the undefined-terms check neither reports nor fetches them. `prefix:*` matches a whole
# namespace. Overridden by `undefined-terms: skip-object-of:` in the lint config.
DEFAULT_SKIP_OBJECT_OF = [
    'rdfs:seeAlso',
    'rdfs:isDefinedBy',
    'dcterms:license',
    'dcterms:source',
    'dcterms:references',
    'dcterms:relation',
    'dcterms:conformsTo',
    'owl:versionIRI',
    'foaf:homepage',
    'foaf:page',
    'vs:*',
    'schema:url',
    'http://schema.org/url',
]
