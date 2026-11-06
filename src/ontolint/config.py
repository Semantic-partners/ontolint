"""
How a run is configured: the .rdf-lint.yml file read and written, which checks it
selects, and the record of the configuration a run actually used.

describe_configuration() is what the DQV report's olq:Configuration is built from - every
setting, with where it came from and why - so a consumer can tell what a result was
computed under.
"""
import os
import sys

import rdflib
import yaml

from . import dqv
from .checks.namespaces import DEFAULT_SKIP_OBJECT_OF
from .resolution import bundled_datasets, bundled_vocabularies, local_imports_from, RunInput
from .terms import expand_curie, iri_key


def parse_lint_config(config):
    """
    Parse configuration dictionary to switch on/off selected metrics.

    Args:
        config (str): Path to the YAML configuration file.

    Returns:
        transformed_selection (dict): User-selected metrics.
        ignore_imports (list): Import URLs skipped by the resolvability check.
        local_imports (dict): Mapping of remote URL -> local file path; used by both
            the owl:imports check (keyed on import URL) and the undefined-terms check
            (keyed on namespace URI).  Relative paths are resolved relative to the
            config file's directory.
        exclude_types (list): Type IRIs whose instances are skipped by the class checks
            (see TYPE_EXCLUDABLE_CHECKS).
        skip_object_of (list | None): Predicate IRIs (or `<namespace>*` wildcards) whose objects
            the undefined-terms check ignores; None when not configured (use the defaults).
        resolve_siblings (bool | None): Whether a run may resolve references against the
            other inputs of the same invocation; None when not configured (on by default).
    """
    if not os.path.isfile(config):
        raise FileNotFoundError(f"Config file not found: {config}")

    with open(config, "r", encoding="utf-8") as f:
        try:
            selection = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")

    if selection is None:
        selection = {"disable": []}

    imports_section = selection.pop("imports", None) or {}
    ignore_imports = [str(u) for u in (imports_section.get("ignore") or [])]
    raw_local = imports_section.get("local") or {}
    # imports.siblings: on unless the project turns it off. A run resolving against files
    # it is not checking is usually what is wanted (#108), but a project that lints a
    # directory of unrelated ontologies may want each judged strictly on its own.
    resolve_siblings = imports_section.get("siblings")
    if resolve_siblings is not None and not isinstance(resolve_siblings, bool):
        raise ValueError(f"imports.siblings must be true or false, got {resolve_siblings!r}")
    config_dir = os.path.dirname(os.path.abspath(config))
    local_imports = {
        str(url): (path if os.path.isabs(path) else os.path.join(config_dir, path))
        for url, path in raw_local.items()
    }

    exclude_section = selection.pop("exclude", None) or {}
    exclude_types = [expand_curie(str(t)) for t in (exclude_section.get("types") or [])]

    # undefined-terms.skip-object-of replaces the defaults when present (an empty list skips nothing).
    undefined_section = selection.pop("undefined-terms", None) or {}
    if "skip-object-of" in undefined_section:
        skip_object_of = [expand_curie(str(t), allow_wildcard=True)
                          for t in (undefined_section["skip-object-of"] or [])]
    else:
        skip_object_of = None

    # Transform the dictionary (check enable/disable keys only)
    transformed_selection = {
        key: [f"check_{item.replace('-', '_')}" for item in value_list]
        for key, value_list in selection.items()
    }

    return (transformed_selection, ignore_imports, local_imports, exclude_types,
            skip_object_of, resolve_siblings)


def lint_selection(selection, checklist, rule_reasons=None):
        """
        Disable the tests that are not included in the 'enable' list or that are included in the 'disable' list.
        The 'enable' and 'disable' keys are mutually exclusive. If both are specified in the configuration file,
        only the first dictionary will be used.
        """
        log = "> Lint configuration file found!\n"
        if 'enable' in selection and isinstance(selection['enable'], list):
            for i, item in enumerate(checklist):
                if item[1].__name__ not in selection['enable']: checklist[i][0] = False
        
        elif 'disable' in selection and isinstance(selection['disable'], list):
            for i, item in enumerate(checklist):
                if item[1].__name__ in selection['disable']: checklist[i][0] = False
        
        elif selection:
            # Non-empty dict with no recognised top-level key
            log += ">\n> WARNING - Invalid keyword in config file:\n> ```yaml\n"
            log += "> " + "> ".join(yaml.dump(selection, default_flow_style=False).splitlines(keepends=True))
            log += "> ```"
        
        # A check whose condition another needs is enabled with it, so a dependent check
        # has something to stand on and the report can say why it could not run. The
        # dependencies are declared once, in dqv.DQV_DEPENDENCIES, and published there too.
        by_key = {item[3]: item for item in checklist}
        for key, (required, _why) in sorted(dqv.DQV_DEPENDENCIES.items()):
            dependent, prerequisite = by_key[key], by_key[required]
            if dependent[0] and not prerequisite[0]:
                prerequisite[0] = True
                selected = config_check_name(dependent[1], key)
                log += (f"> WARNING: Check '{prerequisite[2]}' has been enabled because "
                        f"check '{dependent[2]}' was selected and depends on it.\n")
                if rule_reasons is not None:
                    rule_reasons[required] = (f"Enabled because the {selected} check was selected "
                                              "and depends on it.")
        return checklist, log


