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

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv  # noqa: F401
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
    from scripts.config import (config_check_name, config_kwargs, describe_configuration,  # noqa: F401
                                _display_path, lint_selection, parse_lint_config,
                                _relative_path, write_lint_config)
    from scripts.registry import (CHECKLIST, deepcopy_list, select_checks,  # noqa: F401
                                  TYPE_EXCLUDABLE_CHECKS)
    from scripts.runner import (declared_ontology_sources, duplicate_ontology_iris,  # noqa: F401
                                lint_graph, run_qa)
    from scripts.cli import (_ctrf_filename, main, _process_loaded_graph,  # noqa: F401
                             qa_terminate, _write_dqv)
    from scripts.terms import (CONFIG_PREFIXES, _term_from_string, expand_curie,  # noqa: F401
                               get_namespace, iri_key, ontology_iris, term_text)
except ImportError:  # run as a script: scripts/ itself is on sys.path
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
    from config import (config_check_name, config_kwargs, describe_configuration,  # noqa: F401
                        _display_path, lint_selection, parse_lint_config, _relative_path,
                        write_lint_config)
    from registry import (CHECKLIST, deepcopy_list, select_checks, TYPE_EXCLUDABLE_CHECKS)  # noqa: F401
    from runner import (declared_ontology_sources, duplicate_ontology_iris, lint_graph,  # noqa: F401
                        run_qa)
    from cli import (_ctrf_filename, main, _process_loaded_graph, qa_terminate,  # noqa: F401
                     _write_dqv)
    from terms import (CONFIG_PREFIXES, _term_from_string, expand_curie,  # noqa: F401
                       get_namespace, iri_key, ontology_iris, term_text)


if __name__ == "__main__":
    main()
