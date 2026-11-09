# Ontology Quality Assessment Script
# SEMANTIC PARTNERS LTD, 2026
# Authors: Simon Shapiro, Otello M Roscioni, John Placek, Pel Olson.

"""
A script to perform basic QA on a set of ontologies.
It loads RDF files, applies simple RDFS subclass inference, and runs SPARQL queries to
check for common ontology quality issues.
It reports any violations found in the ontology data.
"""
import argparse
import os
import sys

from . import dqv
from .checks.metadata import check_owl_declaration
from .config import _display_path, lint_selection, parse_lint_config, write_lint_config
from .loading import _collect_files, load_rdf, _parse_failure_log, parse_inputs
from .model import Config
from .profiling import infer_subclass_relations, profiling
from .registry import CHECKLIST, deepcopy_list
from .report.ctrf import build_ctrf_report, write_ctrf_report
from .report.markdown import print_profiling_metrics, print_profiling_table, render_markdown
from .resolution import sibling_imports
from .runner import duplicate_ontology_iris, lint_graph


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
