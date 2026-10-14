# CI/CD (M5)

The actual GitHub Actions workflow lives at `.github/workflows/ci.yml`
(GitHub only picks up workflows from that exact path). This folder is for
supporting scripts (deploy scripts, lint configs) referenced by that workflow.

Current pipeline: lint + build for both `backend` and `frontend` on every
push/PR to `main`. Add test coverage as work packages add tests under `tests/`.
