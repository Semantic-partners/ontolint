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

**parse → graph(s).** `load_rdf()` builds an `rdflib.Dataset` with one named graph per
file, keyed by the file's `file:` IRI. A merged `Graph` answers "is this triple present";
a Dataset also answers "which file put it there", which is what a finding has to name
(#96) and is why `ontology_sources` had to be collected as each file was read.

`default_union` is set, so SPARQL, `len()` and `triples()` all read the union: the checks
see one graph and cannot tell the inputs were separate. Two things do not come from a
file and are handled explicitly — inferred triples get `INFERRED_CONTEXT` rather than
being folded into an input's context, and blank-node canonicalisation materialises the
union first, since canonicalisation is defined over triples.

Nothing downstream requires a Dataset: `ontolint.lint()` passes plain graphs, and every
seam accepts either.

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
| `fragment` | `fragment.ttl` |
| `merged` | both, in one graph |

`reporters.ttl` is deliberately mixed and fails 22 of the 25 checks. `fragment.ttl`
declares no `owl:Ontology`, which is the only way to fail the two ontology-metadata checks —
a file cannot both declare a described ontology and fail to. Together they give every check
a failing case, so a check that silently stops detecting anything is caught. Merged, they
also reach the declaration check's middle branch, where *some* of the inputs declared one.

Neither input needs the network: the autouse `no_network` fixture blocks sockets, and the
unresolvable `owl:imports` points at `example.invalid`, reserved by RFC 2606, so it fails
the same way online or off.

**One term, one failure.** Every term in `reporters.ttl` is complete except for the single
thing the comment beside it names, so a check that changes moves one line of the stored
expectations rather than several, and a term appearing twice in a report is a signal rather
than noise. One exception, and it is in the checks rather than the fixture: an
`owl:imports` that cannot be resolved is by construction a namespace whose terms cannot be
checked, so it fails both. The same rule applies to `fragment.ttl` and to the golden cases
under `tests/dqv/`.

`fragment.ttl` carries the other direction of the same noise, which it cannot avoid: with
no declared namespace to compare against, the undefined-terms check reports its own three
terms and the untyped-property check reports `rdf:type`, `rdfs:label` and friends — terms
the file never put under test. Those are false positives rather than fixture content, and
pinning them is part of what the file is for, since they are #102.

Each DQV golden covers a **single** result, unlike the run-level report the reporter
builds in anger. A report over several results is not the union of their individual ones:
`_mint` hashes the assessment node into every measurement IRI, and a two-result report has
one assessment where its two parts have two, so every measurement IRI differs. Multi-result
run shapes are pinned end-to-end in `tests/dqv/` instead, where `per-file/` and `merged/`
run the CLI over two inputs each.

### What the stored reports pin, and what they do not

A report carries three things that depend on *where and when it ran* rather than on what
the checks found, and all three are hashed into the IRIs it mints, so none can be corrected
after the report is built. Each is pinned at the point it is made, by replacing a
module-level function in `scripts/dqv.py` that is looked up when the report is built rather
than bound in — the same device three times over, because `main()` takes no arguments for
any of them.

| provider | replaced with | otherwise |
|---|---|---|
| `dqv.utc_now`, as `date_time_provider` | a fixed instant | every minted IRI derives from the timestamp, so no two runs agree |
| `dqv.mint_id`, as `node_namer` | a name taken from what a node is *about* | a node's name nests: a violation hashes its measurement, which hashes the assessment, which hashes the effective configuration — which lists every check. Adding one check renamed every node in every stored report |
| `dqv.file_iri` | an IRI relative to the case directory | a report naming an input names it by absolute path, so a golden matches only the machine that wrote it |

The first two are parameters of `build_dqv_graph` and `write_dqv_report`, so a test calling
either passes one in — `test_pipeline_qaresult_to_dqv.py` does. `dqv.file_iri` is not, and
deliberately: it is called from `load_rdf` in `ontology_qa.py`, so a parameter would have to
run through `load_rdf` → `run_qa` → `lint_graph` → `main` to reach the one test that wants
it. It stays a module-level function replaced in place.

Every one of them is *also* replaceable in place, because each default is looked up when the
report is built rather than bound into its definition. A run through `main()` takes no
arguments for any of this, so `test_e2e_dqv.py` replaces all three that way.

That last one is the difference between a reviewable diff and an unreadable one. Adding a
check used to move 161 lines of `tests/dqv/mixed/expected.ttl` and 1120 of
`tests/data/reporters_dqv.ttl`; it now moves 7 and 16, and those are the new metric's own
definition.

**So the stored reports pin content, not identity.** They say which metrics were emitted,
on which datasets, with which values, violations and settings. They do not say that the
real naming scheme is deterministic, unique per run, or sensitive to the configuration —
with `mint_id` replaced, they cannot. Those properties are asserted directly in
`tests/test_dqv.py`, which uses the real one: `test_iris_are_deterministic_per_run_and_unique_across_runs`,
`test_same_inputs_under_different_configurations_get_distinct_assessments`,
`test_settings_differing_only_in_provenance_get_distinct_iris`,
`test_same_ontology_iri_in_two_runs_gives_distinct_measurements` and
`test_aggregate_dataset_iri_is_stable_across_runs`. Change the minting and it is those that
must fail; the goldens staying green is the point. One e2e test does run the real naming
through `main()` — `test_a_real_run_mints_hashed_iris` — so the scheme cannot quietly stop
being wired in, or stay replaced by accident, while every stored report still matches.

One consequence to know about: the substitute names a configuration node by a constant,
since a report has one per result and the goldens have one result each. Two differing
configurations in a single stored report would collide into one node.

### Changing a stored expectation

Every stored expectation regenerates the same way — there is no hand-edited one left:

```
UPDATE_GOLDEN=1 poetry run pytest tests/test_pipeline_*.py tests/test_e2e_dqv.py
```

Review every regenerated diff; that is the point of storing them. A new check should be a
deliberate addition to the expectation, not something that appears while you look away.

The writers live in `tests/golden.py`, in the tree rather than in a script beside it. A
generator that is not in the repo cannot be kept in step with the tests it writes about:
the file headers went stale exactly that way when the suites were renamed, and a
regeneration quietly put the old names back.

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

`--per-file` means one thing: **do the checks run per graph, or across all the graphs at
once?** `main()` is one loop over a list of runs, where a merged run is the list of length
one, so everything after the loop — the DQV report, where output goes, the exit code — is
the same either way.

Two things still differ, both deliberately, and `tests/test_e2e_cli.py` pins them:

- **A CTRF report is named per run.** `--ctrf-filename` names the one a merged run
  produces; per file each is named after its input, and passing both is refused rather
  than quietly ignored.
- **A parse failure aborts a merged run but not a per-file one.** A file that cannot be
  parsed silently shrinks the graph under test, so there is nothing left to check in a
  merged run; per file the others are independent and still worth checking. This one
  follows from what the checks run over, which is the one thing `--per-file` decides.

What remains open is the deeper question of scope, tracked in #96: a check computed over
"whatever was in this invocation" gives an answer that depends on how the caller batched
their files, which is why uniqueness can be reported for two independent ontologies that
merely share a label.

**Where this is going: the unit.** One concept replaces the two modes. A **unit** is one
ontology — one to many files, with exactly one `owl:Ontology` declaration across the whole
unit. A **run** is a set of units. **Context** is every unit in the run, available to
*resolve* references but never to widen what a check is computed over. `--per-file` then
means "each file is a unit", a merged run means "all the files are one unit", and a run may
hold both shapes at once, which is how a family of ontologies is actually laid out and
which nothing in the tool can express today.

`main()` already builds `runs` as `list[list[path]]` and produces one report, one CTRF and
one `QAResult` per entry, so a unit is already the internal shape. What is missing is
underneath it — see the Todo.

**What owns a term.** A term belongs to the ontology declared in the file it sits in — not
to the namespace it is minted under. So a term minted in file 1 under ontology 2's
namespace is ontology 1's defect: file 1 is where someone did the wrong thing, and charging
it to ontology 2 would let one input degrade another's quality score from outside.

A per-file run already reports exactly this, and `tests/dqv/per-file/` pins it: `a:borrowed`
is minted in `b.ttl`, the hijack is charged to `b`, the violation's `sh:focusNode` names the
term, and `a`'s report stays clean.

This is deliberately *not* the longest-matching-namespace rule #96 first proposed. That one
would make `a:borrowed` ontology a's defect, which lets one input degrade another ontology's
score from outside. Ownership follows the file; minting into someone else's namespace is the
finding, not the attribution rule.

## A check that cannot answer says so

The untyped-class and untyped-property checks judge a term by whether it is in the
ontology's own namespace. With no `owl:Ontology` declared there is no such namespace, and
the guard used to read *"keep it if it is mine, **or if I do not know what mine is**"* —
so a headerless file had every term it touched reported, `rdf:type` and `rdfs:label`
included, and the build failed on a list of other people's vocabulary (#102).

The guard now requires a declared namespace, in the queries *and* in the checks: the
queries return nothing, and the checks say `invalid metric` rather than `PASS`, because
reporting nothing and finding nothing are different things and only one of them is a
clean bill of health. It is the same shape as `WARNING - No classes defined, invalid
metric` elsewhere.

What this gives up is deliberate. A term in the file's own namespace, used and never
typed, really is a defect and is no longer named — there is no way to tell it from a
third party's term without a namespace to judge by. Excluding only the vocabularies we
already know offline would keep it, and is worth revisiting; it is not what this change
does.

Each half has its own failing test, because they can hide each other: the checks
short-circuit on the declaration before looking at their results, so a query that went
back to passing everything would be invisible through `run_qa`.

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

The DQV report's clock is injected — `build_dqv_graph(results, date_time_provider=…)` —
and pinning it makes the report, every minted IRI included, reproducible for the same
inputs and base URI.

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

Both reporters pin their clocks the same way, through an injected `date_time_provider`.
The stakes differ: CTRF's timestamp is one field, while DQV's *minted IRIs* derive from
it, so an unpinned DQV run names every measurement differently. DQV's default is looked
up as `dqv.utc_now` when the report is built rather than bound as the parameter's
default, so the CLI — which has no caller to inject one — can still have its clock
replaced, which is how `tests/test_e2e_dqv.py` compares against committed reports.

## Todo

- **Make Markdown a projection of `QAResult`** (#101) — see above. Tracked as its own
  change, since it moves where every check's text is produced.
- **#108 — a unit cannot see its siblings.** `load_rdf()` is called inside `main()`'s loop,
  so a per-file run's graph holds one file and nothing else: an ontology referencing a
  sibling in the same invocation reports every borrowed term as undefined unless the user
  lists it in `imports.local` by hand. Load the invocation once and scope each unit to its
  own share of it. #104 landed the substrate — every triple is already keyed by its file.
- **#107 — hijacking and undefined terms go silent in a merged run.** The same confusion
  from the other end: both ask "is this namespace declared?" against whatever graph they
  are handed, so a sibling file that legitimately declares the namespace excuses a hijack.
  Separating scope from context is one change, so #107 and #108 are likely one PR. It moves
  numbers in the goldens, since it changes what ontolint finds.
- **Smaller, once those exist.** "Exactly one declaration per unit" is not a rule anywhere
  (`check_owl_declaration` counts *files*); a merged run that states several ontologies is
  accepted and papered over with the synthetic `Merged: …` dataset; and one boolean flag
  cannot describe a run whose units have different shapes.

**What the unit model deletes.** Per-ontology attribution of measurements was the plan here
until the model settled it away: a unit yields one result on one ontology, so a check's
violations never split across ontologies, and the aggregate `Merged: …` dataset exists only
to paper over a run the model makes invalid. It also reverses #96's answered question 4 —
inside a unit of five files, one header and four files without it is **correct**, where
today `check_owl_declaration` reports that as a violation and `tests/data/fragment.ttl`
exists on the premise that it is a defect.

## In flight

- **#94** — publish to PyPI; moves these modules into the package.
- **#96** — what per-file versus grouped linting means. Its plumbing landed as #104; the
  unit model above is the rest of it, carried by #107 and #108.
- **#97** — a file declaring two ontologies fails the build while the report says PASS.
- **#102** — the untyped checks report every term when no `owl:Ontology` is declared.
- **#107 / #108** — separating a unit's scope from the run's resolution context.
