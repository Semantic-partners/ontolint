"""
Whether each class, property, NodeShape and PropertyShape carries a label and a
description — eight checks of one shape, differing only in what they look at.
"""
try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv
    from scripts.model import (AS_LIST, decided, EMPTY_POPULATION, not_assessed,
                               records_key, tabulate, violation_formatting)
    from scripts.queries import exec_sparql
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    from model import (AS_LIST, decided, EMPTY_POPULATION, not_assessed, records_key,
                       tabulate, violation_formatting)
    from queries import exec_sparql


def check_class_missing_label(in_metrics, graph, check, status, verbose, exclude_types=None):
    """
    QA test counting classes without a label.
    
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
    results = exec_sparql(graph, 'class_missing_label', exclude_types)
    metrics[check] = 0 # 'missingClassLabel'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        decided(violations, check, "PASS - All classes have a label annotation.")
        if verbose:
            tabulate(violations, check, ("Class", "Label"),
                     [(row.c, row.label) for row in exec_sparql(graph, 'class_labels')],
                     verbose_only=True)
    elif int(in_metrics['classCount']) == 0:
        decided(violations, check, "WARNING - No classes defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)
    
    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} classes missing a label annotation:", AS_LIST)
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[records_key(check)] = [dqv.Violation(row.c) for row in results]
        violations[check] = string
    
    return metrics, violations, status


def check_property_missing_label(in_metrics, graph, check, status, verbose):
    """
    QA test counting properties without a label.
    
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
    results = exec_sparql(graph, 'property_missing_label')
    metrics[check] = 0 # 'missingPropertyLabel'
    violations[check] = ""

    if not results and int(in_metrics['propertyCount']) > 0:
        decided(violations, check, "PASS - All properties have a label annotation.")
        if verbose:
            tabulate(violations, check, ("Property", "Label"),
                     [(row.property, row.label) for row in exec_sparql(graph, 'property_labels')],
                     verbose_only=True)
    elif int(in_metrics['propertyCount']) == 0:
        decided(violations, check, "WARNING - No properties defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)
    
    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} properties missing a label annotation.", AS_LIST)
        status += 1
        string = violation_formatting([row.property for row in results])
        violations[records_key(check)] = [dqv.Violation(row.property) for row in results]
        violations[check] = string
    
    return metrics, violations, status


def check_node_shape_missing_label(in_metrics, graph, check, status, verbose):
    """
    QA test counting node shapes without a label.
    
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
    results = exec_sparql(graph, 'node_shape_missing_label')
    metrics[check] = 0 # 'missingNSLabel'
    violations[check] = ""

    if not results and int(in_metrics['nodeShapes']) > 0:
        decided(violations, check, "PASS - All NodeShape have a label annotation.")
        if verbose:
            tabulate(violations, check, ("NodeShape", "Label"),
                     [(row.ns, row.label) for row in exec_sparql(graph, 'node_shape_labels')],
                     verbose_only=True)
    elif int(in_metrics['nodeShapes']) == 0:
        decided(violations, check, "WARNING - No NodeShape defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)
    
    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} NodeShape missing a label annotation.", AS_LIST)
        status += 1
        string = violation_formatting([row.ns for row in results])
        violations[records_key(check)] = [dqv.Violation(row.ns) for row in results]
        violations[check] = string
    
    return metrics, violations, status


def check_property_shape_missing_label(in_metrics, graph, check, status, verbose):
    """
    QA test counting property shapes without a label.
    
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
    results = exec_sparql(graph, 'property_shape_missing_label')
    metrics[check] = 0 # 'missingPSLabel'
    violations[check] = ""

    if not results and int(in_metrics['propertyShapes']) > 0:
        decided(violations, check, "PASS - All PropertyShape have a label annotation.")
        if verbose:
            tabulate(violations, check, ("PropertyShape", "Label"),
                     [(row.ps, row.label) for row in exec_sparql(graph, 'property_shape_labels')],
                     verbose_only=True)
    elif int(in_metrics['propertyShapes']) == 0:
        decided(violations, check, "WARNING - No PropertyShapes defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)
              
    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} PropertyShape missing a label annotation.", AS_LIST)
        status += 1
        string = violation_formatting([row.ps for row in results])
        violations[records_key(check)] = [dqv.Violation(row.ps) for row in results]
        violations[check] = string
    
    return metrics, violations, status


