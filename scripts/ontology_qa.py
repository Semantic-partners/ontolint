#!/usr/bin/env python3
# Ontology Quality Assessment Script
# SEMANTIC PARTNERS LTD, 2026
# Authors: Simon Shapiro, Otello M Roscioni, John Placek, Pel Olson.

"""
A script to perform basic QA on a set of ontologies.
It loads RDF files, applies simple RDFS subclass inference, and runs SPARQL queries to
check for common ontology quality issues.
It reports any violations found in the ontology data.
"""
import rdflib
from rdflib.util import guess_format
import argparse
import sys
import os
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname
from datetime import datetime
from dataclasses import dataclass, field
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TypeAlias
import yaml
import networkx as nx

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv, graphutil
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    import graphutil

# Create a dictionary with SPARQL queries, from files.
sparql_dir = os.getenv('QA_SPARQL_DIR', os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'sparql'))

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


# An IRI, as an rdflib term or the string form of one. Some of these also accept a CURIE
# in ontolint's config prefixes (e.g. `rdf:PropositionForm`) or a `<namespace>*` wildcard,
# which are strings but not IRIs — hence the union rather than URIRef alone.
IRI: TypeAlias = str | rdflib.URIRef
# A vocabulary to resolve references against: a graph the caller already holds, or a file.
VocabularySource: TypeAlias = rdflib.Graph | str | os.PathLike


@dataclass
class CheckResult:
    name: str
    status: str                       # 'passed', 'failed' or 'skipped'
    count: int
    elements: str
    key: str = ''
    violations: list = field(default_factory=list)
    reason: str | None = None         # why a 'skipped' check could not be computed
    outcome: tuple | None = None      # (sentence, detail) a reporter renders; see decided()
    notes: list = field(default_factory=list)   # remarks that follow the sentence
    table: tuple | None = None        # (headers, rows) the check produced
    verbose_table: tuple | None = None          # the same, shown only on a verbose run

    @property
    def passed(self):
        """A check that could not be computed is not a failure, so it does not fail a build."""
        return self.status != 'failed'


@dataclass
class QAResult:
    profiling: dict
    checks: list
    elements: dict = field(default_factory=dict)
    logs: list = field(default_factory=list)
    datasets: list = field(default_factory=list)
    bnode_keys: dict = field(default_factory=dict)  # BNode -> canonical label, for skolemizing
    settings: list = field(default_factory=list)    # dqv.ConfigSetting: the configuration that ran
    config_file: str | None = None
    inference_log: str = ''                         # empty unless Config.inference was set

    def get(self, name: str):
        return next((c for c in self.checks if c.name == name), None)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self):
        return [c for c in self.checks if not c.passed]

@dataclass
class Config:
    """
    How a lint run is configured: the one description of a run, whichever front end asked
    for it. The CLI builds one from its arguments and `.rdf-lint.yml`; a caller of
    `ontolint.lint()` builds one directly. Each field names the `.rdf-lint.yml` key or CLI
    flag it corresponds to.

    per_file:       check each dataset on its own, so every violation is attributed to the
                    dataset it came from, rather than merging them into one graph
                    (`--per-file`).
    imports:        the vocabularies that define the terms the ontology refers to, so they
                    resolve with no network access (`imports.local`). Pass them as graphs
                    the caller already holds, or as paths to files.

                    Prefer a plain iterable — `imports=[schema_graph, owl_graph]`. Each
                    vocabulary is then registered under everything it defines (see
                    defined_namespaces), which is both less work than naming them and more
                    accurate than a caller picking one main namespace for a vocabulary
                    that spans several. A mapping of namespace or import IRI -> vocabulary
                    works too, where you want to say which is which.

                    The vocabularies bundled with ontolint are merged in underneath, and
                    an entry here overrides a bundled one for the same namespace.

                    A key is matched by iri_key(), which ignores one trailing '#' or '/',
                    so a vocabulary's owl:Ontology IRI and its namespace are the same
                    entry however either is written (`.../core`, `.../core#`, `.../core/`).
                    Terms are then looked up across every supplied vocabulary, so one
                    entry covers all the namespaces that graph defines. There is no need
                    to work out a vocabulary's "real" namespace before keying it.
    ignore_imports: namespaces and import IRIs that are trusted: never fetched, never
                    reported, never resolved (`imports.ignore`).
    exclude_types:  type IRIs, or CURIEs in ontolint's config prefixes, whose instances the
                    class checks skip (`exclude.types`).
    skip_object_of: predicate IRIs or `<namespace>*` wildcards whose objects the
                    undefined-terms check treats as links to documents rather than terms
                    (`undefined-terms.skip-object-of`). None keeps ontolint's defaults; an
                    empty sequence skips nothing.
    checks:         the checks to run, named as in `.rdf-lint.yml` (e.g.
                    "class-missing-label"); None runs all of them. Naming one that doesn't
                    exist is an error rather than a silent no-op. The CLI resolves its own
                    selection from the config file and passes the checklist directly.
    base_iri:       the namespace the DQV report mints its IRIs under (`--base-uri`). Give
                    each run its own when reports are collected into one graph.
    inference:      apply RDFS subclass inference before checking (`-i`/`--inference`).
    uri_parser:     how a namespace outside `imports` is fetched by the undefined-terms
                    check; the default parses the namespace IRI over the network. Pass a
                    callable that raises to forbid network access entirely.
    """

    per_file: bool = False
    imports: Mapping[IRI, VocabularySource] | Iterable[VocabularySource] = field(default_factory=dict)
    ignore_imports: Sequence[IRI] = ()
    exclude_types: Sequence[IRI] = ()
    skip_object_of: Sequence[IRI] | None = None
    checks: Sequence[str] | None = None
    base_iri: IRI | None = None
    inference: bool = False
    uri_parser: Callable[[str], rdflib.Graph] | None = None


def records_key(check):
    """Key under which a check stores its list of dqv.Violation records in its violations dict."""
    return (check, 'records')


def skipped_key(check):
    """Key under which a check records that it could not be computed, and why."""
    return (check, 'skipped')


def outcome_key(check):
    """Key under which a check records what it decided, for a reporter to render."""
    return (check, 'outcome')


# How a check's elements follow its sentence, when it has any.
AS_LIST = 'list'      # one per line, under the sentence
AS_TABLE = 'table'    # the check built a Markdown table


def notes_key(check):
    """Key under which a check records remarks that follow its sentence."""
    return (check, 'notes')


def table_key(check, verbose_only=False):
    """Key under which a check records a table of its own, for a reporter to lay out."""
    return (check, 'verbose-table' if verbose_only else 'table')


def decided(violations, check, sentence, detail=None):
    """
    Record what a check decided, as a sentence and how its elements follow it.

    The sentence says what was found; the reporter lays it out. A check that writes its own
    report cannot be rendered any other way, which is what #101 is about.
    """
    violations[outcome_key(check)] = (sentence, detail)


def note(violations, check, line):
    """Add a remark after a check's sentence — a caveat on what it could see."""
    violations.setdefault(notes_key(check), []).append(line)


def tabulate(violations, check, headers, rows, verbose_only=False):
    """
    Record a table a check produced: its column headings and its rows of cells.

    The rows are data, not Markdown, so a reporter lays them out — including the ones only
    a verbose run shows, which are a second query's worth of detail rather than a finding.
    """
    violations[table_key(check, verbose_only)] = (
        tuple(headers), [tuple(str(cell) for cell in row) for row in rows])


# Why a check could not be computed. Either of these, or the key of a check whose condition
# this one needs (see dqv.DQV_DEPENDENCIES) — then the report names that dependency.
EMPTY_POPULATION = 'empty-population'
SOURCES_NOT_RECORDED = 'sources-not-recorded'


def not_assessed(violations, check, reason):
    """Record that a check could not be computed. A count of 0 would read as a clean result."""
    violations[skipped_key(check)] = reason


NOT_ASSESSED_MESSAGES = {
    EMPTY_POPULATION: "nothing of the kind it measures is present",
    SOURCES_NOT_RECORDED: "the graph does not record which input each triple came from",
}


def not_assessed_message(check, by_key):
    """
    Why a check could not be computed, in words a reader of the report can act on.

    A reason naming another check is a dependency, so the message names that check and what
    became of it: a skip caused by a failure elsewhere should not read like the benign kind.
    """
    if check.reason in NOT_ASSESSED_MESSAGES:
        return f"not assessed: {NOT_ASSESSED_MESSAGES[check.reason]}"
    required = by_key.get(check.reason)
    if required is None:
        return f"not assessed: requires {check.reason}"
    return f"not assessed: requires '{required.name}', which {required.status}"


def source_iris(in_metrics):
    """
    One IRI per processed source, to name it in a violation.

    'sourceIRIs' is set when the caller named its sources itself (the programmatic API,
    whose graphs are not files); otherwise each entry of 'filesProcessed' is a path and
    gets a file: IRI.
    """
    named = in_metrics.get('sourceIRIs') or []
    return [str(iri) for iri in named] or [dqv.file_iri(f) for f in in_metrics.get('filesProcessed', [])]

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

def get_namespace(uri):
    """Extract namespace from a URIRef."""
    if '#' in uri:
        base = uri.rsplit('#', 1)[0]
        if len(base) >= 8:
            return base + '#'
    elif '/' in uri:
        base = uri.rsplit('/', 1)[0]
        if len(base) >= 8:
            return base + '/'
    return uri  # fallback

# ── Bundled vocabularies ─────────────────────────────────────────────────────
# Standard vocabularies shipped with ontolint (vocabularies/, see its README.md). Each is
# added to imports.local, so their namespaces and owl:imports resolve offline and their
# terms are validated by the undefined-terms check.
#
# The DCAT catalog is the single starting point for discovery: which vocabularies are
# bundled, their namespaces, and where each file is (its dcat:downloadURL, resolved
# relative to the catalog). Found relative to this module so the CLI and the composite
# action work from any working directory.
VOCAB_CATALOG = Path(__file__).resolve().parent.parent / 'vocabularies' / 'catalog.ttl'


