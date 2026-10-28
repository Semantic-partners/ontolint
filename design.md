# Design

How a run is put together, and which parts are settled versus in flight. `CLAUDE.md` has
the module-by-module detail; this is the shape.

## The pipeline

```
args + .rdf-lint.yml ──→ Config + checklist
                              │
parse ──→ graph(s) ──→ lint ──→ QAResult(s)
                              ├──→ Markdown   (per result)   ← assembled throughout
                              ├──→ CTRF       (per result)
                              └──→ DQV        (per RUN, over all results)
```

**Config + checklist.** `Config` is the single description of a run — the CLI builds one
from its arguments and `.rdf-lint.yml`, a library caller builds one directly. The checklist
says which checks are enabled, resolved by `select_checks()` or handed in by the CLI.

**parse → graph(s).** One graph per file, or one merged graph, depending on how the run is
scoped (see *per-file*).

**lint.** `lint_graph()` is the single entry point that performs one run: inference if
configured, then every selected check. Both front ends call it, so a run means the same
thing however it was asked for.

**QAResult.** What a run produced: profiling metrics, a `CheckResult` per executed check
(name, passed, count, offending elements, structured violations), the datasets it was
computed on, and the configuration that ran.

## The three reporters

| | granularity | built from | pinned by |
|---|---|---|---|
| **Markdown** | per result | *mixed — see below* | `<case>_markdown.py`, via `tests/test_pipeline_lint_to_markdown.py` |
| **CTRF** | per result | `QAResult`, via `build_ctrf_report()` | `<case>_ctrf.json`, via `tests/test_pipeline_qaresult_to_ctrf.py` |
| **DQV** | **per run** | all `QAResult`s + all inputs, via `build_dqv_graph()` | `<case>_dqv.ttl`, via `tests/test_pipeline_qaresult_to_dqv.py`; run shapes in `tests/dqv/*/expected.ttl` |

Each reporter splits building from writing: `build_ctrf_report()` / `write_ctrf_report()`
and `build_dqv_graph()` / `write_dqv_report()`. The build half is a pure projection of a
`QAResult`, so it can be asserted without touching the filesystem — which is what the
reporter suites do. Markdown has no such split yet.

The asymmetry is load-bearing. CTRF and Markdown describe one result each; **DQV describes
the whole run**, which is why it is written once, outside any per-file loop. Set-level
findings live there and nowhere else — *one file, one ontology* can only be judged across
the inputs, and only before they are merged, since the union of two identical
`owl:Ontology` declarations is a single triple.

## How the reporters are pinned

`tests/data/` holds the whole output of each reporter, written out as data. Each suite
leads with one assertion that the reporter still produces it, and follows with the
assertions that say *why* parts of it must hold — so a failure explains itself instead of
handing over a thousand-line diff.

| suite | input | asserts |
|---|---|---|
| `test_pipeline_lint_to_qaresult.py` | the `.ttl` files | lint still produces the stored `QAResult` |
| `test_pipeline_lint_to_markdown.py` | the `.ttl` files | a lint still renders the stored Markdown |
| `test_pipeline_qaresult_to_ctrf.py` | the stored `QAResult`s | the CTRF projection |
| `test_pipeline_qaresult_to_dqv.py` | the stored `QAResult`s | the DQV projection |

The last two take the *stored* instance, never one they produced, so they never run a
check: a change to what a check finds cannot break them, and a reporter bug cannot be
blamed on the checks. The first two are what keep the stored instances honest.

Verified by sabotage, which is the only way to know a safety net holds: breaking a check
fails suite 1 alone, one line of report wording fails suite 2 alone, and the DQV reporter
fails suite 4 alone.

### The cases

Several checks answer differently depending only on how the inputs were batched, so every
reporter is pinned per case rather than once:

| case | inputs |
|---|---|
| `reporters` | `reporters.ttl` |
| `fragment` | `reporters_fragment.ttl` |
| `merged` | both, in one graph |

