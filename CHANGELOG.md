# Changelog

## [1.0.0](https://github.com/curlsops/ffo-bot/compare/v0.1.0...v1.0.0) (2026-02-28)


### ⚠ BREAKING CHANGES

* **github-action:** Update action actions/setup-python ( v5 ➔ v6 ) ([#29](https://github.com/curlsops/ffo-bot/issues/29))
* **github-action:** Update action actions/checkout ( v4 ➔ v6 ) ([#28](https://github.com/curlsops/ffo-bot/issues/28))
* **python:** Update python dependency isort ( 5.13.2 ➔ 8.0.0 ) ([#15](https://github.com/curlsops/ffo-bot/issues/15))
* **python:** Update python dependency black ( 23.12.1 ➔ 26.1.0 ) ([#14](https://github.com/curlsops/ffo-bot/issues/14))
* **python:** Update python dependency aiofiles ( 23.2.1 ➔ 25.1.0 ) ([#13](https://github.com/curlsops/ffo-bot/issues/13))
* **github-action:** Update action actions/create-github-app-token ( v1 ➔ v2 ) ([#32](https://github.com/curlsops/ffo-bot/issues/32))
* **github-action:** Update action postgres ( 16 ➔ 18 ) ([#12](https://github.com/curlsops/ffo-bot/issues/12))
* **python:** Update python dependency python-json-logger ( 2.0.7 ➔ 4.0.0 ) ([#16](https://github.com/curlsops/ffo-bot/issues/16))
* **github-action:** Update action actions/setup-python ( v5 ➔ v6 ) ([#9](https://github.com/curlsops/ffo-bot/issues/9))
* **github-action:** Update action codecov/codecov-action ( v4 ➔ v5 ) ([#10](https://github.com/curlsops/ffo-bot/issues/10))
* **github-action:** Update action actions/checkout

### Features

* add automated releases and deployment examples ([832d7ae](https://github.com/curlsops/ffo-bot/commit/832d7ae6f9be27c58bcb4f8e118ab708043b50e7))
* add nightly builds with multi-platform support ([db4ea23](https://github.com/curlsops/ffo-bot/commit/db4ea23e72ce5383b19838e9f6823dfa949f9c38))
* add nightly builds with multi-platform support ([d67bb54](https://github.com/curlsops/ffo-bot/commit/d67bb54571ab1fc30c76de44b089b58dc6c6d805))
* **build:** add --fix flag for auto-formatting ([a889999](https://github.com/curlsops/ffo-bot/commit/a889999434635946509c318657091e76ec451ddf))
* **ci:** add custom CI image with pre-installed dependencies ([b161b02](https://github.com/curlsops/ffo-bot/commit/b161b0272e7e0830b4ef462402b3804541a91646))
* **ci:** use pre-built CI image for faster workflows ([e046172](https://github.com/curlsops/ffo-bot/commit/e04617269ee336ec6dc39ce23090b7c6a38dd983))
* **ci:** use pre-built CI image for faster workflows ([a66dbfe](https://github.com/curlsops/ffo-bot/commit/a66dbfeeca554c581d8d7823778448ace039d876))
* emoji validation and phrase autocomplete for reactbot ([3bc0df3](https://github.com/curlsops/ffo-bot/commit/3bc0df34ff64c6e7908ea10ea045bbdac4fab5f9))
* **github-release:** update release python ([#7](https://github.com/curlsops/ffo-bot/issues/7)) ([d79d23a](https://github.com/curlsops/ffo-bot/commit/d79d23a817e8bf3e4136eaff382ec5b7d7ca3e61))
* initial FFO Discord bot implementation ([f416579](https://github.com/curlsops/ffo-bot/commit/f416579098059102f054c6c07cfb7e417bacecf2))
* **python:** Update python dependency aiofiles ( 23.2.1 ➔ 25.1.0 ) ([#13](https://github.com/curlsops/ffo-bot/issues/13)) ([035fba9](https://github.com/curlsops/ffo-bot/commit/035fba9ec5bf6deb905060c88d4bdc10a599039f))
* **python:** Update python dependency black ( 23.12.1 ➔ 26.1.0 ) ([#14](https://github.com/curlsops/ffo-bot/issues/14)) ([979135a](https://github.com/curlsops/ffo-bot/commit/979135ab63cd2dbc793d014ac360be0ecaff63fd))
* **python:** Update python dependency isort ( 5.13.2 ➔ 8.0.0 ) ([#15](https://github.com/curlsops/ffo-bot/issues/15)) ([e773bc5](https://github.com/curlsops/ffo-bot/commit/e773bc59986a05352d84574b56f6987928d23655))
* **python:** Update python dependency python-json-logger ( 2.0.7 ➔ 4.0.0 ) ([#16](https://github.com/curlsops/ffo-bot/issues/16)) ([dfd9941](https://github.com/curlsops/ffo-bot/commit/dfd994185e7fea3604befee2cecb2f84b2b149f9))


### Bug Fixes

* alembic config and partial unique constraints ([f4a0c27](https://github.com/curlsops/ffo-bot/commit/f4a0c27cce872e79fa3bff908422f4d32d31060f))
* **auto-merge:** remove wait-on-check-action ([#24](https://github.com/curlsops/ffo-bot/issues/24)) ([4616d2d](https://github.com/curlsops/ffo-bot/commit/4616d2de7747f27914300169acd1cb2af6bd1f37))
* **autofix:** use GitHub App token to trigger CI ([#30](https://github.com/curlsops/ffo-bot/issues/30)) ([7baba25](https://github.com/curlsops/ffo-bot/commit/7baba2578fed24b8ff089080647669ef9c06c977))
* **ci:** add container for kubernetes runner mode ([1d7e891](https://github.com/curlsops/ffo-bot/commit/1d7e891f18d2849595781963ab7893ee2d1b785b))
* **ci:** add Node.js to CI image for GitHub Actions ([#21](https://github.com/curlsops/ffo-bot/issues/21)) ([352da21](https://github.com/curlsops/ffo-bot/commit/352da2195d97c800806a6e3c02c8d532db3433a7))
* **ci:** improve Renovate auto-merge workflow ([539cb46](https://github.com/curlsops/ffo-bot/commit/539cb463af80ba80cdc1a4c31eb5b6d2d4d07bc8))
* **ci:** update workflows for Kubernetes runner mode ([205e4f2](https://github.com/curlsops/ffo-bot/commit/205e4f2556a089b4ad4daa1ee4c1f20d1f0b30e4))
* **ci:** use python:3.12-slim directly until CI image is built ([17ad15e](https://github.com/curlsops/ffo-bot/commit/17ad15eb7cfee3cf6544fcc5533dcc6a4bdceb92))
* **ci:** use ubuntu-latest for CI tests ([#22](https://github.com/curlsops/ffo-bot/issues/22)) ([b7dba4f](https://github.com/curlsops/ffo-bot/commit/b7dba4ff5dfbd220476b1e3634690757a00aa988))
* graceful duplicate handling and phrase autocomplete ([7fc7545](https://github.com/curlsops/ffo-bot/commit/7fc75458585a2e81457db9a49249a3b08c6e2e3f))
* normalize messages preserving emoticons, strip only @#$ ([0d75f60](https://github.com/curlsops/ffo-bot/commit/0d75f6087fdd14f8da39da142de6c6ed1fb8737f))
* preserve punctuation in phrase matching ([be39bc2](https://github.com/curlsops/ffo-bot/commit/be39bc2804e5a1e569ecbdc874d698c85c73008f))
* register autocomplete in __init__ for Cog compatibility ([f0fc2e6](https://github.com/curlsops/ffo-bot/commit/f0fc2e6befc7274c07213ef634637aa83a949b9a))
* resolve merge conflicts for arc-runner-set ([1aab183](https://github.com/curlsops/ffo-bot/commit/1aab183b50edaf132c047e269f03d5955b68ca63))
* use arc-runner-set for auto-merge workflow ([d81a90d](https://github.com/curlsops/ffo-bot/commit/d81a90db998d994352a2d6105caa4ca7481bcb53))
* **workflows:** use ubuntu-latest for all workflows ([#23](https://github.com/curlsops/ffo-bot/issues/23)) ([8b13928](https://github.com/curlsops/ffo-bot/commit/8b139280956b300129fe5f13f6503782c2aa6965))


### CI/CD

* **github-action:** Update action actions/checkout ([abc885a](https://github.com/curlsops/ffo-bot/commit/abc885a91b0de75c5576676be79bf3354500d338))
* **github-action:** Update action actions/checkout ( v4 ➔ v6 ) ([#28](https://github.com/curlsops/ffo-bot/issues/28)) ([cdde1fd](https://github.com/curlsops/ffo-bot/commit/cdde1fd441e56a2f0e5ef78d5ba77f51cb5981b8))
* **github-action:** Update action actions/create-github-app-token ( v1 ➔ v2 ) ([#32](https://github.com/curlsops/ffo-bot/issues/32)) ([9e02fe3](https://github.com/curlsops/ffo-bot/commit/9e02fe31b283791f66a0564b3633a5a2fde63411))
* **github-action:** Update action actions/setup-python ( v5 ➔ v6 ) ([#29](https://github.com/curlsops/ffo-bot/issues/29)) ([62c6b91](https://github.com/curlsops/ffo-bot/commit/62c6b9138980b785a84fcd8d742bd8fa523a699c))
* **github-action:** Update action actions/setup-python ( v5 ➔ v6 ) ([#9](https://github.com/curlsops/ffo-bot/issues/9)) ([a692dd1](https://github.com/curlsops/ffo-bot/commit/a692dd122bd0704d9c695a45b9b282125d5dba51))
* **github-action:** Update action codecov/codecov-action ( v4 ➔ v5 ) ([#10](https://github.com/curlsops/ffo-bot/issues/10)) ([ee331fa](https://github.com/curlsops/ffo-bot/commit/ee331fafa211221d5f31af3727bf03a40aacbb91))
* **github-action:** Update action postgres ( 16 ➔ 18 ) ([#12](https://github.com/curlsops/ffo-bot/issues/12)) ([cfb4f16](https://github.com/curlsops/ffo-bot/commit/cfb4f16b1d1f8ca7ff8513965cee2e1d8fd82acf))