def iri_key(iri):
    """
    The form imports.ignore / imports.local entries are matched by: the IRI without one
    trailing '#' or '/'. So an ontology IRI (…/skos/core) and its namespace (…/skos/core#)
    match the same entry, whichever form was configured.
    """
    iri = str(iri)
    return iri[:-1] if iri.endswith(('#', '/')) else iri


@lru_cache(maxsize=1)
def bundled_vocabularies():
    """
    {namespace: absolute file path} for every vocabulary in the VOCAB_CATALOG DCAT catalog:
    each dcat:Dataset gives its namespace (vann:preferredNamespaceUri) and a
    dcat:Distribution whose dcat:downloadURL is the file, relative to the catalog.
    """
    catalog = rdflib.Graph().parse(VOCAB_CATALOG, format='turtle')
    vocabularies = {}
    for dataset in sorted(catalog.subjects(rdflib.RDF.type, rdflib.DCAT.Dataset)):
        namespace = catalog.value(dataset, rdflib.VANN.preferredNamespaceUri)
        url = catalog.value(catalog.value(dataset, rdflib.DCAT.distribution), rdflib.DCAT.downloadURL)
        if namespace is None or url is None:
            raise ValueError(f"{dataset} in {VOCAB_CATALOG} needs vann:preferredNamespaceUri "
                             "and a dcat:distribution with a dcat:downloadURL")
        vocabularies[str(namespace)] = str(Path(url2pathname(urlparse(str(url)).path)).resolve())
    return vocabularies


@lru_cache(maxsize=1)
def bundled_datasets():
    """{namespace: catalog dcat:Dataset IRI} for every vocabulary in VOCAB_CATALOG."""
    catalog = rdflib.Graph().parse(VOCAB_CATALOG, format='turtle')
    return {str(catalog.value(d, rdflib.VANN.preferredNamespaceUri)): str(d)
            for d in catalog.subjects(rdflib.RDF.type, rdflib.DCAT.Dataset)}


def ontology_iris(graph):
    """The owl:Ontology IRIs a graph declares, sorted."""
    return sorted(str(o) for o in graph.subjects(rdflib.RDF.type, rdflib.OWL.Ontology)
                  if isinstance(o, rdflib.URIRef))


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


def declared_ontology_sources(sources):
    """
    {ontology IRI: [source IRIs]} from an iterable of (source IRI, graph) pairs.

    The CLI builds the same mapping as it loads (see load_rdf), because it merges the files
    into one graph and that merge destroys the record: the union of two identical
    declarations is a single triple.
    """
    declared = {}
    for source, graph in sources:
        for iri in ontology_iris(graph):
            declared.setdefault(iri, []).append(str(source))
    return declared


def duplicate_ontology_iris(ontology_sources):
    """
    The entries of an {ontology IRI: [source IRIs]} mapping that more than one input declared.

    Ontolint's rule is one file, one ontology, so an IRI declared by two inputs means two
    files claim to be the same ontology. One definition of that, for both front ends.
    """
    return {iri: s for iri, s in (ontology_sources or {}).items() if len(s) > 1}


def defined_namespaces(graph):
    """
    Every namespace a vocabulary graph defines terms in: the owl:Ontology IRIs it declares,
    and the namespace of each of its subjects.

    This is what an unkeyed entry in Config.imports is registered under, so a caller can
    hand over a vocabulary without working out which namespace to file it against — and a
    vocabulary spanning several is registered for all of them, not a guessed main one.
    """
    ontologies = set(ontology_iris(graph))
    namespaces = set(ontologies)
    for subject in graph.subjects(unique=True):
        # The ontology IRI's own namespace is skipped: <.../core> sits in <.../>, and
        # claiming that would register this vocabulary for every sibling beside it.
        if isinstance(subject, rdflib.URIRef) and str(subject) not in ontologies:
            namespace = get_namespace(str(subject))
            if namespace:
                namespaces.add(namespace)
    return namespaces


def local_imports_from(imports):
    """
    Config.imports as the {namespace: vocabulary} mapping the checks take.

    A mapping is used as given. An unkeyed iterable of vocabularies is keyed by what each
    one defines (see defined_namespaces); a path is parsed to find out.
    """
    if not imports:
        return {}
    if isinstance(imports, Mapping):
        return dict(imports)
    keyed = {}
    for vocabulary in imports:
        graph = vocabulary if isinstance(vocabulary, rdflib.Graph) else _parse_local(vocabulary)
        for namespace in defined_namespaces(graph):
            keyed[namespace] = graph
    return keyed


def merge_local_imports(local_imports=None):
    """
    Bundled vocabularies plus the project's imports.local, keyed by iri_key(); the project wins.

    A value is a file path, or an already-loaded rdflib.Graph when the caller supplied one
    through the programmatic API (see ontolint.Config.imports).
    """
    merged = {iri_key(ns): path for ns, path in bundled_vocabularies().items()}
    merged.update({iri_key(k): v for k, v in (local_imports or {}).items()})
    return merged


def _is_bundled(source):
    """Whether a file is one of the catalogued vocabularies (by the catalog, not by directory)."""
    if isinstance(source, rdflib.Graph):
        return False
    return str(Path(source).resolve()) in bundled_vocabularies().values()


@lru_cache(maxsize=None)
def _parse_bundled(path):
    """Parse a bundled vocabulary once per process (treated as read-only)."""
    return rdflib.Graph().parse(path)


def _parse_local(source):
    """The graph for an imports.local entry: a caller-supplied graph, or a file to parse."""
    if isinstance(source, rdflib.Graph):
        return source
    return _parse_bundled(source) if _is_bundled(source) else rdflib.Graph().parse(source)


# rdf:_1, rdf:_2, ... (container membership properties) are defined by RDF but can't be listed.
_CONTAINER_MEMBERSHIP = re.compile(re.escape(str(rdflib.RDF)) + r'_[1-9][0-9]*')


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
    if metrics['HierarchyDepth'] == -1:
        HierarchyDepth = "N/A"
    else:
        HierarchyDepth = metrics['HierarchyDepth']
    log = "\n## Profiling Metrics\n"
    log += "| Name | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape "
    log += "| Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used | Ontologies Imported "
    log += "| Hierarchy depth | Ave branching factor | Cardinality restrictions |\n"
    log += "|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|\n"
    log += f"| {name} | {metrics['triples']} | {metrics['classCount']} | {metrics['propertyCount']} | {metrics['nodeShapes']} | {metrics['propertyShapes']} "
    log += f"| {metrics['classesInNodeShapes']} | {metrics['propertiesInPropertyShapes']} | {metrics['deprecatedClasses']} | {metrics['deprecatedProperties']} "
    log += f"| {metrics['vocabulariesUsed']} | {metrics['imports']} | {HierarchyDepth} | {normalise(metrics['aveBranchFactor'], 1)} | {metrics['CardinalityRestrictions']} |\n"
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
    log += "| Name | Ontology not declared | Multiple ontologies in one file | Ontology without description | Unresolvable Imports | Undefined Terms | Class without label | Property without label | NodeShapes without label | PropertyShape without label "
    log += "| Class without description | Property without description | NodeShapes without description | PropertyShape without description "
    log += "| Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes "
    log += "| Property without domain | Property without range "
    log += "| Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |\n"
    log += "|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|\n"
    log += f"| {name} | {normalise_if_executed_len(metrics, checks, 'ontologyNotDeclared', 'filesProcessed')} "
    log += f"| {normalise_if_executed_len(metrics, checks, 'multipleOntologies', 'filesProcessed')} "
    log += f"| {normalise_if_executed_len(metrics, checks, 'ontologyDescription', 'filesProcessed')} "
    log += f"| {print_if_executed(metrics, checks, 'unresolvedImports')} "
    log += f"| {print_if_executed(metrics, checks, 'undefinedTerms')} "
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

def build_ctrf_report(result: QAResult, date_time_provider=datetime.now):
    """
    A QAResult as a CTRF (Common Test Result Format) report: one test case per executed
    check, with the run's summary. Returns the report; writing it is write_ctrf_report's
    job, so the projection can be built and inspected without touching the filesystem.

    date_time_provider supplies the report's timestamp. It is injected so a caller can fix
    it — without that the projection is not a pure function of the QAResult, and two
    reports built over the same result differ. It is also the only way to fix it: a CTRF
    report written by the CLI carries the wall clock and is not reproducible.
    """
    counts = {'passed': 0, 'failed': 0, 'skipped': 0}
    by_key = {c.key: c for c in result.checks}
    test_cases = []

    for check in result.checks:
        test_case = {
            "name": check.name,
            "status": check.status
        }
        if check.status == 'failed':
            test_case["failure"] = {
                "violations": check.count,
                "elements": check.elements
            }
        elif check.status == 'skipped':
            # Not a pass: the check could not be computed, so the 0 means nothing.
            test_case["message"] = not_assessed_message(check, by_key)
        counts[check.status] += 1
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
                "passed": counts['passed'],
                "failed": counts['failed'],
                "skipped": counts['skipped']
            },
            "tests": test_cases,
            "filesProcessed": result.profiling.get("filesProcessed", []),
            "timestamp": date_time_provider().strftime("%Y-%m-%d %H:%M:%S")
        }
    }
    return ctrf_report


def write_ctrf_report(ctrf_report, file_path, filename):
    """Write a CTRF report (see build_ctrf_report) to a file. Returns the log line."""
    os.makedirs(file_path, exist_ok=True)
    # Fallback CTRF filename
    if not filename:
        filename = f'ontology-qa-report-{os.getpid()}.json'
    output_file = os.path.join(file_path, filename)
    with open(output_file, 'w') as f:
        json.dump(ctrf_report, f, indent=2)

    return f"\nCTRF report written to: {output_file}\n"

