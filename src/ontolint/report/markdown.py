"""
The Markdown report: what a reader sees on stdout or in a file.

A projection of a QAResult. A check records what it found through decided(), note() and
tabulate() and renders nothing; everything about layout - section numbers, headings, rules,
how a list or table is drawn, whether a verbose-only table appears - is decided here.
"""
from ..resolution import _describe_local


def normalise(count, total):
    count = float(count)
    total = float(total)
    if total == 0:
        # Nothing of the kind exists, so nothing violated: 0 out of 0 is not all of them.
        # The check that measured it says so itself — see normalise_if_executed.
        return 0
    out = count / total
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


def print_profiling_table(metrics):
    """
    A table of an RDF graph's profiling metrics.

    Args:
        metrics (dict): The profiling metrics of the graph.

    Returns:
        log (str): The table, formatted in Markdown.
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
        checks (dict): Which checks were selected, by key.

    Returns:
        log (str): The table, formatted in Markdown.
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


# What a cell says when there is no score to give: the check was not selected, or it ran
# and could not measure anything. A number would read as a score either way, and a skipped
# check scoring 0 reads as a clean result it never earned.
NOT_SELECTED = "N/A"


NOT_ASSESSED = "skipped"


def _no_score(checks, key):
    """The cell for a check with no score, or None when it has one."""
    status = checks.get(key)
    if not status:
        return NOT_SELECTED
    return NOT_ASSESSED if status == 'skipped' else None


def normalise_if_executed(metrics, checks, key, total):
    """The check's violations as a fraction of what it measured, or why there is no fraction."""
    return _no_score(checks, key) or normalise(metrics[key], metrics[total])


def normalise_if_executed_len(metrics, checks, key, total):
    """The same, where the denominator is the length of a list rather than a count."""
    return _no_score(checks, key) or normalise(metrics[key], len(metrics[total]))


def print_if_executed(metrics, checks, key):
    """The check's raw count, or why there is none."""
    return _no_score(checks, key) or metrics[key]


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


def render_table(headers, rows):
    """A Markdown table from column headings and rows of cells."""
    out = "| " + " | ".join(headers) + " |\n|" + "--|" * len(headers) + "\n"
    for row in rows:
        out += "| " + " | ".join(str(cell) for cell in row) + " |\n"
    return out


def render_outcome(check, verbose=False):
    """
    A check's section, from the parts it recorded.

    """
    out = ""
    for kind, *payload in check.body:
        if kind == 'text':
            out += f"{payload[0]}\n"
        elif kind == 'elements' and check.elements:
            out += " - " + check.elements.replace(",<br> ", "\n - ") + "\n"
        elif kind == 'table':
            out += render_table(*payload)
        elif kind == 'verbose-table' and verbose:
            out += "\n" + render_table(*payload)
    return out


def render_markdown(result, checklist, verbose=False):
    """
    The Markdown body of a report, from a QAResult.

    The counterpart of build_ctrf_report() and dqv.build_dqv_graph(): one reporter, one
    seam, and a projection of the result alone. A check records what it found; how a
    report says it is decided here.

    `main()` wraps the result of this with the heading, the load log and the config log,
    which are run context rather than anything the checks produced.
    """
    log = result.inference_log
    # What each check did, not merely whether it was selected: a check that could not be
    # computed has no score to show, and a 0 would read as a clean result.
    outcomes = {check.key: check.status for check in result.checks}
    tests = {key: outcomes.get(key) if enabled else None for enabled, _, _, key in checklist}
    log += print_profiling_metrics(result.profiling, result.elements, verbose)
    log += "\n## Quality Assurance Checks\n"
    # Numbering, titling and separating a check's section is the reporter's job: the check
    # says what it found, not how a report lays it out.
    for index, check in enumerate(result.checks, start=1):
        log += f"\nCheck {index}: {check.name}.\n{render_outcome(check, verbose)}{sep()}"
    log += print_profiling_table(result.profiling)
    log += print_qa_table(result.profiling, tests)
    return log
