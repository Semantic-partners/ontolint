#!/usr/bin/env python3
# Ontology Quality Assessment Script
# SEMANTIC PARTNERS LTD, 2026
# Authors: Simon Shapiro, Otello M Roscioni, John Placek.

"""
A script to perform basic QA on a set of ontologies.
It loads RDF files, applies simple RDFS subclass inference, and runs SPARQL queries to
check for common ontology quality issues.
It reports any violations found in the ontology data.
"""
import rdflib
import argparse
from urllib.parse import urlparse
import sys
import os
import json
from datetime import datetime
from dataclasses import dataclass, field
import yaml

# Create a dictionary with SPARQL queries, from files.
sparql_dir = os.getenv('QA_SPARQL_DIR', os.path.dirname(os.path.realpath(sys.argv[0])) + '/../sparql') # Use ENV variable or default value.

# check that the directory exists
if not os.path.isdir(sparql_dir):
    sys.stderr.write(f"SPARQL directory '{sparql_dir}' does not exist.\nSet the QA_SPARQL_DIR environment variable before executing ontology_qa.")
    sys.exit(1)

def load_sparql_queries(directory):
    """
    Create a dictionary of SPARQL queries, using file names as keys.
    """
    queries = {}
    for filename in os.listdir(directory):
        if filename.endswith('.sparql'):
            var_name = os.path.splitext(filename)[0]
            with open(os.path.join(directory, filename), 'r', encoding='utf-8') as f:
                queries[var_name] = f.read()
    return queries

sparql_queries = load_sparql_queries(sparql_dir)


@dataclass
class CheckResult:
    name: str
    passed: bool
    count: int
    elements: str


@dataclass
class QAResult:
    profiling: dict
    checks: list
    elements: dict = field(default_factory=dict)
    logs: list = field(default_factory=list)

    def get(self, name: str):
        return next((c for c in self.checks if c.name == name), None)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self):
        return [c for c in self.checks if not c.passed]

def exec_sparql(graph, key):
    """
    Execute a SPARQL query from the input RDFLib graph, retrieving it from a global dictionary.
    """
    sparql_query = sparql_queries[key]
    results = graph.query(sparql_query)
    return results

def get_namespace(uri):
    """Extract namespace from a URIRef."""
    if '#' in uri:
        return uri.rsplit('#', 1)[0] + '#'
    elif '/' in uri:
        return uri.rsplit('/', 1)[0] + '/'
    return uri  # fallback

def prefixes(g):
    # Create a dictionary for the declared prefixes
    declared_prefixes = {}
    for prefix, uri in g.namespace_manager.namespaces():
        uri_str = str(uri)
        declared_prefixes[uri_str] = prefix

    # Collect all namespaces actually used in the graph
    used_namespaces = set()
    for s, p, o in g:
        for term in [s, p, o]:
            if isinstance(term, rdflib.URIRef):
                ns = get_namespace(str(term))
                used_namespaces.add(ns)

    # Filter the declared prefixes into those that are actually used
    used_prefixes = {}
    for ns in used_namespaces:
        if ns in declared_prefixes:
            prefix = declared_prefixes[ns]
            if len(prefix) > 0: used_prefixes[ns] = prefix

    return used_prefixes

def normalise(count, total):
    count = float(count)
    total = float(total)
    if total > 0:
        out = count / total
    else:
        out = 0
    # Format the normalised value
    if count == total:
        out = 1
    elif out > 0:
        out = f"{out:.3f}"
    else:
        out = 0
    return out

def get_ontology_name(metrics):
    """Retrieve the ontology name from URI (if declared) or return a warning."""
    names = ""
    count = 0
    num_files = len(metrics['filesProcessed'])
    num_uri = len(metrics['ontologyURI'])
    if num_uri > num_files: num_files = num_uri
    for _ in range(num_files):
        if _ < num_uri and metrics['ontologyURI']:
            names += f"{metrics['ontologyURI'][_]},<br> "
        else:
            count += 1
    if count == 1 and num_uri == 0:
        # special case if one file without ontology declaration is found
        names = metrics['filesProcessed'][0].split('/')[-1]
    elif count >= 1:
        names += f"{count} URIs not found.,<br> "
    names = names.removesuffix(",<br> ")
    return names

def qa_terminate(file, log):
    """
    Print the results to a file name if specified, otherwise print to the STDOUT.

    Args:
        file (str): Name of the output file. If undefined, print to the STDOUT.
        log (str): Results of the Quality Assurance tests, formatted in markdown.
    """
    # Print output to file or STDOUT.
    if file:
         # Ensure directory exists
        os.makedirs(os.path.dirname(file) or '.', exist_ok=True)
        with open(file, "w", encoding="utf-8") as f:
            f.write(log)
    else:
        print(log)

def print_profiling_table(metrics):
    """
    Print a table with the profiling metrics of an RDF graph.

    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
    
    Returns:
        log (str): Pretty table with results.
    """

    name = get_ontology_name(metrics)
    log = "\n## Profiling Metrics\n"
    log += f"| Name | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape "
    log += f"| Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used | Ontologies Imported "
    log += f"| Hierarchy depth | Ave branching factor | Cardinality restrictions |\n"
    log += "|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|\n"
    log += f"| {name} | {metrics['triples']} | {metrics['classCount']} | {metrics['propertyCount']} | {metrics['nodeShapes']} | {metrics['propertyShapes']} "
    log += f"| {metrics['classesInNodeShapes']} | {metrics['propertiesInPropertyShapes']} | {metrics['deprecatedClasses']} | {metrics['deprecatedProperties']} "
    log += f"| {metrics['vocabulariesUsed']} | {metrics['imports']} | {metrics['HierarchyDepth']} | {normalise(metrics['aveBranchFactor'], 1)} | {metrics['CardinalityRestrictions']} |\n"
    return log