def print_profiling_metrics(metrics, elements, verbose):
    log  = "\n## Profiling Details\n\n"
    log += f"RDF/OWL classes: {metrics['classCount']}\n"
    log += f"RDF/OWL properties: {metrics['propertyCount']}\n"
    log += f"Instance data: {metrics['instances']}\n"
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
    
    fa = metrics.get('fetchActivity', {})
    total = len(fa.get('local', {})) + len(fa.get('fetched', {})) + len(fa.get('failed', []))
    if total > 0:
        log += f"\nRemote namespace resolution: {total} checked\n"
        for ns, path in sorted(fa.get('local', {}).items()):
            log += f"  - {chr(9989)} `{ns}` — {_describe_local(path)}\n"
        for ns, count in sorted(fa.get('fetched', {}).items()):
            log += f"  - {chr(9989)} `{ns}` — fetched ({count} subject(s))\n"
        for ns in fa.get('failed', []):
            log += f"  - {chr(10060)} `{ns}` — fetch failed\n"
        log += "\n"

    if metrics['HierarchyDepth'] == -1:
        log += "Hierarchy depth: N/A\n"
        log += "WARNING - The ontology contains cycles in the subclass hierarchy, so the hierarchy depth cannot be computed.\n"
    else:
        log += f"Hierarchy depth: {metrics['HierarchyDepth']}\n"
    log += f"Average branching factor: {normalise(metrics['aveBranchFactor'], 1)}\n"
    log += f"Number of cardinality restrictions: {metrics['CardinalityRestrictions']}\n"
    return log

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

# Where inferred triples live in a Dataset: not a file, so not one of the file contexts.
INFERRED_CONTEXT = rdflib.URIRef("urn:ontolint:inferred")


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
    metrics['ontologyURI'] = [ ]
    c, log = c + 1, ''
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
    if metrics[check] == num_files:
        log += "VIOLATION - No `owl:Ontology` declaration found.\n"
        violations[check] = "**All** processed files missing ontology declaration."
        violations[records_key(check)] = [
            dqv.Violation(iri, comment="no owl:Ontology declaration")
            for iri in source_iris(in_metrics)
        ] or [dqv.Violation(comment="no owl:Ontology declaration")]
    
    elif metrics[check] > 0 and metrics[check] < num_files:
        if metrics[check] == 1:
            log += "VIOLATION - 1 ontology without `owl:Ontology` declaration.\n"
        else:
            log += f"VIOLATION - {metrics[check]} ontologies without `owl:Ontology` declaration.\n"
        violations[check] = "**Some** processed files missing ontology declaration.<br> Check files individually."
        violations[records_key(check)] = [dqv.Violation(comment=f"{metrics[check]} processed file(s) have no owl:Ontology declaration; check files individually")]
    
    else:
        if num_uri == 1:
            log += "PASS - Found 1 ontology with `owl:Ontology` declaration.\n"
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
    
    return metrics, violations, log, c, status

def check_one_ontology_per_file(in_metrics, graph, name, check, c, status, verbose):
    """
    QA test verifying that no single input declares more than one `owl:Ontology`.

    Ontolint's rule is one file, one ontology. `check_owl_declaration` covers "no less";
    this covers "no more". It is judged per source rather than over the merged graph,
    where several declarations are normal and correct — one per file.

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
    c, log = c + 1, ''
    declared = ontologies_by_source(graph, in_metrics)
    offenders = {} if declared is None else {
        source: iris for source, iris in sorted(declared.items()) if len(iris) > 1}
    metrics[check] = len(offenders) # 'multipleOntologies'
    violations[check] = ""

    if declared is None:
        log += "WARNING - Several files merged into one graph with no record of their sources, invalid metric.\n"
        not_assessed(violations, check, SOURCES_NOT_RECORDED)
    elif not offenders:
        log += "PASS - No violations found.\n"
    else:
        log += f"VIOLATION - Found {metrics[check]} file(s) declaring more than one `owl:Ontology`:\n - "
        status += 1
        string = violation_formatting(
            [f"{source} declares {len(iris)}: {', '.join(iris)}" for source, iris in offenders.items()])
        violations[check] = string
        violations[records_key(check)] = [
            dqv.Violation(rdflib.URIRef(source),
                          comment=f"declares {len(iris)} ontologies; one file, one ontology",
                          related=[rdflib.URIRef(iri) for iri in iris])
            for source, iris in offenders.items()
        ]
        log += string.replace(",<br> ", "\n - ") + "\n"

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
    c, log = c + 1, ''

    if in_metrics['ontologyNotDeclared'] == num_files:
        log += "WARNING - No ontology declared, invalid metric.\n"
        not_assessed(violations, check, 'ontologyNotDeclared')
        metrics[check] = 1 # 'ontologyDescription': no
        violations[check] = "No ontology declared"
        violations[records_key(check)] = [dqv.Violation(comment="no ontology declared")]
    else:
        results = exec_sparql(graph, 'owl_no_description')
        if not results:
            log += "PASS - All declared ontologies have a description.\n"
            metrics[check] = 0 # yes
            violations[check] = ""
            if verbose:
                log_results = exec_sparql(graph, 'owl_description')
                log += "\n**Ontology + Description:**\n"
                for row in log_results:
                    log += f" - {row.ont}\n   *{row.comment}*\n"
                
        else:
            metrics[check] = len(results) #  violations
            status += 1
            string = violation_formatting([row.ont for row in results])
            violations[records_key(check)] = [dqv.Violation(row.ont) for row in results]
            violations[check] = string
            log += f"VIOLATION - Found {metrics[check]} ontologies without description:\n - "
            log += string.replace(",<br> ", "\n - ")
    
    return metrics, violations, log, c, status

def check_class_missing_label(in_metrics, graph, name, check, c, status, verbose, exclude_types=None):
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
        exclude_types (list): Type IRIs whose instances are skipped by this check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = c + 1, ''
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
    c, log = c + 1, ''
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
    c, log = c + 1, ''
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
    c, log = c + 1, ''
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
    
    return metrics, violations, log, c, status

def check_class_missing_comment(in_metrics, graph, name, check, c, status, verbose, exclude_types=None):
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
        exclude_types (list): Type IRIs whose instances are skipped by this check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = c + 1, ''
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
    c, log = c + 1, ''
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
    c, log = c + 1, ''
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
    c, log = c + 1, ''
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
    
    return metrics, violations, log, c, status

def check_class_same_label(in_metrics, graph, name, check, c, status, verbose, exclude_types=None):
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
        exclude_types (list): Type IRIs whose instances are skipped by this check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = c + 1, ''
    results = exec_sparql(graph, 'class_same_label', exclude_types)
    metrics[check] = 0 # 'nonUniqueClassLabels'
    violations[check] = ""
    
    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - No classes share the same label.\n"

    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} labels shared by multiple classes.\n"
        status += 1
        string = ""
        records = []
        log += "| Label | Label Property | Classes |\n|--|--|--|\n"
        for row in results:
            members = concat_members(row.classes)
            log += f"| {row.label} | {row.labelProperty} | {members} |\n"
            string += f"\"{row.label}, {row.labelProperty}\": {members};<br> "
            records.extend(_same_label_records(row.label, row.labelProperty, row.classes))
        
        string = string.removesuffix(";<br> ")
        violations[check] = string
        violations[records_key(check)] = records
    
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
    c, log = c + 1, ''
    results = exec_sparql(graph, 'property_same_label')
    metrics[check] = 0 # 'nonUniquePropertyLabels'
    violations[check] = ""

    if not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - No property share the same label.\n"

    elif int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} labels shared by multiple properties.\n"
        status += 1
        string = ""
        records = []
        log += "| Label | Label Property | Properties |\n|--|--|--|\n"
        for row in results:
            members = concat_members(row.properties)
            log += f"| {row.label} | {row.labelProperty} | {members} |\n"
            string += f"\"{row.label}, {row.labelProperty}\": {members};<br> "
            records.extend(_same_label_records(row.label, row.labelProperty, row.properties))
        string = string.removesuffix(";<br> ")
        violations[check] = string
        violations[records_key(check)] = records
    
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
    c, log = c + 1, ''
    results = exec_sparql(graph, 'node_shape_same_label')
    metrics[check] = 0 # 'nonUniqueNSLabels'
    violations[check] = ""

    if not results and int(in_metrics['nodeShapes']) > 0:
        log += "PASS - No NodeShape share the same label.\n"

    elif int(in_metrics['nodeShapes']) == 0:
        log += "WARNING - No NodeShape defined, invalid metric.\n"
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} labels shared by multiple NodeShapes.\n"
        status += 1
        string = ""
        records = []
        log += "| Label | Label Property | NodeShapes |\n|--|--|--|\n"
        for row in results:
            members = concat_members(row.nsList)
            log += f"| {row.label} | {row.labelProperty} | {members} |\n"
            string += f"\"{row.label}, {row.labelProperty}\": {members};<br> "
            records.extend(_same_label_records(row.label, row.labelProperty, row.nsList))
        
        string = string.removesuffix(";<br> ")
        violations[check] = string
        violations[records_key(check)] = records
    
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
    c, log = c + 1, ''
    results = exec_sparql(graph, 'property_shape_same_label')
    metrics[check] = 0 # 'nonUniquePSLabels'
    violations[check] = ""

    if not results and int(in_metrics['propertyShapes']) > 0:
       log += "PASS - No PropertyShape share the same label.\n"

    elif int(in_metrics['propertyShapes']) == 0:
        log += "WARNING - No PropertyShapes defined, invalid metric.\n"
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} labels shared by multiple PropertyShapes.\n"
        status += 1
        string = ""
        records = []
        log += "| Label | Label Property | PropertyShapes |\n|--|--|--|\n"
        for row in results:
            members = concat_members(row.psList)
            log += f"| {row.label} | {row.labelProperty} | {members} |\n"
            string += f"\"{row.label}, {row.labelProperty}\": {members};<br> "
            records.extend(_same_label_records(row.label, row.labelProperty, row.psList))
        
        string = string.removesuffix(";<br> ")
        violations[check] = string
        violations[records_key(check)] = records
    
    return metrics, violations, log, c, status

def check_isolated_classes(in_metrics, graph, name, check, c, status, verbose, exclude_types=None):
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
        exclude_types (list): Type IRIs whose instances are skipped by this check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = c + 1, ''
    results = exec_sparql(graph, 'isolated_classes', exclude_types)
    metrics[check] = 0 # 'isolatedClasses'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - All classes are connected to another class through a subclass or property relation.\n"
    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} isolated classes:\n - "
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[records_key(check)] = [dqv.Violation(row.c) for row in results]
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    return metrics, violations, log, c, status

def check_property_missing_domain_range(in_metrics, graph, _, check, c, status, verbose):
    """
    QA test checking properties for rdfs:domain or rdfs:range declaration.
    
    Args:
        in_metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        _ (str): Not used. The reporter titles the check (see MARKDOWN_HEADINGS)
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
        c, log = c + 1, ''
        dCount = []
        rCount = []

        # Print the output of the check only once.
        if not results and int(in_metrics['propertyCount']) > 0:
            log += "INFO - All properties have domain and range defined.\n"
            if verbose: log += "\n"

        elif int(in_metrics['propertyCount']) == 0:
            log += "WARNING - No properties defined, invalid metric.\n"
            not_assessed(violations, check, EMPTY_POPULATION)

        elif results:
            metrics['missingDomainRange'] = len(results)
            log += f"WARNING - Found {metrics['missingDomainRange']} properties without `rdfs:domain` or `rdfs:range` declaration:\n\n"
            if not verbose: log += "| Property | Domain | Range |\n|--|--|--|\n"
            status += 1
            for row in results:
                predicate = row.property
                if row.domain:
                    domain = term_text(row.domain)
                else:
                    domain = 'None'
                    dCount.append(predicate)
                if row.range:
                    range = term_text(row.range)
                else:
                    range = 'None'
                    rCount.append(predicate)
                if not verbose: log += f"| {predicate} | {domain} | {range} |\n"

            if not verbose: log  += "\n"

        # If verbose, print a table with domain and range for all properties.
        if verbose and int(in_metrics['propertyCount']) > 0:
            # Show all properties in the results.
            results = exec_sparql(graph, 'dr_property')
            log += "| Property | Domain | Range |\n|--|--|--|\n"
            for row in results:
                if row.domain:
                    domain = term_text(row.domain)
                else:
                    domain = 'None'
                
                if row.range:
                    range = term_text(row.range)
                else:
                    range = 'None'
                
                log += f"| {term_text(row.property)} | {domain} | {range} |\n"
            
            log  += "\n"
        
        # Control which check triggered the first execution.
        if check == 'missingDomain':
            # remove duplicates from dCount list.
            dCount = list(set(dCount))
            dCount.sort()
            metrics[check] = len(dCount)
            if metrics[check] > 0:
                string = violation_formatting(dCount)
                violations[records_key(check)] = [dqv.Violation(p) for p in dCount]
                violations[check] = string
                string = string.replace(',<br> ', '\n - ')
                log += f"VIOLATION - Found {metrics[check]} properties without `rdfs:domain` declaration:\n - {string}\n"
            else:
                violations[check] = ""
                if int(in_metrics['propertyCount']) > 0: log += "PASS - All properties have domain defined.\n"

        elif check == 'missingRange':
            # remove duplicates from rCount list.
            rCount = list(set(rCount))
            rCount.sort()
            metrics[check]  = len(rCount)
            if metrics[check] > 0:
                string = violation_formatting(rCount)
                violations[records_key(check)] = [dqv.Violation(p) for p in rCount]
                violations[check] = string
                string = string.replace(',<br> ', '\n - ')
                log += f"VIOLATION - Found {metrics[check]} properties without `rdfs:range` declaration:\n - {string}\n"
            else:
                violations[check] = ""
                if int(in_metrics['propertyCount']) > 0: log += "PASS - All properties have range defined.\n"
        

    else:
        # This condition is satisfied only for range violations.
        # It relies on the fact that the array test_checklist is ordered,
        # with missingDomain defined before missingRange.
        c, log = c + 1, ''
        rCount = []

        # Analyse the results
        if results:
            for row in results:
                predicate = row.property
                if not row.range:
                    rCount.append(predicate)
        
        # Report
        rCount = list(set(rCount))
        rCount.sort()
        metrics[check]  = len(rCount)
        if int(in_metrics['propertyCount']) == 0:
            violations[check] = ""
            log += "WARNING - No properties defined, invalid metric.\n"
            not_assessed(violations, check, EMPTY_POPULATION)
        elif metrics[check] > 0:
            string = violation_formatting(rCount)
            violations[records_key(check)] = [dqv.Violation(p) for p in rCount]
            violations[check] = string
            string = string.replace(',<br> ', '\n - ')
            log += f"VIOLATION - Found {metrics[check]} properties without `rdfs:range` declaration:\n - {string}\n"
        else:
            violations[check] = ""
            log += "PASS - All properties have range defined.\n"
        

    return metrics, violations, log, c, status

