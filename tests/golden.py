"""
Writing the stored expectations back out, for UPDATE_GOLDEN=1.

The CTRF and DQV goldens are just JSON and Turtle, so their suites serialise them inline.
A `QAResult` and the Markdown need a little more: a Python literal that round-trips, and a
docstring saying what the file is. Both live here rather than in a script beside the repo,
because a generator that is not in the tree cannot be kept in step with the tests it
writes about — the names in these headers went stale exactly that way.
"""
import hashlib
import re
from pathlib import Path

from rdflib import BNode, Literal, URIRef

DATA = Path(__file__).parent / 'data'

QARESULT_HEADER = '''"""
The QAResult that linting {inputs} produces, written out as data.

This is the input to the reporter suites — `test_pipeline_qaresult_to_ctrf.py` and
`test_pipeline_qaresult_to_dqv.py` take *these* instances, not ones produced by running the
linter, so they test the projection alone: a change to what a check finds cannot break
them, and a change to a reporter cannot be blamed on the checks.

`test_pipeline_lint_to_qaresult.py` is what keeps it honest — it asserts that linting the
input still produces this. Regenerate with:

    UPDATE_GOLDEN=1 poetry run pytest tests/test_pipeline_lint_to_qaresult.py

and read the diff: a new check should be a deliberate addition to the expectation.

`logs` and `elements` are left empty. They are the Markdown's raw material — rendered text
and profiling detail — consumed by no other reporter, and they leave QAResult entirely once
Markdown becomes a projection (see design.md). `test_pipeline_lint_to_markdown.py` covers
them.
"""

{imports}from scripts.dqv import ConfigSetting, Dataset, Violation
from scripts.ontology_qa import CheckResult, QAResult

EXPECTED = QAResult(
'''

MARKDOWN_HEADER = '''"""
The Markdown that linting {inputs} produces, written out as data.

`test_pipeline_lint_to_markdown.py` asserts a lint still renders exactly this. Regenerate
with:

    UPDATE_GOLDEN=1 poetry run pytest tests/test_pipeline_lint_to_markdown.py

Markdown is not a projection of QAResult yet — the per-check text is rendered inside each
check as it runs — so this is the output of the lint, not of a reporter (see design.md).
When it does become a projection, this file stays as it is and only the way it is produced
changes, which is how the move will be checked.

The report assembled by `main()` wraps this with the heading, the load log and the config
log. Those are run context rather than anything the checks produced, and they carry input
paths, so they are covered by `test_e2e_cli.py` instead.
"""

EXPECTED = """
'''


def _term(value):
    if isinstance(value, URIRef):
        return f"URIRef({str(value)!r})"
    if isinstance(value, BNode):
        return f"BNode({str(value)!r})"
    if isinstance(value, Literal):
        if str(value.datatype) == 'http://www.w3.org/2001/XMLSchema#integer':
            return f"Literal({int(value)})"
        if value.datatype:
            return f"Literal({str(value)!r}, datatype=XSD.{str(value.datatype).rsplit('#', 1)[-1]})"
        return f"Literal({str(value)!r})"
    return repr(value)


def _violation(violation):
    parts = [_term(violation.resource)]
    if violation.comment is not None:
        parts.append(f"comment={violation.comment!r}")
    if violation.related:
        parts.append("related=[" + ", ".join(_term(t) for t in violation.related) + "]")
    if violation.value is not None:
        parts.append(f"value={_term(violation.value)}")
    return "Violation(" + ", ".join(parts) + ")"


def _profiling_value(key, value, repo):
    if key == 'fetchActivity':
        # Sorted: fetchActivity is built by iterating a set, so dict equality passes while
        # the file churns on every regeneration. Paths are relative to the repo root,
        # because an absolute one matches only the machine that wrote it.
        local = {}
        for namespace, source in value['local'].items():
            try:
                local[namespace] = Path(source).resolve().relative_to(repo).as_posix()
            except (ValueError, TypeError):
                local[namespace] = source
        return ("{'local': " + repr(dict(sorted(local.items())))
                + ", 'fetched': " + repr(dict(sorted(value['fetched'].items())))
                + ", 'failed': " + repr(sorted(value['failed'])) + "}")
    if isinstance(value, list):
        return "[" + ", ".join(
            _term(v) if isinstance(v, (URIRef, BNode, Literal)) else repr(v) for v in value) + "]"
    if isinstance(value, (URIRef, BNode, Literal)):
        return _term(value)
    return repr(value)


def _inputs_phrase(names):
    return " and ".join(f"`{n}`" for n in names) + (" together" if len(names) > 1 else "")


