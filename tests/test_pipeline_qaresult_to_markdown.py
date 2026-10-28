"""
QAResult -> Markdown: the stored `QAResult` renders the Markdown stored in
`tests/data/reporters_report.md`, and a fresh lint renders the same thing.

The stored text is the expectation, exactly as the stored QAResult is for the checks. The
assertions after it are not a second expectation — they say *why* parts of it must hold, so
a failure explains itself instead of handing over a 189-line diff.

Markdown is a projection of QAResult like the other two reporters (#101). The stored text
is unchanged by that move but for the inconsistencies it straightened out, which is how the
move was checked.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import CASES, render_result, stored_markdown_for, stored_qa_result_for
from tests.golden import write_markdown

# An rdflib blank node identifier: invented per parse, so it must never reach the report.
RAW_BNODE = re.compile(r'\bn[0-9a-f]{32}b\d+\b')


@pytest.mark.parametrize('case', CASES)
def test_it_renders_the_stored_markdown(case):
    """
    The projection, whole, from the **stored** QAResult.

    Like the CTRF and DQV suites, this takes the stored instance rather than a freshly
    linted one, so it tests the reporter alone: a change to what a check finds cannot break
    it, and a reporter bug cannot be blamed on the checks.

    Nothing here asserts that a *lint* renders this text, because nothing needs to: linting
    produces the stored instance (`test_pipeline_lint_to_qaresult.py`) and the stored
    instance renders this (above), so the composition holds. The tests below use a fresh
    lint for a different reason — to render twice and compare the renders, which is how
    instability shows up at all.
    """
    rendered = render_result(stored_qa_result_for(case))
    if os.environ.get('UPDATE_GOLDEN'):
        pytest.skip(f"updated {write_markdown(case, rendered, CASES[case]).name}")

    assert rendered == stored_markdown_for(case)


def test_it_renders_the_same_text_every_time(render_markdown):
    # Each call reparses: blank node identifiers and SPARQL row order differ between
    # parses, and without this the stored text could not be an expectation at all.
    assert render_markdown() == render_markdown()


# Two calls in one process cannot catch everything: PYTHONHASHSEED is fixed for a
# process's lifetime, so anything whose order follows a hash — a set of URIRefs, a
# GROUP_CONCAT cell — renders identically both times and varies between runs anyway.
# These seeds are a sample, not a proof; 0 and 1 are kept because they straddled the
# GROUP_CONCAT ordering bug that concat_members() fixes.
HASH_SEEDS = ("0", "1", "5")

RENDER_UNDER_SEED = """
import os, socket, sys
root, ctrf = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
os.environ.setdefault('QA_SPARQL_DIR', os.path.join(root, 'sparql'))

def blocked(*args, **kwargs):
    raise OSError("network access is blocked")
socket.getaddrinfo = blocked
socket.socket.connect = blocked

from scripts.ontology_qa import CHECKLIST, main
sys.argv = ['ontology_qa.py', os.path.join(root, 'tests/data/reporters.ttl'),
            '--ctrf-dir', ctrf]
main()
"""


def test_it_renders_the_same_text_under_any_hash_seed(tmp_path):
    # A subprocess per seed, because an interpreter cannot change its own hash seed. This
    # goes through main() rather than the render_markdown fixture: the fixture's seam was
    # stable under every seed while the CLI was not, so only the full path shows it.
    script = tmp_path / "render_under_seed.py"
    script.write_text(RENDER_UNDER_SEED)
    root = str(Path(__file__).resolve().parent.parent)

    rendered = {}
    for seed in HASH_SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        run = subprocess.run([sys.executable, str(script), root, str(tmp_path / "ctrf")],
                             capture_output=True, text=True, env=env, check=True)
        rendered[seed] = run.stdout

    first, *rest = HASH_SEEDS
    for seed in rest:
        assert rendered[seed] == rendered[first], (
            f"the report differs under PYTHONHASHSEED={seed}: something is rendered in "
            f"hash order rather than sorted"
        )


def test_no_blank_node_identifier_reaches_the_report(stored_markdown):
    assert not RAW_BNODE.search(stored_markdown), "a raw blank node identifier reached the report"




def test_the_metrics_table_scores_no_check_it_could_not_compute():
    """
    A skipped check gets no score, because every number in that row is one.

    It used to get the worst one. `normalise(count, total)` ends with
    `if count == total: out = 1`, and a check with nothing to measure has 0 of 0 — so
    *"no NodeShapes exist"* and *"every NodeShape is unlabelled"* rendered identically,
    while the section above said `WARNING - No NodeShape defined, invalid metric.`
    """
    result = stored_qa_result_for('fragment')
    skipped = {c.key for c in result.checks if c.status == 'skipped'}
    assert skipped, "the fragment case should skip several checks"

    # The last such row is the QA metrics table; the profiling table above it starts alike.
    row = [cell.strip() for cell in
           [line for line in render_result(result).splitlines()
            if line.startswith('| fragment.ttl |')][-1].strip('|').split('|')]
    # By count, not by column: print_qa_table writes its columns in its own order, which is
    # not the checklist's, so there is nothing to pair a cell with.
    assert row.count('skipped') == len(skipped), f"{len(skipped)} skipped, {row.count('skipped')} cells say so"