def _term_from_string(value):
    """An absolute IRI string as a URIRef; anything else is an rdflib blank-node id."""
    return rdflib.URIRef(value) if ':' in value else rdflib.BNode(value)


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

def term_text(term):
    """
    A term as it appears in a text report.

    A blank node's rdflib identifier is invented at parse time and differs on every run, so
    printing it makes the report vary run to run while telling a reader nothing they can
    act on or look up. Anything that needs stable identity has it in the DQV report, where
    blank nodes are skolemized under the report's base.
    """
    return "[anonymous]" if isinstance(term, rdflib.BNode) else term


def concat_members(value):
    """
    The members of a GROUP_CONCAT cell, sorted, as text.

    GROUP_CONCAT has no defined order, so the same inputs render the members of a group in
    a different order from run to run. exec_sparql() sorts the rows; this sorts within one.
    The DQV records already sort their own copy (see _same_label_records); this is for the
    text reports, which carry the concatenation as it came back.
    """
    return ", ".join(sorted(m.strip() for m in str(value).split(",") if m.strip()))


def violation_formatting(array, unique=False):
    """
    Format a string of elements into a markdown list.
    
    Elements are always sorted. They arrive in SPARQL result order, which varies between
    runs, so without this the same inputs produce a different report each time: diffs are
    unreviewable and the output can't be compared against an expected one.

    Args:
        array (list): List of elements to format.
        unique (bool): Logical flag to also remove duplicates.
    
    Returns:
        formatted_string (str): String formatted as a markdown list.
    """
    if unique:
        array = set(array)
    # Rendered before sorting: sorting blank nodes by their invented identifiers would be
    # as unstable as printing them.
    array = sorted((term_text(element) for element in array), key=str)

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
    c, log = c + 1, ''
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
        records = []
        for row in results:
            declared = concat_members(row.declaredAs)
            log += f"| {row.iri} | {declared} |\n"
            iri.append(row.iri)
            records.append(dqv.Violation(row.iri, comment=f"declared as {declared}"))

        violations[check] = violation_formatting(iri)
        violations[records_key(check)] = records
    
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
    c, log = c + 1, ''
    results = exec_sparql(graph, 'subclass_cycles')
    metrics[check] = 0 # 'subclassCycles'
    violations[check] = ""

    if not results and int(in_metrics['classCount']) > 0:
        log += "PASS - No violations found.\n"

    elif int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} classes involved in subclass cycles:\n - "
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[records_key(check)] = [dqv.Violation(row.c) for row in results]
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    return metrics, violations, log, c, status

def check_untyped_class(in_metrics, graph, name, check, c, status, verbose, exclude_types=None):
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
        exclude_types (list): Type IRIs whose instances are skipped by this check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        log (str): Result of the QA test, formatted in markdown.
        c (int): Incremented counter, tracking QA tests selected.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    c, log = c + 1, ''
    results = exec_sparql(graph, 'untyped_class', exclude_types)
    metrics[check] = 0 # 'untypedClasses'
    violations[check] = ""
    num_files = len(in_metrics['filesProcessed'])

    if not ontology_iris(graph):
        # Without a declared namespace, a term of the ontology's own cannot be told from an
        # external vocabulary's, so the query reports nothing. PASS would imply it had looked.
        log += "WARNING - Ontology namespace undefined, invalid metric. No way to confirm if a class is defined in the ontology or an external vocabulary.\n"
        not_assessed(violations, check, 'ontologyNotDeclared')

    elif not results and int(in_metrics['classCount']) > 0:
        log += "PASS - No violations found.\n"

    elif not results and int(in_metrics['classCount']) == 0:
        log += "WARNING - No classes defined, invalid metric.\n"
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} classes without `owl:Class` or `rdfs:Class` declaration:\n - "
        status += 1
        string = violation_formatting([row.c for row in results])
        violations[records_key(check)] = [dqv.Violation(row.c) for row in results]
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"

    if ('ontologyNotDeclared' in in_metrics
            and 0 < in_metrics['ontologyNotDeclared'] < num_files and metrics[check] > 0):
        log += "WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.\n"
    
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
    c, log = c + 1, ''
    results = exec_sparql(graph, 'untyped_property')
    metrics[check] = 0 # 'untypedProperties'
    violations[check] = ""
    num_files = len(in_metrics['filesProcessed'])

    if not ontology_iris(graph):
        # Without a declared namespace, a term of the ontology's own cannot be told from an
        # external vocabulary's, so the query reports nothing. PASS would imply it had looked.
        log += "WARNING - Ontology namespace undefined, invalid metric. No way to confirm if a property is defined in the ontology or an external vocabulary.\n"
        not_assessed(violations, check, 'ontologyNotDeclared')

    elif not results and int(in_metrics['propertyCount']) > 0:
        log += "PASS - No violations found.\n"
              
    elif not results and int(in_metrics['propertyCount']) == 0:
        log += "WARNING - No properties defined, invalid metric.\n"
        not_assessed(violations, check, EMPTY_POPULATION)

    elif results:
        metrics[check] = len(results)
        log += f"VIOLATION - Found {metrics[check]} property without `rdf:Property`, `owl:ObjectProperty`, or `owl:DatatypeProperty` declaration:\n"
        status += 1
        string = violation_formatting([row.property for row in results])
        violations[records_key(check)] = [dqv.Violation(row.property) for row in results]
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    if ('ontologyNotDeclared' in in_metrics
            and 0 < in_metrics['ontologyNotDeclared'] < num_files and metrics[check] > 0):
        log += "WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.\n"
    
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
    c, log = c + 1, ''
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
        violations[records_key(check)] = [dqv.Violation(row.resource) for row in results]
        violations[check] = string
        log += string.replace(",<br> ", "\n - ") + "\n"
    
    if ontology_check:
        if (in_metrics['ontologyNotDeclared'] > 0 and num_files == 1) or in_metrics['ontologyNotDeclared'] == num_files:
            log += "WARNING - Ontology namespace undefined. The reported violations may be incorrect.\n"
        elif in_metrics['ontologyNotDeclared'] > 0 and in_metrics['ontologyNotDeclared'] < num_files and metrics[check] > 0:
            log += "WARNING - Some ontology namespaces are not defined. The reported violations may be incorrect.\n"
    else:
        log += "WARNING - Ontology namespace not checked. The reported violations may be incorrect.\n"
    
    return metrics, violations, log, c, status

