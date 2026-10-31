# Package a reusable macOS wheel in this repository

## Goal and scope

Make the current macOS arm64 build installable from a wheel stored in this
repository. A later user should be able to clone the repository, obtain the
wheel as a normal Git file, and install it without a local Firefox
source tree or a native rebuild. Add a repeatable maintainer command to
regenerate that wheel from the pinned local donor build.

The target is the `git@github.com:meng-clb/ruyijs-macos.git` repository on
`main`. Keep the Windows wheel build path and its pinned runtime unchanged.
Do not commit donor Firefox source, temporary build directories, or the helper
venv. The current uncommitted `python/ruyijs/_context.py` path fix is part of
the macOS wheel and must be preserved.

## Baseline and invariants

- `setup.py` already stages `dist/js`, the Necko donor closure, and macOS helper
  sources into a `macosx_26_0_arm64` wheel, but its donor path currently needs
  `RUYIJS_XPCSHELL` after the repository move.
- The macOS runtime archive recorded in `runtime.json` is 109,374,640 bytes.
  The first wheel exceeded GitHub's 100 MiB ordinary-file limit. Strip debug
  and local symbols from the staged XUL copy so the distributable fits below
  that limit; keep the original donor artifact intact.
- `pyproject.toml` currently declares `requests`, `brotli`, and `zstandard` for
  Darwin; inspect and declare any additional runtime imports needed by the
  packaged native Necko path. Do not silently rely on the developer's helper
  venv.
- The wheel must contain real files, not symlinks to
  `/Users/ameng/Desktop/firefox-src`. No build or install hook should compile
  Firefox on the consuming computer.
- Existing supported wheel tag is `macosx_26_0_arm64`; do not claim support
  for Intel Macs or older macOS versions.

## Implementation checklist

1. Record the source commit, working-tree diff, donor paths and hashes, and the
   current wheel/runtime manifest. Verify the donor contains the required
   `xpcshell`, XUL, NSS, and SpiderMonkey artifacts.
2. Add a single maintainer packaging command under `tools/` that checks its
   inputs, sets the donor path explicitly, builds the macOS wheel with pinned
   build tooling, writes a SHA-256 manifest, and fails on missing runtime files.
   Keep build output separate from the installable wheel directory.
3. Update macOS wheel metadata for the helper's actual Python dependencies and
   document the exact build and install commands. Preserve the Windows path in
   `setup.py` and `runtime.json`.
4. Build the wheel from the current checkout. Inspect its platform tag, size,
   contents, symlink entries, and absolute donor-path references. Store the
   final wheel under a clear repository directory such as `wheels/`.
5. Verify the wheel stays below GitHub's 100 MiB normal-file limit and is
   tracked as a regular Git blob. GitHub rejected new LFS uploads from this
   public fork, so the earlier LFS attempt remains only in an unpushed local
   commit. Do not split the wheel into opaque pieces.
6. Create a fresh Python 3.12 environment outside this checkout, clear
   `RUYIJS_*`/`NECKO_*` overrides, install only the stored wheel and its
   declared dependencies, run `pip check`, import `ruyijs`, evaluate a simple
   `Context`, and run one HTTPS fetch. Confirm the chosen runtime path stays
   inside the fresh environment. Run the source smoke and macOS parity suites.
7. Check the final diff and artifact hash. Commit the wheel, manifest, build
   command, metadata, and docs together with a descriptive commit. Push to
   `origin/main` after the remote accepts the ordinary Git blob; verify a fresh
   clone can retrieve and install the wheel.

## Validation and rollback

The acceptance gate is an isolated wheel install that executes JavaScript and
fetches HTTPS with no donor-path environment variables, plus passing source
tests and a valid wheel SHA-256. A wheel file merely existing is insufficient.

If building or isolated installation fails, keep the existing `dist/` and
Firefox donor untouched, remove only the newly generated wheel/staging files,
and retain diagnostics. If a push fails, do not rewrite Git history; leave the
local commit for inspection and report the failure. For a
regression after publication, publish a corrected wheel/commit or revert the
packaging commit with a new commit.
