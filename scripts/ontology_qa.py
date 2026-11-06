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
import argparse
import sys
import os
import yaml

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv
    from scripts.resolution import (bundled_datasets, bundled_vocabularies,  # noqa: F401
                                    defined_namespaces, _describe_local, _is_bundled,
                                    local_imports_from, merge_local_imports, _parse_bundled,
                                    _parse_local, RunInput, sibling_imports, VOCAB_CATALOG)
    from scripts.queries import (EXCLUDE_TYPES_PLACEHOLDER, exec_sparql,  # noqa: F401
                                 load_sparql_queries, sparql_dir, sparql_queries)
    from scripts.model import (AS_LIST, AS_TABLE, body_key, CheckResult, concat_members,  # noqa: F401
                               Config, decided, EMPTY_POPULATION, INFERRED_CONTEXT, IRI,
                               not_assessed, not_assessed_message, NOT_ASSESSED_MESSAGES,
                               note, outcome_key, _part, QAResult, records_key, skipped_key,
                               source_iris, SOURCES_NOT_RECORDED, tabulate,
                               violation_formatting, VocabularySource)
    from scripts.checks.metadata import (check_one_ontology_per_file, check_owl_declaration,  # noqa: F401
                                         check_owl_description, check_owl_imports,
                                         ontologies_by_source)
    from scripts.checks.annotations import (check_class_missing_comment,  # noqa: F401
                                            check_class_missing_label,
                                            check_node_shape_missing_comment,
                                            check_node_shape_missing_label,
                                            check_property_missing_comment,
                                            check_property_missing_label,
                                            check_property_shape_missing_comment,
                                            check_property_shape_missing_label)
    from scripts.checks.uniqueness import (check_class_same_label,  # noqa: F401
                                           check_node_shape_same_label,
                                           check_property_same_label,
                                           check_property_shape_same_label,
                                           check_unique_identifiers, _same_label_records)
    from scripts.checks.structure import (check_isolated_classes,  # noqa: F401
                                          check_property_missing_domain,
                                          check_property_missing_range,
                                          check_subclass_cycles, _domain_range_rows,
                                          _missing_declaration)
    from scripts.checks.namespaces import (check_hijacking, check_undefined_terms,  # noqa: F401
                                           check_untyped_class, check_untyped_property,
                                           _CONTAINER_MEMBERSHIP, DEFAULT_SKIP_OBJECT_OF,
                                           _reference_predicate_matcher)
    from scripts.profiling import (exclude_instance_data, exec_hierarchy_depth,  # noqa: F401
                                   infer_subclass_relations, prefixes, profiling)
    from scripts.report.markdown import (get_ontology_name, _no_score, normalise,  # noqa: F401
                                         normalise_if_executed, normalise_if_executed_len,
                                         NOT_ASSESSED, NOT_SELECTED, print_if_executed,
                                         print_profiling_metrics, print_profiling_table,
                                         print_qa_table, render_markdown, render_outcome,
                                         render_table, sep)
    from scripts.report.ctrf import (build_ctrf_report, write_ctrf_report)  # noqa: F401
    from scripts.loading import (_collect_files, load_rdf, load_rdf_file,  # noqa: F401
                                 _parse_failure_log, parse_inputs)
    from scripts.terms import (CONFIG_PREFIXES, _term_from_string, expand_curie,  # noqa: F401
                               get_namespace, iri_key, ontology_iris, term_text)
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    from resolution import (bundled_datasets, bundled_vocabularies, defined_namespaces,  # noqa: F401
                            _describe_local, _is_bundled, local_imports_from,
                            merge_local_imports, _parse_bundled, _parse_local, RunInput,
                            sibling_imports, VOCAB_CATALOG)
    from queries import (EXCLUDE_TYPES_PLACEHOLDER, exec_sparql, load_sparql_queries,  # noqa: F401
                         sparql_dir, sparql_queries)
    from model import (AS_LIST, AS_TABLE, body_key, CheckResult, concat_members, Config,  # noqa: F401
                       decided, EMPTY_POPULATION, INFERRED_CONTEXT, IRI, not_assessed,
                       not_assessed_message, NOT_ASSESSED_MESSAGES, note, outcome_key,
                       _part, QAResult, records_key, skipped_key, source_iris,
                       SOURCES_NOT_RECORDED, tabulate, violation_formatting,
                       VocabularySource)
    from checks.metadata import (check_one_ontology_per_file, check_owl_declaration,  # noqa: F401
                                 check_owl_description, check_owl_imports,
                                 ontologies_by_source)
    from checks.annotations import (check_class_missing_comment, check_class_missing_label,  # noqa: F401
                                    check_node_shape_missing_comment,
                                    check_node_shape_missing_label,
                                    check_property_missing_comment,
                                    check_property_missing_label,
                                    check_property_shape_missing_comment,
                                    check_property_shape_missing_label)
    from checks.uniqueness import (check_class_same_label, check_node_shape_same_label,  # noqa: F401
                                   check_property_same_label,
                                   check_property_shape_same_label,
                                   check_unique_identifiers, _same_label_records)
    from checks.structure import (check_isolated_classes, check_property_missing_domain,  # noqa: F401
                                  check_property_missing_range, check_subclass_cycles,
                                  _domain_range_rows, _missing_declaration)
    from checks.namespaces import (check_hijacking, check_undefined_terms,  # noqa: F401
                                   check_untyped_class, check_untyped_property,
                                   _CONTAINER_MEMBERSHIP, DEFAULT_SKIP_OBJECT_OF,
                                   _reference_predicate_matcher)
    from profiling import (exclude_instance_data, exec_hierarchy_depth,  # noqa: F401
                           infer_subclass_relations, prefixes, profiling)
    from report.markdown import (get_ontology_name, _no_score, normalise,  # noqa: F401
                                 normalise_if_executed, normalise_if_executed_len,
                                 NOT_ASSESSED, NOT_SELECTED, print_if_executed,
                                 print_profiling_metrics, print_profiling_table,
                                 print_qa_table, render_markdown, render_outcome,
                                 render_table, sep)
    from report.ctrf import (build_ctrf_report, write_ctrf_report)  # noqa: F401
    from loading import (_collect_files, load_rdf, load_rdf_file, _parse_failure_log,  # noqa: F401
                         parse_inputs)
    from terms import (CONFIG_PREFIXES, _term_from_string, expand_curie,  # noqa: F401
                       get_namespace, iri_key, ontology_iris, term_text)