def check_owl_imports(in_metrics, graph, name, check, c, status, verbose, ignore_imports=None, local_imports=None):
    """
    QA test verifying that all owl:imports URLs resolve and contain triples.

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
    c, log = c + 1, ''
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
            log += "WARNING - All owl:imports URLs are ignored by configuration.\n"
        else:
            log += "WARNING - No owl:imports statements found.\n"
        return metrics, violations, log, c, status

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
        log += f"> NOTE - {len(local_subs)} import(s) resolved from local file(s):\n"
        for url, path in local_subs:
            log += f">   `{url}` → {_describe_local(path)}\n"

    if not failed_imports:
        log += f"PASS - All {len(import_urls)} import(s) resolved and contain triples.\n"
    else:
        metrics[check] = len(failed_imports)
        status += 1
        string = violation_formatting(failed_imports)
        violations[check] = string
        violations[records_key(check)] = [
            dqv.Violation(url, comment="import could not be resolved or is empty", related=[ontology])
            for ontology, url in failed_pairs
        ]
        log += f"VIOLATION - Found {metrics[check]} unresolvable or empty import(s):\n - "
        log += string.replace(",<br> ", "\n - ") + "\n"

    def _check(failed):
        if failed in failed_imports:
            return chr(10060) # X
        else:
            return chr(9989)  # V

    if verbose:
        log += "\n| Ontology | Import URL | Resolves? |\n|--|--|--|\n"
        for ontology, url in import_urls:
            log += f"| {ontology} | {url} | {_check(url)} |\n"

    return metrics, violations, log, c, status


def _reference_predicate_matcher(predicates):
    """A predicate test for skip-object-of: exact IRIs, or `<namespace>*` wildcards."""
    exact = {p for p in predicates if not p.endswith('*')}
    namespaces = tuple(p[:-1] for p in predicates if p.endswith('*'))
    return lambda p: str(p) in exact or (bool(namespaces) and str(p).startswith(namespaces))


def _describe_local(source):
    if isinstance(source, rdflib.Graph):
        return f"graph supplied by the caller ({len(source)} triples)"
    return f"bundled: `{Path(source).name}`" if _is_bundled(source) else f"local file: `{source}`"


def check_undefined_terms(in_metrics, graph, name, check, c, status, verbose,
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
    c, log = c + 1, ''
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
        log += "WARNING - No terms to check.\n"
        return metrics, violations, log, c, status

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
        log += "PASS - All used terms are defined locally or in their respective remote ontologies.\n"
        if verbose:
            log += f"\nChecked {len(used_terms)} term(s) across {len(remote_namespaces)} remote namespace(s).\n"
    else:
        metrics[check] = len(all_violations)
        status += 1
        string = violation_formatting(all_violations)
        violations[check] = string
        violations[records_key(check)] = [dqv.Violation(uri) for uri in undefined_terms] + [
            dqv.Violation(uri, comment=f"namespace {get_namespace(uri)} could not be fetched")
            for uri in fetch_failure_terms
        ]
        log += f"VIOLATION - Found {metrics[check]} term(s) used but not defined locally or in their vocabulary (bundled, local or fetched):\n - "
        log += string.replace(",<br> ", "\n - ") + "\n"
    if remote_namespaces:
        applied_subs_map = {ns: path for ns, path in applied_subs}
        log += f"\n> **Remote namespace activity** — {len(remote_namespaces)} checked:\n"
        for ns in sorted(remote_namespaces):
            if ns in applied_subs_map:
                log += f">   - {chr(9989)} `{ns}` — {_describe_local(applied_subs_map[ns])}\n"
            elif ns in fetch_failures:
                log += f">   - {chr(10060)} `{ns}` — fetch failed\n"
            else:
                count = len(remote_subjects_by_ns.get(ns, set()))
                log += f">   - {chr(9989)} `{ns}` — fetched ({count} subject(s))\n"

    if not local_namespaces:
        log += "\nWARNING - No owl:Ontology declared; local namespace is unknown. Local dangling references may not be detected.\n"

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

def load_rdf(paths, verbose: bool = False):
    """
    Load RDF files from files or directories.

    Args:
        paths (list): List of file and/or directory paths.
        verbose (bool): Logical flag for printing additional information during loading.

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
        success, file_graph, log_msg = load_rdf_file(file_path)
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

# Prefixes accepted in compact IRIs in the lint config (e.g. `rdf:PropositionForm`).
CONFIG_PREFIXES = {
    'rdf': str(rdflib.RDF),
    'rdfs': str(rdflib.RDFS),
    'owl': str(rdflib.OWL),
    'xsd': str(rdflib.XSD),
    'skos': str(rdflib.SKOS),
    'sh': str(rdflib.SH),
    'dcterms': str(rdflib.DCTERMS),
    'foaf': str(rdflib.FOAF),
    'schema': 'https://schema.org/',
    'vs': 'http://www.w3.org/2003/06/sw-vocab-status/ns#',
}

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

def expand_curie(value, allow_wildcard=False):
    """
    Expand a compact IRI using CONFIG_PREFIXES; full IRIs are returned unchanged. With
    allow_wildcard, a trailing `*` (e.g. `vs:*`) is kept, to match a whole namespace.
    """
    if value.endswith('*') and not allow_wildcard:
        raise ValueError(f"Wildcards are not supported here: '{value}'")
    if value.startswith(('http://', 'https://', 'urn:')):
        return value
    prefix, sep, local = value.partition(':')
    if sep and prefix in CONFIG_PREFIXES:
        return CONFIG_PREFIXES[prefix] + local
    raise ValueError(f"Cannot expand '{value}': use a full IRI or one of the prefixes {', '.join(CONFIG_PREFIXES)}")

def parse_lint_config(config):
    """
    Parse configuration dictionary to switch on/off selected metrics.

    Args:
        config (str): Path to the YAML configuration file.

    Returns:
        transformed_selection (dict): User-selected metrics.
        ignore_imports (list): Import URLs skipped by the resolvability check.
        local_imports (dict): Mapping of remote URL -> local file path; used by both
            the owl:imports check (keyed on import URL) and the undefined-terms check
            (keyed on namespace URI).  Relative paths are resolved relative to the
            config file's directory.
        exclude_types (list): Type IRIs whose instances are skipped by the class checks
            (see TYPE_EXCLUDABLE_CHECKS).
        skip_object_of (list | None): Predicate IRIs (or `<namespace>*` wildcards) whose objects
            the undefined-terms check ignores; None when not configured (use the defaults).
    """
    if not os.path.isfile(config):
        raise FileNotFoundError(f"Config file not found: {config}")

    with open(config, "r", encoding="utf-8") as f:
        try:
            selection = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")

    if selection is None:
        selection = {"disable": []}

    imports_section = selection.pop("imports", None) or {}
    ignore_imports = [str(u) for u in (imports_section.get("ignore") or [])]
    raw_local = imports_section.get("local") or {}
    config_dir = os.path.dirname(os.path.abspath(config))
    local_imports = {
        str(url): (path if os.path.isabs(path) else os.path.join(config_dir, path))
        for url, path in raw_local.items()
    }

    exclude_section = selection.pop("exclude", None) or {}
    exclude_types = [expand_curie(str(t)) for t in (exclude_section.get("types") or [])]

    # undefined-terms.skip-object-of replaces the defaults when present (an empty list skips nothing).
    undefined_section = selection.pop("undefined-terms", None) or {}
    if "skip-object-of" in undefined_section:
        skip_object_of = [expand_curie(str(t), allow_wildcard=True)
                          for t in (undefined_section["skip-object-of"] or [])]
    else:
        skip_object_of = None

    # Transform the dictionary (check enable/disable keys only)
    transformed_selection = {
        key: [f"check_{item.replace('-', '_')}" for item in value_list]
        for key, value_list in selection.items()
    }

    return transformed_selection, ignore_imports, local_imports, exclude_types, skip_object_of

