# Releasing LLMWho

GitHub Actions publishes the Python and Node packages from an immutable
`vX.Y.Z` tag. The tag must exactly match every package version. The workflow
tests and builds both distributions, smoke-tests the built artifacts, then
publishes those same artifacts to PyPI and npm. It creates the GitHub Release
only after both registries accept the release.

No PyPI or npm token belongs in GitHub secrets. Both registries use GitHub OIDC
trusted publishing, scoped to `.github/workflows/release.yml` and separate
GitHub environments.

## One-time repository and registry setup

Create GitHub environments named `pypi` and `npm`. Add deployment reviewers if
the repository plan supports them. Configure each package's trusted publisher
with these exact values:

| Registry | Owner | Repository | Workflow | Environment |
|---|---|---|---|---|
| PyPI `llmwho` | `tcztzy` | `llmwho` | `release.yml` | `pypi` |
| npm `llmwho` | `tcztzy` | `llmwho` | `release.yml` | `npm` |

For PyPI, open the `llmwho` project, choose **Manage → Publishing**, and add a
GitHub Actions trusted publisher. For npm, open the `llmwho` package settings,
choose **Trusted Publisher → GitHub Actions**, enter the same repository and
workflow, select the `npm` environment, and allow `npm publish`.

The publishing jobs receive only `contents: read` and `id-token: write`. The
GitHub Release job separately receives `contents: write`; it has no registry
identity permission.

## Release procedure

1. Merge a commit on `main` where Node, Python, and module versions all equal
   the intended version.
2. Confirm CI is green.
3. Verify locally with `node scripts/check-release-tag.mjs vX.Y.Z`.
4. Create and push an annotated `vX.Y.Z` tag.
5. Watch the `Release` workflow. If one registry job fails after the other has
   published, rerun only the failed job; registry versions are immutable. If
   the workflow itself needs a fix, merge that fix and dispatch `release.yml`
   against the same immutable tag with only the missing registry selected:

   ```bash
   gh workflow run release.yml \
     --field tag=vX.Y.Z \
     --field publish_pypi=false \
     --field publish_npm=true
   ```

The recovery run checks out and rebuilds the existing tag. It verifies that the
same version exists on both registries before creating or updating the GitHub
Release. npm tarballs are passed as explicit `./dist/*.tgz` filesystem paths so
the npm CLI cannot parse them as package or GitHub shorthand.

If both registries already contain the version and only the GitHub Release is
missing, run the same command with both `publish_pypi=false` and
`publish_npm=false`. Registry verification remains mandatory; no package is
uploaded again.

Do not move or reuse a release tag. Prepare a new patch version for any change
after a registry has accepted the release.
