"""
Things that should be told apart and cannot be: classes, properties and shapes
sharing a label, and one IRI declared as two different kinds of thing.
"""
import rdflib

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv
    from scripts.model import (concat_members, decided, EMPTY_POPULATION, not_assessed,
                               records_key, tabulate, violation_formatting)
    from scripts.queries import exec_sparql
    from scripts.terms import _term_from_string
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    from model import (concat_members, decided, EMPTY_POPULATION, not_assessed, records_key,
                       tabulate, violation_formatting)
    from queries import exec_sparql
    from terms import _term_from_string


def check_class_same_label(in_metrics, graph, check, status, verbose, exclude_types=None):
    """
    QA test counting classes sharing the same label.
    
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
    results = exec_sparql(graph, 'class_same_label', exclude_types)
    metrics[check] = 0 # 'nonUniqueClassLabels'
    violations[check] = ""
    
    if not results and int(in_metrics['classCount']) > 0:
        decided(violations, check, "PASS - No classes share the same label.")

    elif int(in_metrics['classCount']) == 0:
        decided(violations, check, "WARNING - No classes defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} labels shared by multiple classes.")
        status += 1
        string = ""
        records = []
        rows = []
        for row in results:
            members = concat_members(row.classes)
            rows.append((row.label, row.labelProperty, members))
            string += f"\"{row.label}, {row.labelProperty}\": {members};<br> "
            records.extend(_same_label_records(row.label, row.labelProperty, row.classes))
        tabulate(violations, check, ('Label', 'Label Property', 'Classes'), rows)
        string = string.removesuffix(";<br> ")
        violations[check] = string
        violations[records_key(check)] = records
    
    return metrics, violations, status


def check_property_same_label(in_metrics, graph, check, status, verbose):
    """
    QA test counting properties sharing the same label.
    
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
    results = exec_sparql(graph, 'property_same_label')
    metrics[check] = 0 # 'nonUniquePropertyLabels'
    violations[check] = ""

    if not results and int(in_metrics['propertyCount']) > 0:
        decided(violations, check, "PASS - No property share the same label.")

    elif int(in_metrics['propertyCount']) == 0:
        decided(violations, check, "WARNING - No properties defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} labels shared by multiple properties.")
        status += 1
        string = ""
        records = []
        rows = []
        for row in results:
            members = concat_members(row.properties)
            rows.append((row.label, row.labelProperty, members))
            string += f"\"{row.label}, {row.labelProperty}\": {members};<br> "
            records.extend(_same_label_records(row.label, row.labelProperty, row.properties))
        tabulate(violations, check, ('Label', 'Label Property', 'Properties'), rows)
        string = string.removesuffix(";<br> ")
        violations[check] = string
        violations[records_key(check)] = records
    
    return metrics, violations, status


def check_node_shape_same_label(in_metrics, graph, check, status, verbose):
    """
    QA test counting node shapes sharing the same label.
    
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
    results = exec_sparql(graph, 'node_shape_same_label')
    metrics[check] = 0 # 'nonUniqueNSLabels'
    violations[check] = ""

    if not results and int(in_metrics['nodeShapes']) > 0:
        decided(violations, check, "PASS - No NodeShape share the same label.")

    elif int(in_metrics['nodeShapes']) == 0:
        decided(violations, check, "WARNING - No NodeShape defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} labels shared by multiple NodeShapes.")
        status += 1
        string = ""
        records = []
        rows = []
        for row in results:
            members = concat_members(row.nsList)
            rows.append((row.label, row.labelProperty, members))
            string += f"\"{row.label}, {row.labelProperty}\": {members};<br> "
            records.extend(_same_label_records(row.label, row.labelProperty, row.nsList))
        tabulate(violations, check, ('Label', 'Label Property', 'NodeShapes'), rows)
        string = string.removesuffix(";<br> ")
        violations[check] = string
        violations[records_key(check)] = records
    
    return metrics, violations, status


def check_property_shape_same_label(in_metrics, graph, check, status, verbose):
    """
    QA test counting property shapes sharing the same label.
    
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
    results = exec_sparql(graph, 'property_shape_same_label')
    metrics[check] = 0 # 'nonUniquePSLabels'
    violations[check] = ""

    if not results and int(in_metrics['propertyShapes']) > 0:
       decided(violations, check, "PASS - No PropertyShape share the same label.")

    elif int(in_metrics['propertyShapes']) == 0:
        decided(violations, check, "WARNING - No PropertyShapes defined, invalid metric.")
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} labels shared by multiple PropertyShapes.")
        status += 1
        string = ""
        records = []
        rows = []
        for row in results:
            members = concat_members(row.psList)
            rows.append((row.label, row.labelProperty, members))
            string += f"\"{row.label}, {row.labelProperty}\": {members};<br> "
            records.extend(_same_label_records(row.label, row.labelProperty, row.psList))
        tabulate(violations, check, ('Label', 'Label Property', 'PropertyShapes'), rows)
        string = string.removesuffix(";<br> ")
        violations[check] = string
        violations[records_key(check)] = records
    
    return metrics, violations, status


def _same_label_records(label, label_property, members):
    """One dqv.Violation per member of a same-label group, each related to the other members."""
    # GROUP_CONCAT flattens members to strings; blank nodes come back as their bare id.
    # GROUP_CONCAT has no defined order, so sort for reproducible records and hashes.
    iris = sorted((_term_from_string(m.strip()) for m in str(members).split(", ") if m.strip()),
                  key=lambda t: (isinstance(t, rdflib.BNode), str(t)))
    property_name = str(label_property) if label_property is not None else "an annotation property"
    records = []
    for iri in iris:
        others = [o for o in iris if o != iri]
        # Blank-node ids are arbitrary per parse, so name them generically; the skolem IRI
        # is given by olq:relatedResource.
        names = ["a blank node" if isinstance(o, rdflib.BNode) else str(o) for o in others]
        comment = f"shares label '{label}' with predicate {property_name} and " + ", ".join(names)
        records.append(dqv.Violation(iri, comment=comment, related=others, value=label))
    return records


def check_unique_identifiers(in_metrics, graph, check, status, verbose):
    """
    QA test checking for the same resource being declared as semantically inconsistent elements,
    e.g. owl:Class or rdfs:Class and owl:ObjectProperty, rdf:Property owl:DatatypeProperty  owl:AnnotationProperty.
    
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
    results = exec_sparql(graph, 'unique_identifiers')
    metrics[check] = 0 # 'nonUniqueIdentifiers'
    violations[check] = ""

    if not results:
        decided(violations, check, "PASS - No violations found.")
        
    elif results:
        metrics[check] = len(results)
        decided(violations, check, f"VIOLATION - Found {metrics[check]} elements with non-unique identifiers.")
        status += 1
        iri = []
        records = []
        rows = []
        for row in results:
            declared = concat_members(row.declaredAs)
            rows.append((row.iri, declared))
            iri.append(row.iri)
            records.append(dqv.Violation(row.iri, comment=f"declared as {declared}"))
        tabulate(violations, check, ("URI", "Declared as"), rows)

        violations[check] = violation_formatting(iri)
        violations[records_key(check)] = records
    
    return metrics, violations, status