def lint_selection(selection, checklist, rule_reasons=None):
        """
        Disable the tests that are not included in the 'enable' list or that are included in the 'disable' list.
        The 'enable' and 'disable' keys are mutually exclusive. If both are specified in the configuration file,
        only the first dictionary will be used.
        """
        log = "> Lint configuration file found!\n"
        if 'enable' in selection and isinstance(selection['enable'], list):
            for i, item in enumerate(checklist):
                if item[1].__name__ not in selection['enable']: checklist[i][0] = False

            # Special case for the check_property_missing_domain_range test, which is triggered by both missingDomain and missingRange checks.
            if 'check_property_missing_domain' in selection['enable']:
                index = [i for i, item in enumerate(checklist) if item[3] == 'missingDomain'][0]
                checklist[index][0] = True
            
            if 'check_property_missing_range' in selection['enable']:
                index = [i for i, item in enumerate(checklist) if item[3] == 'missingRange'][0]
                checklist[index][0] = True
        
        elif 'disable' in selection and isinstance(selection['disable'], list):
            for i, item in enumerate(checklist):
                if item[1].__name__ in selection['disable']: checklist[i][0] = False
            
            # Special case for the check_property_missing_domain_range test, which is triggered by both missingDomain and missingRange checks.
            if 'check_property_missing_domain' in selection['disable']:
                index = [i for i, item in enumerate(checklist) if item[3] == 'missingDomain'][0]
                checklist[index][0] = False

            if 'check_property_missing_range' in selection['disable']:
                index = [i for i, item in enumerate(checklist) if item[3] == 'missingRange'][0]
                checklist[index][0] = False
        
        elif selection:
            # Non-empty dict with no recognised top-level key
            log += ">\n> WARNING - Invalid keyword in config file:\n> ```yaml\n"
            log += "> " + "> ".join(yaml.dump(selection, default_flow_style=False).splitlines(keepends=True))
            log += "> ```"
        
        # A check whose condition another needs is enabled with it, so a dependent check
        # has something to stand on and the report can say why it could not run. The
        # dependencies are declared once, in dqv.DQV_DEPENDENCIES, and published there too.
        by_key = {item[3]: item for item in checklist}
        for key, (required, _why) in sorted(dqv.DQV_DEPENDENCIES.items()):
            dependent, prerequisite = by_key[key], by_key[required]
            if dependent[0] and not prerequisite[0]:
                prerequisite[0] = True
                selected = config_check_name(dependent[1], key)
                log += (f"> WARNING: Check '{prerequisite[2]}' has been enabled because "
                        f"check '{dependent[2]}' was selected and depends on it.\n")
                if rule_reasons is not None:
                    rule_reasons[required] = (f"Enabled because the {selected} check was selected "
                                              "and depends on it.")
        return checklist, log

CHECKLIST = [
    [True, check_owl_declaration,                "Ontology without declaration",       'ontologyNotDeclared'       ],
    [True, check_one_ontology_per_file,          "Multiple ontologies in one file",    'multipleOntologies'        ],
    [True, check_owl_description,                "Ontology without description",       'ontologyDescription'       ],
    [True, check_owl_imports,                    "Unresolvable imports",               'unresolvedImports'         ],
    [True, check_undefined_terms,                "Undefined terms",                    'undefinedTerms'            ],
    [True, check_class_missing_label,            "Class without label",                'missingClassLabel'         ],
    [True, check_property_missing_label,         "Property without label",             'missingPropertyLabel'      ],
    [True, check_node_shape_missing_label,       "NodeShape without label",            'missingNSLabel'            ],
    [True, check_property_shape_missing_label,   "PropertyShape without label",        'missingPSLabel'            ],
    [True, check_class_missing_comment,          "Class without description",          'missingClassDescription'   ],
    [True, check_property_missing_comment,       "Property without description",       'missingPropertyDescription'],
    [True, check_node_shape_missing_comment,     "NodeShape without description",      'missingNSDescription'      ],
    [True, check_property_shape_missing_comment, "PropertyShape without description",  'missingPSDescription'      ],
    [True, check_class_same_label,               "Classes with the same label",        'nonUniqueClassLabels'      ],
    [True, check_property_same_label,            "Properties with the same label",     'nonUniquePropertyLabels'   ],
    [True, check_node_shape_same_label,          "NodeShapes with the same label",     'nonUniqueNSLabels'         ],
    [True, check_property_shape_same_label,      "PropertyShapes with the same label", 'nonUniquePSLabels'         ],
    [True, check_isolated_classes,               "Isolated classes",                   'isolatedClasses'           ],
    [True, check_property_missing_domain_range,  "Property without domain",            'missingDomain'             ],
    [True, check_property_missing_domain_range,  "Property without range",             'missingRange'              ],
    [True, check_unique_identifiers,             "Non-unique identifiers",             'nonUniqueIdentifiers'      ],
    [True, check_subclass_cycles,                "Subclass Cycles",                    'subclassCycles'            ],
    [True, check_untyped_class,                  "Untyped Classes",                    'untypedClasses'            ],
    [True, check_untyped_property,               "Untyped Properties",                 'untypedProperties'         ],
    [True, check_hijacking,                      "Namespace hijacking",                'hijacking'                 ],
]

def deepcopy_list(nested_list):
    """
    Creates a true deep copy of a list of lists (of lists...) 
    using recursion.
    """
    # Base case: if the item is not a list, return it as-is (primitive value)
    if not isinstance(nested_list, list):
        return nested_list
    
    # Recursive case: map the function over every element in the list
    return [deepcopy_list(item) for item in nested_list]

# Class checks that skip resources typed with a configured `exclude.types` IRI.
TYPE_EXCLUDABLE_CHECKS = (
    check_class_missing_label,
    check_class_missing_comment,
    check_class_same_label,
    check_isolated_classes,
    check_untyped_class,
)

def config_check_name(func, key):
    """The name a check has in .rdf-lint.yml enable/disable lists (e.g. 'class-missing-label')."""
    if key == 'missingDomain':
        return 'property-missing-domain'
    if key == 'missingRange':
        return 'property-missing-range'
    return func.__name__.removeprefix('check_').replace('_', '-')


def describe_configuration(checklist, lint_config=None, rule_reasons=None, ignore_imports=None,
                           local_imports=None, exclude_types=None, skip_object_of=None, config_file=None):
    """
    The configuration a run actually uses, as dqv.ConfigSetting records. Each records the
    .rdf-lint.yml key it corresponds to and where it came from: the config file, an
    ontolint default (e.g. a check enabled by default, the default skip-object-of list),
    a vocabulary bundled with ontolint (imports.local), or an ontolint rule (a check
    enabled because another depends on it). Without a config_file, values passed straight
    to run_qa() are recorded as coming from its caller. local_imports is the project's own
    mapping, before the bundled vocabularies are merged in.
    """
    selection = lint_config or {}
    rule_reasons = rule_reasons or {}
    given = 'config' if config_file else 'caller'
    settings = []

    for enabled, func, display_name, key in checklist:
        # enable:/disable: lists hold names as check_<name>, see parse_lint_config.
        config_name = f"check_{config_check_name(func, key).replace('-', '_')}"
        if key in rule_reasons:
            origin, reason = 'rule', rule_reasons[key]
        elif isinstance(selection.get('enable'), list):
            origin = given
            reason = ("Listed under enable:" if config_name in selection['enable']
                      else "Not listed under enable:, so not run")
        elif isinstance(selection.get('disable'), list) and config_name in selection['disable']:
            origin, reason = given, "Listed under disable:"
        elif not enabled:
            # Every check is enabled by default, so one that isn't was switched off by the caller.
            origin, reason = 'caller', "Disabled by the caller"
        else:
            origin, reason = 'default', "Enabled by default"
        settings.append(dqv.ConfigSetting('checks', key, origin, reason, enabled=bool(enabled), label=display_name))

    for iri in ignore_imports or []:
        settings.append(dqv.ConfigSetting('imports.ignore', iri, given,
                                          "Trusted: never fetched or reported, and not resolved as an import"))

    config_dir = os.path.dirname(os.path.abspath(config_file)) if config_file else None
    user_local = {iri_key(k): (k, v) for k, v in (local_imports or {}).items()}
    datasets = bundled_datasets()
    bundled_by_key = {iri_key(ns): ns for ns in bundled_vocabularies()}
    for k, (iri, path) in user_local.items():
        overrides = bundled_by_key.get(k)
        if isinstance(path, rdflib.Graph):
            # Supplied through the programmatic API: there is no file to name.
            shown = None
            reason = ("Resolved from a graph supplied by the caller; overrides the bundled vocabulary"
                      if overrides else "Resolved from a graph supplied by the caller")
        else:
            try:
                shown = os.path.relpath(path, config_dir) if config_dir else path
            except ValueError:  # Windows: the file is on another drive than the config file
                shown = path
            reason = ("Resolved from a local file instead of the network; overrides the bundled vocabulary"
                      if overrides else "Resolved from a local file instead of the network")
        settings.append(dqv.ConfigSetting('imports.local', iri, given, reason, local_file=shown,
                                          derived_from=datasets.get(overrides) if overrides else None))
    for ns, path in bundled_vocabularies().items():
        if iri_key(ns) not in user_local:
            settings.append(dqv.ConfigSetting('imports.local', ns, 'bundled',
                                              "Bundled with ontolint; resolved offline",
                                              local_file=os.path.basename(path), derived_from=datasets.get(ns)))

    for t in exclude_types or []:
        settings.append(dqv.ConfigSetting('exclude.types', t, given,
                                          "Instances are skipped by the class checks"))

    if skip_object_of is not None:
        for p in skip_object_of:
            settings.append(dqv.ConfigSetting('undefined-terms.skip-object-of', p, given,
                                              "Objects of this property are not checked as terms"))
    else:
        for p in DEFAULT_SKIP_OBJECT_OF:
            settings.append(dqv.ConfigSetting('undefined-terms.skip-object-of', expand_curie(p, allow_wildcard=True),
                                              'default', "ontolint default; undefined-terms.skip-object-of is not set"))
    return settings