# check that the directory exists
if not os.path.isdir(sparql_dir):
    sys.stderr.write(f"SPARQL directory '{sparql_dir}' does not exist.\nSet the QA_SPARQL_DIR environment variable before executing ontology_qa.")
    sys.exit(1)


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


def qa_terminate(file, log):
    """
    Print the results to a file name if specified, otherwise print to the STDOUT.

    Args:
        file (str): Name of the output file. If undefined, print to the STDOUT.
    """
    # Print output to file or STDOUT.
    if file:
         # Ensure directory exists
        os.makedirs(os.path.dirname(file) or '.', exist_ok=True)
        with open(file, "w", encoding="utf-8") as f:
            f.write(log)
    else:
        print(log)


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
        resolve_siblings (bool | None): Whether a run may resolve references against the
            other inputs of the same invocation; None when not configured (on by default).
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
    # imports.siblings: on unless the project turns it off. A run resolving against files
    # it is not checking is usually what is wanted (#108), but a project that lints a
    # directory of unrelated ontologies may want each judged strictly on its own.
    resolve_siblings = imports_section.get("siblings")
    if resolve_siblings is not None and not isinstance(resolve_siblings, bool):
        raise ValueError(f"imports.siblings must be true or false, got {resolve_siblings!r}")
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

    return (transformed_selection, ignore_imports, local_imports, exclude_types,
            skip_object_of, resolve_siblings)

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
        
        elif 'disable' in selection and isinstance(selection['disable'], list):
            for i, item in enumerate(checklist):
                if item[1].__name__ in selection['disable']: checklist[i][0] = False
        
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
    [True, check_property_missing_domain,        "Property without domain",            'missingDomain'             ],
    [True, check_property_missing_range,         "Property without range",             'missingRange'              ],
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
    return func.__name__.removeprefix('check_').replace('_', '-')


