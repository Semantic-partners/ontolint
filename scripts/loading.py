"""
Reading the inputs from disk: files and directories into an rdflib.Dataset, one named
graph per file, so which file a triple came from survives the load (#104).

The whole invocation is parsed once (parse_inputs), however the runs are batched, because a
run resolves references against the files it is not checking (#108) and those have to be
read too.
"""
import os

from rdflib.util import guess_format
import rdflib

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv, graphutil
    from scripts.terms import ontology_iris
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    import graphutil
    from terms import ontology_iris


def load_rdf_file(file):
    """
    Load RDF data from a file and return an RDFLib Graph.
    
    Args:
        file (str): Path to the RDF file.
    
    Returns:
        bool: True if the file was successfully loaded, False otherwise.
        graph (rdflib.Graph): The RDF graph object to parse into.
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


def _collect_files(paths):
    """
    Expand a list of file/directory paths into a flat list of individual file paths.

    Files named explicitly are always included. Files found by walking a directory are
    included only if rdflib recognises their extension as an RDF format, so that
    READMEs, configs etc. sitting alongside ontologies are skipped rather than failing.
    """
    result = []
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs.sort()  # in-place, so os.walk descends in a deterministic order
                for f in sorted(files):
                    if guess_format(f) is not None:
                        result.append(os.path.join(root, f))
        else:
            result.append(path)
    return result


def parse_inputs(paths):
    """
    Every input of this invocation, parsed once: {path: (success, graph, log)}.

    A run is checked against its own files, but resolves references against all of them, so
    the files outside a run still have to be read. Parsing here rather than inside each run
    means each file is read once however the runs are batched.
    """
    return {path: load_rdf_file(path) for path in _collect_files(paths)}


def load_rdf(paths, verbose: bool = False, parsed=None):
    """
    Load RDF files from files or directories.

    Args:
        paths (list): List of file and/or directory paths.
        verbose (bool): Logical flag for printing additional information during loading.
        parsed (dict): {path: (success, graph, log)} from parse_inputs(), so a file read
            once for the whole invocation is not read again per run.

    Returns:
        file_counter (int): Number of files successfully loaded.
        files_processed (list): List of successfully processed file names.
        graph (rdflib.Graph): The RDF graph object with all loaded data.
        log_results (str): Parsing result and status log.
        files_failed (list): List of file names that could not be loaded.
        ontology_sources (dict): {ontology IRI: [file: IRI, ...]}, recorded as each file is
            read. The files are merged into one graph here and that merge destroys the
            record of which file declared what — two identical owl:Ontology declarations
            become a single triple — so it has to be taken while they are still separate.
    """
    # Process all files
    file_counter = 0
    files_processed = []
    files_failed = []
    # One named graph per file, so which file a triple came from survives the load. A
    # merged Graph loses that — two identical owl:Ontology declarations become a single
    # triple — which is why ontology_sources had to be taken as each file was read. With
    # default_union the checks still see one graph: SPARQL, len() and triples() all read
    # the union, so a check cannot tell the difference.
    graph = rdflib.Dataset(default_union=True)
    log_results = ""
    ontology_sources = {}

    for file_path in _collect_files(paths):
        success, file_graph, log_msg = (parsed or {}).get(file_path) or load_rdf_file(file_path)
        if success:
            log_results += log_msg
            files_processed.append(file_path)
            file_counter += 1
            for iri in ontology_iris(file_graph):
                ontology_sources.setdefault(iri, []).append(dqv.file_iri(file_path))
            graph.graph(rdflib.URIRef(dqv.file_iri(file_path))).__iadd__(file_graph)
            graphutil.copy_namespaces(graph, file_graph)
        else:
            # Always report parse failures, regardless of verbosity.
            log_results += f"ERROR - {log_msg}"
            files_failed.append(file_path)

    return file_counter, files_processed, graph, log_results, files_failed, ontology_sources


def _parse_failure_log(files_failed):
    """Format a Markdown error block listing files that failed to parse."""
    log = f"\nERROR - {len(files_failed)} file(s) could not be parsed:\n"
    for f in files_failed:
        log += f"> - `{f}`\n"
    return log
