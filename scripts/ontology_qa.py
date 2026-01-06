#!/usr/bin/env python3
# Ontology Quality Assessment Script (v0.1)
# SEMANTIC PARTNERS LTD, 2025
# Authors: Simon Shapiro, Otello M Roscioni.
# Last revision: 2025-11-30

"""
A script to perform basic QA on a set of ontologies.
It loads RDF files, applies simple RDFS subclass inference, and runs SPARQL queries to
check for common ontology quality issues.
It reports any violations found in the ontology data.
"""
import rdflib
from rdflib import Graph, URIRef
import argparse
from urllib.parse import urlparse
import sys
import os
import json
from datetime import datetime

# Create a dictionary with SPARQL queries, from files.
sparql_dir = os.getenv('QA_SPARQL_DIR', './sparql') # Use ENV variable or default value.

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
            if isinstance(term, URIRef):
                ns = get_namespace(str(term))
                used_namespaces.add(ns)

    # Filter the declared prefixes into those that are actually used
    used_prefixes = {}
    for ns in used_namespaces:
        if ns in declared_prefixes:
            prefix = declared_prefixes[ns]
            if len(prefix) > 0: used_prefixes[prefix] = ns

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
    names = names.rstrip(",<br> ")
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
    log += f"| Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used |\n"
    log += "|--|--|--|--|--|--|--|--|--|--|--|\n"
    log += f"| {name} | {metrics['triples']} | {metrics['classCount']} | {metrics['propertyCount']} | {metrics['nodeShapes']} | {metrics['propertyShapes']} | {metrics['classesInNodeShapes']} | {metrics['propertiesInPropertyShapes']} | {metrics['deprecatedClasses']} | {metrics['deprecatedProperties']} | {metrics['vocabulariesUsed']} |\n"
    return log

def print_qa_table(metrics):
    """
    Print a table with the quality assurance metrics of an RDF graph.

    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
    
    Returns:
        log (str): Pretty table with results.
    """
    name = get_ontology_name(metrics)
    log = "\n## Quality Metrics\n"
    log += f"| Name | Ontology not declared | Ontology without description | Class without label | Property without label | NodeShapes without label | PropertyShape without label "
    log += f"| Class without description | Property without description | NodeShapes without description | PropertyShape without description "
    log += f"| Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes "
    log += f"| Property without domain | Property without range "
    log += f"| Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |\n"
    log += "|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|\n"
    log += f"| {name} | {normalise(metrics['ontologyNotDeclared'],len(metrics['filesProcessed']))} "
    log += f"| {normalise(metrics['ontologyDescription'],len(metrics['filesProcessed']))} "
    log += f"| {normalise(metrics['missingClassLabel'],metrics['classCount'])} "
    log += f"| {normalise(metrics['missingPropertyLabel'],metrics['propertyCount'])} "
    log += f"| {normalise(metrics['missingNSLabel'],metrics['nodeShapes'])} "
    log += f"| {normalise(metrics['missingPSLabel'],metrics['propertyShapes'])} "
    log += f"| {normalise(metrics['missingClassDescription'],metrics['classCount'])} "
    log += f"| {normalise(metrics['missingPropertyDescription'],metrics['propertyCount'])} "
    log += f"| {normalise(metrics['missingNSDescription'],metrics['nodeShapes'])} "
    log += f"| {normalise(metrics['missingPSDescription'],metrics['propertyShapes'])} "
    log += f"| {normalise(metrics['nonUniqueClassLabels'],metrics['classCount'])} "
    log += f"| {normalise(metrics['nonUniquePropertyLabels'],metrics['propertyCount'])} "
    log += f"| {normalise(metrics['nonUniqueNSLabels'],metrics['nodeShapes'])} "
    log += f"| {normalise(metrics['nonUniquePSLabels'],metrics['propertyShapes'])} "
    log += f"| {normalise(metrics['isolatedClasses'],metrics['classCount'])} "
    log += f"| {normalise(metrics['missingDomain'],metrics['propertyCount'])} "
    log += f"| {normalise(metrics['missingRange'],metrics['propertyCount'])} "
    log += f"| {metrics['nonUniqueIdentifiers']} | {metrics['subclassCycles']} "
    log += f"| {metrics['untypedClasses']} | {metrics['untypedProperties']} | {metrics['hijacking']} |\n"
    return log