def check_class_missing_comment(in_metrics, graph, check, status, verbose, exclude_types=None):
    """
    QA test counting classes without description.
    
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
    results = exec_sparql(graph, 'class_missing_comment', exclude_types)
    metrics[check] = 0 # 'missingClassDescription'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        decided(violations, check, "PASS - All classes have a description annotation.")
        if verbose:
            tabulate(violations, check, ("Class", "Description"),
                     [(row.c, row.comment) for row in exec_sparql(graph, 'class_comments')],
                     verbose_only=True)
    elif int(in_metrics['classCount']) == 0:
        decided(violations, check, "WARNING - No classes defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)
    
    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} classes missing a description annotation:", AS_LIST)
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[records_key(check)] = [dqv.Violation(row.c) for row in results]
        violations[check] = string
    
    return metrics, violations, status


def check_property_missing_comment(in_metrics, graph, check, status, verbose):
    """
    QA test counting properties without description.
    
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
    results = exec_sparql(graph, 'property_missing_comment')
    metrics[check] = 0 # 'missingPropertyDescription'
    violations[check] = ""

    if not results and int(in_metrics['propertyCount']) > 0:
        decided(violations, check, "PASS - All properties have a description annotation.")
        if verbose:
            tabulate(violations, check, ("Property", "Description"),
                     [(row.property, row.comment) for row in exec_sparql(graph, 'property_comments')],
                     verbose_only=True)
    elif int(in_metrics['propertyCount']) == 0:
        decided(violations, check, "WARNING - No properties defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)
    
    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} properties missing a description annotation.", AS_LIST)
        status += 1
        string = violation_formatting([row.property for row in results])
        violations[records_key(check)] = [dqv.Violation(row.property) for row in results]
        violations[check] = string
    
    return metrics, violations, status


def check_node_shape_missing_comment(in_metrics, graph, check, status, verbose):
    """
    QA test counting node shapes without description.
    
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
    results = exec_sparql(graph, 'node_shape_missing_comment')
    metrics[check] = 0 # 'missingNSDescription'
    violations[check] = ""

    if not results and int(in_metrics['nodeShapes']) > 0:
        decided(violations, check, "PASS - All NodeShape have a description annotation.")
        if verbose:
            tabulate(violations, check, ("NodeShape", "Description"),
                     [(row.ns, row.comment) for row in exec_sparql(graph, 'node_shape_comments')],
                     verbose_only=True)
    elif int(in_metrics['nodeShapes']) == 0:
        decided(violations, check, "WARNING - No NodeShape defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)
    
    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} NodeShape missing a description annotation:", AS_LIST)
        status += 1
        string = violation_formatting([row.ns for row in results])
        violations[records_key(check)] = [dqv.Violation(row.ns) for row in results]
        violations[check] = string
    
    return metrics, violations, status


def check_property_shape_missing_comment(in_metrics, graph, check, status, verbose):
    """
    QA test counting property shapes without description.
    
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
    results = exec_sparql(graph, 'property_shape_missing_comment')
    metrics[check] = 0 # 'missingPSDescription'
    violations[check] = ""

    if not results and int(in_metrics['propertyShapes']) > 0:
        decided(violations, check, "PASS - All PropertyShape have a description annotation.")
        if verbose:
            tabulate(violations, check, ("PropertyShape", "Description"),
                     [(row.ps, row.comment) for row in exec_sparql(graph, 'property_shape_comments')],
                     verbose_only=True)
    
    elif int(in_metrics['propertyShapes']) == 0:
        decided(violations, check, "WARNING - No PropertyShapes defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)
    
    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} PropertyShape missing a description annotation:", AS_LIST)
        status += 1
        string = violation_formatting([row.ps for row in results])
        violations[records_key(check)] = [dqv.Violation(row.ps) for row in results]
        violations[check] = string
    
    return metrics, violations, status
