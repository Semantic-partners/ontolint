"""
Ontolint: ontology quality assessment.

`lint()` checks graphs you already hold in memory and hands back the results as a DQV
graph, with no temporary files, config file or subprocess in between:

    from ontolint import Config, lint

    report = lint([activities_graph, parties_graph], config=Config(per_file=True))

Hand over the graphs and nothing else: a graph that declares its own `owl:Ontology` is
reported under that IRI, so there is nothing to name. Pass a mapping of names instead
where a graph declares none and you want it identified across runs. See `ontolint.api`
for the full Config.
"""

from .api import Config, lint

__all__ = ["Config", "lint"]
