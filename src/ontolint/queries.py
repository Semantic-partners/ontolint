"""
The SPARQL every check runs: loaded once from sparql/, and run against a graph.

Queries are read at import time from the directory named by QA_SPARQL_DIR, defaulting to
the sparql/ directory shipped inside the package, into a dict keyed by filename stem.
"""
import os


# Create a dictionary with SPARQL queries, from files.
sparql_dir = os.getenv('QA_SPARQL_DIR', os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sparql'))


def load_sparql_queries(directory):
    """
    Create a dictionary of SPARQL queries, using file names as keys.
    """
    # Raised, never sys.exit: importing ontolint must not end the importing process.
    if not os.path.isdir(directory):
        raise FileNotFoundError(
            f"ontolint's SPARQL directory '{directory}' does not exist. It ships inside the "
            "package; if QA_SPARQL_DIR is set, it must name a directory of .sparql files.")
    queries = {}
    for filename in os.listdir(directory):
        if filename.endswith('.sparql'):
            var_name = os.path.splitext(filename)[0]
            with open(os.path.join(directory, filename), 'r', encoding='utf-8') as f:
                queries[var_name] = f.read()
    return queries


sparql_queries = load_sparql_queries(sparql_dir)


# Placeholder comment in a SPARQL query marking where the exclude-types filter is injected.
EXCLUDE_TYPES_PLACEHOLDER = "# {{EXCLUDE_TYPES}}"


def exec_sparql(graph, key, exclude_types=None):
    """
    Execute a SPARQL query from the input RDFLib graph, retrieving it from a global dictionary.

    If exclude_types is given, resources (bound to ?c) typed with any of those IRIs are
    filtered out. The query must contain the EXCLUDE_TYPES_PLACEHOLDER comment.
    """
    sparql_query = sparql_queries[key]
    if exclude_types:
        if EXCLUDE_TYPES_PLACEHOLDER not in sparql_query:
            raise ValueError(f"Query '{key}' does not support exclude-types")
        values = " ".join(f"<{t}>" for t in exclude_types)
        sparql_query = sparql_query.replace(
            EXCLUDE_TYPES_PLACEHOLDER,
            f"FILTER NOT EXISTS {{ VALUES ?excludedType {{ {values} }} ?c a ?excludedType . }}"
        )
    results = graph.query(sparql_query)
    if results.type == 'SELECT':
        return sorted(results, key=lambda row: tuple(str(value) for value in row))
    return results
