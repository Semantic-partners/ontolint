"""
The checks, one module per family.

Deliberately empty: the registry that lists them in order and resolves a selection is
ontolint.registry, not this package. Putting it here would make importing any one check
run the registry first — and the registry imports the configuration code, which imports
the undefined-terms check's default list from here. That is a cycle.
"""
