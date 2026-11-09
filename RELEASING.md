# Releasing ontolint

Releases are cut by **pushing a version tag onto a commit**. The tag is the single source
of truth: it selects the exact SHA that ships and the version it ships under. CI
([`.github/workflows/publish.yml`](.github/workflows/publish.yml)) runs the full test matrix
on that commit, builds it, publishes it to PyPI and cuts a matching GitHub Release with
generated notes.

**One tag, one version, everywhere.** The same `v2.1.0` tag is the version of the GitHub
Action (`uses: Semantic-partners/ontolint@v2.1.0`), the GitHub Release, and the PyPI
package (`ontolint==2.1.0`; PyPI versions carry no `v`). Releases have used `v` tags since
`v0.1.0`, and the PyPI package continues from them: the latest release before PyPI was
`v2.0.1`.

The committed `version` in `pyproject.toml` is cosmetic, because the workflow overwrites it
at build time. You never edit it by hand to release.

## Version numbers are ordinals, not promises

We don't do semver. A version digit can't honestly encode "is this a breaking change" —
that's a human judgement, not something a `.` in a string decides. So the number is just
**the next number**: `v2.0.2`, `v2.1.0` or `v3.0.0`, depending on how big the change feels.
The only hard constraints:

- it must be a valid [PEP 440](https://peps.python.org/pep-0440/) version once the `v` is
  dropped, so PyPI and pip order it correctly, and
- it must be higher than the last one: tags are monotonic, and PyPI won't let you
  overwrite a version.

Say what changed for users in the release notes regardless, especially anything that
breaks a working setup.

## Cut a release

```bash
git tag v2.1.0 <sha>        # omit <sha> to tag HEAD
git push origin v2.1.0
```

CI tests that commit on every supported OS and Python version, publishes `ontolint 2.1.0`
to PyPI and creates GitHub Release `v2.1.0`.

**Push the tag; don't create the release in the GitHub UI.** The workflow creates the
release itself, and fails if one already exists.

## Cut a candidate / beta

Append a PEP 440 pre-release suffix — `rc` (candidate), `b` (beta) or `a` (alpha):

```bash
git tag v2.1.0rc1 <sha>
git push origin v2.1.0rc1
```

pip **hides pre-releases from normal installs**. `pip install ontolint` keeps resolving the
latest *final* version; a pre-release only lands if the user opts in:

```bash
pip install --pre ontolint          # newest, including pre-releases
pip install ontolint==2.1.0rc1      # or pin the exact candidate
```

The GitHub Release is marked "pre-release" automatically when the version has an
`a`/`b`/`rc` suffix.

## Rehearsing a release

Pushing a **candidate tag** (`v2.1.0rc1`) is a safe rehearsal: a real, end-to-end publish
to real PyPI, which pip won't serve to normal installs, so nobody gets it by accident. If
it's wrong, bump the `rcN` and push again.

To check the package without publishing at all, `scripts/consumer_smoke.sh` builds the
wheel, installs it into a clean virtualenv and runs it from outside the repository, exactly
as CI does before every publish.

## If something goes wrong

- **Typo'd tag / bad version:** the workflow validates PEP 440 up front and fails before
  publishing. Delete the bad tag (`git push --delete origin <tag>`) and push a corrected
  one.
- **Tests fail on the tagged commit:** nothing is published. Fix it on `main`, then tag
  the fixed commit with the same version, after deleting the old tag, or with the next one.
- **Bad release already on PyPI:** you can't overwrite a version. *Yank* it on PyPI (hides
  it from resolution without breaking existing pins) and push the next ordinal with the
  fix.

## Auth

Publishing uses PyPI [Trusted Publishing](https://docs.pypi.org/trusted-publishers/):
PyPI trusts `.github/workflows/publish.yml` in `Semantic-partners/ontolint`, running in the
`pypi` GitHub environment, and GitHub proves that identity on every run. There is no token
or secret to store, share or rotate, and no other repo or workflow can publish ontolint.

Setting it up, once:

1. **On PyPI:** before the first upload, add a *pending publisher* under **Your account →
   Publishing** (afterwards, under the project's own **Settings → Publishing**). Use the
   **GitHub** tab: owner `Semantic-partners`, repository `ontolint`, workflow
   `publish.yml`, environment `pypi`. A pending publisher does **not** reserve the
   project name — only the first upload does.
2. **On GitHub:** under **Settings → Environments**, create the `pypi` environment. Adding
   required reviewers makes every release wait for an approval before it publishes.

If a publish fails with an authentication error, the four values on PyPI must match the
repository, the workflow file name and the environment exactly.