def print_qa_table(metrics, checks):
    """
    Print a table with the quality assurance metrics of an RDF graph.

    Args:
        metrics (dict): Number of violations for various ontology metrics.
        checks (dict): Number of violations for various ontology metrics.
    
    Returns:
        log (str): Pretty table with results.
    """
    name = get_ontology_name(metrics)
    log = "\n## Quality Assurance Metrics\n"
    log += f"| Name | Ontology not declared | Ontology without description | Class without label | Property without label | NodeShapes without label | PropertyShape without label "
    log += f"| Class without description | Property without description | NodeShapes without description | PropertyShape without description "
    log += f"| Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes "
    log += f"| Property without domain | Property without range "
    log += f"| Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |\n"
    log += "|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|\n"
    log += f"| {name} | {normalise_if_executed_len(metrics, checks, 'ontologyNotDeclared', 'filesProcessed')} "
    log += f"| {normalise_if_executed_len(metrics, checks, 'ontologyDescription', 'filesProcessed')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingClassLabel', 'classCount')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingPropertyLabel', 'propertyCount')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingNSLabel', 'nodeShapes')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingPSLabel', 'propertyShapes')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingClassDescription', 'classCount')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingPropertyDescription', 'propertyCount')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingNSDescription', 'nodeShapes')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingPSDescription', 'propertyShapes')} "
    log += f"| {normalise_if_executed(metrics, checks, 'nonUniqueClassLabels', 'classCount')} "
    log += f"| {normalise_if_executed(metrics, checks, 'nonUniquePropertyLabels', 'propertyCount')} "
    log += f"| {normalise_if_executed(metrics, checks, 'nonUniqueNSLabels', 'nodeShapes')} "
    log += f"| {normalise_if_executed(metrics, checks, 'nonUniquePSLabels', 'propertyShapes')} "
    log += f"| {normalise_if_executed(metrics, checks, 'isolatedClasses', 'classCount')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingDomain', 'propertyCount')} "
    log += f"| {normalise_if_executed(metrics, checks, 'missingRange', 'propertyCount')} "
    log += f"| {print_if_executed(metrics, checks, 'nonUniqueIdentifiers')} | {print_if_executed(metrics, checks, 'subclassCycles')} "
    log += f"| {print_if_executed(metrics, checks, 'untypedClasses')} | {print_if_executed(metrics, checks, 'untypedProperties')} "
    log += f"| {print_if_executed(metrics, checks, 'hijacking')} |\n"
    return log

def normalise_if_executed(metrics, checks, key, total):
    """
    Normalise the value of a QA metrics if the test has been executed.
    Otherwise, print a N/A value.
    """
    output = "N/A"
    if checks[key]:
        output = normalise(metrics[key], metrics[total])
    return output

def normalise_if_executed_len(metrics, checks, key, total):
    """
    Normalise the value of a QA metrics if the test has been executed.
    Otherwise, print a N/A value.
    Use the length of an array to normalise.
    """
    output = "N/A"
    if checks[key]:
        output = normalise(metrics[key], len(metrics[total]))
    return output

def print_if_executed(metrics, checks, key):
    """
    Print the value of a QA metrics if the test has been executed.
    Otherwise, print a N/A value.
    """
    output = "N/A"
    if checks[key]:
        output = metrics[key]
    return output

def write_ctrf_report(result: QAResult, file_path, filename):
    """
    Convert QA metrics to CTRF (Common Test Result Format) JSON.
    """
    passed = 0
    failed = 0
    test_cases = []

    for check in result.checks:
        test_case = {
            "name": check.name,
            "status": "passed" if check.passed else "failed"
        }
        if not check.passed:
            test_case["failure"] = {
                "violations": check.count,
                "elements": check.elements
            }
            failed += 1
        else:
            passed += 1
        test_cases.append(test_case)
    
    # Build CTRF report
    ctrf_report = {
        "results": {
            "tool": {
                "name": "Ontology QA",
                "version": "2025-11-17"
            },
            "summary": {
                "tests": len(test_cases),
                "passed": passed,
                "failed": failed
            },
            "tests": test_cases,
            "timestamp": datetime.now().isoformat()
        }
    }
    
    # Write to file
    os.makedirs(file_path, exist_ok=True)
    # Fallback CTRF filename
    if not filename:
        filename = f'ontology-qa-report-{os.getpid()}.json'
    output_file = os.path.join(file_path, filename)
    with open(output_file, 'w') as f:
        json.dump(ctrf_report, f, indent=2)
    
    log = f"\nCTRF report written to: {output_file}\n"
    return ctrf_report, log

def print_profiling_metrics(metrics, elements, verbose):
    log  = f"\n## Profiling Details\n\n"
    log += f"RDF/OWL classes: {metrics['classCount']}\n"
    log += f"RDF/OWL properties: {metrics['propertyCount']}\n"
    log += f"SHACL Node Shapes: {metrics['nodeShapes']}\n"
    log += f"SHACL Property Shapes: {metrics['propertyShapes']}\n"

    log += f"Local classes in Node Shapes: {metrics['classesInNodeShapes']}\n"
    if verbose and metrics['classesInNodeShapes'] > 0:
        log += "\n| NodeShape | Class count |\n|--|--|\n"
        for _ in range( len(elements['classesInNodeShapes']['ns']) ):
            log += f"| {elements['classesInNodeShapes']['ns'][_]} "
            log += f"| {elements['classesInNodeShapes']['classCount'][_]} |\n"
        log += "\n"

    log += f"Local properties in Property Shapes: {metrics['propertiesInPropertyShapes']}\n"
    if verbose and metrics['propertiesInPropertyShapes'] > 0:
        log += "\n| PropertyShape | Local Property |\n|--|--|\n"
        for _ in range( len(elements['propertiesInPropertyShapes']['ps']) ):
            log += f"| {elements['propertiesInPropertyShapes']['ps'][_]} "
            log += f"| {elements['propertiesInPropertyShapes']['propCount'][_]} |\n"
        log += "\n"
    
    log += f"Deprecated classes: {metrics['deprecatedClasses']}\n"
    if verbose and metrics['deprecatedClasses'] > 0:
        log += "List of deprecated classes:\n"
        for _ in range( len(elements['deprecatedClasses']) ):
            log += f" - {elements['deprecatedClasses'][_]}\n"
        log += "\n"
    
    log += f"Deprecated properties: {metrics['deprecatedProperties']}\n"
    if verbose and metrics['deprecatedProperties'] > 0:
        log += "List of deprecated properties:\n"
        for _ in range( len(elements['deprecatedProperties']) ):
            log += f" - {elements['deprecatedProperties'][_]}\n"
        log += "\n"

    log += f"External vocabularies declared: {metrics['vocabulariesUsed']}\n"
    if metrics['vocabulariesUsed'] > 0:
        log += "\n| Prefix | URI |\n|--|--|\n"
        for _ in range( len(elements['vocabulariesUsed']['prefix']) ):
            log += f"| {elements['vocabulariesUsed']['prefix'][_]} "
            log += f"| {elements['vocabulariesUsed']['uri'][_]} |\n"
        log += "\n"
    
    log += f"Ontologies imported: {metrics['imports']}\n"
    if metrics['imports'] > 0:
        for ont in elements['imports']:
            log += f"* Ontology \'{ont}\' imports:\n"
            for res in elements['imports'][ont]: log += f"  - {res}\n" 
        log += "\n"
    
    log += f"Hierarchy depth: {metrics['HierarchyDepth']}\n"
    log += f"Average branching factor: {normalise(metrics['aveBranchFactor'], 1)}\n"
    log += f"Number of cardinality restrictions: {metrics['CardinalityRestrictions']}\n"
    return log

