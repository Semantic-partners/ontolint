from scripts.ontology_qa import run_qa

CHECK_NAME = "Unresolvable imports"

# ── No imports ────────────────────────────────────────────────────────────────

def test_no_imports_passes(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    """)
    check = run_qa(g).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


# ── Valid import ──────────────────────────────────────────────────────────────

def test_valid_import_passes(make_graph, tmp_path):
    ont_file = tmp_path / "imported.ttl"
    ont_file.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<http://imported.example.org#> a owl:Ontology .\n"
        "<http://imported.example.org#Thing> a owl:Class .\n"
    )
    import_url = ont_file.as_uri()

    g = make_graph(f"""
    : a owl:Ontology .
    : owl:imports <{import_url}> .
    """)
    check = run_qa(g).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_multiple_valid_imports_pass(make_graph, tmp_path):
    for name in ("a.ttl", "b.ttl"):
        f = tmp_path / name
        f.write_text(
            "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
            f"<http://example.org/{name}#> a owl:Class .\n"
        )

    url_a = (tmp_path / "a.ttl").as_uri()
    url_b = (tmp_path / "b.ttl").as_uri()

    g = make_graph(f"""
    : a owl:Ontology .
    : owl:imports <{url_a}> .
    : owl:imports <{url_b}> .
    """)
    assert run_qa(g).get(CHECK_NAME).passed


# ── Unresolvable URL ──────────────────────────────────────────────────────────

def test_unresolvable_url_fails(make_graph):
    # .invalid TLD is guaranteed to not resolve (RFC 2606)
    g = make_graph("""
    : a owl:Ontology .
    : owl:imports <http://does-not-exist.invalid/ont.ttl> .
    """)
    check = run_qa(g).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1
    assert "does-not-exist.invalid" in check.elements


# ── Empty graph ───────────────────────────────────────────────────────────────

def test_import_resolves_but_is_empty_fails(make_graph, tmp_path):
    # A syntactically valid turtle file with no triples
    ont_file = tmp_path / "empty.ttl"
    ont_file.write_text("# no triples here\n")
    import_url = ont_file.as_uri()

    g = make_graph(f"""
    : a owl:Ontology .
    : owl:imports <{import_url}> .
    """)
    check = run_qa(g).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1
    assert str(import_url) in check.elements


# ── Mixed: some pass, some fail ───────────────────────────────────────────────

def test_mixed_imports_count_reflects_only_failures(make_graph, tmp_path):
    good_file = tmp_path / "good.ttl"
    good_file.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<http://good.example.org#A> a owl:Class .\n"
    )

    g = make_graph(f"""
    : a owl:Ontology .
    : owl:imports <{good_file.as_uri()}> .
    : owl:imports <http://bad1.invalid/ont.ttl> .
    : owl:imports <http://bad2.invalid/ont.ttl> .
    """)
    check = run_qa(g).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 2
    assert "bad1.invalid" in check.elements
    assert "bad2.invalid" in check.elements


def test_failing_import_url_appears_in_elements(make_graph):
    bad_url = "http://missing.invalid/ontology.ttl"
    g = make_graph(f"""
    : a owl:Ontology .
    : owl:imports <{bad_url}> .
    """)
    check = run_qa(g).get(CHECK_NAME)
    assert bad_url in check.elements


# ── ignore-imports ────────────────────────────────────────────────────────────

def test_ignored_unresolvable_import_passes(make_graph):
    bad_url = "http://ignored.invalid/ont.ttl"
    g = make_graph(f"""
    : a owl:Ontology .
    : owl:imports <{bad_url}> .
    """)
    check = run_qa(g, ignore_imports=[bad_url]).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_ignored_import_not_in_elements(make_graph):
    bad_url = "http://ignored.invalid/ont.ttl"
    g = make_graph(f"""
    : a owl:Ontology .
    : owl:imports <{bad_url}> .
    """)
    check = run_qa(g, ignore_imports=[bad_url]).get(CHECK_NAME)
    assert bad_url not in check.elements


def test_ignore_only_affects_listed_url(make_graph):
    ignored_url = "http://ignored.invalid/ont.ttl"
    bad_url = "http://still-bad.invalid/ont.ttl"
    g = make_graph(f"""
    : a owl:Ontology .
    : owl:imports <{ignored_url}> .
    : owl:imports <{bad_url}> .
    """)
    check = run_qa(g, ignore_imports=[ignored_url]).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1
    assert bad_url in check.elements
    assert ignored_url not in check.elements


def test_all_imports_ignored_passes(make_graph):
    urls = ["http://a.invalid/ont.ttl", "http://b.invalid/ont.ttl"]
    g = make_graph(f"""
    : a owl:Ontology .
    : owl:imports <{urls[0]}> .
    : owl:imports <{urls[1]}> .
    """)
    check = run_qa(g, ignore_imports=urls).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0
