# Changelog

## [2.0.0](https://github.com/curlsops/ffo-bot/compare/v1.7.0...v2.0.0) (2026-03-14)


### ⚠ BREAKING CHANGES

* **deps:** Update actions/create-github-app-token action ( v2 ➔ v3 )
* **deps:** Update dorny/paths-filter action ( v3.0.3 ➔ v4.0.0 )
* **deps:** Update github/codeql-action action ( v3 ➔ v4 )
* **deps:** Update GitHub Artifact Actions
* **deps:** Update github/codeql-action action ( v3 ➔ v4 )
* **deps:** Update pre-commit hook pre-commit/pre-commit-hooks ( v4.5.0 ➔ v6.0.0 )
* **deps:** Update docker/setup-buildx-action action ( v3 ➔ v4 )
* **deps:** Update docker/metadata-action action ( v5 ➔ v6 )
* **deps:** Update docker/login-action action ( v3 ➔ v4 )
* **deps:** Update docker/build-push-action action ( v6 ➔ v7 )

### Features

* add anonymous post, help command, Tidal mix, whitelist refactor ([ceb5be5](https://github.com/curlsops/ffo-bot/commit/ceb5be5082cddf8419243f83e1393d0e01595c5f))
* **ci:** add Snyk for Python and Docker vulnerability scanning ([1a3b9f0](https://github.com/curlsops/ffo-bot/commit/1a3b9f0ea5a3bd224b481d5b1132e905227b1d96))
* **deps:** Update actions/create-github-app-token action ( v2 ➔ v3 ) ([8929a0c](https://github.com/curlsops/ffo-bot/commit/8929a0cf8e5b9221b3f9fb1759a5a18e667a120f))
* **deps:** Update docker/build-push-action action ( v6 ➔ v7 ) ([501ee49](https://github.com/curlsops/ffo-bot/commit/501ee49f24c7fd2fda5d47c28ac5fde8e31b0bba))
* **deps:** Update docker/login-action action ( v3 ➔ v4 ) ([98b1da4](https://github.com/curlsops/ffo-bot/commit/98b1da4537fdc8244401c79ce44ce4dc821aefee))
* **deps:** Update docker/metadata-action action ( v5 ➔ v6 ) ([d6dfb4b](https://github.com/curlsops/ffo-bot/commit/d6dfb4bd127284dfee9ad6646529876c1457423f))
* **deps:** Update docker/setup-buildx-action action ( v3 ➔ v4 ) ([72390a1](https://github.com/curlsops/ffo-bot/commit/72390a1d4535fefc0b2f828c7cde6f403f3c254e))
* **deps:** Update dorny/paths-filter action ( v3.0.3 ➔ v4.0.0 ) ([bbe4c72](https://github.com/curlsops/ffo-bot/commit/bbe4c7268d32b3c55dd75b898fd0226151fe6c85))
* **deps:** Update GitHub Artifact Actions ([96cb7c6](https://github.com/curlsops/ffo-bot/commit/96cb7c66e62af57c4c4a4dacb66ab3a972c23c44))
* **deps:** Update github/codeql-action action ( v3 ➔ v4 ) ([be69340](https://github.com/curlsops/ffo-bot/commit/be693407fad5344205ac5f0f3dace5e59665972c))
* **deps:** Update github/codeql-action action ( v3 ➔ v4 ) ([bc42158](https://github.com/curlsops/ffo-bot/commit/bc421582a82666015f29c82fffa765316dbf4c0d))
* **deps:** Update pre-commit hook pre-commit/pre-commit-hooks ( v4.5.0 ➔ v6.0.0 ) ([a3798ed](https://github.com/curlsops/ffo-bot/commit/a3798edd80a90323381a6bb846659b3a5f085cf2))
* **github-action:** update action aquasecurity/trivy-action ( 0.34.0 ➔ 0.35.0 ) ([#112](https://github.com/curlsops/ffo-bot/issues/112)) ([0606bae](https://github.com/curlsops/ffo-bot/commit/0606bae2253cd0c90bd3314aec2b202c160a7db4))
* **health:** cache metrics size, explicit UTF-8 decode, configurable host ([b7af526](https://github.com/curlsops/ffo-bot/commit/b7af526a67b8903560fd791749d84540d0082f62))
* **pre-commit:** update hook psf/black ( 26.1.0 ➔ 26.3.0 ) ([#114](https://github.com/curlsops/ffo-bot/issues/114)) ([24d77bf](https://github.com/curlsops/ffo-bot/commit/24d77bf4a61f14c2e5bb7182ef24f41e3c62a805))
* **pre-commit:** update hook pycqa/flake8 ( 7.0.0 ➔ 7.3.0 ) ([#115](https://github.com/curlsops/ffo-bot/issues/115)) ([9236a0f](https://github.com/curlsops/ffo-bot/commit/9236a0fa93b3b4014ae600808a83427bf4687aa4))
* **python:** update dependency black ( 26.1.0 ➔ 26.3.0 ) ([#105](https://github.com/curlsops/ffo-bot/issues/105)) ([4367374](https://github.com/curlsops/ffo-bot/commit/4367374fb98d28291bb086233256819bed96a9c1))


### Bug Fixes

* address CodeQL findings and CI git ownership ([b00ce6c](https://github.com/curlsops/ffo-bot/commit/b00ce6c01ef44691d5d2f34d7c66f91ff431706c))
* **admin:** correct clear_commands usage - sync method, not async ([92d6741](https://github.com/curlsops/ffo-bot/commit/92d6741b70e9e08bc8a704d919376d6d5bb5d8eb))
* **ci:** upgrade Trivy action, add if: always() for SARIF upload ([32bf8ce](https://github.com/curlsops/ffo-bot/commit/32bf8ce7894b747aeb69cc3b5a0cae7b30e40f54))
* **ci:** use codecov_yml_path for Codecov config ([7af8f34](https://github.com/curlsops/ffo-bot/commit/7af8f34e3349edc158358094bac80295a0c59e45))
* **github-action:** update action dorny/paths-filter ( v3.0.2 ➔ v3.0.3 ) ([#122](https://github.com/curlsops/ffo-bot/issues/122)) ([7137c03](https://github.com/curlsops/ffo-bot/commit/7137c03f5a7d711f283f0e3b5c9d6d1e02ff3ed4))
* **github-action:** update action dorny/paths-filter ( v4.0.0 ➔ v4.0.1 ) ([#127](https://github.com/curlsops/ffo-bot/issues/127)) ([13f74e9](https://github.com/curlsops/ffo-bot/commit/13f74e9d3fc3db87723de1ebeaf318f6ee1655fc))
* **giveaway:** exclude previous winners from reroll pool ([cb807dc](https://github.com/curlsops/ffo-bot/commit/cb807dc6e8a6509c9365b11a044f8d68f44dd438))
* **help:** cap embed fields at 25 to avoid Discord API limit ([a6f3ef6](https://github.com/curlsops/ffo-bot/commit/a6f3ef6a9556b0ebb707c9afbd6fc191dabf15d2))
* **pre-commit:** update hook psf/black ( 26.3.0 ➔ 26.3.1 ) ([9ef0ecb](https://github.com/curlsops/ffo-bot/commit/9ef0ecb1348eb9025fd374813fafa43f41855292))
* **pre-commit:** update hook psf/black ( 26.3.0 ➔ 26.3.1 ) ([adc1ea7](https://github.com/curlsops/ffo-bot/commit/adc1ea73b08e0fd792f0947fc798256c57865511))
* **pre-commit:** update hook pycqa/isort ( 8.0.0 ➔ 8.0.1 ) ([#111](https://github.com/curlsops/ffo-bot/issues/111)) ([fb69da0](https://github.com/curlsops/ffo-bot/commit/fb69da038522860007a2e1dc4a85e142c623ff33))
* URL parsing for music links, secure health response, Trivy exit-code ([9945cab](https://github.com/curlsops/ffo-bot/commit/9945cab64dd70bd0ae17234021c0239f00faffd2))
