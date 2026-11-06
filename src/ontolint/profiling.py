"""
What an ontology contains, counted: classes, properties, shapes, deprecations, the
vocabularies it uses and the depth of its hierarchy - and the two things done to a graph
before the checks see it, which are removing instance data and inferring subclass
relations.
"""
import networkx as nx
import rdflib

from .model import INFERRED_CONTEXT
from .queries import exec_sparql
from .terms import get_namespace


def prefixes(g):
    # Create a dictionary for the declared prefixes
    declared_prefixes = {}
    for prefix, uri in g.namespace_manager.namespaces():
        uri_str = str(uri)
        declared_prefixes[uri_str] = prefix

    # Collect all namespaces actually used in the graph
    used_namespaces = set()
    for s, p, o in g.triples((None, None, None)):
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


def profiling(graph):
    """
    Compute profiling information for an RDF graph.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        metrics (dict): Count of ontology metrics.
        elements (dict): Elements in ontology metrics.
        exclusions (rdflib.Graph): The RDF graph with instance data to exclude
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
            elements['propertiesInPropertyShapes']['propCount'].append(row.property)

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
    results = exec_sparql(graph, 'owl_imports')
    metrics['imports'] = len(results)
    elements['imports'] = {}
    if metrics['imports'] > 0:
        old =  ""
        for row in results:
            if row.ontology != old:
                elements['imports'][str(row.ontology)] = []
                old = row.ontology
            elements['imports'][str(row.ontology)].append(str(row.imp))
    
    # hierarchy depth
    metrics['HierarchyDepth'] = exec_hierarchy_depth(graph)
    
    # average branching factor
    results = exec_sparql(graph, 'average_branching_factor')
    (row,) = results
    metrics['aveBranchFactor'] = row.avgBranchingFactor

    # use of restrictions
    results = exec_sparql(graph, 'cardinality_restrictions')
    (row,) = results
    metrics['CardinalityRestrictions'] = row.counter

    # Exclude instance data from linting.
    exclusions, metrics['instances'] = exclude_instance_data(graph)

    return metrics, elements, exclusions


def exec_hierarchy_depth(graph):
    """Compute the hierarchy depth of the ontology by constructing a directed graph of subclass relationships"""
    results = exec_sparql(graph, 'hierarchy_depth')
    G = nx.DiGraph()
    for child, parent in results:
        G.add_edge(str(parent), str(child))
    if not G.nodes:
        return 0
    if not nx.is_directed_acyclic_graph(G):
        return -1
    return nx.dag_longest_path_length(G)


def exclude_instance_data(graph):
    """
    Find instance data and remove them from the graph.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        instances (rdflib.Graph): A RDF graph with the instance to remove.
        count (int): The number of instance subjects found.
    """

    instances = exec_sparql(graph, 'return_instances')
    subjects = {s for s, _, _ in instances}

    return instances, len(subjects)


def infer_subclass_relations(graph):
    """
    Construct sub-class relations recursively using the sub-class inference rule.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        graph (rdflib.Graph): The RDF graph, after inference applied.
    """
    
    log = f"\n## Simulate Inference\n\nInitial graph size: {len(graph)} triples.\nApplying Subclass inference rule iteratively...\n"
    while True:
        inferred_triples_result = exec_sparql(graph, 'subclass_inference_rule')
        if not inferred_triples_result:
            log += "No new subclass inferences to add. Inference complete.\n"
            break
        graph_size_before = len(graph)
        # Inferred triples came from no file, so they get a context of their own rather
        # than being folded into one that stands for an input. On a plain Graph (the
        # programmatic API passes one) there are no contexts and they just go in.
        if isinstance(graph, rdflib.Dataset):
            inferred = graph.graph(INFERRED_CONTEXT)
            for triple in inferred_triples_result:
                inferred.add(triple)
        else:
            graph += inferred_triples_result
        graph_size_after = len(graph)
        if graph_size_after == graph_size_before:
            log += "No new subclass inferences in this pass. Inference complete.\n"
            break
        else:
            log += f"Added {graph_size_after - graph_size_before} new triples. Continuing inference...\n"
    log += f"Final graph size after inference: {len(graph)} triples.\n"
    return graph, log
