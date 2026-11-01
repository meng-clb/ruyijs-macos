# Sync the macOS fork with upstream 0.3.0

## Scope and invariants

- Use `cutetailbud/ff-ruyijs` `main` at `5c6a68e` as the source baseline. It already includes `Facetomyself/ff-ruyijs` `macos-necko-adapter` at `00b31c5` and the Cloudflare access tracker at `1fff7db`.
- Preserve this fork's tracked, directly installable macOS wheel workflow and its previous 0.2.1 wheel as a rollback artifact until a verified 0.3.0 wheel replaces it.
- Keep Windows build and runtime contracts from upstream. Do not commit donor trees, caches, credentials, or machine-specific paths.
- Do not claim full Windows/macOS parity from source inspection alone. Verify the installed Mac wheel and report remaining platform-specific behavior.

## Implementation checklist

- [x] Merge upstream `main` into a clean feature worktree, resolve conflicts in package metadata, documentation, and the repository wheel workflow without dropping upstream runtime changes.
- [x] Adapt the in-repository wheel packaging script to 0.3.0's optional xpcshell and Darwin adapter layout. Require both core and QUIC native libraries; validate wheel members and Git's 100 MiB single-file limit.
- [x] Build the updated Mac runtime from the local Firefox 159 donor, build the 0.3.0 wheel, record SHA-256, and install it in a fresh environment outside the checkout.
- [x] Run smoke, local network/proxy/HTTP3, Mac integration and Cloudflare-related offline signal tests. Windows archive identity was verified; Windows execution requires a Windows host.
- [x] Commit a reviewable diff (`71caea6`) and merge it into the local `main`. The current request targets local files; pushing `origin` is a separate step.

## Validation and rollback

- Run `python3.12 -m unittest discover -s tests -v`, targeted network tests, `python3.12 ci/smoke_test.py` from the installed wheel, `python3.12 -m pip check`, and `shasum -a 256 -c wheels/SHA256SUMS` where applicable.
- Inspect `git diff --check`, wheel contents/architecture/signatures, and `git status` before publishing.
- The published `3b43d04` commit and its 0.2.1 wheel remain a rollback point. Revert with a new commit if the new wheel fails; do not rewrite remote history.

## Verified result (2026-11-01)

- Wheel: `ruyijs-0.3.0-py3-none-macosx_26_0_arm64.whl`, 98,987,312 bytes, SHA-256 `19c0756ece9392f14440f1a8214886ca58d5b271c419618998a40119e2f5d65c`. Two independent package runs produced the same hash.
- Fresh install: `uv pip check` passed; installed smoke, online network, local CONNECT proxy, Firefox 159 ClientHello, atob, 17 macOS integration cases, 13 local parity cases, and local HTTP/3/certificate-rejection proof passed.
- `RUYIJS_CF_ACCESS_LOG` wrote property-access records from the installed wheel. This checks the diagnostic feature, not an external challenge outcome.
- The Windows 0.3.0 archive matched `runtime.json` size and SHA-256; its Necko component inventory passed. Windows binary behavior was not executed on this Mac.