def describe_configuration(checklist, lint_config=None, rule_reasons=None, ignore_imports=None,
                           local_imports=None, exclude_types=None, skip_object_of=None,
                           config_file=None, resolve_siblings=None):
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
        if isinstance(path, RunInput):
            # Another input of the same invocation, named so it is explicit which ontology
            # the run resolved from where. Nobody configured it — it is derived from what
            # was passed in — so it is its own origin, and a per-file run's configuration
            # then differs per file, because its resolution context genuinely does.
            shown = path.source
            reason = ("Resolved from another input of this run, which declares it"
                      + ("; overrides the bundled vocabulary" if overrides else ""))
            settings.append(dqv.ConfigSetting('imports.local', iri, 'input', reason,
                                              local_file=shown,
                                              derived_from=datasets.get(overrides) if overrides else None))
            continue
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

    # Whether a run may resolve against the files it is not checking changes what the
    # undefined-terms result means, so a consumer is told it was in force — as the setting
    # it is, not as one entry per sibling, which would differ from run to run (#108).
    settings.append(dqv.ConfigSetting(
        'imports.siblings', resolve_siblings is not False,
        'config' if resolve_siblings is not None else 'default',
        "References may resolve against the other inputs of this run, without fetching them"
        if resolve_siblings is not False else
        "Each input is checked on its own; references do not resolve against the other inputs"))

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
                body=qa_violations.get(body_key(key), []),
            ))
    
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


def _process_loaded_graph(g, files_processed, args, config, checklist, provenance=None,
                          context_imports=None):
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
        metrics, violations, _ = check_owl_declaration(qa_metrics, g, 'ontologyNotDeclared', 0, args.verbose)
        qa_metrics.update(metrics)
        qa_elements.update(violations)
        log += print_profiling_metrics(qa_metrics, qa_elements, args.verbose)
        log += print_profiling_table(qa_metrics)
        return log, None

    result = lint_graph(g, files_processed, config, checklist=checklist,
                        verbose=args.verbose, provenance=provenance,
                        context_imports=context_imports)
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
    resolve_siblings = None            # unset: a run resolves against its siblings
    config_log = ""
    # Everything that describes the run itself goes into a Config, which is what
    # lint_graph() takes — the same object a caller of ontolint.lint() builds by hand.
    # Where the configuration came from, recorded in the DQV report (describe_configuration).
    provenance = {}
    config_path = os.path.join(os.getcwd(), '.rdf-lint.yml')
    if args.config or os.path.isfile(config_path):
        if args.config:
            config_path = args.config
        (lint_config, ignore_imports, local_imports, exclude_types, skip_object_of,
         resolve_siblings) = parse_lint_config(config_path)
        rule_reasons = {}
        checklist, config_log = lint_selection(lint_config, checklist, rule_reasons)
        provenance = {'lint_config': lint_config, 'rule_reasons': rule_reasons,
                      'config_file': _display_path(config_path),
                      'resolve_siblings': resolve_siblings}
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

    # Every input read once, however the runs are batched: a run resolves references
    # against the files it is not checking, so those have to be read too (#108).
    parsed = parse_inputs(args.data_files)

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
            run_inputs, verbose=args.verbose, parsed=parsed)
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
                                               provenance,
                                               context_imports=(
                                                   sibling_imports(parsed, set(files_processed))
                                                   if resolve_siblings is not False else None))
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
