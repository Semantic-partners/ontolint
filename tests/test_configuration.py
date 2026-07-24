import os
import pytest
from ontolint.ontology_qa import parse_lint_config, lint_selection, run_qa, CHECKLIST, deepcopy_list


# ── parse_lint_config ─────────────────────────────────────────────────────────

def test_parse_lint_config_disable_transforms_keys(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("disable:\n  - class-missing-label\n  - hijacking\n")
    result, ignore = parse_lint_config(str(cfg))
    assert result == {"disable": ["check_class_missing_label", "check_hijacking"]}
    assert ignore == []


def test_parse_lint_config_enable_transforms_keys(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("enable:\n  - class-missing-label\n")
    result, ignore = parse_lint_config(str(cfg))
    assert result == {"enable": ["check_class_missing_label"]}
    assert ignore == []


def test_parse_lint_config_empty_file_returns_disable_empty(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("")
    result, ignore = parse_lint_config(str(cfg))
    assert result == {"disable": []}
    assert ignore == []


def test_parse_lint_config_ignore_imports_returned_separately(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text(
        "disable:\n  - hijacking\n"
        "ignore-imports:\n"
        "  - http://www.w3.org/ns/shacl\n"
        "  - https://schema.org/\n"
    )
    result, ignore = parse_lint_config(str(cfg))
    assert result == {"disable": ["check_hijacking"]}
    assert ignore == ["http://www.w3.org/ns/shacl", "https://schema.org/"]


def test_parse_lint_config_ignore_imports_only(tmp_path):
    cfg = tmp_path / ".rdf-lint.yml"
    cfg.write_text("ignore-imports:\n  - http://example.org/ont\n")
    result, ignore = parse_lint_config(str(cfg))
    assert result == {}
    assert ignore == ["http://example.org/ont"]


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
    from ontolint.ontology_qa import main
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