def write_ctrf_report(metrics, violations, tests, file_path, filename):
    """
    Convert QA metrics to CTRF (Common Test Result Format) JSON.
    """

    # Each QA check becomes a test case
    checks = [
        ("Ontology without declaration",     'ontologyNotDeclared'       ),
        ("Ontology without description",     'ontologyDescription'       ), 
        ("Class without label",              'missingClassLabel'         ), 
        ("Property without label",           'missingPropertyLabel'      ), 
        ("NodeShape without label",          'missingNSLabel'            ), 
        ("PropertyShape without label",      'missingPSLabel'            ), 
        ("Class without description",        'missingClassDescription'   ), 
        ("Property without description",     'missingPropertyDescription'), 
        ("NodeShape without description",    'missingNSDescription'      ), 
        ("PropertyShape without description",'missingPSDescription'      ), 
        ("Non-Unique Class Labels",          'nonUniqueClassLabels'      ), 
        ("Non-Unique Property Labels",       'nonUniquePropertyLabels'   ), 
        ("Non-Unique NodeShape Labels",      'nonUniqueNSLabels'         ), 
        ("Non-Unique PropertyShape Labels",  'nonUniquePSLabels'         ), 
        ("Isolated Classes",                 'isolatedClasses'           ), 
        ("Property without domain",          'missingDomain'             ), 
        ("Property without range",           'missingRange'              ), 
        ("Non-Unique Identifiers",           'nonUniqueIdentifiers'      ), 
        ("Subclass Cycles",                  'subclassCycles'            ), 
        ("Untyped Classes",                  'untypedClasses'            ), 
        ("Untyped Properties",               'untypedProperties'         ),
        ("Namespace hijacking",              'hijacking'                 )
    ]
    
    passed = 0
    failed = 0
    test_cases = []

    for check_name, key in checks:
        violation_count = metrics[key]
        violation_element = violations[key]
        violation_test = tests[key]
        if violation_test:
          test_case = {
              "name": check_name,
              "status": "pass" if violation_count == 0 else "fail"
          }
          if violation_count > 0:
              test_case["failure"] = {
                  "violations": violation_count,
                  "elements": violation_element
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

def print_profiling_metrics(metrics, violations, verbose):
    log  = f"RDF/OWL classes: {metrics['classCount']}\n"
    log += f"RDF/OWL properties: {metrics['propertyCount']}\n"
    log += f"SHACL Node Shapes: {metrics['nodeShapes']}\n"
    log += f"SHACL Property Shapes: {metrics['propertyShapes']}\n"

    log += f"Local classes in Node Shapes: {metrics['classesInNodeShapes']}\n"
    if verbose and metrics['classesInNodeShapes'] > 0:
        log += "\n| NodeShape | Class count |\n|--|--|\n"
        for _ in range( len(violations['classesInNodeShapes']['ns']) ):
            log += f"| {violations['classesInNodeShapes']['ns'][_]} "
            log += f"| {violations['classesInNodeShapes']['classCount'][_]} |\n"
        log += "\n"

    log += f"Local properties in Property Shapes: {metrics['propertiesInPropertyShapes']}\n"
    if verbose and metrics['propertiesInPropertyShapes'] > 0:
        log += "\n| PropertyShape | Local Property |\n|--|--|\n"
        for _ in range( len(violations['propertiesInPropertyShapes']['ps']) ):
            log += f"| {violations['propertiesInPropertyShapes']['ps'][_]} "
            log += f"| {violations['propertiesInPropertyShapes']['propCount'][_]} |\n"
        log += "\n"
    
    log += f"Deprecated classes: {metrics['deprecatedClasses']}\n"
    if verbose and metrics['deprecatedClasses'] > 0:
        log += "List of deprecated classes:\n"
        for _ in range( len(violations['deprecatedClasses']) ):
            log += f" - {violations['deprecatedClasses'][_]}\n"
        log += "\n"
    
    log += f"Deprecated properties: {metrics['deprecatedProperties']}\n"
    if verbose and metrics['deprecatedProperties'] > 0:
        log += "List of deprecated properties:\n"
        for _ in range( len(violations['deprecatedProperties']) ):
            log += f" - {violations['deprecatedProperties'][_]}\n"
        log += "\n"

    log += f"External vocabularies declared: {metrics['vocabulariesUsed']}\n"
    if metrics['vocabulariesUsed'] > 0:
        log += "\n| Prefix | URI |\n|--|--|\n"
        for _ in range( len(violations['vocabulariesUsed']['prefix']) ):
            # print(f" - {pfx}: {ns}")
            log += f"| {violations['vocabulariesUsed']['prefix'][_]} "
            log += f"| {violations['vocabulariesUsed']['uri'][_]} |\n"
        log += "\n"

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
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
    """
    metrics = {}
    violations = {}

    # Count classes, properties before inferencing.
    results = exec_sparql(graph, 'count_cp')
    (row,) = results
    metrics['classCount']= row.classCount
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
        violations['classesInNodeShapes'] = {
            'ns': [],
            'classCount': []
            }
        for row in results:
            violations['classesInNodeShapes']['ns'].append(row.ns)
            violations['classesInNodeShapes']['classCount'].append(row.classCount)

    # Count properties in PropertyShapes.
    results = exec_sparql(graph, 'property_in_property_shape')
    total_properties_in_shapes = len(results)
    metrics['propertiesInPropertyShapes'] = total_properties_in_shapes
    if total_properties_in_shapes > 0:
        violations['propertiesInPropertyShapes'] = {
            'ps': [],
            'propCount': []
            }
        for row in results:
            violations['propertiesInPropertyShapes']['ps'].append(row.ps)
            violations['propertiesInPropertyShapes']['propCount'].append(row.prop)

    # Number of Deprecated Classes and Properties
    results = exec_sparql(graph, 'deprecated_class')
    metrics['deprecatedClasses'] = len(results)
    if metrics['deprecatedClasses'] > 0:
        violations['deprecatedClasses'] = []
        for row in results:
            violations['deprecatedClasses'].append(row.c)
    
    results = exec_sparql(graph, 'deprecated_property')
    metrics['deprecatedProperties'] = len(results)
    if metrics['deprecatedProperties'] > 0:
        violations['deprecatedProperties'] = []
        for row in results:
            violations['deprecatedProperties'].append(row.p)

    # List all used prefixes
    active_prefixes = prefixes(graph)
    results = exec_sparql(graph, 'owl_declaration')
    if results:
        for row in results:
            # Remove ontology namespace from active_prefixes
            to_remove = []
            for row in results:
                for pfx, ns in active_prefixes.items():
                    if str(row.ont) == ns: to_remove.append(pfx)
            for pfx in to_remove:
                del active_prefixes[pfx]
    metrics['vocabulariesUsed'] = len(active_prefixes)

    # These are not violations, but the dictionary is nevertheless used to store elements
    # matching the same key of the metrics dictionary.
    violations['vocabulariesUsed'] = {
        'prefix': [],
        'uri': []
        }
    for pfx, ns in active_prefixes.items():
        # print(f" - {pfx}: {ns}")
        violations['vocabulariesUsed']['prefix'].append(pfx)
        violations['vocabulariesUsed']['uri'].append(ns)
    return metrics, violations

def infer_subclass_relations(graph):
    """
    Infer sub-class relations from ...
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        graph (rdflib.Graph): The RDF graph, after inference applied.
        log (str): Result of inferencing.
    """
    
    log = f"\nInitial graph size: {len(graph)} triples.\nApplying Subclass inference rule iteratively...\n"
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
    log += f"Final graph size after inference: {len(graph)} triples.\n" + sep() + "\n"
    return graph, log

def check_owl_declaration_description(in_metrics, graph, name, c, status, verbose):
    """
    QA test verifying that the ontology has a namespace declared as `owl:Ontology` and also contain a description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    num_files = len(in_metrics['filesProcessed'])
    metrics['ontologyNotDeclared'] = num_files # Assume no ontology has been declared.
    metrics['ontologyURI'] = [ ]
    test = {}
    test['ontologyNotDeclared'] = True
    test['ontologyDescription'] = True

    # Check the ontology declaration.
    name = "OWL ontology declaration"
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'owl_declaration')
    if not results:
        status += 1
    else:
        for row in results:
            metrics['ontologyURI'].append(row.ont)
            metrics['ontologyNotDeclared'] -= 1
    
    # Record the violation elements.
    num_uri = len(metrics['ontologyURI'])
    if metrics['ontologyNotDeclared'] == num_files:
        log += "VIOLATION - No `owl:Ontology` declaration found.\n"
        violations['ontologyNotDeclared'] = "**All** processed files missing ontology declaration."
    
    elif metrics['ontologyNotDeclared'] > 0 and metrics['ontologyNotDeclared'] < num_files:
        if metrics['ontologyNotDeclared'] == 1:
            log += f"VIOLATION - 1 ontology without `owl:Ontology` declaration.\n"
        else:
            log += f"VIOLATION - {metrics['ontologyNotDeclared']} ontologies without `owl:Ontology` declaration.\n"
        violations['ontologyNotDeclared'] = "**Some** processed files missing ontology declaration.<br> Check files individually."
    
    else:
        if num_uri == 1:
            log += f"PASS - Found 1 ontology with `owl:Ontology` declaration.\n"
        else:
            log += f"PASS - Found {num_uri} ontologies with `owl:Ontology` declaration.\n"
        
        violations['ontologyNotDeclared'] = ""
    
    # Print additional information.
    if verbose and metrics['ontologyNotDeclared'] <= 0:
        log = log.rstrip(".\n")
        log += ":\n"
        for _ in range(num_uri):
            log += f" - {metrics['ontologyURI'][_]}\n"

    # Print more information if violations are found.
    if metrics['ontologyNotDeclared'] > 0:
        log += "Check the input files individually to find out which one violates this check.\n"
        if num_uri > 0: log += "WARNING - The following ontology URIs were found:\n"
        for _ in range(num_uri):
            log += f" - {metrics['ontologyURI'][_]}\n"
    
    log += sep()
    
    # Check the ontology description.
    name = "OWL ontology description"
    if metrics['ontologyNotDeclared'] == num_files:
        log += f"\nSkipping check {c}: Ontology description (no ontology declared).\n"
        c += 1
        metrics['ontologyDescription'] = 1 # no
        violations['ontologyDescription'] = "No ontology declared"
    else:
        c, log_results = qa_check_results(name, c)
        log += log_results
        results = exec_sparql(graph, 'no_ont_description')
        if not results:
            log += "PASS - All declared ontologies have a description.\n"
            metrics['ontologyDescription'] = 0 # yes
            violations['ontologyDescription'] = ""
            if verbose:
                log_results = exec_sparql(graph, 'ont_description')
                log += "\n**Ontology + Description:**\n"
                for row in log_results:
                    log += f" - {row.ont}\n   *{row.d}*\n"
                
        else:
            owd = len(results)
            metrics['ontologyDescription'] = len(results) #  violations
            status += 1
            string = ""
            for row in results:
                string += f"{row.ont},<br> "
            
            string = string.rstrip(",<br> ")
            violations['ontologyDescription'] = string
            log += f"VIOLATION - Found {metrics['ontologyDescription']} ontologies without description:\n - "
            log += string.replace(",<br> ", "\n - ")
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_class_missing_label(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting classes without a label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'class_missing_label')
    metrics['missingClassLabel'] = 0
    violations['missingClassLabel'] = ""
    test = {}
    test['missingClassLabel'] = True

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
        metrics['missingClassLabel'] = len(results)
        log += f"VIOLATION - Found {metrics['missingClassLabel']} classes missing a label annotation:\n - "
        status += 1
        string = ""
        for t in results:
            string += f"{t[0]},<br> "
        
        string = string.rstrip(",<br> ")
        violations['missingClassLabel'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_property_missing_label(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting properties without a label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_missing_label')
    metrics['missingPropertyLabel'] = 0
    violations['missingPropertyLabel'] = ""
    test = {}
    test['missingPropertyLabel'] = True

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
        metrics['missingPropertyLabel'] = len(results)
        log += f"VIOLATION - Found {metrics['missingPropertyLabel']} properties missing a label annotation.\n - "
        status += 1
        string = ""
        for t in results:
            string += f"{t[0]},<br> "
        
        string = string.rstrip(",<br> ")
        violations['missingPropertyLabel'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_node_shape_missing_label(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting node shapes without a label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'node_shape_missing_label')
    metrics['missingNSLabel'] = 0
    violations['missingNSLabel'] = ""
    test = {}
    test['missingNSLabel'] = True

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
        metrics['missingNSLabel'] = len(results)
        log += f"VIOLATION - Found {metrics['missingNSLabel']} NodeShape missing a label annotation.\n - "
        status += 1
        string = ""
        for row in results:
            string += f"{row.ns},<br> "
        
        string = string.rstrip(",<br> ")
        violations['missingNSLabel'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_property_shape_missing_label(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting property shapes without a label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_shape_missing_label')
    metrics['missingPSLabel'] = 0
    violations['missingPSLabel'] = ""
    test = {}
    test['missingPSLabel'] = True

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
        metrics['missingPSLabel'] = len(results)
        log += f"VIOLATION - Found {metrics['missingPSLabel']} PropertyShape missing a label annotation.\n - "
        status += 1
        string = ""
        for row in results:
          string += f"{row.ps},<br> "
        
        string = string.rstrip(",<br> ")
        violations['missingPSLabel'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_class_missing_comment(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting classes without description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'class_missing_comment')
    metrics['missingClassDescription'] = 0
    violations['missingClassDescription'] = ""
    test = {}
    test['missingClassDescription'] = True

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - All classes have a description annotation.\n"
        if verbose:
            log_results = exec_sparql(graph, 'class_labels')
            log += "|  Class | Description |\n|--|--|\n"
            for row in log_results:
                log += f"| {row.c} | {row.lbl} |\n"
    
    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"
    
    elif results:
        metrics['missingClassDescription'] = len(results)
        log += f"VIOLATION - Found {metrics['missingClassDescription']} classes missing a description annotation:\n - "
        status += 1
        string = ""
        for t in results:
          string += f"{t[0]},<br> "

        string = string.rstrip(",<br> ")
        violations['missingClassDescription'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_property_missing_comment(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting properties without description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_missing_comment')
    metrics['missingPropertyDescription'] = 0
    violations['missingPropertyDescription'] = ""
    test = {}
    test['missingPropertyDescription'] = True

    if not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - All properties have a description annotation.\n"
        if verbose:
            log_results = exec_sparql(graph, 'class_labels')
            log += "| Property | Description |\n|--|--|\n"
            for row in log_results:
                log += f"| {row.p} | {row.lbl} |\n"
    
    elif int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"
    
    elif results:
        metrics['missingPropertyDescription'] = len(results)
        log += f"VIOLATION - Found {metrics['missingPropertyDescription']} properties missing a description annotation.\n - "
        status += 1
        string = ""
        for t in results:
          string += f"{t[0]},<br> "
        string = string.rstrip(",<br> ")
        violations['missingPropertyDescription'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_node_shape_missing_comment(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting node shapes without description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'node_shape_missing_comment')
    metrics['missingNSDescription'] = 0
    violations['missingNSDescription'] = ""
    test = {}
    test['missingNSDescription'] = True

    if not results and int(in_metrics['nodeShapes']) > 0:
        log += "PASS - All NodeShape have a description annotation.\n"
        if verbose:
            results = exec_sparql(graph, 'node_shape_labels')
            log += "| NodeShape | Description |\n|--|--|\n"
            for row in results:
                log += f"| {row.ns} | {row.lbl} |\n"
    elif int(in_metrics['nodeShapes']) == 0:
        log += "WARNING - No NodeShape defined, invalid metric.\n"
    
    elif results:
        metrics['missingNSDescription'] = len(results)
        log += f"VIOLATION - Found {metrics['missingNSDescription']} NodeShape missing a description annotation:\n - "
        status += 1
        string = ""
        for row in results:
          string += f"{row.ns},<br> "
        
        string = string.rstrip(",<br> ")
        violations['missingNSDescription'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_property_shape_missing_comment(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting property shapes without description.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_shape_missing_comment')
    metrics['missingPSDescription'] = 0
    violations['missingPSDescription'] = ""
    test = {}
    test['missingPSDescription'] = True

    if not results and int(in_metrics['propertyShapes']) > 0:
        log += "PASS - All PropertyShape have a description annotation.\n"
        if verbose:
            results = exec_sparql(graph, 'property_shape_labels')
            log += "| PropertyShape | Description |\n|--|--|\n"
            for row in results:
                log += f"| {row.ps} | {row.lbl} |\n"
    
    elif int(in_metrics['propertyShapes']) == 0:
        log += "WARNING - No PropertyShapes defined, invalid metric.\n"
    
    elif results:
        metrics['missingPSDescription'] = len(results)
        log += f"VIOLATION - Found {metrics['missingPSDescription']} PropertyShape missing a description annotation:\n - "
        status += 1
        string = ""
        for row in results:
          string += f"{row.ps},<br> "
        string = string.rstrip(",<br> ")
        violations['missingPSDescription'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_class_same_label(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting classes sharing the same label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'class_same_label')
    metrics['nonUniqueClassLabels'] = 0
    violations['nonUniqueClassLabels'] = ""
    test = {}
    test['nonUniqueClassLabels'] = True
    
    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - No classes share the same label.\n"

    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"

    elif results:
        metrics['nonUniqueClassLabels'] = len(results)
        log += f"VIOLATION - Found {metrics['nonUniqueClassLabels']} labels shared by multiple classes.\n"
        status += 1
        string = ""
        log += "| Label | Classes |\n|--|--|\n"
        for row in results:
            log += f"| {row.label} | {row.classes} |\n"
            string += f"\"{row.label}\": {row.classes};<br> "
        
        string = string.rstrip(";<br> ")
        violations['nonUniqueClassLabels'] = string
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_property_same_label(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting properties sharing the same label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_same_label')
    metrics['nonUniquePropertyLabels'] = 0
    violations['nonUniquePropertyLabels'] = ""
    test = {}
    test['nonUniquePropertyLabels'] = True

    if not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - No property share the same label.\n"

    elif int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"

    elif results:
        metrics['nonUniquePropertyLabels'] = len(results)
        log += f"VIOLATION - Found {metrics['nonUniquePropertyLabels']} labels shared by multiple properties.\n"
        status += 1
        string = ""
        log += "| Label | Properties |\n|--|--|\n"
        for row in results:
            log += f"| {row.label} | {row.properties} |\n"
            string += f"\"{row.label}\": {row.properties};<br> "
        string = string.rstrip(";<br> ")
        violations['nonUniquePropertyLabels'] = string
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_node_shape_same_label(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting node shapes sharing the same label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'node_shape_same_label')
    metrics['nonUniqueNSLabels'] = 0
    violations['nonUniqueNSLabels'] = ""
    test = {}
    test['nonUniqueNSLabels'] = True

    if not results and int(in_metrics['nodeShapes']) > 0:
        log += "PASS - No NodeShape share the same label.\n"

    elif int(in_metrics['nodeShapes']) == 0:
        log += "WARNING - No NodeShape defined, invalid metric.\n"

    elif results:
        metrics['nonUniqueNSLabels'] = len(results)
        log += f"VIOLATION - Found {metrics['nonUniqueNSLabels']} labels shared by multiple NodeShapes.\n"
        status += 1
        string = ""
        log += "| Label | NodeShapes |\n|--|--|\n"
        for row in results:
            log += f"| {row.label} | {row.nsList} |\n"
            string += f"\"{row.label}\": {row.nsList};<br> "
        
        string = string.rstrip(";<br> ")
        violations['nonUniqueNSLabels'] = string
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_property_shape_same_label(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting property shapes sharing the same label.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'property_shape_same_label')
    metrics['nonUniquePSLabels'] = 0
    violations['nonUniquePSLabels'] = ""
    test = {}
    test['nonUniquePSLabels'] = True

    if not results and int(in_metrics['propertyShapes']) > 0:
       log += "PASS - No PropertyShape share the same label.\n"

    elif int(in_metrics['propertyShapes']) == 0:
        log += "WARNING - No PropertyShapes defined, invalid metric.\n"

    elif results:
        metrics['nonUniquePSLabels'] = len(results)
        log += f"VIOLATION - Found {metrics['nonUniquePSLabels']} labels shared by multiple PropertyShapes.\n"
        status += 1
        string = ""
        log += "| Label | PropertyShapes |\n|--|--|\n"
        for row in results:
            log += f"| {row.label} | {row.psList} |\n"
            string += f"\"{row.label}\": {row.psList};<br> "
        
        string = string.rstrip(";<br> ")
        violations['nonUniquePSLabels'] = string
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_isolated_classes(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting classes declared but never used in any other triple connecting them to the rest of the ontology.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'isolated_classes')
    metrics['isolatedClasses'] = 0
    violations['isolatedClasses'] = ""
    test = {}
    test['isolatedClasses'] = True

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - All classes are connected to another class through a subclass or property relation.\n"
    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"

    elif results:
        metrics['isolatedClasses'] = len(results)
        log += f"VIOLATION - Found {metrics['isolatedClasses']} isolated classes:\n - "
        status += 1
        string = ""
        for row in results:
          string += f"{row[0]},<br> "
        
        string = string.rstrip(",<br> ")
        violations['isolatedClasses'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_missing_dr_property(in_metrics, graph, name, c, status, verbose):
    """
    QA test checking properties for rdfs:domain or rdfs:range declaration.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'missing_dr_property')
    dCount = 0
    rCount = 0
    metrics['missingDomainRange'] = 0
    test = {}
    test['missingDomain'] = True
    test['missingRange'] = True

    if not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - All properties have domain and range defined.\n"

    elif int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"

    elif results:
        metrics['missingDomainRange'] = len(results)
        log += f"VIOLATION - Found {metrics['missingDomainRange']} properties without `rdfs:domain` or `rdfs:range` declaration:\n"
        if not verbose: log += f"| Property | Domain | Range |\n| -------- | ------ | ----- |\n"
        status += 1
        string = ""
        string2 = ""
        for row in results:
            predicate = row.p
            if row.domain:
                domain = row.domain
            else:
                domain = 'None'
                dCount += 1
                string += f"{predicate},<br> "
            if row.range:
                range = row.range
            else:
                range = 'None'
                rCount += 1
                string2 += f"{predicate},<br> "
            if not verbose: log += f"| {predicate} | {domain} | {range} |\n"
    
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

    if dCount > 0:
        string = string.rstrip(",<br> ")
        violations['missingDomain'] = string
    else:
        violations['missingDomain'] = ""
    
    if rCount > 0:
        string2 = string2.rstrip(",<br> ")
        violations['missingRange'] = string2
    else:
        violations['missingRange'] = ""
    
    metrics['missingDomain'] = dCount
    metrics['missingRange']  = rCount
    log += sep()
    return metrics, violations, test, log, c, status

def check_unique_identifiers(in_metrics, graph, name, c, status, verbose):
    """
    QA test checking for the same resource being declared as semantically inconsistent elements,
    e.g. owl:Class or rdfs:Class and owl:ObjectProperty, rdf:Property owl:DatatypeProperty  owl:AnnotationProperty.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'unique_identifiers')
    test = {}
    test['nonUniqueIdentifiers'] = True

    if not results:
        log += "PASS - No violations found.\n"
        metrics['nonUniqueIdentifiers'] = 0
        violations['nonUniqueIdentifiers'] = ""
        
    elif results:
        metrics['nonUniqueIdentifiers'] = len(results)
        log += f"VIOLATION - Found {metrics['nonUniqueIdentifiers']} elements with non-unique identifiers.\n"
        log += "| URI | Declared as |\n|--|--|\n"
        status += 1
        string = ""
        for row in results:
            log += f"| {row.iri} | {row.declaredAs} |\n"
            string += f"{row.iri},<br> "
        string = string.rstrip(",<br> ")
        violations['nonUniqueIdentifiers'] = string
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_subclass_cycles(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting classes involved in subclass cycles.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'subclass_cycles')
    metrics['subclassCycles'] = 0
    violations['subclassCycles'] = ""
    test = {}
    test['subclassCycles'] = True

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - No violations found.\n"

    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"

    elif results:
        metrics['subclassCycles'] = len(results)
        log += f"VIOLATION - Found {metrics['subclassCycles']} classes involved in subclass cycles:\n - "
        status += 1
        string = ""
        for row in results:
            string += f"{row.c},<br> "
        
        string = string.rstrip(",<br> ")
        violations['subclassCycles'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_untyped_class(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting classes in the current namespace without owl:Class or rdfs:Class declaration
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'untyped_class')
    metrics['untypedClasses'] = 0
    violations['untypedClasses'] = ""
    num_files = len(in_metrics['filesProcessed'])
    test = {}
    test['untypedClasses'] = True

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - No violations found.\n"

    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"

    elif results:
        metrics['untypedClasses'] = len(results)
        log += f"VIOLATION - Found {metrics['untypedClasses']} classes without `owl:Class` or `rdfs:Class` declaration:\n - "
        status += 1
        string = ""
        for row in results:
            string += f"{row.c},<br> "

        string = string.rstrip(",<br> ")
        violations['untypedClasses'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"

    if (in_metrics['ontologyNotDeclared'] > 0 and num_files == 1) or in_metrics['ontologyNotDeclared'] == num_files:
        log += f"WARNING - Ontology namespace undefined. No way to confirm if a class is defined in the ontology or an external vocabulary.\n"
    elif in_metrics['ontologyNotDeclared'] > 0 and in_metrics['ontologyNotDeclared'] < num_files and metrics['untypedClasses'] > 0:
        log += f"WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

def check_untyped_property(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting properties in the current namespace without rdf:Property, owl:ObjectProperty or owl:DatatypeProperty declaration.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'untyped_property')
    metrics['untypedProperties'] = 0
    violations['untypedProperties'] = ""
    num_files = len(in_metrics['filesProcessed'])
    test = {}
    test['untypedProperties'] = True

    if not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - No violations found.\n"
              
    elif int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"

    elif results:
        metrics['untypedProperties'] = len(results)
        log += f"VIOLATION - Found {metrics['untypedProperties']} property without `rdf:Property`, `owl:ObjectProperty`, or `owl:DatatypeProperty` declaration:\n"
        status += 1
        string = ""
        for row in results:
            string += f"{row.p},<br> "
        
        string = string.rstrip(",<br> ")
        violations['untypedProperties'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    if (in_metrics['ontologyNotDeclared'] > 0 and num_files == 1) or in_metrics['ontologyNotDeclared'] == num_files:
        log += f"WARNING - Ontology namespace undefined. No way to confirm if a property is defined in the ontology or an external vocabulary.\n"
    elif in_metrics['ontologyNotDeclared'] > 0 and in_metrics['ontologyNotDeclared'] < num_files and metrics['untypedProperties'] > 0:
        log += f"WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.\n"
        
    log += sep()
    return metrics, violations, test, log, c, status

def check_hijacking(in_metrics, graph, name, c, status, verbose):
    """
    QA test counting instances of hijacking, that is, resources defined in the current namespace but using a URI from an external vocabulary.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        name (str): Name of the QA check being carried out.
        c (int): Counter for the QA checks selected.
        status (int): Number of violations before the check.
        verbose (bool): Logical flag for printing additional information.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        test (dict): Was QA test executed? (bool)
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    num_files = len(in_metrics['filesProcessed'])
    c, log = qa_check_results(name, c)
    results = exec_sparql(graph, 'hijacking')
    test = {}
    test['hijacking'] = True

    if not results:
        log += "PASS - No violations found.\n"
        metrics['hijacking'] = 0
        violations['hijacking'] = ""

    elif results:
        metrics['hijacking'] = len(results)
        log += f"VIOLATION - Found {metrics['hijacking']} resources defined using an external vocabulary prefix:\n - "
        # log += f"| Namespace | Count |\n|--|--|\n"
        string = ""
        for row in results:
            string += f"{row.resource},<br> "
            # log += f"| {row.namespace} | {rrow['count']} |\n"
            # el = int(row['count']) # for hijacking_count
            # if el == 1:
            #     string += f"{row.namespace}: ({row['count']} element),<br> "
            # elif el > 1:
            #     string += f"{row.namespace}: ({row['count']} elements),<br> "
        
        string = string.rstrip(",<br> ")
        violations['hijacking'] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
        
    if (in_metrics['ontologyNotDeclared'] > 0 and num_files == 1) or in_metrics['ontologyNotDeclared'] == num_files:
        log += f"WARNING - Ontology namespace undefined. The reported violations may be incorrect.\n"
    elif in_metrics['ontologyNotDeclared'] > 0 and in_metrics['ontologyNotDeclared'] < num_files and metrics['hijacking'] > 0:
        log += f"WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.\n"
    
    log += sep()
    return metrics, violations, test, log, c, status

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

def load_rdf(f):
    """
    Load RDF files from file or directory name.

    Args:
        f (str): The name of a file or directory.
    
    Returns:
        counter (int): Number of files successfully loaded.
        metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        log (str): Parsing result.
    """
    counter = 0
    metrics = {}
    metrics['filesProcessed'] = []
    graph = rdflib.Graph()
    log = ""
    # check if f is a directory
    if os.path.isdir(f):
        for root, _, files in os.walk(f):
            for file in files:
                file_path = os.path.join(root, file)
                go, g, results = load_rdf_file(file_path)
                log += results
                if go:
                    # Append processed file
                    metrics['filesProcessed'].append(file)
                    counter += 1
                    graph += g
    else:
        go, g, results = load_rdf_file(f)
        log += results
        if go:
            # Append processed file
            metrics['filesProcessed'].append(f)
            counter += 1
            graph += g

    return counter, metrics, graph, log

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-e', '--exit-status', action='store_true', help='Report an exit status to determine if one or more violations were detected.')
    parser.add_argument('-v', '--verbose',action='store_true', help='Enable verbose output.')
    parser.add_argument('-p', '--profile-only',action='store_true', help='Compute only the profiling metrics and skip the QA part.')
    parser.add_argument('--ctrf-dir', type=str, metavar='directory', default='ctrf', help='Directory to write CTRF report to.')
    parser.add_argument('--ctrf-filename', type=str, metavar='filename', default=None, help='Filename for CTRF report (if None, uses default pattern).')
    parser.add_argument('-o', '--output', type=str, metavar='filename', help='Output file name (optional). If omitted, print to stdout.')
    parser.add_argument('data_files', nargs='+', help='List of RDF files or folders to process.')
    args = parser.parse_args()

    # Create empty dictionaries to store the ontology metrics.
    qa_metrics = {}    # violation count
    qa_violations = {} # violation elements
    qa_tests = {}      # violation test? (boolean) 

    # Load Data
    g = rdflib.Graph()
    file_counter = 0
    log_output = "# Ontology Quality Assurance\n\n"
    files_processed = []
    for f in args.data_files:
        c, file_metrics, file_graph, results = load_rdf(f)
        file_counter += c
        files_processed.extend(file_metrics['filesProcessed'])
        g += file_graph # accumulate in the main graph.
        log_output += results

    if file_counter == 0:
        print(f"{log_output}\nERROR - No RDF data in input files or directories.")
        return
    else:
        # Update the filesProcessed key
        qa_metrics['filesProcessed'] = files_processed

    # Compute and store the profiling metrics.
    qa_metrics['triples'] = len(g)
    metrics, violations = profiling(g)
    qa_metrics.update(metrics)
    qa_violations.update(violations)
    log_output += f"\n> {file_counter} files processed.\n"

    # Terminate the execution if further QA checks are not required.
    if args.profile_only:
        log_output += "\n> Profile-only mode enabled. Skipping additional QA checks.\n\n"
        qa_metrics, violations, test, log_results, test_counter, num_violations = check_owl_declaration_description(qa_metrics, g, "", 1, 0, args.verbose)
        qa_violations.update(violations)
        log_output += print_profiling_metrics(qa_metrics, qa_violations, args.verbose)
        log_output += print_profiling_table(qa_metrics)
        qa_terminate(args.output, log_output)
        return
    
    # Simulate Inference
    g, results = infer_subclass_relations(g)
    log_output += results

    # Compute the metrics for Quality Assurance.
    num_violations = 0
    test_counter = 1

    # Array with all tests for QA metrics.
    test_checklist = [
        (True, check_owl_declaration_description,    "OWL ontology declaration and description"),
        (True, check_class_missing_label,            "Class without label"                     ),
        (True, check_property_missing_label,         "Property without label"                  ),
        (True, check_node_shape_missing_label,       "NodeShape without label"                 ),
        (True, check_property_shape_missing_label,   "PropertyShape without label"             ),
        (True, check_class_missing_comment,          "Class without description"               ),
        (True, check_property_missing_comment,       "Property without description"            ),
        (True, check_node_shape_missing_comment,     "NodeShape without description"           ),
        (True, check_property_shape_missing_comment, "PropertyShape without description"       ),
        (True, check_class_same_label,               "Classes with the same label"             ),
        (True, check_property_same_label,            "Properties with the same label"          ),
        (True, check_node_shape_same_label,          "NodeShapes with the same label"          ),
        (True, check_property_shape_same_label,      "PropertyShapes with the same label"      ),
        (True, check_isolated_classes,               "Isolated classes"                        ),
        (True, check_missing_dr_property,            "Missing Domain or Range in Properties"   ),
        (True, check_unique_identifiers,             "Non-unique identifiers"                  ),
        (True, check_subclass_cycles,                "Including Cycles in a Class Hierarchy"   ),
        (True, check_untyped_class,                  "Untyped Classes"                         ),
        (True, check_untyped_property,               "Untyped Properties"                      ),
        (True, check_hijacking,                      "Namespace hijacking"                     )
    ]

    # TO DO:
    # Parse a configuration file to enable/disable individual tests.

    # Aggregate and format the results.
    log_output += print_profiling_metrics(qa_metrics, qa_violations, args.verbose)

    # Cycle through selected tests.
    for enabled, func, test_name in test_checklist:
        if enabled:
            metrics, violations, test, log_results, test_counter, num_violations = func(qa_metrics, g, test_name, test_counter, num_violations, args.verbose)

            # Merge returned metrics and violations into global dictionaries
            qa_metrics.update(metrics)
            qa_violations.update(violations)
            qa_tests.update(test)
            log_output += log_results

    # Profiling Table
    log_output += print_profiling_table(qa_metrics)

    # QA metrics Table
    log_output += print_qa_table(qa_metrics)

    # Generate CTRF report
    write_ctrf_report(qa_metrics, qa_violations, qa_tests, args.ctrf_dir, args.ctrf_filename)

    # Print the results
    qa_terminate(args.output, log_output)

    # Exit status
    if args.exit_status and num_violations > 0: sys.exit(1)

if __name__ == "__main__":
    main()
