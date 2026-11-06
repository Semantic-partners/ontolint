"""
The ontology's own declaration: that there is one, only one per file, that it is
described, and that what it imports can be resolved.
"""
import rdflib

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv
    from scripts.model import (AS_LIST, decided, INFERRED_CONTEXT, not_assessed, note,
                               records_key, source_iris, SOURCES_NOT_RECORDED, tabulate,
                               violation_formatting)
    from scripts.queries import exec_sparql
    from scripts.resolution import _describe_local, _parse_local
    from scripts.terms import iri_key, ontology_iris
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    from model import (AS_LIST, decided, INFERRED_CONTEXT, not_assessed, note, records_key,
                       source_iris, SOURCES_NOT_RECORDED, tabulate, violation_formatting)
    from queries import exec_sparql
    from resolution import _describe_local, _parse_local
    from terms import iri_key, ontology_iris


def ontologies_by_source(graph, in_metrics):
    """
    {source IRI: [owl:Ontology IRI, ...]} for each input the graph was built from, or
    None when the graph does not record which source a triple came from.

    The CLI loads into a Dataset with one named graph per file, so a source is a context.
    A plain Graph has no contexts: it answers for one source when that is all it was built
    from, and for nothing when several files were merged into it, since the merge is what
    destroys the record.
    """
    if isinstance(graph, rdflib.Dataset):
        declared = {}
        for context in graph.graphs():
            source = str(context.identifier)
            if source == str(INFERRED_CONTEXT) or source.startswith('urn:x-rdflib:default'):
                continue
            declared[source] = ontology_iris(context)
        return declared
    if len(in_metrics.get('filesProcessed') or []) > 1:
        return None
    names = source_iris(in_metrics)
    return {names[0] if names else '': ontology_iris(graph)}


def check_owl_declaration(in_metrics, graph, check, status, verbose):
    """
    QA test verifying that the ontology has a namespace declared as `owl:Ontology` and also contain a description.
    
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
    num_files = max(len(in_metrics['filesProcessed']), 1)
    metrics['ontologyURI'] = [ ]
    results = exec_sparql(graph, 'owl_declaration')

    declared = ontologies_by_source(graph, in_metrics)
    if declared is None:
        metrics[check] = max(num_files - len(results), 0)
    else:
        metrics[check] = sum(1 for iris in declared.values() if not iris)

    if not results:
        status += 1
    else:
        for row in results:
            metrics['ontologyURI'].append(row.ont)
    
    # Record the violation elements.
    num_uri = len(metrics['ontologyURI'])
    # A verbose run lists the ontologies it found, so the verdict introduces them rather
    # than ending. It used to be rewritten after the fact, by trimming the full stop off a
    # sentence already in the log — which only a check that writes its own report can do.
    lists_ontologies = verbose and metrics[check] <= 0
    end = ":" if lists_ontologies else "."
    if metrics[check] == num_files:
        decided(violations, check, "VIOLATION - No `owl:Ontology` declaration found.")
        violations[check] = "**All** processed files missing ontology declaration."
        violations[records_key(check)] = [
            dqv.Violation(iri, comment="no owl:Ontology declaration")
            for iri in source_iris(in_metrics)
        ] or [dqv.Violation(comment="no owl:Ontology declaration")]
    
    elif metrics[check] > 0 and metrics[check] < num_files:
        found = "1 ontology" if metrics[check] == 1 else f"{metrics[check]} ontologies"
        decided(violations, check, f"VIOLATION - {found} without `owl:Ontology` declaration.")
        violations[check] = "**Some** processed files missing ontology declaration.<br> Check files individually."
        violations[records_key(check)] = [dqv.Violation(comment=f"{metrics[check]} processed file(s) have no owl:Ontology declaration; check files individually")]
    
    else:
        found = "1 ontology" if num_uri == 1 else f"{num_uri} ontologies"
        decided(violations, check, f"PASS - Found {found} with `owl:Ontology` declaration{end}")
        violations[check] = ""
    
    if lists_ontologies:
        for iri in metrics['ontologyURI']:
            note(violations, check, f" - {iri}")

    # What was found is worth naming when something is missing, to say where to look.
    if metrics[check] > 0:
        note(violations, check, "Check the input files individually to find out which one violates this check.")
        if num_uri > 0:
            note(violations, check, "WARNING - The following ontology URIs were found:")
        for iri in metrics['ontologyURI']:
            note(violations, check, f" - {iri}")
    
    return metrics, violations, status


def check_one_ontology_per_file(in_metrics, graph, check, status, verbose):
    """
    QA test verifying that no single input declares more than one `owl:Ontology`.

    Ontolint's rule is one file, one ontology. `check_owl_declaration` covers "no less";
    this covers "no more". It is judged per source rather than over the merged graph,
    where several declarations are normal and correct — one per file.

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
    declared = ontologies_by_source(graph, in_metrics)
    offenders = {} if declared is None else {
        source: iris for source, iris in sorted(declared.items()) if len(iris) > 1}
    metrics[check] = len(offenders) # 'multipleOntologies'
    violations[check] = ""

    if declared is None:
        decided(violations, check, "WARNING - Several files merged into one graph with no record of their sources, invalid metric.")
        not_assessed(violations, check, SOURCES_NOT_RECORDED)
    elif not offenders:
        decided(violations, check, "PASS - No violations found.")
    else:
        decided(violations, check, f"VIOLATION - Found {metrics[check]} file(s) declaring more than one `owl:Ontology`:", AS_LIST)
        status += 1
        violations[check] = violation_formatting(
            [f"{source} declares {len(iris)}: {', '.join(iris)}" for source, iris in offenders.items()])
        violations[records_key(check)] = [
            dqv.Violation(rdflib.URIRef(source),
                          comment=f"declares {len(iris)} ontologies; one file, one ontology",
                          related=[rdflib.URIRef(iri) for iri in iris])
            for source, iris in offenders.items()
        ]

    return metrics, violations, status


