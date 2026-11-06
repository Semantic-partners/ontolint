"""
How the classes and properties connect: isolated classes, properties without a
domain or range, and subclass cycles.
"""
try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv
    from scripts.model import (AS_LIST, decided, EMPTY_POPULATION, not_assessed, note,
                               records_key, tabulate, violation_formatting)
    from scripts.queries import exec_sparql
    from scripts.terms import term_text
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    from model import (AS_LIST, decided, EMPTY_POPULATION, not_assessed, note, records_key,
                       tabulate, violation_formatting)
    from queries import exec_sparql
    from terms import term_text


def check_isolated_classes(in_metrics, graph, check, status, verbose, exclude_types=None):
    """
    QA test counting classes declared but never used in any other triple connecting them to the rest of the ontology.
    
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
    results = exec_sparql(graph, 'isolated_classes', exclude_types)
    metrics[check] = 0 # 'isolatedClasses'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        decided(violations, check, "PASS - All classes are connected to another class through a subclass or property relation.")
    elif int(in_metrics['classCount']) == 0:
        decided(violations, check, "WARNING - No classes defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} isolated classes:", AS_LIST)
        status += 1
        violations[records_key(check)] = [dqv.Violation(row.c) for row in results]
        violations[check] = violation_formatting([row.c for row in results])
    
    return metrics, violations, status


def _domain_range_rows(graph):
    """
    Every property the domain/range query returns, and which declaration each one lacks.

    One query, read three ways: the rows as they are reported, the properties without a
    domain, and those without a range. Both checks need it, and it is cheap enough to run
    per check — which is what lets them be two functions rather than one that remembers
    whether it has already run.
    """
    rows, without_domain, without_range = [], [], []
    for row in exec_sparql(graph, 'missing_dr_property'):
        domain = term_text(row.domain) if row.domain else 'None'
        range_ = term_text(row.range) if row.range else 'None'
        if not row.domain:
            without_domain.append(row.property)
        if not row.range:
            without_range.append(row.property)
        rows.append((row.property, domain, range_))
    return rows, sorted(set(without_domain)), sorted(set(without_range))


def _missing_declaration(in_metrics, violations, check, status, missing, word):
    """The verdict of one of the two checks: the properties lacking that declaration."""
    if int(in_metrics['propertyCount']) == 0:
        violations[check] = ""
        decided(violations, check, "WARNING - No properties defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)
    elif missing:
        status += 1
        violations[records_key(check)] = [dqv.Violation(p) for p in missing]
        violations[check] = violation_formatting(missing)
        decided(violations, check,
                f"VIOLATION - Found {len(missing)} properties without `rdfs:{word}` declaration:", AS_LIST)
    else:
        violations[check] = ""
        decided(violations, check, f"PASS - All properties have {word} defined.")
    return status


def check_property_missing_domain(in_metrics, graph, check, status, verbose):
    """
    QA test counting properties without an rdfs:domain declaration.

    It carries the preamble both checks share — how many properties lack either
    declaration, and, on a verbose run, the domain and range of every property — because
    that is where the report has always shown it.

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
    rows, without_domain, _ = _domain_range_rows(graph)
    properties = int(in_metrics['propertyCount'])
    metrics['missingDomainRange'] = len(rows)

    if not rows and properties > 0:
        note(violations, check, "INFO - All properties have domain and range defined.")
        if verbose:
            note(violations, check, "")
    elif rows:
        note(violations, check,
             f"WARNING - Found {len(rows)} properties without `rdfs:domain` or `rdfs:range` declaration:\n")
        if not verbose:
            tabulate(violations, check, ("Property", "Domain", "Range"), rows)
            note(violations, check, "")

    # A verbose run shows every property's domain and range, not only the incomplete ones.
    if verbose and properties > 0:
        tabulate(violations, check, ("Property", "Domain", "Range"),
                 [(term_text(row.property),
                   term_text(row.domain) if row.domain else 'None',
                   term_text(row.range) if row.range else 'None')
                  for row in exec_sparql(graph, 'dr_property')], verbose_only=True)
        note(violations, check, "")

    metrics[check] = len(without_domain)
    status = _missing_declaration(in_metrics, violations, check, status, without_domain, 'domain')
    return metrics, violations, status


def check_property_missing_range(in_metrics, graph, check, status, verbose):
    """
    QA test counting properties without an rdfs:range declaration.

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
    _, _, without_range = _domain_range_rows(graph)
    metrics[check] = len(without_range)
    status = _missing_declaration(in_metrics, violations, check, status, without_range, 'range')
    return metrics, violations, status


def check_subclass_cycles(in_metrics, graph, check, status, verbose):
    """
    QA test counting classes involved in subclass cycles.
    
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
    results = exec_sparql(graph, 'subclass_cycles')
    metrics[check] = 0 # 'subclassCycles'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        decided(violations, check, "PASS - No violations found.")

    elif int(in_metrics['classCount']) == 0:
        decided(violations, check, "WARNING - No classes defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} classes involved in subclass cycles:", AS_LIST)
        status += 1
        violations[records_key(check)] = [dqv.Violation(row.c) for row in results]
        violations[check] = violation_formatting([row.c for row in results])
    
    return metrics, violations, status