def config_check_name(func, key):
    """The name a check has in .rdf-lint.yml enable/disable lists (e.g. 'class-missing-label')."""
    return func.__name__.removeprefix('check_').replace('_', '-')


def describe_configuration(checklist, lint_config=None, rule_reasons=None, ignore_imports=None,
                           local_imports=None, exclude_types=None, skip_object_of=None,
                           config_file=None, resolve_siblings=None):
    """
    The configuration a run actually uses, as dqv.ConfigSetting records. Each records the
    .rdf-lint.yml key it corresponds to and where it came from: the config file, an
    ontolint default (e.g. a check enabled by default, the default skip-object-of list),
    a vocabulary bundled with ontolint (imports.local), or an ontolint rule (a check
    enabled because another depends on it). Without a config_file, values passed straight
    to run_qa() are recorded as coming from its caller. local_imports is the project's own
    mapping, before the bundled vocabularies are merged in.
    """
    selection = lint_config or {}
    rule_reasons = rule_reasons or {}
    given = 'config' if config_file else 'caller'
    settings = []

    for enabled, func, display_name, key in checklist:
        # enable:/disable: lists hold names as check_<name>, see parse_lint_config.
        config_name = f"check_{config_check_name(func, key).replace('-', '_')}"
        if key in rule_reasons:
            origin, reason = 'rule', rule_reasons[key]
        elif isinstance(selection.get('enable'), list):
            origin = given
            reason = ("Listed under enable:" if config_name in selection['enable']
                      else "Not listed under enable:, so not run")
        elif isinstance(selection.get('disable'), list) and config_name in selection['disable']:
            origin, reason = given, "Listed under disable:"
        elif not enabled:
            # Every check is enabled by default, so one that isn't was switched off by the caller.
            origin, reason = 'caller', "Disabled by the caller"
        else:
            origin, reason = 'default', "Enabled by default"
        settings.append(dqv.ConfigSetting('checks', key, origin, reason, enabled=bool(enabled), label=display_name))

    for iri in ignore_imports or []:
        settings.append(dqv.ConfigSetting('imports.ignore', iri, given,
                                          "Trusted: never fetched or reported, and not resolved as an import"))

    config_dir = os.path.dirname(os.path.abspath(config_file)) if config_file else None
    user_local = {iri_key(k): (k, v) for k, v in (local_imports or {}).items()}
    datasets = bundled_datasets()
    bundled_by_key = {iri_key(ns): ns for ns in bundled_vocabularies()}
    for k, (iri, path) in user_local.items():
        overrides = bundled_by_key.get(k)
        if isinstance(path, RunInput):
            # Another input of the same invocation, named so it is explicit which ontology
            # the run resolved from where. Nobody configured it — it is derived from what
            # was passed in — so it is its own origin, and a per-file run's configuration
            # then differs per file, because its resolution context genuinely does.
            shown = path.source
            reason = ("Resolved from another input of this run, which declares it"
                      + ("; overrides the bundled vocabulary" if overrides else ""))
            settings.append(dqv.ConfigSetting('imports.local', iri, 'input', reason,
                                              local_file=shown,
                                              derived_from=datasets.get(overrides) if overrides else None))
            continue
        if isinstance(path, rdflib.Graph):
            # Supplied through the programmatic API: there is no file to name.
            shown = None
            reason = ("Resolved from a graph supplied by the caller; overrides the bundled vocabulary"
                      if overrides else "Resolved from a graph supplied by the caller")
        else:
            try:
                shown = os.path.relpath(path, config_dir) if config_dir else path
            except ValueError:  # Windows: the file is on another drive than the config file
                shown = path
            reason = ("Resolved from a local file instead of the network; overrides the bundled vocabulary"
                      if overrides else "Resolved from a local file instead of the network")
        settings.append(dqv.ConfigSetting('imports.local', iri, given, reason, local_file=shown,
                                          derived_from=datasets.get(overrides) if overrides else None))
    for ns, path in bundled_vocabularies().items():
        if iri_key(ns) not in user_local:
            settings.append(dqv.ConfigSetting('imports.local', ns, 'bundled',
                                              "Bundled with ontolint; resolved offline",
                                              local_file=os.path.basename(path), derived_from=datasets.get(ns)))

    # Whether a run may resolve against the files it is not checking changes what the
    # undefined-terms result means, so a consumer is told it was in force — as the setting
    # it is, not as one entry per sibling, which would differ from run to run (#108).
    settings.append(dqv.ConfigSetting(
        'imports.siblings', resolve_siblings is not False,
        'config' if resolve_siblings is not None else 'default',
        "References may resolve against the other inputs of this run, without fetching them"
        if resolve_siblings is not False else
        "Each input is checked on its own; references do not resolve against the other inputs"))

    for t in exclude_types or []:
        settings.append(dqv.ConfigSetting('exclude.types', t, given,
                                          "Instances are skipped by the class checks"))

    if skip_object_of is not None:
        for p in skip_object_of:
            settings.append(dqv.ConfigSetting('undefined-terms.skip-object-of', p, given,
                                              "Objects of this property are not checked as terms"))
    else:
        for p in DEFAULT_SKIP_OBJECT_OF:
            settings.append(dqv.ConfigSetting('undefined-terms.skip-object-of', expand_curie(p, allow_wildcard=True),
                                              'default', "ontolint default; undefined-terms.skip-object-of is not set"))
    return settings


