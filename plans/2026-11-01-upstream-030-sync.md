# Sync the macOS fork with upstream 0.3.0

## Scope and invariants

- Use `cutetailbud/ff-ruyijs` `main` at `5c6a68e` as the source baseline. It already includes `Facetomyself/ff-ruyijs` `macos-necko-adapter` at `00b31c5` and the Cloudflare access tracker at `1fff7db`.
- Preserve this fork's tracked, directly installable macOS wheel workflow and its previous 0.2.1 wheel as a rollback artifact until a verified 0.3.0 wheel replaces it.
- Keep Windows build and runtime contracts from upstream. Do not commit donor trees, caches, credentials, or machine-specific paths.
- Do not claim full Windows/macOS parity from source inspection alone. Verify the installed Mac wheel and report remaining platform-specific behavior.

## Implementation checklist

- [ ] Merge upstream `main` into a clean feature worktree, resolve conflicts in package metadata, documentation, and the repository wheel workflow without dropping upstream runtime changes.
- [ ] Adapt the in-repository wheel packaging script to 0.3.0's optional xpcshell and Darwin adapter layout. Require both core and QUIC native libraries; validate wheel members and Git's 100 MiB single-file limit.
- [ ] Build the updated Mac runtime from the local Firefox 159 donor, build the 0.3.0 wheel, record SHA-256, and install it in a fresh environment outside the checkout.
- [ ] Run smoke, local network/proxy/HTTP3, Mac integration and Cloudflare-related offline signal tests. Keep failed or untested behavior explicit in documentation.
- [ ] Commit a reviewable diff. Push to the user's `meng-clb/ruyijs-macos` remote only after local verification and without rewriting history.

## Validation and rollback

- Run `python3.12 -m unittest discover -s tests -v`, targeted network tests, `python3.12 ci/smoke_test.py` from the installed wheel, `python3.12 -m pip check`, and `shasum -a 256 -c wheels/SHA256SUMS` where applicable.
- Inspect `git diff --check`, wheel contents/architecture/signatures, and `git status` before publishing.
- The published `3b43d04` commit and its 0.2.1 wheel remain a rollback point. Revert with a new commit if the new wheel fails; do not rewrite remote history.