def qa_check_results(description,qan):
    log = f"\nCheck {qan}: {description}.\n"
    qan += 1
    return qan, log

def sep():
    return "\n" + "-"*20 + "\n"

def profiling(graph):
    """
    Compute profiling information for an RDF graph.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        metrics (dict): Count of ontology metrics.
        elements (dict): Elements in ontology metrics.
    """
    metrics = {}
    elements = {}

    # Count classes, properties before inferencing.
    results = exec_sparql(graph, 'count_cp')
    (row,) = results
    metrics['classCount'] = row.classCount
    metrics['propertyCount'] = row.propertyCount

    # Count shapes.
    results = exec_sparql(graph, 'node_shape')
    if results:
        (row,) = results
        metrics['nodeShapes'] = row.shapeCount
    else:
        metrics['nodeShapes'] = 0
    results = exec_sparql(graph, 'property_shape')
    if results:
        (row,) = results
        metrics['propertyShapes'] = row.shapeCount
    else:
        metrics['propertyShapes'] = 0
    
    # Count classes in NodeShapes.
    results = exec_sparql(graph, 'classes_in_node_shape')
    total_classes_in_shapes = sum(int(row.classCount) for row in results)
    metrics['classesInNodeShapes'] = total_classes_in_shapes
    if total_classes_in_shapes > 0:
        elements['classesInNodeShapes'] = {
            'ns': [],
            'classCount': []
            }
        for row in results:
            elements['classesInNodeShapes']['ns'].append(row.ns)
            elements['classesInNodeShapes']['classCount'].append(row.classCount)

    # Count properties in PropertyShapes.
    results = exec_sparql(graph, 'property_in_property_shape')
    total_properties_in_shapes = len(results)
    metrics['propertiesInPropertyShapes'] = total_properties_in_shapes
    if total_properties_in_shapes > 0:
        elements['propertiesInPropertyShapes'] = {
            'ps': [],
            'propCount': []
            }
        for row in results:
            elements['propertiesInPropertyShapes']['ps'].append(row.ps)
            elements['propertiesInPropertyShapes']['propCount'].append(row.prop)

    # Number of Deprecated Classes and Properties
    results = exec_sparql(graph, 'deprecated_class')
    metrics['deprecatedClasses'] = len(results)
    if metrics['deprecatedClasses'] > 0:
        elements['deprecatedClasses'] = []
        for row in results:
            elements['deprecatedClasses'].append(row.c)
    
    results = exec_sparql(graph, 'deprecated_property')
    metrics['deprecatedProperties'] = len(results)
    if metrics['deprecatedProperties'] > 0:
        elements['deprecatedProperties'] = []
        for row in results:
            elements['deprecatedProperties'].append(row.p)

    # List all used prefixes
    active_prefixes = prefixes(graph)
    results = exec_sparql(graph, 'owl_declaration')
    if results:
        for row in results:
            # Remove ontology namespace from active_prefixes
            to_remove = []
            for ns, pfx in active_prefixes.items():
                if str(row.ont) == ns: to_remove.append(ns)
            for ns in to_remove:
                del active_prefixes[ns]
    metrics['vocabulariesUsed'] = len(active_prefixes)

    # These are not violations, but the dictionary is nevertheless used to store elements
    # matching the same key of the metrics dictionary.
    elements['vocabulariesUsed'] = {
        'prefix': [],
        'uri': []
        }
    # Build a (namespace, prefix) array and sort it by namespace
    items = [(ns, pfx) for ns, pfx in active_prefixes.items()]
    items.sort(key=lambda x: x[1])
    for ns, pfx in items:
        elements['vocabulariesUsed']['prefix'].append(pfx)
        elements['vocabulariesUsed']['uri'].append(ns)

    # List all imports
    results = exec_sparql(graph, 'ont_imports')
    metrics['imports'] = len(results)
    elements['imports'] = {}
    if metrics['imports'] > 0:
        old =  ""
        for row in results:
            if row.ont != old:
                elements['imports'][str(row.ont)] = []
                old = row.ont
            elements['imports'][str(row.ont)].append(str(row.res))
    
    # hierarchy depth
    results = exec_sparql(graph, 'hierarchy_depth')
    if len(results) > 1:
        (row,) = results 
        metrics['HierarchyDepth'] = row.maxDepth
    else:
        metrics['HierarchyDepth'] = 0

    # average branching factor
    results = exec_sparql(graph, 'average_branching_factor')
    (row,) = results
    metrics['aveBranchFactor'] = row.avgBranchingFactor

    # use of restrictions
    results = exec_sparql(graph, 'cardinality_restrictions')
    (row,) = results
    metrics['CardinalityRestrictions'] = row.counter

    return metrics, elements

def infer_subclass_relations(graph):
    """
    Construct sub-class relations recursively using the sub-class inference rule.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        graph (rdflib.Graph): The RDF graph, after inference applied.
        log (str): Result of inferencing.
    """
    
    log = f"\n## Simulate Inference\n\nInitial graph size: {len(graph)} triples.\nApplying Subclass inference rule iteratively...\n"
    while True:
        inferred_triples_result = exec_sparql(graph, 'subclass_inference_rule')
        if not inferred_triples_result:
            log += "No new subclass inferences to add. Inference complete.\n"
            break
        graph_size_before = len(graph)
        graph += inferred_triples_result
        graph_size_after = len(graph)
        if graph_size_after == graph_size_before:
            log += "No new subclass inferences in this pass. Inference complete.\n"
            break
        else:
            log += f"Added {graph_size_after - graph_size_before} new triples. Continuing inference...\n"
    log += f"Final graph size after inference: {len(graph)} triples.\n"
    return graph, log

