"""
lint -> QAResult: linting `tests/data/reporters.ttl` produces the QAResult written out in
`tests/data/reporters_qaresult.py`.

That stored instance is the input to the reporter suites, so this is the test that keeps it
honest. When a check changes on purpose, this fails and the stored instance is edited to
match — deliberately, in a diff a reviewer can read.

`logs` and `elements` are not compared: they are the Markdown's raw material and are left
empty in the stored instance (see its docstring). `test_lint_to_markdown.py` covers them.
"""

from pathlib import Path, PurePath

import pytest

from tests.conftest import CASES, lint_case, stored_qa_result_for


@pytest.mark.parametrize('case', CASES)
def test_a_lint_produces_the_stored_result(case):
    """
    Every case, whole. The assertions below take the main case apart field by field, so a
    failure there says which field; this one says which case.
    """
    produced = lint_case(case)
    stored = stored_qa_result_for(case)

    assert _repo_relative(produced.profiling) == stored.profiling
    assert produced.checks == stored.checks
    assert produced.datasets == stored.datasets
    assert produced.settings == stored.settings


def test_no_stored_expectation_embeds_a_checkout_path():
    """
    A stored expectation that names where the repo lives matches only the machine that
    wrote it. It has happened twice — fetchActivity's vocabulary paths, and a violation
    naming its source file — and both times the suite was green locally and red in CI, so
    this asserts the class rather than the two instances.
    """
    repo = Path(__file__).resolve().parent.parent
    offenders = []
    for stored in sorted((repo / 'tests' / 'data').iterdir()):
        if stored.suffix not in ('.py', '.json', '.ttl'):
            continue
        text = stored.read_text()
        if str(repo) in text:
            offenders.append(f"{stored.name}: contains the repo root")
        if 'file:///' in text:
            # Minted from the working directory, so it is a checkout path by construction.
            offenders.append(f"{stored.name}: contains a file: IRI")

    assert not offenders, "\n".join(offenders)


def test_the_fragment_is_the_only_case_failing_the_metadata_checks():
    """
    The reason the fragment exists. reporters.ttl declares a described ontology, so it
    cannot fail either check; the fragment declares none, so it fails both.
    """
    failed = {case: {c.key for c in stored_qa_result_for(case).failures} for case in CASES}

    assert 'ontologyDescription' in failed['fragment']
    assert 'ontologyDescription' not in failed['reporters']
    # Declaration is the three-way one: none of the files declared an ontology, some did,
    # all did. The merged case is the only one that reaches the middle branch.
    assert 'ontologyNotDeclared' in failed['fragment']
    assert 'ontologyNotDeclared' in failed['merged']
    assert 'ontologyNotDeclared' not in failed['reporters']


def test_batching_the_same_files_changes_the_answer():
    """
    Grouping is not neutral, which is the whole of #96. The fragment's terms sit outside
    the only declared namespace once the two are merged, so they become hijacking; and its
    predicates stop being reported as untyped, because that check's namespace guard has an
    ontology to bind to again.
    """
    alone = {c.key: c.count for c in stored_qa_result_for('fragment').failures}
    merged = {c.key: c.count for c in stored_qa_result_for('merged').failures}

    assert 'hijacking' not in alone and merged['hijacking'] > 0
    assert alone['untypedProperties'] > merged.get('untypedProperties', 0)


def test_the_same_checks_ran(reporters_result, stored_qa_result):
    assert [c.key for c in reporters_result.checks] == [c.key for c in stored_qa_result.checks]


def test_every_check_decided_the_same(reporters_result, stored_qa_result):
    actual = {c.key: c for c in reporters_result.checks}

    for expected in stored_qa_result.checks:
        assert actual[expected.key] == expected, (
            f"{expected.name} differs:\n  linted: {actual[expected.key]}\n  stored: {expected}")


def test_the_same_checks_failed(reporters_result, stored_qa_result):
    # Stated separately so a change in what fails reads as that, rather than as a diff
    # buried in twenty-four check objects.
    assert ({c.name: c.count for c in reporters_result.failures}
            == {c.name: c.count for c in stored_qa_result.failures})


def test_the_profiling_metrics_match(reporters_result, stored_qa_result):
    assert _repo_relative(reporters_result.profiling) == stored_qa_result.profiling


def _repo_relative(profiling):
    """
    `profiling` with fetchActivity's vocabulary paths relative to the repo root.

    fetchActivity records where each namespace was resolved from, and a bundled vocabulary
    resolves to an absolute path under VOCAB_DIR — so the raw value names the checkout, not
    the run. Stored absolute, the expectation matched only the machine that generated it and
    failed everywhere else, CI included. Relative, it still pins which vocabulary resolved
    which namespace, which is the part worth pinning.
    """
    activity = profiling.get('fetchActivity')
    if not activity or not activity.get('local'):
        return profiling
    root = Path(__file__).resolve().parent.parent
    local = {ns: _relative_to(path, root) for ns, path in activity['local'].items()}
    return {**profiling, 'fetchActivity': {**activity, 'local': local}}


def _relative_to(path, root):
    # A caller-supplied graph has no path, and a vocabulary outside the checkout keeps its
    # own, so neither is rewritten into something misleading.
    if not isinstance(path, (str, PurePath)):
        return path
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        return path


def test_the_datasets_match(reporters_result, stored_qa_result):
    assert reporters_result.datasets == stored_qa_result.datasets


def test_the_configuration_that_ran_matches(reporters_result, stored_qa_result):
    assert reporters_result.settings == stored_qa_result.settings


def test_the_remaining_fields_match(reporters_result, stored_qa_result):
    assert reporters_result.bnode_keys == stored_qa_result.bnode_keys
    assert reporters_result.config_file == stored_qa_result.config_file
    assert reporters_result.inference_log == stored_qa_result.inference_log


def test_the_stored_instance_is_a_failing_run(stored_qa_result):
    # If it ever became clean the reporter suites would stop exercising violations at all.
    assert not stored_qa_result.passed
    assert stored_qa_result.failures