`reporters.ttl` is deliberately mixed and fails 22 of the 24 checks. `reporters_fragment.ttl`
declares no `owl:Ontology`, which is the only way to fail the two ontology-metadata checks —
a file cannot both declare a described ontology and fail to. Together they give every check
a failing case, so a check that silently stops detecting anything is caught. Merged, they
also reach the declaration check's middle branch, where *some* of the inputs declared one.

Neither input needs the network: the autouse `no_network` fixture blocks sockets, and the
unresolvable `owl:imports` points at `example.invalid`, reserved by RFC 2606, so it fails
the same way online or off.

Each DQV golden covers a **single** result, unlike the run-level report the reporter
builds in anger. A report over several results is not the union of their individual ones:
`_mint` hashes the assessment node into every measurement IRI, and a two-result report has
one assessment where its two parts have two, so every measurement IRI differs. Multi-result
run shapes are pinned end-to-end in `tests/dqv/` instead, where `per-file/` and `merged/`
run the CLI over two inputs each.

### Changing a stored expectation

```
UPDATE_GOLDEN=1 poetry run pytest tests/test_pipeline_qaresult_to_ctrf.py tests/test_pipeline_qaresult_to_dqv.py
UPDATE_GOLDEN=1 poetry run pytest tests/test_e2e_dqv.py
```

The stored `QAResult` and Markdown are still edited by hand from the failing diff. For the
`QAResult` that is deliberate — a new check should be a deliberate addition to the
expectation — but it is a cost. Review every regenerated diff; that is the point of
storing them.

Two rules for anything that reaches a stored expectation:

- **It must not name the checkout.** An absolute path makes the expectation match only the
  machine that wrote it, and the symptom is a suite that is green locally and red in CI.
  It has happened twice — `fetchActivity`'s vocabulary paths, and a violation naming its
  source file — so `test_no_stored_expectation_embeds_a_checkout_path` now asserts the
  class rather than the instances. `source_iris` exists so a run can name its inputs
  without minting a `file:` IRI from the working directory.
- **Anything derived from a set must be sorted.** Dict and graph comparison ignore order,
  so an unsorted value passes the test while churning the file on every regeneration.

Running the whole suite from a second checkout at a different path is the cheapest way to
catch the first before CI does.

## Markdown is not a projection of QAResult (yet)

Worth stating plainly, because it is the thing most likely to be assumed otherwise: **you
cannot write a `QAResult → Markdown` test today.** Markdown is assembled from three
different kinds of source:

1. **Projections of `QAResult`** — `print_profiling_metrics()`, `print_profiling_table()`
   and `print_qa_table()` render from `result.profiling`, `result.elements` and the
   checklist. These *are* projections.
2. **Text the checks already rendered.** Each `check_*` builds a `log` string as it runs
   and `run_qa()` collects them into `result.logs`. The Markdown for every check is
   therefore produced *inside* the check, as a side effect of running it, and the reporter
   only concatenates. A test at this boundary would assert that concatenation concatenates.
3. **Run context that never reaches `QAResult`** — the load log (which files parsed, which
   failed) and the config log (what `.rdf-lint.yml` changed), both assembled in `main()`.

So the only boundary that exists for Markdown is **argv → stdout**, and that is what the
end-to-end goldens pin.

The reporter suites are built around that split. `tests/data/reporters_qaresult.py` holds
a `QAResult` as data; `test_pipeline_qaresult_to_ctrf.py` and `test_pipeline_qaresult_to_dqv.py` take **that
instance** and assert the projection, so they never run a check.
`test_pipeline_lint_to_qaresult.py` keeps the stored instance honest by asserting lint still
produces it — normalising the vocabulary paths in `fetchActivity` to the repo root first,
since a stored expectation that embeds the checkout path matches only the machine that
wrote it — and `test_pipeline_lint_to_markdown.py` does the same for `reporters_markdown.py`, the
rendered text stored beside it. Markdown is the odd one out only in *how* it is produced:
it has to run the linter, because the per-check text is rendered inside the checks. Once it
is a projection, the stored text stays exactly as it is and only the way it is produced
changes — which is how the move gets checked.

