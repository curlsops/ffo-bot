---
description: FFO Bot changelog overview.
---

# Changelog

Each release lists fixes, dependency bumps, and features in the [complete changelog](CHANGELOG.md). The sections below highlight **significant** changes when moving between **major** versions.

For every tagged release (machine-readable), see [`CHANGELOG.md`](CHANGELOG.md) ([Release Please](https://github.com/googleapis/release-please) updates this file). Browse [4.x](v4.md), [3.x](v3.md), or [2.x](v2.md) for full notes per series.

## Significant changes

<details markdown="1" open>
<summary>v3.x → v4.0.0</summary>

* **Removed** the media download feature.
* **CI:** Codecov GitHub Action updated from v5 to v6 (affects workflows that pin this action).
* **Bot:** Optional Discord **gateway sharding** for larger deployments.
* **Commands / UX:** Per-command `/help`, whitelist cache reconciliation, anonymous messaging destination channel behavior.
* **Observability:** OTLP tracing hooks and related telemetry work.
* **Logging:** `python-json-logger` and related dependency updates.

</details>

<details markdown="1">
<summary>v2.x → v3.0.0</summary>

* **CI:** GitHub CodeQL Action updated from v3 to v4.
* **Features:** Help permission filtering, whitelist notifications, quotebook import, moderation fixes.
* **Quality:** Postgres service in CI for integration tests; database metrics, migrations, and query/index tuning on hot paths.

</details>

<details markdown="1">
<summary>v1.x → v2.0.0</summary>

* **CI/CD:** Broad bumps for GitHub Actions (artifact uploads, CodeQL, paths-filter, create-github-app-token, Docker build/login/metadata/buildx, pre-commit hooks).
* **Features:** Anonymous posting, `/help`, Tidal mix support, whitelist refactor.
* **Ops:** Health endpoint behavior (metrics cache, UTF-8 decoding, configurable bind).

</details>