def config_kwargs(config):
    """The run_qa() arguments a Config maps to, leaving the empty ones at their defaults."""
    kwargs = {}
    if config.imports:
        kwargs['local_imports'] = local_imports_from(config.imports)
    if config.ignore_imports:
        kwargs['ignore_imports'] = [str(i) for i in config.ignore_imports]
    if config.exclude_types:
        kwargs['exclude_types'] = [expand_curie(str(t)) for t in config.exclude_types]
    if config.skip_object_of is not None:
        kwargs['skip_object_of'] = [expand_curie(str(p), allow_wildcard=True) for p in config.skip_object_of]
    if config.uri_parser is not None:
        kwargs['uri_parser'] = config.uri_parser
    return kwargs


def write_lint_config(checklist):
    """
    Generate a default .rdf-lint.yml config file
    """
    sys.stderr.write("Ontolint: creating default configuration file .rdf-lint.yml in the current directory.\n")

    # abort if path exists
    path = os.path.join(os.getcwd(), '.rdf-lint.yml')
    if os.path.exists(path):
        sys.stderr.write(f"ERROR: configuration file already exists: {path}\n\n")
        sys.exit(1)

    sequence = sorted(config_check_name(func, key) for _, func, _, key in checklist)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"""\
# Ontolint configuration file: use it to enable or disable specific QA checks.
# Place this file as .rdf-lint.yml in your project root.\n
# Available checks:
{chr(10).join(f'# - {s}' for s in sequence)}\n
# Enable only specific checks (empty = all checks enabled)
# enable:
#   - owl-description
#   - class-missing-label
#   - property-missing-label\n
# Disable specific checks
# disable:
#   - hijacking
#   - isolated-classes
#   - property-missing-domain\n
# Import settings: trust (ignore) namespaces or resolve them from local files.
# Core vocabularies (RDF, RDFS, OWL, XSD, SHACL, SKOS, Dublin Core, FOAF, schema.org, ...)
# are bundled with ontolint and resolve offline without any entry here.
# 'ignore': never fetched or reported by undefined-terms, not resolved by owl-imports.
# 'local': namespace or owl:imports IRI -> file; overrides the bundled copy.
# Entries match with or without a trailing '#' or '/'. Relative paths are resolved
# relative to this config file.
# imports:
#   ignore:
#     - http://example.org/vendor/ns#
#   local:
#     http://www.w3.org/ns/shacl#: local/shacl-1.2.ttl\n
# Skip resources of the listed types in the class checks (class-missing-label,
# class-missing-comment, class-same-label, isolated-classes, untyped-class).
# Accepts full IRIs or rdf:/rdfs:/owl:/xsd:/skos:/sh:/dcterms:/foaf:/schema:/vs: compact IRIs.
# e.g. rdf:PropositionForm stand-ins produced when downgrading RDF 1.2 to RDF 1.1.
# exclude:
#   types:
#     - rdf:PropositionForm\n
# The undefined-terms check ignores objects of reference properties, which link to
# documents rather than terms. Defaults (used when this key is absent):
{chr(10).join(f'#   {p}' for p in DEFAULT_SKIP_OBJECT_OF)}
# Listing properties here replaces the defaults; `prefix:*` matches a namespace and
# an empty list checks every object.
# undefined-terms:
#   skip-object-of:
#     - rdfs:seeAlso
#     - dcterms:license
        """)


def _relative_path(path, start=None):
    """path relative to start (default: the working directory), or None when it is outside it."""
    try:
        relative = os.path.relpath(os.path.abspath(path), start)
    except ValueError:  # Windows: path and start are on different drives
        return None
    # By component, so an in-tree directory named e.g. '..config' still counts as inside.
    return None if relative == os.pardir or relative.startswith(os.pardir + os.sep) else relative


def _display_path(path):
    """A path as shown in reports: relative to the working directory when inside it."""
    return _relative_path(path) or path
