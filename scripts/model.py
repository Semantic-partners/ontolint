"""
What a run produces and how a check records it: the types every other layer shares.

A check records its verdict, its remarks and its tables here through decided(), note() and
tabulate(), and renders nothing. A reporter reads a QAResult and lays it out. Neither knows
about the other, so this module sits below both — which is what lets each reporter be
tested against a stored QAResult without running a check (see design.md).
"""
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TypeAlias

import rdflib

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts import dqv
    from scripts.terms import term_text
except ImportError:  # run as a script: scripts/ itself is on sys.path
    import dqv
    from terms import term_text


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
    body: list = field(default_factory=list)    # the parts of its section, in order

    @property
    def passed(self):
        """A check that could not be computed is not a failure, so it does not fail a build."""
        return self.status != 'failed'


@dataclass
class QAResult:
    profiling: dict
    checks: list
    elements: dict = field(default_factory=dict)
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
    resolve_siblings: with per_file, let each dataset resolve references against the
                    other datasets of the same call, so a family that refers to itself
                    needs no `imports` entries for its own members. A dataset answers only
                    for the ontology it declares. Set False to check each one strictly
                    alone.
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
    resolve_siblings: bool = True
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


def body_key(check):
    """Key under which a check records the parts of its section, in order."""
    return (check, 'body')


def _part(violations, check, kind, *payload):
    """Append one part to a check's section. Order is the order they are recorded in."""
    violations.setdefault(body_key(check), []).append((kind, *payload))


def decided(violations, check, sentence, detail=None):
    """
    Record what a check decided: a sentence, and whether its elements are listed under it.

    The verdict is kept apart from the rest of the section as well as placed in it, because
    it is the one part a consumer other than a reporter might want.
    """
    violations[outcome_key(check)] = (sentence, detail)
    _part(violations, check, 'text', sentence)
    if detail == AS_LIST:
        _part(violations, check, 'elements')


def note(violations, check, line):
    """Add a line to a check's section — a caveat, an aside, a heading for what follows."""
    _part(violations, check, 'text', line)


def tabulate(violations, check, headers, rows, verbose_only=False):
    """
    Record a table a check produced: its column headings and its rows of cells.

    The rows are data, not Markdown, so a reporter lays them out — including the ones only
    a verbose run shows, which are a second query's worth of detail rather than a finding.
    """
    _part(violations, check, 'verbose-table' if verbose_only else 'table',
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


# Where inferred triples live in a Dataset: not a file, so not one of the file contexts.
INFERRED_CONTEXT = rdflib.URIRef("urn:ontolint:inferred")


def source_iris(in_metrics):
    """
    One IRI per processed source, to name it in a violation.

    'sourceIRIs' is set when the caller named its sources itself (the programmatic API,
    whose graphs are not files); otherwise each entry of 'filesProcessed' is a path and
    gets a file: IRI.
    """
    named = in_metrics.get('sourceIRIs') or []
    return [str(iri) for iri in named] or [dqv.file_iri(f) for f in in_metrics.get('filesProcessed', [])]
