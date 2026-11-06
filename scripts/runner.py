"""
One lint run: inference if asked for, profiling, then every selected check, collected
into a QAResult.

lint_graph() is the single entry point both front ends take - the CLI for each file or the
merged graph, ontolint.lint() for each dataset - so a run means the same thing however it
was asked for. The set-level helpers here judge what can only be seen across the inputs,
before they are merged.
"""
import rdflib

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv
    from scripts.checks.metadata import check_owl_declaration, check_owl_imports
    from scripts.checks.namespaces import check_undefined_terms
    from scripts.config import config_kwargs, describe_configuration
    from scripts.model import (body_key, CheckResult, Config, outcome_key, QAResult,
                               records_key, skipped_key)
    from scripts.profiling import infer_subclass_relations, profiling
    from scripts.registry import (CHECKLIST, deepcopy_list, select_checks,
                                  TYPE_EXCLUDABLE_CHECKS)
    from scripts.resolution import merge_local_imports
    from scripts.terms import ontology_iris
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    from checks.metadata import check_owl_declaration, check_owl_imports
    from checks.namespaces import check_undefined_terms
    from config import config_kwargs, describe_configuration
    from model import (body_key, CheckResult, Config, outcome_key, QAResult, records_key,
                       skipped_key)
    from profiling import infer_subclass_relations, profiling
    from registry import CHECKLIST, deepcopy_list, select_checks, TYPE_EXCLUDABLE_CHECKS
    from resolution import merge_local_imports
    from terms import ontology_iris


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


def run_qa(graph: rdflib.Graph, verbose: bool = False, files_processed: list | None = None, source_iris: list | None = None, checklist=None, ignore_imports: list | None = None, uri_parser=None, local_imports: dict | None = None, exclude_types: list | None = None, skip_object_of: list | None = None, lint_config: dict | None = None, rule_reasons: dict | None = None, config_file: str | None = None, resolve_siblings: bool | None = None) -> QAResult:
    """
    Run all QA checks on the given RDF graph.
    Returns structured pass/fail results — no file I/O, no arg parsing.

    lint_config, rule_reasons, config_file and resolve_siblings describe where the
    configuration came from (see describe_configuration); they don't change what runs.

    files_processed names the sources the graph was built from. They are file paths unless
    source_iris gives an IRI for each of them, as the programmatic API does for graphs that
    were never on disk.
    """
    if checklist is None:
        checklist = deepcopy_list(CHECKLIST)
    settings = describe_configuration(checklist, lint_config, rule_reasons, ignore_imports,
                                      local_imports, exclude_types, skip_object_of, config_file,
                                      resolve_siblings)
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

    checks = []
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
            metrics, violations, num_violations = func(
                qa_metrics, graph, key, num_violations, verbose, **kwargs
            )
            qa_metrics.update(metrics)
            qa_violations.update(violations)
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
                body=qa_violations.get(body_key(key), [])))
    
    # Fallback to add profiling elements from OWL declaration, which could have been disabled in the QA checks.
    if 'ontologyURI' not in qa_metrics:
        metrics, _, _ = check_owl_declaration(qa_metrics, graph, 'ontologyNotDeclared', 0, verbose)
        qa_metrics.update(metrics)
    
    return QAResult(
        profiling=qa_metrics,
        checks=checks,
        elements=profiling_elements,
        datasets=dqv.datasets_for(graph, qa_metrics),
        bnode_keys=dqv.canonical_bnode_labels(graph, dqv.violation_bnodes(checks)),
        settings=settings,
        config_file=config_file)


def lint_graph(graph: rdflib.Graph, names, config: Config | None = None, checklist=None,
               source_iris: list | None = None, verbose: bool = False,
               provenance: dict | None = None, context_imports: dict | None = None) -> QAResult:
    """
    One lint run over one graph: inference if the configuration asks for it, then every
    selected check. This is the single path both front ends take — the CLI for each file
    (or for the merged graph) and ontolint.lint() for each dataset — so a run means the
    same thing however it was asked for.

    names identifies the sources the graph was built from: file paths for the CLI, the
    caller's dataset names for the API, which then passes the IRI each one is reported
    under in source_iris.

    context_imports are namespaces this run may resolve against but is not checking — the
    other inputs of the same invocation (#108). They rank below the project's own
    imports.local, which is an explicit instruction, and above the bundled vocabularies.

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

    kwargs = config_kwargs(config)
    if context_imports:
        # The project's own imports.local wins: it is an instruction, while a sibling input
        # is merely available. Both outrank the bundled vocabularies (see merge_local_imports).
        kwargs['local_imports'] = {**context_imports, **(kwargs.get('local_imports') or {})}
    result = run_qa(graph, verbose=verbose, files_processed=list(names), source_iris=source_iris,
                    checklist=checklist, **kwargs, **(provenance or {}))
    result.inference_log = inference_log
    return result