def run_qa(graph: rdflib.Graph, verbose: bool = False, files_processed: list | None = None, source_iris: list | None = None, checklist=None, ignore_imports: list | None = None, uri_parser=None, local_imports: dict | None = None, exclude_types: list | None = None, skip_object_of: list | None = None, lint_config: dict | None = None, rule_reasons: dict | None = None, config_file: str | None = None) -> QAResult:
    """
    Run all QA checks on the given RDF graph.
    Returns structured pass/fail results — no file I/O, no arg parsing.

    lint_config, rule_reasons and config_file describe where the configuration came from
    (see describe_configuration); they don't change what runs.

    files_processed names the sources the graph was built from. They are file paths unless
    source_iris gives an IRI for each of them, as the programmatic API does for graphs that
    were never on disk.
    """
    if checklist is None:
        checklist = deepcopy_list(CHECKLIST)
    settings = describe_configuration(checklist, lint_config, rule_reasons, ignore_imports,
                                      local_imports, exclude_types, skip_object_of, config_file)
    # Bundled vocabularies resolve offline unless the project maps the namespace itself.
    local_imports = merge_local_imports(local_imports)

    qa_metrics = {
        'filesProcessed': files_processed or [],
        'triples': len(graph)
    }
    if source_iris:
        qa_metrics['sourceIRIs'] = [str(iri) for iri in source_iris]
    qa_violations = {}

    metrics, profiling_elements, exclusions = profiling(graph)
    qa_metrics.update(metrics)
    if (len(exclusions) > 0):
        graph -= exclusions

    logs = []
    checks = []
    test_counter = 1
    num_violations = 0
    for enabled, func, display_name, key in checklist:
        if enabled:
            kwargs = {}
            if func is check_owl_imports:
                kwargs["ignore_imports"] = ignore_imports
                kwargs["local_imports"] = local_imports
            if func is check_undefined_terms:
                if uri_parser is not None:
                    kwargs["uri_parser"] = uri_parser
                if local_imports:
                    kwargs["local_imports"] = local_imports
                if ignore_imports:
                    kwargs["ignore_imports"] = ignore_imports
                if skip_object_of is not None:
                    kwargs["skip_object_of"] = skip_object_of
            if func in TYPE_EXCLUDABLE_CHECKS and exclude_types:
                kwargs["exclude_types"] = exclude_types
            metrics, violations, log_results, test_counter, num_violations = func(
                qa_metrics, graph, display_name, key, test_counter, num_violations, verbose, **kwargs
            )
            qa_metrics.update(metrics)
            qa_violations.update(violations)
            logs.append(log_results)
            count = int(qa_metrics.get(key, 0))
            raw = qa_violations.get(key, '')
            # A check that could not be computed says so, rather than reporting the 0 it
            # never measured: a consumer cannot otherwise tell a clean result from one
            # nothing looked at.
            reason = qa_violations.get(skipped_key(key))
            checks.append(CheckResult(
                name=display_name,
                status='skipped' if reason else ('passed' if count == 0 else 'failed'),
                count=count,
                elements=str(raw) if raw else '',
                key=key,
                violations=qa_violations.get(records_key(key), []) if count else [],
                reason=reason,
                outcome=qa_violations.get(outcome_key(key)),
                notes=qa_violations.get(notes_key(key), []),
                table=qa_violations.get(table_key(key)),
                verbose_table=qa_violations.get(table_key(key, verbose_only=True)),
            ))
    
    # Fallback to add profiling elements from OWL declaration, which could have been disabled in the QA checks.
    if 'ontologyURI' not in qa_metrics:
        metrics, _, _, _, _ = check_owl_declaration(qa_metrics, graph, "", 'ontologyNotDeclared', 1, 0, verbose)
        qa_metrics.update(metrics)
    
    return QAResult(
        profiling=qa_metrics,
        checks=checks,
        elements=profiling_elements,
        logs=logs,
        datasets=dqv.datasets_for(graph, qa_metrics),
        bnode_keys=dqv.canonical_bnode_labels(graph, dqv.violation_bnodes(checks)),
        settings=settings,
        config_file=config_file,
    )

def select_checks(checks):
    """
    (checklist, lint_config, rule_reasons) for the checks named in Config.checks.

    The names are the ones .rdf-lint.yml uses under `enable:`, so a selection made in code
    behaves exactly as the same selection in the config file — including the rules that
    pull in a check another one depends on. None selects every check.
    """
    checklist = deepcopy_list(CHECKLIST)
    if checks is None:
        return checklist, None, {}

    valid = {config_check_name(func, key) for _, func, _, key in CHECKLIST}
    requested, unknown = [], []
    for name in checks:
        canonical = str(name).removeprefix('check_').replace('_', '-')
        (requested if canonical in valid else unknown).append(canonical)
    if unknown:
        raise ValueError(f"Unknown check(s): {', '.join(sorted(unknown))}. "
                         f"Available: {', '.join(sorted(valid))}")

    lint_config = {'enable': [f"check_{name.replace('-', '_')}" for name in requested]}
    rule_reasons = {}
    checklist, _ = lint_selection(lint_config, checklist, rule_reasons)
    return checklist, lint_config, rule_reasons


def config_kwargs(config):
    """The run_qa() arguments a Config maps to, leaving the empty ones at their defaults."""
    kwargs = {}
    if config.imports:
        kwargs['local_imports'] = local_imports_from(config.imports)
    if config.ignore_imports:
        kwargs['ignore_imports'] = [str(i) for i in config.ignore_imports]
    if config.exclude_types:
        kwargs['exclude_types'] = [expand_curie(str(t)) for t in config.exclude_types]
    if config.skip_object_of is not None:
        kwargs['skip_object_of'] = [expand_curie(str(p), allow_wildcard=True) for p in config.skip_object_of]
    if config.uri_parser is not None:
        kwargs['uri_parser'] = config.uri_parser
    return kwargs


def lint_graph(graph: rdflib.Graph, names, config: Config | None = None, checklist=None,
               source_iris: list | None = None, verbose: bool = False,
               provenance: dict | None = None) -> QAResult:
    """
    One lint run over one graph: inference if the configuration asks for it, then every
    selected check. This is the single path both front ends take — the CLI for each file
    (or for the merged graph) and ontolint.lint() for each dataset — so a run means the
    same thing however it was asked for.

    names identifies the sources the graph was built from: file paths for the CLI, the
    caller's dataset names for the API, which then passes the IRI each one is reported
    under in source_iris.

    checklist overrides config.checks, for the CLI, which resolves its selection from the
    config file. provenance records where the configuration came from (see
    describe_configuration); it doesn't change what runs.

    The graph is checked in place: the checks remove instance data from it and inference
    adds to it, so hand over a copy if the caller still needs theirs intact.
    """
    config = config or Config()
    inference_log = ''
    if config.inference:
        graph, inference_log = infer_subclass_relations(graph)
    if checklist is None:
        checklist, lint_config, rule_reasons = select_checks(config.checks)
        provenance = provenance or {'lint_config': lint_config, 'rule_reasons': rule_reasons}

    result = run_qa(graph, verbose=verbose, files_processed=list(names), source_iris=source_iris,
                    checklist=checklist, **config_kwargs(config), **(provenance or {}))
    result.inference_log = inference_log
    return result


