"""
Ontolint: ontology quality assessment.

`lint()` checks graphs you already hold in memory and hands back the results as a DQV
graph, with no temporary files, config file or subprocess in between:

    from ontolint import Config, lint

    report = lint({"https://example.org/core": my_graph}, config=Config(per_file=True))

Name each dataset by its ontology IRI where you have one: that IRI identifies it in the
report, so results from different runs line up.

See `ontolint.api` for the full Config, and `lint_results()` for the structured
pass/fail of each check.
"""

from .api import CheckResult, Config, QAResult, lint, lint_results

__all__ = ["Config", "lint", "lint_results", "CheckResult", "QAResult"]
