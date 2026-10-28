"""
lint -> Markdown: linting `tests/data/reporters.ttl` renders the Markdown stored in
`tests/data/reporters_markdown.py`.

The stored text is the expectation, exactly as the stored QAResult is for the checks. The
assertions after it are not a second expectation — they say *why* parts of it must hold, so
a failure explains itself instead of handing over a 189-line diff.

Markdown is the one reporter that is not a projection of QAResult: the per-check text is
rendered inside each check as it runs (see design.md). When that moves, the stored text
stays as it is and only the way it is produced changes — which is how the move gets checked.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import CASES, render_case, stored_markdown_for
from tests.golden import write_markdown

# An rdflib blank node identifier: invented per parse, so it must never reach the report.
RAW_BNODE = re.compile(r'\bn[0-9a-f]{32}b\d+\b')


@pytest.mark.parametrize('case', CASES)
def test_a_lint_renders_the_stored_markdown(case):
    """Every case, whole. The assertions below are about the main case's content."""
    rendered = render_case(case)
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

from scripts.ontology_qa import main
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