**The target** is for Markdown to become a projection like the other two: checks return
data only, a renderer turns a `QAResult` into Markdown, and run context is carried on the
result rather than accumulated alongside it. Then all three reporters are projections of
the same data, each testable at its own boundary, and the reporters stop constraining how
the insides are organised. That is a change to make deliberately, not a prerequisite for
the ones in flight.

## per-file

`--per-file` should mean one thing: **do the checks run per graph, or across all the graphs
at once?** Everything else about the two modes — how reports are named, where they are
written, which messages are emitted — is incidental and should not differ.

It does differ today (`main()` has two paths), which is tracked in #96 along with the
deeper question of scope: a check computed over "whatever was in this invocation" gives an
answer that depends on how the caller batched their files, which is why uniqueness can be
reported for two independent ontologies that merely share a label.

## Determinism

Reports must be byte-identical for the same inputs, or diffs are unreviewable and no
expected output can be pinned. Two things are needed and are in place:

- **SELECT results are sorted** in `exec_sparql()`. Rows otherwise arrive in store order,
  which varies between runs. CONSTRUCT results are graphs and are left alone.
- **Violation lists are sorted** in `violation_formatting()`.
- **GROUP_CONCAT cells are sorted** by `concat_members()`. Six queries concatenate a
  group's members into one cell, and GROUP_CONCAT has no defined order: sorting the rows
  does not sort within one. The DQV records always sorted their own copy; the text
  reports carried the concatenation as it came back, so the same inputs rendered a
  group's members in a different order on roughly half of runs.
- **Blank nodes are rendered as `[anonymous]`** by `term_text()`, wherever a term reaches a
  text report. An rdflib blank-node identifier is invented at parse time and differs every
  run, so printing it varied the output while telling a reader nothing they could act on.
  Anything needing stable identity has it in the DQV report, where blank nodes are
  skolemized under the report's base.

`SOURCE_DATE_EPOCH` pins the report timestamp, so with the same inputs and base URI the DQV
report — including every minted IRI — is reproducible.

**Rendering twice in one process is not enough to prove it.** `PYTHONHASHSEED` is fixed
for a process's lifetime, so anything ordered by a hash renders identically both times
and still varies between runs — which is how the GROUP_CONCAT ordering above survived a
test asserting two renders match. `test_it_renders_the_same_text_under_any_hash_seed`
covers that class of bug by rendering in a subprocess per seed. It samples a few seeds,
so it is a detector rather than a proof.

**CTRF is not reproducible from the CLI**: its timestamp is `datetime.now()`, so two runs
over identical inputs differ by that one field. The clock is injected —
`build_ctrf_report(result, date_time_provider=…)` — and that is the only way to fix it.
Nothing else in the report varies, so a caller that supplies a clock gets a byte-identical
file, which is what `tests/data/reporters_ctrf.json` is compared against.

The two reporters pin their clocks differently on purpose. DQV reads `SOURCE_DATE_EPOCH`
because its *minted IRIs* derive from the timestamp, so a whole run has to agree on one
instant even across processes. CTRF has no such dependency — only the one field — so the
clock is a parameter, and the published format keeps the wall clock it has always carried.

## Todo

- **Make Markdown a projection of `QAResult`** — see above. Tracked as its own change,
  since it moves where every check's text is produced.
- **Collapse the two `main()` paths**, so `--per-file` only decides what the checks run
  over and nothing else differs between the modes. What differs today is pinned in
  `test_e2e_cli.py`: `-o` writes a file in a single run and is ignored per-file,
  `--ctrf-filename` likewise, an empty directory reports differently in each, and
  `--profile-only --per-file` is the one combination producing no CTRF and no report. The
  collapse has to decide what each of those means, and these tests are what make that a
  decision rather than an accident.

## In flight

- **#94** — publish to PyPI; moves these modules into the package.
- **#96** — what per-file versus grouped linting means; proposes loading into an
  `rdflib.Dataset` with one named graph per file, so provenance is recorded per triple and
  a term can be attributed to the ontology that owns it.
- **#97** — a file declaring two ontologies fails the build while the report says PASS.
