import os
import pytest
from scripts.ontology_qa import (parse_lint_config, lint_selection, run_qa, CHECKLIST, deepcopy_list,
                                 describe_configuration, _display_path)


# ── parse_lint_config ─────────────────────────────────────────────────────────

def test_parse_lint_config_disable_transforms_keys(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("disable:\n  - class-missing-label\n  - hijacking\n")
    result, ignore, local, _, _ = parse_lint_config(str(cfg))
    assert result == {"disable": ["check_class_missing_label", "check_hijacking"]}
    assert ignore == []
    assert local == {}


def test_parse_lint_config_enable_transforms_keys(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("enable:\n  - class-missing-label\n")
    result, ignore, local, _, _ = parse_lint_config(str(cfg))
    assert result == {"enable": ["check_class_missing_label"]}
    assert ignore == []
    assert local == {}


def test_parse_lint_config_empty_file_returns_disable_empty(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("")
    result, ignore, local, _, _ = parse_lint_config(str(cfg))
    assert result == {"disable": []}
    assert ignore == []
    assert local == {}


def test_parse_lint_config_imports_ignore_returned_separately(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text(
        "disable:\n  - hijacking\n"
        "imports:\n"
        "  ignore:\n"
        "    - http://www.w3.org/ns/shacl\n"
        "    - https://schema.org/\n"
    )
    result, ignore, local, _, _ = parse_lint_config(str(cfg))
    assert result == {"disable": ["check_hijacking"]}
    assert ignore == ["http://www.w3.org/ns/shacl", "https://schema.org/"]
    assert local == {}


def test_parse_lint_config_imports_ignore_only(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("imports:\n  ignore:\n    - http://example.org/ont\n")
    result, ignore, local, _, _ = parse_lint_config(str(cfg))
    assert result == {}
    assert ignore == ["http://example.org/ont"]
    assert local == {}


def test_parse_lint_config_imports_local_absolute_path(tmp_path):
    local_file = tmp_path / "copy.ttl"
    local_file.write_text("")
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text(
        f"imports:\n  local:\n    http://remote.example.org/ont.ttl: {local_file}\n"
    )
    result, ignore, local, _, _ = parse_lint_config(str(cfg))
    assert ignore == []
    assert local == {"http://remote.example.org/ont.ttl": str(local_file)}


def test_parse_lint_config_imports_local_relative_path_resolved(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text(
        "imports:\n  local:\n    http://remote.example.org/ont.ttl: copy.ttl\n"
    )
    _, _, local, _, _ = parse_lint_config(str(cfg))
    expected = str(tmp_path / "copy.ttl")
    assert local == {"http://remote.example.org/ont.ttl": expected}


def test_parse_lint_config_imports_ignore_and_local_together(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text(
        "imports:\n"
        "  ignore:\n"
        "    - http://ignored.invalid/ont.ttl\n"
        "  local:\n"
        "    http://remote.example.org/ont.ttl: copy.ttl\n"
    )
    result, ignore, local, _, _ = parse_lint_config(str(cfg))
    assert ignore == ["http://ignored.invalid/ont.ttl"]
    assert "http://remote.example.org/ont.ttl" in local


def test_parse_lint_config_exclude_types_expands_curies(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text(
        "exclude:\n"
        "  types:\n"
        "    - rdf:PropositionForm\n"
        "    - http://example.org/ns#StandIn\n"
    )
    result, _, _, exclude_types, _ = parse_lint_config(str(cfg))
    assert exclude_types == [
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#PropositionForm",
        "http://example.org/ns#StandIn",
    ]
    # exclude: is not treated as an enable/disable key
    assert result == {}


def test_parse_lint_config_exclude_types_defaults_empty(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("disable:\n  - hijacking\n")
    _, _, _, exclude_types, _ = parse_lint_config(str(cfg))
    assert exclude_types == []


def test_parse_lint_config_exclude_types_unknown_prefix_raises(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("exclude:\n  types:\n    - ex:StandIn\n")
    with pytest.raises(ValueError):
        parse_lint_config(str(cfg))


def test_parse_lint_config_skip_object_of_expands_curies_and_wildcards(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text(
        "undefined-terms:\n"
        "  skip-object-of:\n"
        "    - rdfs:seeAlso\n"
        "    - vs:*\n"
        "    - http://example.org/ns#docs\n"
    )
    result, _, _, _, skip_object_of = parse_lint_config(str(cfg))
    assert skip_object_of == [
        "http://www.w3.org/2000/01/rdf-schema#seeAlso",
        "http://www.w3.org/2003/06/sw-vocab-status/ns#*",
        "http://example.org/ns#docs",
    ]
    # undefined-terms: is a config section, not an enable/disable key.
    assert result == {}


def test_parse_lint_config_skip_object_of_absent_is_none(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("disable:\n  - hijacking\n")
    assert parse_lint_config(str(cfg))[4] is None


def test_parse_lint_config_skip_object_of_empty_is_empty_list(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("undefined-terms:\n  skip-object-of: []\n")
    assert parse_lint_config(str(cfg))[4] == []


def test_parse_lint_config_skip_object_of_unknown_prefix_raises(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("undefined-terms:\n  skip-object-of:\n    - ex:docs\n")
    with pytest.raises(ValueError):
        parse_lint_config(str(cfg))


def test_parse_lint_config_exclude_types_rejects_wildcard(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("exclude:\n  types:\n    - vs:*\n")
    with pytest.raises(ValueError):
        parse_lint_config(str(cfg))


def test_parse_lint_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_lint_config(str(tmp_path / "nonexistent.yml"))


# ── lint_selection ────────────────────────────────────────────────────────────

def _enabled_names(checklist):
    return {item[1].__name__ for item in checklist if item[0]}


def _disabled_names(checklist):
    return {item[1].__name__ for item in checklist if not item[0]}


def test_lint_selection_disable_removes_check():
    checklist = deepcopy_list(CHECKLIST)
    selection = {"disable": ["check_hijacking"]}
    checklist, _ = lint_selection(selection, checklist)
    assert "check_hijacking" in _disabled_names(checklist)
    assert "check_class_missing_label" in _enabled_names(checklist)


def test_lint_selection_disable_multiple_checks():
    checklist = deepcopy_list(CHECKLIST)
    selection = {"disable": ["check_hijacking", "check_isolated_classes"]}
    checklist, _ = lint_selection(selection, checklist)
    disabled = _disabled_names(checklist)
    assert "check_hijacking" in disabled
    assert "check_isolated_classes" in disabled


def test_lint_selection_enable_only_keeps_listed_checks():
    checklist = deepcopy_list(CHECKLIST)
    selection = {"enable": ["check_class_missing_label", "check_property_missing_label"]}
    checklist, _ = lint_selection(selection, checklist)
    enabled = _enabled_names(checklist)
    assert enabled == {"check_class_missing_label", "check_property_missing_label"}


def test_lint_selection_enable_uses_first_key_when_both_present():
    # enable takes precedence over disable (first key wins)
    checklist = deepcopy_list(CHECKLIST)
    selection = {"enable": ["check_class_missing_label"], "disable": ["check_hijacking"]}
    checklist, _ = lint_selection(selection, checklist)
    enabled = _enabled_names(checklist)
    # only class-missing-label should be enabled; disable is ignored
    assert enabled == {"check_class_missing_label"}


def test_lint_selection_invalid_key_produces_warning():
    checklist = deepcopy_list(CHECKLIST)
    selection = {"unknown-key": ["check_class_missing_label"]}
    checklist, log = lint_selection(selection, checklist)
    assert "WARNING" in log
    # all checks remain enabled
    assert len(_disabled_names(checklist)) == 0


def test_lint_selection_disable_domain_leaves_range_enabled():
    checklist = deepcopy_list(CHECKLIST)
    selection = {"disable": ["check_property_missing_domain"]}
    checklist, _ = lint_selection(selection, checklist)
    domain_entry = next(item for item in checklist if item[3] == 'missingDomain')
    range_entry  = next(item for item in checklist if item[3] == 'missingRange')
    assert not domain_entry[0]
    assert range_entry[0]


def test_lint_selection_disable_range_leaves_domain_enabled():
    checklist = deepcopy_list(CHECKLIST)
    selection = {"disable": ["check_property_missing_range"]}
    checklist, _ = lint_selection(selection, checklist)
    domain_entry = next(item for item in checklist if item[3] == 'missingDomain')
    range_entry  = next(item for item in checklist if item[3] == 'missingRange')
    assert domain_entry[0]
    assert not range_entry[0]


# ── run_qa with filtered checklist ────────────────────────────────────────────
#
# Same ontology: Cat has a label but no description.
# Scenario 1 — enable only class-missing-label  → passes (label is present)
# Scenario 2 — also enable class-missing-comment → fails  (description is absent)

def test_enable_single_check_passes_when_satisfied(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; rdfs:label "Cat" .
    """)
    checklist = deepcopy_list(CHECKLIST)
    checklist, _ = lint_selection({"enable": ["check_class_missing_label"]}, checklist)
    result = run_qa(g, checklist=checklist)
    assert result.get("Class without label").passed


def test_enable_additional_check_exposes_violation(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; rdfs:label "Cat" .
    """)
    checklist = deepcopy_list(CHECKLIST)
    checklist, _ = lint_selection(
        {"enable": ["check_class_missing_label", "check_class_missing_comment"]}, checklist
    )
    result = run_qa(g, checklist=checklist)
    assert result.get("Class without label").passed
    assert not result.get("Class without description").passed


# ── end-to-end via main() ─────────────────────────────────────────────────────

TESTS_DIR = os.path.join(os.path.dirname(__file__))


def run_main(*args):
    from unittest.mock import patch
    from scripts.ontology_qa import main
    with patch('sys.argv', ['ontology_qa.py', *args]):
        main()


def test_main_accepts_config_flag(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("disable:\n  - hijacking\n")
    ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    # should not raise
    run_main(ttl, '-c', str(cfg), '--ctrf-dir', str(tmp_path))
    reports = list(tmp_path.glob('*.json'))
    assert len(reports) == 1


def test_main_disable_via_config_marks_check_as_passed_in_ctrf(tmp_path):
    import json
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("disable:\n  - hijacking\n")
    # example_failure.ttl has Namespace hijacking violations; disabling it should not appear in results
    ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    run_main(ttl, '-c', str(cfg), '--ctrf-dir', str(tmp_path))
    data = json.loads(list(tmp_path.glob('*.json'))[0].read_text())
    assert not any(t['name'] == 'Namespace hijacking' for t in data['results']['tests'])


# ── config paths as shown in reports ─────────────────────────────────────────

def test_display_path_relative_inside_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _display_path(str(tmp_path / 'cfg' / '.rdf-lint.yml')) == os.path.join('cfg', '.rdf-lint.yml')


def test_display_path_keeps_paths_outside_working_directory(tmp_path, monkeypatch):
    (tmp_path / 'work').mkdir()
    monkeypatch.chdir(tmp_path / 'work')
    outside = str(tmp_path / 'other' / '.rdf-lint.yml')
    assert _display_path(outside) == outside


def test_display_path_dot_dot_named_directory_is_inside(tmp_path, monkeypatch):
    # '..config' starts with '..' but is a directory in the working tree, not its parent.
    monkeypatch.chdir(tmp_path)
    assert _display_path(str(tmp_path / '..config' / 'x.yml')) == os.path.join('..config', 'x.yml')


def _relpath_across_drives(path, start=None):
    raise ValueError("path is on mount 'D:', start on mount 'C:'")


def test_display_path_on_another_drive_falls_back_to_the_path(monkeypatch):
    # On Windows os.path.relpath raises ValueError across drives; that must not abort the run.
    monkeypatch.setattr(os.path, 'relpath', _relpath_across_drives)
    assert _display_path('D:/project/.rdf-lint.yml') == 'D:/project/.rdf-lint.yml'


def test_local_import_on_another_drive_is_shown_as_given(monkeypatch):
    monkeypatch.setattr(os.path, 'relpath', _relpath_across_drives)
    settings = describe_configuration(deepcopy_list(CHECKLIST), local_imports={'https://example.org/ns#': 'D:/vocab/ns.ttl'},
                                      config_file='C:/project/.rdf-lint.yml')
    [local] = [s for s in settings if s.key == 'imports.local' and s.origin == 'config']
    assert local.local_file == 'D:/vocab/ns.ttl'