def write_lint_config(checklist):
    """
    Generate a default .rdf-lint.yml config file
    """
    sys.stderr.write("Ontolint: creating default configuration file .rdf-lint.yml in the current directory.\n")

    # abort if path exists
    path = os.path.join(os.getcwd(), '.rdf-lint.yml')
    if os.path.exists(path):
        sys.stderr.write(f"ERROR: configuration file already exists: {path}\n\n")
        sys.exit(1)

    sequence = []
    for item in checklist:
        name = item[1].__name__.replace("check_", "").replace("_", "-")
        sequence.append(name)
    
    # Replace the "property-missing-domain-range" check with two separate checks for domain and range.
    sequence.remove("property-missing-domain-range")
    sequence.remove("property-missing-domain-range")
    sequence.append("property-missing-domain")
    sequence.append("property-missing-range")
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
#   - property-missing-domain\n
# Import settings: trust (ignore) namespaces or resolve them from local files.
# Core vocabularies (RDF, RDFS, OWL, XSD, SHACL, SKOS, Dublin Core, FOAF, schema.org, ...)
# are bundled with ontolint and resolve offline without any entry here.
# 'ignore': never fetched or reported by undefined-terms, not resolved by owl-imports.
# 'local': namespace or owl:imports IRI -> file; overrides the bundled copy.
# Entries match with or without a trailing '#' or '/'. Relative paths are resolved
# relative to this config file.
# imports:
#   ignore:
#     - http://example.org/vendor/ns#
#   local:
#     http://www.w3.org/ns/shacl#: local/shacl-1.2.ttl\n
# Skip resources of the listed types in the class checks (class-missing-label,
# class-missing-comment, class-same-label, isolated-classes, untyped-class).
# Accepts full IRIs or rdf:/rdfs:/owl:/xsd:/skos:/sh:/dcterms:/foaf:/schema:/vs: compact IRIs.
# e.g. rdf:PropositionForm stand-ins produced when downgrading RDF 1.2 to RDF 1.1.
# exclude:
#   types:
#     - rdf:PropositionForm\n
# The undefined-terms check ignores objects of reference properties, which link to
# documents rather than terms. Defaults (used when this key is absent):
{chr(10).join(f'#   {p}' for p in DEFAULT_SKIP_OBJECT_OF)}
# Listing properties here replaces the defaults; `prefix:*` matches a namespace and
# an empty list checks every object.
# undefined-terms:
#   skip-object-of:
#     - rdfs:seeAlso
#     - dcterms:license
        """)

def _relative_path(path, start=None):
    """path relative to start (default: the working directory), or None when it is outside it."""
    try:
        relative = os.path.relpath(os.path.abspath(path), start)
    except ValueError:  # Windows: path and start are on different drives
        return None
    # By component, so an in-tree directory named e.g. '..config' still counts as inside.
    return None if relative == os.pardir or relative.startswith(os.pardir + os.sep) else relative


def _display_path(path):
    """A path as shown in reports: relative to the working directory when inside it."""
    return _relative_path(path) or path


def render_table(headers, rows):
    """A Markdown table from column headings and rows of cells."""
    out = "| " + " | ".join(headers) + " |\n|" + "--|" * len(headers) + "\n"
    for row in rows:
        out += "| " + " | ".join(str(cell) for cell in row) + " |\n"
    return out


def render_outcome(check, verbose=False):
    """
    A check's section body, from what it decided.

    Empty for a check that has not been converted yet and still renders its own text (see
    #101); the reporter falls back to that while the move is in progress.
    """
    if not check.outcome:
        return ""
    sentence, detail = check.outcome
    body = f"{sentence}\n"
    if detail == AS_LIST and check.elements:
        body = f"{sentence}\n - " + check.elements.replace(",<br> ", "\n - ") + "\n"
    if check.table:
        body += render_table(*check.table)
    if verbose and check.verbose_table:
        body += "\n" + render_table(*check.verbose_table)
    body += "".join(f"{line}\n" for line in check.notes)
    return body


def render_markdown(result, checklist, verbose=False):
    """
    The Markdown body of a report, from a QAResult.

    The counterpart of build_ctrf_report() and dqv.build_dqv_graph(): one reporter, one
    seam. It is not yet a projection of the result alone — the per-check text is still
    rendered inside each check as it runs and carried on `logs` — so this assembles what
    is already text rather than producing it. See design.md and #101.

    `main()` wraps the result of this with the heading, the load log and the config log,
    which are run context rather than anything the checks produced.
    """
    log = result.inference_log
    tests = {key: enabled for enabled, _, _, key in checklist}
    log += print_profiling_metrics(result.profiling, result.elements, verbose)
    log += "\n## Quality Assurance Checks\n"
    # Numbering, titling and separating a check's section is the reporter's job: the check
    # says what it found, not how a report lays it out.
    for index, (check, body) in enumerate(zip(result.checks, result.logs), start=1):
        log += f"\nCheck {index}: {check.name}.\n{render_outcome(check, verbose) or body}{sep()}"
    log += print_profiling_table(result.profiling)
    log += print_qa_table(result.profiling, tests)
    return log


def _process_loaded_graph(g, files_processed, args, config, checklist, provenance=None):
    """
    Run inference (if requested), then profiling or full QA on an already-loaded graph.
    Returns (log_str, QAResult|None) — None in profile-only mode.
    """
    log = ""

    if args.profile_only:
        # Profile-only runs no checks, so it never reaches lint_graph.
        inference_log = ""
        if config.inference:
            g, inference_log = infer_subclass_relations(g)
        qa_metrics = {'filesProcessed': files_processed, 'triples': len(g)}
        qa_elements = {}
        metrics, elements, _ = profiling(g)
        qa_metrics.update(metrics)
        qa_elements.update(elements)
        log += "> Profile-only mode enabled. Skipping additional QA checks.\n\n"
        log += inference_log
        metrics, violations, _, _, _ = check_owl_declaration(qa_metrics, g, "", 'ontologyNotDeclared', 1, 0, args.verbose)
        qa_metrics.update(metrics)
        qa_elements.update(violations)
        log += print_profiling_metrics(qa_metrics, qa_elements, args.verbose)
        log += print_profiling_table(qa_metrics)
        return log, None

    result = lint_graph(g, files_processed, config, checklist=checklist,
                        verbose=args.verbose, provenance=provenance)
    log += render_markdown(result, checklist, args.verbose)
    return log, result


def _ctrf_filename(args, run_inputs):
    """
    What this run's CTRF report is called.

    A merged run produces one report, so --ctrf-filename names it. Per file there is one
    per input, so each is named after the input it describes; a single name could not hold
    them, which is why passing both is rejected rather than quietly ignored.
    """
    if not args.per_file:
        return args.ctrf_filename
    return f"{os.path.splitext(os.path.basename(run_inputs[0]))[0]}-qa-report.json"


def _write_dqv(args, config, results, ontology_sources=None):
    """Write the DQV report if --dqv-dir or --dqv-filename was given."""
    if not (args.dqv_dir or args.dqv_filename):
        return
    if not results:
        sys.stderr.write("Ontolint: no QA results, DQV report not written.\n")
        return
    duplicates = duplicate_ontology_iris(ontology_sources)
    _, log = dqv.write_dqv_report(results, args.dqv_dir or '.', args.dqv_filename, config.base_iri,
                                  duplicate_ontologies=duplicates)
    sys.stderr.write(log.lstrip())

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(add_help=False, description=__doc__)
    parser.add_argument('-h', '--help', action='help', help='Show this help message and exit.')
    parser.add_argument('-e', '--exit-status', action='store_true', help='Report an exit status to determine if one or more violations were detected.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output.')
    parser.add_argument('-p', '--profile-only', action='store_true', help='Compute only the profiling metrics and skip the QA part.')
    parser.add_argument('-i', '--inference', action='store_true', help='Enable inference of subclass relations before running QA checks. (default: False)')
    parser.add_argument('--per-file', action='store_true', help='Run QA independently on each input file and produce a separate report per file.')
    parser.add_argument('--ctrf-dir', type=str, metavar='directory', default='ctrf', help='Directory to write CTRF report to.')
    parser.add_argument('--ctrf-filename', type=str, metavar='filename', default=None, help='Filename for the CTRF report (if None, uses default pattern). Not valid with --per-file, which names each report after its input.')
    parser.add_argument('--dqv-dir', type=str, metavar='directory', default=None, help='Directory to write a DQV (W3C Data Quality Vocabulary) Turtle report to. Setting this or --dqv-filename enables DQV output.')
    parser.add_argument('--dqv-filename', type=str, metavar='filename', default=None, help=f'Filename for the DQV report (default: {dqv.DEFAULT_DQV_FILENAME}). With --per-file, all files are written to this one report.')
    parser.add_argument('--base-uri', type=str, metavar='uri', default=None, help=f'Namespace under which DQV instance IRIs (metrics, dimensions, measurements, violations, assessment) are minted (default: {dqv.DEFAULT_BASE_URI}).')
    parser.add_argument('-o', '--output', type=str, metavar='filename', help='Write the report to this file instead of printing it. With --per-file it holds every report, in the order the inputs were checked.')
    parser.add_argument('-c', '--config', type=str, metavar='path/to/config.yml', help='Path to a YAML configuration file to enable or disable individual checks. Note that if the current directory contains a .rdf-lint.yml file, it will be used by default.')
    parser.add_argument('--init', action='store_true', help='Generate a default .rdf-lint.yml config file in the current directory.')
    parser.add_argument('data_files', nargs='*', help='List of RDF files or folders to process.')
    args = parser.parse_args()
    try:
        if args.dqv_filename is not None:
            dqv.check_dqv_filename(args.dqv_filename)
        if args.base_uri is not None:
            dqv.check_base_uri(args.base_uri)
    except ValueError as e:
        parser.error(str(e))

    # Validate arguments: data_files is required unless --init is used.
    if not args.init and not args.data_files:
        parser.error("data_files is required unless -i/--init option is used")
    if args.per_file and args.ctrf_filename:
        parser.error("--ctrf-filename names a single report; with --per-file each input "
                     "gets its own, named after it")

    # Write an empty lint configuration file and exit.
    if args.init:
        write_lint_config(CHECKLIST)
        exit(0)

    # Apply lint config (shared by both single-run and per-file modes).
    checklist = deepcopy_list(CHECKLIST)
    ignore_imports = []
    local_imports = {}
    exclude_types = []
    skip_object_of = None
    config_log = ""
    # Everything that describes the run itself goes into a Config, which is what
    # lint_graph() takes — the same object a caller of ontolint.lint() builds by hand.
    # Where the configuration came from, recorded in the DQV report (describe_configuration).
    provenance = {}
    config_path = os.path.join(os.getcwd(), '.rdf-lint.yml')
    if args.config or os.path.isfile(config_path):
        if args.config:
            config_path = args.config
        lint_config, ignore_imports, local_imports, exclude_types, skip_object_of = parse_lint_config(config_path)
        rule_reasons = {}
        checklist, config_log = lint_selection(lint_config, checklist, rule_reasons)
        provenance = {'lint_config': lint_config, 'rule_reasons': rule_reasons,
                      'config_file': _display_path(config_path)}
        if exclude_types:
            config_log += "> Class checks skip resources typed as: " + ", ".join(f"`{t}`" for t in exclude_types) + "\n"

    config = Config(per_file=args.per_file, inference=args.inference, imports=local_imports,
                    ignore_imports=ignore_imports, exclude_types=exclude_types,
                    skip_object_of=skip_object_of, base_iri=args.base_uri)

    # --per-file decides one thing: whether the checks run over each input on its own or
    # over all of them merged. Everything else about a run is the same either way, so
    # there is one loop rather than two paths — see #103 for what used to differ.
    if args.per_file:
        runs = [[path] for path in _collect_files(args.data_files)]
    else:
        runs = [args.data_files]

    log_output = ""
    results = []
    ontology_sources = {}
    files_checked = 0
    any_parse_failure = False

    for run_inputs in runs:
        # One report per run, on one stream. Each was printed separately before, so the
        # blank line between them came from print(); it has to be explicit now, or a
        # heading lands directly under the previous report's table and stops being one.
        if log_output:
            log_output += "\n"
        log_output += "# Ontology Quality Assurance\n\n"
        file_counter, files_processed, g, load_log, files_failed, sources = load_rdf(
            run_inputs, verbose=args.verbose)
        files_checked += file_counter
        for iri, iri_sources in sources.items():
            ontology_sources.setdefault(iri, []).extend(iri_sources)
        log_output += load_log

        # A file that can't be parsed would silently shrink the graph under test. That is
        # the one thing --per-file legitimately changes beyond the checks' scope: in a
        # merged run the whole graph is compromised and there is nothing left to check,
        # while per file the others are independent runs and still worth checking.
        if files_failed:
            log_output += _parse_failure_log(files_failed)
            for failed in files_failed:
                print(f"ERROR - Failed to parse: {failed}", file=sys.stderr)
            any_parse_failure = True
            continue

        if file_counter == 0:
            continue

        log_output += f"\n> {file_counter} file{'' if file_counter == 1 else 's'} processed.\n"
        for processed in files_processed:
            log_output += f"> - `{processed}`\n"
        log_output += ">\n"
        if config_log:
            log_output += config_log

        qa_log, result = _process_loaded_graph(g, files_processed, args, config, checklist,
                                               provenance)
        log_output += qa_log
        if result is not None:
            write_ctrf_report(build_ctrf_report(result), args.ctrf_dir,
                              _ctrf_filename(args, run_inputs))
            results.append(result)

    if files_checked == 0:
        log_output += "ERROR - No RDF data in input files or directories."

    _write_dqv(args, config, results, ontology_sources)
    qa_terminate(args.output, log_output)

    if any_parse_failure:
        sys.exit(1)
    if args.exit_status and (files_checked == 0 or not all(r.passed for r in results)):
        sys.exit(1)


if __name__ == "__main__":
    main()