def write_qaresult(case, result, inputs):
    """Write tests/data/<case>_qaresult.py from a freshly linted result."""
    repo = Path(__file__).resolve().parent.parent
    body = ["    profiling={"]
    for key, value in result.profiling.items():
        body.append(f"        {key!r}: {_profiling_value(key, value, repo)},")
    body.append("    },")
    body.append("    checks=[")
    for check in result.checks:
        body.append(f"        CheckResult(name={check.name!r}, key={check.key!r}, "
                    f"status={check.status!r}, count={check.count},")
        body.append(f"                    elements={check.elements!r},")
        if check.reason:
            body.append(f"                    reason={check.reason!r},")
        if check.outcome:
            body.append(f"                    outcome={check.outcome!r},")
        if check.notes:
            body.append(f"                    notes={check.notes!r},")
        for field_name in ('table', 'verbose_table'):
            value = getattr(check, field_name)
            if value:
                body.append(f"                    {field_name}={value!r},")
        if not check.violations:
            body.append("                    violations=[]),")
        else:
            rendered = ",\n                        ".join(_violation(v) for v in check.violations)
            body.append(f"                    violations=[{rendered}]),")
    body.append("    ],")
    body.append("    datasets=[" + ", ".join(
        f"Dataset(iri={d.iri!r}, label={d.label!r})" for d in result.datasets) + "],")
    body.append("    settings=[")
    for setting in result.settings:
        parts = [repr(setting.key), repr(setting.value), repr(setting.origin)]
        for name in ('reason', 'enabled', 'local_file', 'derived_from', 'label'):
            value = getattr(setting, name, None)
            if value is not None:
                parts.append(f"{name}={value!r}")
        body.append("        ConfigSetting(" + ", ".join(parts) + "),")
    body.append("    ],")
    text = "\n".join(body) + "\n"

    used = [n for n in ('XSD', 'BNode', 'Literal', 'URIRef') if f'{n}(' in text or f'={n}.' in text]
    imports = f"from rdflib import {', '.join(used)}\n\n" if used else ""
    path = DATA / f'{case}_qaresult.py'
    path.write_text(QARESULT_HEADER.format(inputs=_inputs_phrase(inputs), imports=imports)
                    + text + ")\n")
    return path


def write_markdown(case, rendered, inputs):
    """Write tests/data/<case>_markdown.py from a freshly rendered report."""
    # EXPECTED = """ already supplies the opening newline.
    body = rendered[1:] if rendered.startswith("\n") else rendered
    assert '"""' not in body, "the rendered report cannot be stored as a triple-quoted string"
    path = DATA / f'{case}_markdown.py'
    path.write_text(MARKDOWN_HEADER.format(inputs=_inputs_phrase(inputs)) + body + '"""\n')
    return path


# ── naming the nodes in a stored report ───────────────────────────────────────

MINTED = re.compile(r'[#/:](assessment|measurement|violation|dataset|configuration|setting|bnode)-\w{6,}$')

# Which of a node's parts to name it after, per kind. The rest still go into the digest.
NAMED_AFTER = {'measurement': -1, 'assessment': None}

# A configuration is named from the whole settings list, so adding one check renamed it and
# with it every olq:setting link — hundreds of lines saying nothing. A report has one
# configuration per result and the goldens have one result, so a constant name is enough;
# two differing configurations in one report would collide, which no golden has.
CONSTANT = {'configuration': 'effective'}


def stable_mint_id(kind, *parts):
    """
    A node name for the stored reports, in place of dqv.mint_id.

    The real scheme hashes every part that identifies a node, and those parts nest: a
    violation hashes its measurement, which hashes the assessment, which hashes the
    effective configuration — which lists every check. So adding one check renamed every
    node in every stored report, and the diff said nothing about what had changed.

    This drops the parts that are themselves minted IRIs, so a node is named after what it
    is about rather than after the run it belongs to, and prefixes a readable word. A
    report's *content* is what these goldens are for; that the real scheme is
    deterministic, unique per run and sensitive to the configuration is asserted directly
    in tests/test_dqv.py, which does not use this.
    """
    if kind in CONSTANT:
        return CONSTANT[kind]
    own = [str(p) for p in parts if p not in (None, '') and not MINTED.search(str(p))]
    digest = hashlib.sha256("\x1f".join(own).encode("utf-8")).hexdigest()[:8]
    index = NAMED_AFTER.get(kind, 0)
    if index is None or not own:
        return digest
    word = re.sub(r'[^a-zA-Z0-9]+', '-', own[index].rsplit('/', 1)[-1].rsplit('#', 1)[-1])
    return f"{word.strip('-')[:40].lower()}-{digest}" if word.strip('-') else digest
