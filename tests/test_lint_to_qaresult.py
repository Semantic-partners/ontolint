"""
lint -> QAResult: linting `tests/data/reporters.ttl` produces the QAResult written out in
`tests/data/reporters_qaresult.py`.

That stored instance is the input to the reporter suites, so this is the test that keeps it
honest. When a check changes on purpose, this fails and the stored instance is edited to
match — deliberately, in a diff a reviewer can read.

`logs` and `elements` are not compared: they are the Markdown's raw material and are left
empty in the stored instance (see its docstring). `test_lint_to_markdown.py` covers them.
"""


def test_the_same_checks_ran(reporters_result, stored_result):
    assert [c.key for c in reporters_result.checks] == [c.key for c in stored_result.checks]


def test_every_check_decided_the_same(reporters_result, stored_result):
    actual = {c.key: c for c in reporters_result.checks}

    for expected in stored_result.checks:
        assert actual[expected.key] == expected, (
            f"{expected.name} differs:\n  linted: {actual[expected.key]}\n  stored: {expected}")


def test_the_same_checks_failed(reporters_result, stored_result):
    # Stated separately so a change in what fails reads as that, rather than as a diff
    # buried in twenty-four check objects.
    assert ({c.name: c.count for c in reporters_result.failures}
            == {c.name: c.count for c in stored_result.failures})


def test_the_profiling_metrics_match(reporters_result, stored_result):
    assert reporters_result.profiling == stored_result.profiling


def test_the_datasets_match(reporters_result, stored_result):
    assert reporters_result.datasets == stored_result.datasets


def test_the_configuration_that_ran_matches(reporters_result, stored_result):
    assert reporters_result.settings == stored_result.settings


def test_the_remaining_fields_match(reporters_result, stored_result):
    assert reporters_result.bnode_keys == stored_result.bnode_keys
    assert reporters_result.config_file == stored_result.config_file
    assert reporters_result.inference_log == stored_result.inference_log


def test_the_stored_instance_is_a_failing_run(stored_result):
    # If it ever became clean the reporter suites would stop exercising violations at all.
    assert not stored_result.passed
    assert stored_result.failures
