# Changelog

## [5.0.0](https://github.com/curlsops/ffo-bot/compare/v4.4.0...v5.0.0) (2026-05-20)


### ⚠ BREAKING CHANGES

* **commands:** remove anonymous post feature
* **python:** Update dependency cryptography ( 47.0.0 ➔ 48.0.0 )
* **python:** Update dependency mypy ( 1.20.2 ➔ 2.1.0 )
* **python:** Update dependency cryptography ( 46.0.7 ➔ 47.0.0 )
* **deps:** Update googleapis/release-please-action action ( v4 ➔ v5 )

### Features

* **commands:** remove anonymous post feature ([ab5106e](https://github.com/curlsops/ffo-bot/commit/ab5106eb8b1262afee58521bc14577fa5af497c7))
* **deps:** Update googleapis/release-please-action action ( v4 ➔ v5 ) ([2f26fbf](https://github.com/curlsops/ffo-bot/commit/2f26fbf6fb9dead13518e18fee1f6d45c6e60386))
* **github-action:** update action actions/labeler ( v6.0.1 ➔ v6.1.0 ) ([#218](https://github.com/curlsops/ffo-bot/issues/218)) ([e2eb22b](https://github.com/curlsops/ffo-bot/commit/e2eb22bfb410f03b03b46eef9414287ea3bd3e35))
* **github-action:** update action useblacksmith/setup-docker-builder ( v1.7.0 ➔ v1.8.0 ) ([#212](https://github.com/curlsops/ffo-bot/issues/212)) ([d8ae668](https://github.com/curlsops/ffo-bot/commit/d8ae668d95a433a471f79906eb9694d6dc9cd2f9))
* **music:** generalize lazy playlist prefetch and tidal sampling ([9c43e23](https://github.com/curlsops/ffo-bot/commit/9c43e237ddda2e8247b5e2729dbf92353173c753))
* **music:** Spotify-first URLs and lazy playlist resolution ([f734696](https://github.com/curlsops/ffo-bot/commit/f7346967309ed7a9b895620bbb70f3cfa76bb0ed))
* **python:** Update dependency cryptography ( 46.0.7 ➔ 47.0.0 ) ([52e043e](https://github.com/curlsops/ffo-bot/commit/52e043e564fbc80806afd9ec4a687cc0f918818f))
* **python:** Update dependency cryptography ( 47.0.0 ➔ 48.0.0 ) ([08dfaae](https://github.com/curlsops/ffo-bot/commit/08dfaae6cd811bc3a77893707b801ff91e516288))
* **python:** Update dependency mypy ( 1.20.2 ➔ 2.1.0 ) ([31646f8](https://github.com/curlsops/ffo-bot/commit/31646f86f8407097dac2b30265dbad2066e47ab8))
* **python:** update dependency pre-commit ( 4.5.1 ➔ 4.6.0 ) ([#206](https://github.com/curlsops/ffo-bot/issues/206)) ([f22594d](https://github.com/curlsops/ffo-bot/commit/f22594d1c71715b56439e23c00c553674bad0116))
* **python:** update dependency pydantic ( 2.12.5 ➔ 2.13.4 ) ([#190](https://github.com/curlsops/ffo-bot/issues/190)) ([3e4cc61](https://github.com/curlsops/ffo-bot/commit/3e4cc61731a0b47c036d285aaae9b65e5397219f))
* **python:** update dependency pydantic-settings ( 2.13.1 ➔ 2.14.0 ) ([#207](https://github.com/curlsops/ffo-bot/issues/207)) ([ffc9197](https://github.com/curlsops/ffo-bot/commit/ffc9197130a0c85a4c19ede4bd3d64feaea2d49d))
* **python:** update dependency requests ( 2.33.1 ➔ 2.34.1 ) ([#219](https://github.com/curlsops/ffo-bot/issues/219)) ([675eb35](https://github.com/curlsops/ffo-bot/commit/675eb35843aee5ba86182873ab4d56e7a29f2a86))
* **python:** update dependency urllib3 ( 2.6.3 ➔ 2.7.0 ) ([#214](https://github.com/curlsops/ffo-bot/issues/214)) ([9922929](https://github.com/curlsops/ffo-bot/commit/9922929b103ad19926c588ade799866077cfd426))
* **spotify:** fetch full playlists without cap or sampling ([4cb0cb8](https://github.com/curlsops/ffo-bot/commit/4cb0cb821d95afc4c426d9cfec50b8b11a528f47))


### Bug Fixes

* **music:** surface missing Spotify Web API creds for playlist URLs ([f8d4cb0](https://github.com/curlsops/ffo-bot/commit/f8d4cb0af706405deb197532c3511820cd1e12d8))
* **music:** validate YouTube URLs for status embed link label ([6d49844](https://github.com/curlsops/ffo-bot/commit/6d49844696eb4ac9b62adf9cdb171c32e76293e7))
* **python:** align OpenTelemetry stack and Renovate grouping ([9542a7a](https://github.com/curlsops/ffo-bot/commit/9542a7a5a5ab18aa745953fcb1051c2938dec740))
* **python:** update dependency authlib ( 1.7.0 ➔ 1.7.2 ) ([#213](https://github.com/curlsops/ffo-bot/issues/213)) ([7df8f88](https://github.com/curlsops/ffo-bot/commit/7df8f8882f0136087930e812c42ff4a6bde98360))
* **python:** update dependency mypy ( 1.20.1 ➔ 1.20.2 ) ([#204](https://github.com/curlsops/ffo-bot/issues/204)) ([6ac36cb](https://github.com/curlsops/ffo-bot/commit/6ac36cb3f6a95099a8f6b2c9177170ded3cfcbb8))
* **python:** update dependency psycopg2-binary ( 2.9.11 ➔ 2.9.12 ) ([#205](https://github.com/curlsops/ffo-bot/issues/205)) ([5595daa](https://github.com/curlsops/ffo-bot/commit/5595daa6d1ef7b64511c072a73ac616764ac849e))
* **python:** update dependency pydantic-settings ( 2.14.0 ➔ 2.14.1 ) ([#221](https://github.com/curlsops/ffo-bot/issues/221)) ([92e862c](https://github.com/curlsops/ffo-bot/commit/92e862cb135baa9724b1ae17b08b0a2729d4f6b4))
* **python:** update dependency requests ( 2.34.1 ➔ 2.34.2 ) ([#224](https://github.com/curlsops/ffo-bot/issues/224)) ([0317f58](https://github.com/curlsops/ffo-bot/commit/0317f58c5463d9d0da6a8ed6559de6a7a3cfd344))
* **python:** update dependency types-aiofiles ( 25.1.0.20260409 ➔ 25.1.0.20260508 ) ([#222](https://github.com/curlsops/ffo-bot/issues/222)) ([2668b93](https://github.com/curlsops/ffo-bot/commit/2668b9353aa560e6c2105e63dd8249557b508d86))
* **python:** update dependency types-python-dateutil ( 2.9.0.20260408 ➔ 2.9.0.20260508 ) ([#223](https://github.com/curlsops/ffo-bot/issues/223)) ([940c208](https://github.com/curlsops/ffo-bot/commit/940c208fb14c15e551786dd2ee5f3a90bfcda764))