def check_owl_description(in_metrics, graph, check, status, verbose):
    """
    QA test verifying that the ontology has a description, if `owl:Ontology` was also declared.
    
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
    num_files = max(len(in_metrics['filesProcessed']), 1)

    if in_metrics['ontologyNotDeclared'] == num_files:
        decided(violations, check, "WARNING - No ontology declared, invalid metric.")
        not_assessed(violations, check, 'ontologyNotDeclared')
        metrics[check] = 1 # 'ontologyDescription': no
        violations[check] = "No ontology declared"
        violations[records_key(check)] = [dqv.Violation(comment="no ontology declared")]
    else:
        results = exec_sparql(graph, 'owl_no_description')
        if not results:
            decided(violations, check, "PASS - All declared ontologies have a description.")
            metrics[check] = 0 # yes
            violations[check] = ""
            if verbose:
                log_results = exec_sparql(graph, 'owl_description')
                note(violations, check, "\n**Ontology + Description:**")
                for row in log_results:
                    note(violations, check, f" - {row.ont}\n   *{row.comment}*")
                
        else:
            metrics[check] = len(results) #  violations
            status += 1
            string = violation_formatting([row.ont for row in results])
            violations[records_key(check)] = [dqv.Violation(row.ont) for row in results]
            violations[check] = string
            decided(violations, check, f"VIOLATION - Found {metrics[check]} ontologies without description:", AS_LIST)
    
    return metrics, violations, status


def check_owl_imports(in_metrics, graph, check, status, verbose, ignore_imports=None, local_imports=None):
    """
    QA test verifying that all owl:imports URLs resolve and contain triples.

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
    results = exec_sparql(graph, 'owl_imports')
    metrics[check] = 0  # 'unresolvedImports'
    violations[check] = ""

    ignored = {iri_key(i) for i in (ignore_imports or [])}
    local_map = {iri_key(k): v for k, v in (local_imports or {}).items()}
    import_urls = [
        (str(row.ontology), str(row.imp))
        for row in results
        if iri_key(row.imp) not in ignored
    ]
    import_urls.sort()

    if not import_urls:
        if ignored:
            decided(violations, check, "WARNING - All owl:imports URLs are ignored by configuration.")
        else:
            decided(violations, check, "WARNING - No owl:imports statements found.")
        return metrics, violations, status

    failed_imports = []
    failed_pairs = []   # (importing ontology, url), one per failed owl:imports statement
    resolved = {}       # url -> bool, so a URL imported by several ontologies is fetched once
    for ontology, import_url in import_urls:
        if import_url not in resolved:
            try:
                local = local_map.get(iri_key(import_url))
                tmp = _parse_local(local) if local else rdflib.Graph().parse(import_url)
                resolved[import_url] = len(tmp) > 0
            except Exception:
                resolved[import_url] = False
        if not resolved[import_url]:
            failed_imports.append(import_url)
            failed_pairs.append((ontology, import_url))

    local_subs = sorted({(url, local_map[iri_key(url)]) for _, url in import_urls if iri_key(url) in local_map})
    if local_subs:
        note(violations, check, f"> NOTE - {len(local_subs)} import(s) resolved from local file(s):")
        for url, path in local_subs:
            note(violations, check, f">   `{url}` → {_describe_local(path)}")

    if not failed_imports:
        decided(violations, check, f"PASS - All {len(import_urls)} import(s) resolved and contain triples.")
    else:
        metrics[check] = len(failed_imports)
        status += 1
        string = violation_formatting(failed_imports)
        violations[check] = string
        violations[records_key(check)] = [
            dqv.Violation(url, comment="import could not be resolved or is empty", related=[ontology])
            for ontology, url in failed_pairs
        ]
        decided(violations, check, f"VIOLATION - Found {metrics[check]} unresolvable or empty import(s):", AS_LIST)

    def _check(failed):
        if failed in failed_imports:
            return chr(10060) # X
        else:
            return chr(9989)  # V

    if verbose:
        tabulate(violations, check, ("Ontology", "Import URL", "Resolves?"),
                 [(ontology, url, _check(url)) for ontology, url in import_urls],
                 verbose_only=True)

    return metrics, violations, status