def check_owl_declaration(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test verifying that the ontology has a namespace declared as `owl:Ontology` and also contain a description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    num_files = max(len(in_metrics['filesProcessed']), 1)
    metrics[check] = num_files # 'ontologyNotDeclared': Assume no ontology has been declared.
    metrics['ontologyURI'] = [ ]
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'owl_declaration')

    if not results:
        status += 1
    else:
        for row in results:
            metrics['ontologyURI'].append(row.ont)
            metrics[check] -= 1
    
    # Record the violation elements.
    num_uri = len(metrics['ontologyURI'])
    if metrics[check] == num_files:
        log += "VIOLATION - No `owl:Ontology` declaration found.\n"
        violations[check] = "**All** processed files missing ontology declaration."
    
    elif metrics[check] > 0 and metrics[check] < num_files:
        if metrics[check] == 1:
            log += f"VIOLATION - 1 ontology without `owl:Ontology` declaration.\n"
        else:
            log += f"VIOLATION - {metrics[check]} ontologies without `owl:Ontology` declaration.\n"
        violations[check] = "**Some** processed files missing ontology declaration.<br> Check files individually."
    
    else:
        if num_uri == 1:
            log += f"PASS - Found 1 ontology with `owl:Ontology` declaration.\n"
        else:
            log += f"PASS - Found {num_uri} ontologies with `owl:Ontology` declaration.\n"
        
        violations[check] = ""
    
    # Print additional information.
    if verbose and metrics[check] <= 0:
        log = log.removesuffix(".\n")
        log += ":\n"
        for _ in range(num_uri):
            log += f" - {metrics['ontologyURI'][_]}\n"

    # Print more information if violations are found.
    if metrics[check] > 0:
        log += "Check the input files individually to find out which one violates this check.\n"
        if num_uri > 0: log += "WARNING - The following ontology URIs were found:\n"
        for _ in range(num_uri):
            log += f" - {metrics['ontologyURI'][_]}\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_owl_description(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test verifying that the ontology has a description, if `owl:Ontology` was also declared.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    num_files = max(len(in_metrics['filesProcessed']), 1)
    c, log = qa_check_results(name, c)

    if in_metrics['ontologyNotDeclared'] == num_files:
        log += f"\nSkipping check {c}: Ontology description (no ontology declared).\n"
        c += 1
        metrics[check] = 1 # 'ontologyDescription': no
        violations[check] = "No ontology declared"
    else:
        results = exec_sparql(graph, 'no_ont_description')
        if not results:
            log += "PASS - All declared ontologies have a description.\n"
            metrics[check] = 0 # yes
            violations[check] = ""
            if verbose:
                log_results = exec_sparql(graph, 'ont_description')
                log += "\n**Ontology + Description:**\n"
                for row in log_results:
                    log += f" - {row.ont}\n   *{row.d}*\n"
                
        else:
            owd = len(results)
            metrics[check] = len(results) #  violations
            status += 1
            string = violation_formatting([row.ont for row in results])
            violations[check] = string
            log += f"VIOLATION - Found {metrics[check]} ontologies without description:\n - "
            log += string.replace(",<br> ", "\n - ")
    
    log += sep()
    return metrics, violations, log, c, status

def check_class_missing_label(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting classes without a label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'class_missing_label')
    metrics[check] = 0 # 'missingClassLabel'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - All classes have a label annotation.\n"
        if verbose:
            log_results = exec_sparql(graph, 'class_labels')
            log += "\n|  Class | Label |\n|--|--|\n"
            for row in log_results:
                log += f"| {row.c} | {row.lbl} |\n"
            
    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"
    
    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} classes missing a label annotation:\n - "
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_property_missing_label(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting properties without a label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_missing_label')
    metrics[check] = 0 # 'missingPropertyLabel'
    violations[check] = ""

    if not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - All properties have a label annotation.\n"
        if verbose:
            log_results = exec_sparql(graph, 'property_labels')
            log += "|  Property | Label |\n|--|--|\n"
            for row in log_results:
                log += f"| {row.p} | {row.lbl} |\n"

    elif int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"
    
    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} properties missing a label annotation.\n - "
        status += 1
        string = violation_formatting([row.p for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_node_shape_missing_label(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting node shapes without a label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'node_shape_missing_label')
    metrics[check] = 0 # 'missingNSLabel'
    violations[check] = ""

    if not results and int(in_metrics['nodeShapes']) > 0:
        log += "PASS - All NodeShape have a label annotation.\n"
        if verbose:
            log_results = exec_sparql(graph, 'node_shape_labels')
            log += "|  NodeShape | Label |\n|--|--|\n"
            for row in log_results:
                log += f"| {row.ns} | {row.lbl} |\n"
            
    elif int(in_metrics['nodeShapes']) == 0:
        log += "WARNING - No NodeShape defined, invalid metric.\n"
    
    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} NodeShape missing a label annotation.\n - "
        status += 1
        string = violation_formatting([row.ns for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_property_shape_missing_label(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting property shapes without a label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_shape_missing_label')
    metrics[check] = 0 # 'missingPSLabel'
    violations[check] = ""

    if not results and int(in_metrics['propertyShapes']) > 0:
        log += "PASS - All PropertyShape have a label annotation.\n"
        if verbose:
            log_results = exec_sparql(graph, 'property_shape_labels')
            log += "|  PropertyShape | Label |\n|--|--|\n"
            for row in log_results:
                log += f"| {row.ps} | {row.lbl} |\n"
    
    elif int(in_metrics['propertyShapes']) == 0:
        log += "WARNING - No PropertyShapes defined, invalid metric.\n"
              
    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} PropertyShape missing a label annotation.\n - "
        status += 1
        string = violation_formatting([row.ps for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_class_missing_comment(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting classes without description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'class_missing_comment')
    metrics[check] = 0 # 'missingClassDescription'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - All classes have a description annotation.\n"
        if verbose:
            log_results = exec_sparql(graph, 'class_comments')
            log += "|  Class | Description |\n|--|--|\n"
            for row in log_results:
                log += f"| {row.c} | {row.lbl} |\n"
    
    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"
    
    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} classes missing a description annotation:\n - "
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_property_missing_comment(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting properties without description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_missing_comment')
    metrics[check] = 0 # 'missingPropertyDescription'
    violations[check] = ""

    if not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - All properties have a description annotation.\n"
        if verbose:
            log_results = exec_sparql(graph, 'property_comments')
            log += "| Property | Description |\n|--|--|\n"
            for row in log_results:
                log += f"| {row.p} | {row.lbl} |\n"
    
    elif int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"
    
    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} properties missing a description annotation.\n - "
        status += 1
        string = violation_formatting([row.p for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_node_shape_missing_comment(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting node shapes without description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'node_shape_missing_comment')
    metrics[check] = 0 # 'missingNSDescription'
    violations[check] = ""

    if not results and int(in_metrics['nodeShapes']) > 0:
        log += "PASS - All NodeShape have a description annotation.\n"
        if verbose:
            results = exec_sparql(graph, 'node_shape_comments')
            log += "| NodeShape | Description |\n|--|--|\n"
            for row in results:
                log += f"| {row.ns} | {row.lbl} |\n"
    elif int(in_metrics['nodeShapes']) == 0:
        log += "WARNING - No NodeShape defined, invalid metric.\n"
    
    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} NodeShape missing a description annotation:\n - "
        status += 1
        string = violation_formatting([row.ns for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_property_shape_missing_comment(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting property shapes without description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_shape_missing_comment')
    metrics[check] = 0 # 'missingPSDescription'
    violations[check] = ""

    if not results and int(in_metrics['propertyShapes']) > 0:
        log += "PASS - All PropertyShape have a description annotation.\n"
        if verbose:
            results = exec_sparql(graph, 'property_shape_comments')
            log += "| PropertyShape | Description |\n|--|--|\n"
            for row in results:
                log += f"| {row.ps} | {row.lbl} |\n"
    
    elif int(in_metrics['propertyShapes']) == 0:
        log += "WARNING - No PropertyShapes defined, invalid metric.\n"
    
    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} PropertyShape missing a description annotation:\n - "
        status += 1
        string = violation_formatting([row.ps for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_class_same_label(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting classes sharing the same label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'class_same_label')
    metrics[check] = 0 # 'nonUniqueClassLabels'
    violations[check] = ""
    
    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - No classes share the same label.\n"

    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} labels shared by multiple classes.\n"
        status += 1
        string = ""
        log += "| Label | Classes |\n|--|--|\n"
        for row in results:
            log += f"| {row.label} | {row.classes} |\n"
            string += f"\"{row.label}\": {row.classes};<br> "
        
        string = string.removesuffix(";<br> ")
        violations[check] = string
    
    log += sep()
    return metrics, violations, log, c, status

def check_property_same_label(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting properties sharing the same label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_same_label')
    metrics[check] = 0 # 'nonUniquePropertyLabels'
    violations[check] = ""

    if not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - No property share the same label.\n"

    elif int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} labels shared by multiple properties.\n"
        status += 1
        string = ""
        log += "| Label | Properties |\n|--|--|\n"
        for row in results:
            log += f"| {row.label} | {row.properties} |\n"
            string += f"\"{row.label}\": {row.properties};<br> "
        string = string.removesuffix(";<br> ")
        violations[check] = string
    
    log += sep()
    return metrics, violations, log, c, status

def check_node_shape_same_label(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting node shapes sharing the same label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'node_shape_same_label')
    metrics[check] = 0 # 'nonUniqueNSLabels'
    violations[check] = ""

    if not results and int(in_metrics['nodeShapes']) > 0:
        log += "PASS - No NodeShape share the same label.\n"

    elif int(in_metrics['nodeShapes']) == 0:
        log += "WARNING - No NodeShape defined, invalid metric.\n"

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} labels shared by multiple NodeShapes.\n"
        status += 1
        string = ""
        log += "| Label | NodeShapes |\n|--|--|\n"
        for row in results:
            log += f"| {row.label} | {row.nsList} |\n"
            string += f"\"{row.label}\": {row.nsList};<br> "
        
        string = string.removesuffix(";<br> ")
        violations[check] = string
    
    log += sep()
    return metrics, violations, log, c, status

def check_property_shape_same_label(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting property shapes sharing the same label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_shape_same_label')
    metrics[check] = 0 # 'nonUniquePSLabels'
    violations[check] = ""

    if not results and int(in_metrics['propertyShapes']) > 0:
       log += "PASS - No PropertyShape share the same label.\n"

    elif int(in_metrics['propertyShapes']) == 0:
        log += "WARNING - No PropertyShapes defined, invalid metric.\n"

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} labels shared by multiple PropertyShapes.\n"
        status += 1
        string = ""
        log += "| Label | PropertyShapes |\n|--|--|\n"
        for row in results:
            log += f"| {row.label} | {row.psList} |\n"
            string += f"\"{row.label}\": {row.psList};<br> "
        
        string = string.removesuffix(";<br> ")
        violations[check] = string
    
    log += sep()
    return metrics, violations, log, c, status

def check_isolated_classes(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting classes declared but never used in any other triple connecting them to the rest of the ontology.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'isolated_classes')
    metrics[check] = 0 # 'isolatedClasses'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - All classes are connected to another class through a subclass or property relation.\n"
    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} isolated classes:\n - "
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_property_missing_domain_range(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test checking properties for rdfs:domain or rdfs:range declaration.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = exec_sparql(graph, 'missing_dr_property')

    # Check if the test has been run already.
    if 'missingDomainRange' not in in_metrics:
        metrics['missingDomainRange'] = 0
        local_name = "Missing Domain or Range in Properties"
        c, log = qa_check_results(local_name, c)
        dCount = []
        rCount = []

        # Print the output of the check only once.
        if not results and int(in_metrics['propertyCount']) > 0:
            log += "INFO - All properties have domain and range defined.\n"
            if verbose: log += f"\n"

        elif int(in_metrics['propertyCount']) == 0:
            log += "WARNING - No properties defined, invalid metric.\n"

        elif results:
            metrics['missingDomainRange'] = len(results)
            log += f"WARNING - Found {metrics['missingDomainRange']} properties without `rdfs:domain` or `rdfs:range` declaration:\n\n"
            if not verbose: log += f"| Property | Domain | Range |\n| -------- | ------ | ----- |\n"
            status += 1
            for row in results:
                predicate = row.p
                if row.domain:
                    domain = row.domain
                else:
                    domain = 'None'
                    dCount.append(predicate)
                if row.range:
                    range = row.range
                else:
                    range = 'None'
                    rCount.append(predicate)
                if not verbose: log += f"| {predicate} | {domain} | {range} |\n"

            if not verbose: log  += f"\n"

        # If verbose, print a table with domain and range for all properties.
        if verbose and int(in_metrics['propertyCount']) > 0:
            # Show all properties in the results.
            results = exec_sparql(graph, 'dr_property')
            log += f"| Property | Domain | Range |\n| -------- | ------ | ----- |\n"
            for row in results:
                if row.domain:
                    domain = row.domain
                else:
                    domain = 'None'
                
                if row.range:
                    range = row.range
                else:
                    range = 'None'
                
                log += f"| {row.p} | {domain} | {range} |\n"
            
            log  += f"\n"
        
        # Control which check triggered the first execution.
        if check == 'missingDomain':
            # remove duplicates from dCount list.
            dCount = list(set(dCount))
            dCount.sort()
            metrics[check] = len(dCount)
            if metrics[check] > 0:
                string = violation_formatting(dCount)
                violations[check] = string
                string = string.replace(',<br> ', '\n - ')
                log += f"VIOLATION - Found {metrics[check]} properties without `rdfs:domain` declaration:\n - {string}\n"
            else:
                violations[check] = ""
                log += "PASS - All properties have domain defined.\n"

        elif check == 'missingRange':
            # remove duplicates from rCount list.
            rCount = list(set(rCount))
            rCount.sort()
            metrics[check]  = len(rCount)
            if metrics[check] > 0:
                string = violation_formatting(rCount)
                violations[check] = string
                string = string.replace(',<br> ', '\n - ')
                log += f"VIOLATION - Found {metrics[check]} properties without `rdfs:range` declaration:\n - {string}\n"
            else:
                violations[check] = ""
                log += "PASS - All properties have range defined.\n"
        
        log += sep()

    else:
        # This condition is satisfied only for range violations.
        # It relies on the fact that the array test_checklist is ordered,
        # with missingDomain defined before missingRange.
        local_name = "Missing Range in Properties"
        c, log = qa_check_results(local_name, c)
        rCount = []

        # Analyse the results
        if results:
            for row in results:
                predicate = row.p
                if not row.range:
                    rCount.append(predicate)
        
        # Report
        rCount = list(set(rCount))
        rCount.sort()
        metrics[check]  = len(rCount)
        if metrics[check] > 0:
            string = violation_formatting(rCount)
            violations[check] = string
            string = string.replace(',<br> ', '\n - ')
            log += f"VIOLATION - Found {metrics[check]} properties without `rdfs:range` declaration:\n - {string}\n"
        else:
            violations[check] = ""
            log += "PASS - All properties have range defined.\n"
        
        log += sep()

    return metrics, violations, log, c, status

def violation_formatting(array, unique=False):
    """
    Format a string of elements into a markdown list.
    
    Args:
        array (list): List of elements to format.
        unique (bool): Logical flag to sort and remove duplicates.
    
    Returns:
        formatted_string (str): String formatted as a markdown list.
    """
    if unique:
        array = list(set(array))
        array.sort()
    
    formatted_string = ""
    for element in array:
        formatted_string += f"{element},<br> "
    
    return formatted_string.removesuffix(",<br> ")

def check_unique_identifiers(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test checking for the same resource being declared as semantically inconsistent elements,
    e.g. owl:Class or rdfs:Class and owl:ObjectProperty, rdf:Property owl:DatatypeProperty  owl:AnnotationProperty.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'unique_identifiers')
    metrics[check] = 0 # 'nonUniqueIdentifiers'
    violations[check] = ""

    if not results:
        log += "PASS - No violations found.\n"
        
    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} elements with non-unique identifiers.\n"
        log += "| URI | Declared as |\n|--|--|\n"
        status += 1
        iri = []
        for row in results:
            log += f"| {row.iri} | {row.declaredAs} |\n"
            iri.append(row.iri)

        violations[check] = violation_formatting(iri)
    
    log += sep()
    return metrics, violations, log, c, status

def check_subclass_cycles(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting classes involved in subclass cycles.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'subclass_cycles')
    metrics[check] = 0 # 'subclassCycles'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - No violations found.\n"

    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} classes involved in subclass cycles:\n - "
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_untyped_class(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting classes in the current namespace without owl:Class or rdfs:Class declaration
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'untyped_class')
    metrics[check] = 0 # 'untypedClasses'
    violations[check] = ""
    num_files = len(in_metrics['filesProcessed'])
    ontology_check = False
    if 'ontologyNotDeclared' in in_metrics: ontology_check = True

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - No violations found.\n"

    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} classes without `owl:Class` or `rdfs:Class` declaration:\n - "
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"

    if ontology_check:
        if (in_metrics['ontologyNotDeclared'] > 0 and num_files == 1) or in_metrics['ontologyNotDeclared'] == num_files:
            log += f"WARNING - Ontology namespace undefined. No way to confirm if a class is defined in the ontology or an external vocabulary.\n"
        elif in_metrics['ontologyNotDeclared'] > 0 and in_metrics['ontologyNotDeclared'] < num_files and metrics[check] > 0:
            log += f"WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.\n"
    else:
        log += f"WARNING - Ontology namespace not checked. The reported violations may be incorrect.\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_untyped_property(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting properties in the current namespace without rdf:Property, owl:ObjectProperty or owl:DatatypeProperty declaration.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'untyped_property')
    metrics[check] = 0 # 'untypedProperties'
    violations[check] = ""
    num_files = len(in_metrics['filesProcessed'])
    ontology_check = False
    if 'ontologyNotDeclared' in in_metrics: ontology_check = True

    if not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - No violations found.\n"
              
    elif not results and int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} property without `rdf:Property`, `owl:ObjectProperty`, or `owl:DatatypeProperty` declaration:\n"
        status += 1
        string = violation_formatting([row.p for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    if ontology_check:
        if (in_metrics['ontologyNotDeclared'] > 0 and num_files == 1) or in_metrics['ontologyNotDeclared'] == num_files:
            log += f"WARNING - Ontology namespace undefined. No way to confirm if a property is defined in the ontology or an external vocabulary.\n"
        elif in_metrics['ontologyNotDeclared'] > 0 and in_metrics['ontologyNotDeclared'] < num_files and metrics[check] > 0:
            log += f"WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.\n"
    else:
        log += f"WARNING - Ontology namespace not checked. The reported violations may be incorrect.\n"
    
    log += sep()
    return metrics, violations, log, c, status

def check_hijacking(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test counting instances of hijacking, that is, resources defined in the current namespace but using a URI from an external vocabulary.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        check (str): Dictionary key of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    num_files = len(in_metrics['filesProcessed'])
    c, log = qa_check_results(name, c)
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
        log += "PASS - No violations found.\n"

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} resources defined using an external vocabulary prefix:\n - "
        string = violation_formatting([row.resource for row in results])
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    if ontology_check:
        if (in_metrics['ontologyNotDeclared'] > 0 and num_files == 1) or in_metrics['ontologyNotDeclared'] == num_files:
            log += f"WARNING - Ontology namespace undefined. The reported violations may be incorrect.\n"
        elif in_metrics['ontologyNotDeclared'] > 0 and in_metrics['ontologyNotDeclared'] < num_files and metrics[check] > 0:
            log += f"WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.\n"
    else:
        log += f"WARNING - Ontology namespace not checked. The reported violations may be incorrect.\n"
    
    log += sep()
    return metrics, violations, log, c, status

def load_rdf_file(file):
    """
    Load RDF data from a file and return an RDFLib Graph.
    
    Args:
        file (str): Path to the RDF file.
    
    Returns:
        bool: True if the file was successfully loaded, False otherwise.
        graph (rdflib.Graph): The RDF graph object to parse into.
        log (str): Parsing result.
    """
    log = f"Loading data from: {file}\n"
    graph = rdflib.Graph()

    # Try to guess format from file extension
    if file.lower().endswith(('.ttl', '.turtle')):
        fmt = "turtle"
    elif file.lower().endswith(('.rdf', '.owl', '.xml')):
        fmt = "xml"
    else:
        fmt = None  # Let rdflib try to guess
    try:
        graph.parse(file, format=fmt)
        return True, graph, log
    except Exception as e:
        log += f"Failed to parse {file} ({fmt if fmt else 'auto'}): {e}\n"
        return False, graph, log

def load_rdf(paths):
    """
    Load RDF files from files or directories.

    Args:
        paths (list): List of file and/or directory paths.
    
    Returns:
        file_counter (int): Number of files successfully loaded.
        files_processed (list): List of successfully processed file names.
        graph (rdflib.Graph): The RDF graph object with all loaded data.
        log_results (str): Parsing result and status log.
    """
    def _bind_namespaces(target_graph, source_graph):
        """Bind namespaces from source to target graph."""
        for prefix, uri in source_graph.namespace_manager.namespaces():
            try:
                target_graph.namespace_manager.bind(prefix, uri)
            except Exception:
                pass  # ignore binding errors

    # Collect all files to process
    files_to_load = []
    for path in paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    files_to_load.append(os.path.join(root, file))
        else:
            files_to_load.append(path)

    # Process all files
    file_counter = 0
    files_processed = []
    graph = rdflib.Graph()
    log_results = ""

    for file_path in files_to_load:
        success, file_graph, log_msg = load_rdf_file(file_path)
        log_results += log_msg
        if success:
            files_processed.append(os.path.basename(file_path))
            file_counter += 1
            graph += file_graph
            _bind_namespaces(graph, file_graph)

    return file_counter, files_processed, graph, log_results

def parse_lint_config(config):
    """
    Parse configuration dictionary to switch on/off selected metrics.

    Args:
        config (str): Path to the YAML configuration file.
    
    Returns:
        transformed_selection (dict): User-selected metrics.
    """
    if not os.path.isfile(config):
        raise FileNotFoundError(f"Config file not found: {config}")

    with open(config, "r", encoding="utf-8") as f:
        try:
            selection = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")
    
    if selection is None:
        selection = { "disable": [] }

    # Transform the dictionary
    transformed_selection = {
        key: [f"check_{item.replace('-', '_')}" for item in value_list]
        for key, value_list in selection.items()
    }

    return transformed_selection

def lint_selection(selection, checklist):
        """
        Disable the tests that are not included in the 'enable' list or that are included in the 'disable' list.
        The 'enable' and 'disable' keys are mutually exclusive. If both are specified in the configuration file,
        only the first dictionary will be used.
        """
        log = "> Lint configuration file found!\n"
        if 'enable' in selection and isinstance(selection['enable'], list):
            for i, item in enumerate(checklist):
                if not item[1].__name__ in selection['enable']:
                    checklist[i] = (False, item[1], item[2], item[3])

            # Special case for the check_property_missing_domain_range test, which is triggered by both missingDomain and missingRange checks.
            if 'check_property_missing_domain' in selection['enable']:
                index = [i for i, item in enumerate(checklist) if item[3] == 'missingDomain'][0]
                checklist[index] = (True, checklist[index][1], checklist[index][2], checklist[index][3])
            
            if 'check_property_missing_range' in selection['enable']:
                index = [i for i, item in enumerate(checklist) if item[3] == 'missingRange'][0]
                checklist[index] = (True, checklist[index][1], checklist[index][2], checklist[index][3])
        
        elif 'disable' in selection and isinstance(selection['disable'], list):
            for i, item in enumerate(checklist):
                if item[1].__name__ in selection['disable']:
                    checklist[i] = (False, item[1], item[2], item[3])
            
            # Special case for the check_property_missing_domain_range test, which is triggered by both missingDomain and missingRange checks.
            if 'check_property_missing_domain' in selection['disable']:
                index = [i for i, item in enumerate(checklist) if item[3] == 'missingDomain'][0]
                checklist[index] = (False, checklist[index][1], checklist[index][2], checklist[index][3])

            if 'check_property_missing_range' in selection['disable']:
                index = [i for i, item in enumerate(checklist) if item[3] == 'missingRange'][0]
                checklist[index] = (False, checklist[index][1], checklist[index][2], checklist[index][3])

        else:
            # Print a warning
            log += f">\n> WARNING - Invalid keyword in config file:\n> ```yaml\n"
            log += "> " + "> ".join(yaml.dump(selection, default_flow_style=False).splitlines(keepends=True))
            log += f"> ```"
        
        # Constraints
        # 1. Enable owl-declaration if only owl-description is enabled.
        for i, item in enumerate(checklist):
            if item[3] == 'ontologyNotDeclared': index_owl_declaration = i
            if item[3] == 'ontologyDescription': index_owl_description = i
        
        if not checklist[index_owl_declaration][0] and checklist[index_owl_description][0]:
            checklist[index_owl_declaration] = (True, checklist[index_owl_declaration][1], checklist[index_owl_declaration][2], checklist[index_owl_declaration][3])
            log += f"> WARNING: Check for OWL ontology declaration has been enabled because check for ontology description was selected.\n"
        
        return checklist, log

CHECKLIST = [
    (True, check_owl_declaration,                "Ontology without declaration",       'ontologyNotDeclared'       ),
    (True, check_owl_description,                "Ontology without description",       'ontologyDescription'       ),
    (True, check_class_missing_label,            "Class without label",                'missingClassLabel'         ),
    (True, check_property_missing_label,         "Property without label",             'missingPropertyLabel'      ),
    (True, check_node_shape_missing_label,       "NodeShape without label",            'missingNSLabel'            ),
    (True, check_property_shape_missing_label,   "PropertyShape without label",        'missingPSLabel'            ),
    (True, check_class_missing_comment,          "Class without description",          'missingClassDescription'   ),
    (True, check_property_missing_comment,       "Property without description",       'missingPropertyDescription'),
    (True, check_node_shape_missing_comment,     "NodeShape without description",      'missingNSDescription'      ),
    (True, check_property_shape_missing_comment, "PropertyShape without description",  'missingPSDescription'      ),
    (True, check_class_same_label,               "Classes with the same label",        'nonUniqueClassLabels'      ),
    (True, check_property_same_label,            "Properties with the same label",     'nonUniquePropertyLabels'   ),
    (True, check_node_shape_same_label,          "NodeShapes with the same label",     'nonUniqueNSLabels'         ),
    (True, check_property_shape_same_label,      "PropertyShapes with the same label", 'nonUniquePSLabels'         ),
    (True, check_isolated_classes,               "Isolated classes",                   'isolatedClasses'           ),
    (True, check_property_missing_domain_range,  "Property without domain",            'missingDomain'             ),
    (True, check_property_missing_domain_range,  "Property without range",             'missingRange'              ),
    (True, check_unique_identifiers,             "Non-unique identifiers",             'nonUniqueIdentifiers'      ),
    (True, check_subclass_cycles,                "Subclass Cycles",                    'subclassCycles'            ),
    (True, check_untyped_class,                  "Untyped Classes",                    'untypedClasses'            ),
    (True, check_untyped_property,               "Untyped Properties",                 'untypedProperties'         ),
    (True, check_hijacking,                      "Namespace hijacking",                'hijacking'                 ),
]


def run_qa(graph: rdflib.Graph, verbose: bool = False, files_processed: list | None = None, checklist=None) -> QAResult:
    """
    Run all QA checks on the given RDF graph.
    Applies RDFS subclass inference in-place, then runs all checks.
    Returns structured pass/fail results — no file I/O, no arg parsing.
    """
    if checklist is None:
        checklist = CHECKLIST

    qa_metrics = {
        'filesProcessed': files_processed or [],
        'triples': len(graph)
    }
    qa_violations = {}

    metrics, profiling_elements = profiling(graph)
    qa_metrics.update(metrics)

    logs = []
    checks = []
    test_counter = 1
    num_violations = 0
    for enabled, func, display_name, key in checklist:
        if enabled:
            metrics, violations, log_results, test_counter, num_violations = func(
                qa_metrics, graph, display_name, key, test_counter, num_violations, verbose
            )
            qa_metrics.update(metrics)
            qa_violations.update(violations)
            logs.append(log_results)
            count = int(qa_metrics.get(key, 0))
            raw = qa_violations.get(key, '')
            checks.append(CheckResult(
                name=display_name,
                passed=(count == 0),
                count=count,
                elements=str(raw) if raw else ''
            ))
    
    # Fallback to add profiling elements from OWL declaration, which could have been disabled in the QA checks.
    if 'ontologyURI' not in qa_metrics:
        metrics, _, _, _, _ = check_owl_declaration(qa_metrics, graph, "", 'ontologyNotDeclared', 1, 0, verbose)
        qa_metrics.update(metrics)
    
    return QAResult(
        profiling=qa_metrics,
        checks=checks,
        elements=profiling_elements,
        logs=logs
    )


def write_lint_config(checklist):
    """
    Generate a default .rdf-lint.yml config file
    """
    sys.stderr.write(f"Ontolint: creating default configuration file .rdf-lint.yml in the current directory.\n")

    # abort if path exists
    path = os.path.join(os.getcwd(), '.rdf-lint.yml')
    if os.path.exists(path):
        sys.stderr.write(f"ERROR: configuration file already exists: {path}\n\n")
        sys.exit(1)

    sequence = []
    for i, item in enumerate(checklist):
        name = item[1].__name__.replace("check_", "").replace("_", "-")
        sequence.append(name)
    
    for item in sequence:
        if item == "property-missing-domain-range":
            index = sequence.index(item)
            sequence[index] = "property-missing-domain"
        # Do it again :)
        if item == "property-missing-domain-range":
            index = sequence.index(item)
            sequence[index] = "property-missing-range"
    
    sequence.sort()

    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"""\
# Ontolint configuration file: use it to enable or disable specific QA checks.
# Place this file as .rdf-lint.yml in your project root.\n
# Available checks:
{chr(10).join(f'# - {s}' for s in sequence)}\n
# Enable only specific checks (empty = all checks enabled)
# enable:
#   - owl-description
#   - class-missing-label
#   - property-missing-label\n
# Disable specific checks
# disable:
#   - hijacking
#   - isolated-classes
#   - property-missing-domain
        """)

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(add_help=False, description=__doc__)
    parser.add_argument('-h', '--help', action='help', help='Show this help message and exit.')
    parser.add_argument('-e', '--exit-status', action='store_true', help='Report an exit status to determine if one or more violations were detected.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output.')
    parser.add_argument('-p', '--profile-only', action='store_true', help='Compute only the profiling metrics and skip the QA part.')
    parser.add_argument('-i', '--inference',action='store_true', help='Enable inference of subclass relations before running QA checks.(default: False)')
    parser.add_argument('--ctrf-dir', type=str, metavar='directory', default='ctrf', help='Directory to write CTRF report to.')
    parser.add_argument('--ctrf-filename', type=str, metavar='filename', default=None, help='Filename for CTRF report (if None, uses default pattern).')
    parser.add_argument('-o', '--output', type=str, metavar='filename', help='Output file name (optional). If omitted, print to stdout.')
    parser.add_argument('-c', '--config', type=str, metavar='path/to/config.yml', help='Path to a YAML configuration file to enable or disable individual checks. Note that if the current directory contains a .rdf-lint.yml file, it will be used by default.')
    parser.add_argument('--init', action='store_true', help='Generate a default .rdf-lint.yml config file in the current directory.')
    parser.add_argument('data_files', nargs='*', help='List of RDF files or folders to process.')
    args = parser.parse_args()

    # Validate arguments: data_files is required unless -i is used.
    if not args.init and not args.data_files:
        parser.error("data_files is required unless -i/--init option is used")

    # Write an empty lint configuration file and exit.
    if args.init:
        write_lint_config(CHECKLIST)
        exit(0)

    # Load Data and create an rdflib.Graph()
    log_output = "# Ontology Quality Assurance\n\n"
    file_counter, files_processed, g, log_results = load_rdf(args.data_files)
    log_output += log_results

    if file_counter == 0:
        print(f"{log_output}\nERROR - No RDF data in input files or directories.")
        return

    log_output += f"\n> {file_counter} files processed.\n"

    # Apply lint config to enable/disable individual checks.
    checklist = list(CHECKLIST)
    config_path = os.path.join(os.getcwd(), '.rdf-lint.yml')
    if args.config or os.path.isfile(config_path):
        if args.config:
            config_path = args.config
        lint_config = parse_lint_config(config_path)
        checklist, log_results = lint_selection(lint_config, checklist)
        log_output += log_results
       
    # Simulate Inference (optional)
    if args.inference:
        g, inference_log = infer_subclass_relations(g)
        log_output += inference_log

    # Profile-only path: compute profiling metrics only, skip full QA
    if args.profile_only:
        qa_metrics = {'filesProcessed': files_processed, 'triples': len(g)}
        qa_violations = {}
        metrics, violations = profiling(g)
        qa_metrics.update(metrics)
        qa_violations.update(violations)
        log_output += "\n> Profile-only mode enabled. Skipping additional QA checks.\n\n"
        metrics, violations, _, _, _ = check_owl_declaration(qa_metrics, g, "", 'ontologyNotDeclared', 1, 0, args.verbose)
        qa_metrics.update(metrics)
        qa_violations.update(violations)
        log_output += print_profiling_metrics(qa_metrics, qa_violations, args.verbose)
        log_output += print_profiling_table(qa_metrics)
        qa_terminate(args.output, log_output)
        return

    # Full QA path
    result = run_qa(g, verbose=args.verbose, files_processed=files_processed, checklist=checklist)
    qa_metrics = result.profiling
    qa_tests = {key: enabled for enabled, _, _, key in checklist}

    log_output += print_profiling_metrics(qa_metrics, result.elements, args.verbose)
    log_output += "\n## Quality Assurance Checks\n"
    for log in result.logs:
        log_output += log

    log_output += print_profiling_table(qa_metrics)
    log_output += print_qa_table(qa_metrics, qa_tests)

    write_ctrf_report(result, args.ctrf_dir, args.ctrf_filename)

    qa_terminate(args.output, log_output)

    if args.exit_status and not result.passed:
        sys.exit(1)

if __name__ == "__main__":
    main()
