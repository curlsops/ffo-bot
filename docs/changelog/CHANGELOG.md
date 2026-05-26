# Changelog

## [6.0.0](https://github.com/curlsops/ffo-bot/compare/v5.0.0...v6.0.0) (2026-05-26)


### ⚠ BREAKING CHANGES

* **deps:** Update actions/upload-pages-artifact action ( v3 ➔ v5.0.0 )
* **deps:** Update actions/setup-python action ( v5 ➔ v6.2.0 )
* **deps:** Update actions/checkout action ( v4 ➔ v6.0.2 )
* **deps:** Update actions/cache action ( v4 ➔ v5.0.5 )
* **python:** Update dependency zipp ( 3.23.1 ➔ 4.1.0 )

### Features

* **deps:** Update actions/cache action ( v4 ➔ v5.0.5 ) ([3a466cc](https://github.com/curlsops/ffo-bot/commit/3a466ccf74d0482fac27ac6197cbf2e9669ec1f3))
* **deps:** Update actions/checkout action ( v4 ➔ v6.0.2 ) ([d40d541](https://github.com/curlsops/ffo-bot/commit/d40d541a179f292995a3cc83de9131079efd4451))
* **deps:** Update actions/setup-python action ( v5 ➔ v6.2.0 ) ([76507a0](https://github.com/curlsops/ffo-bot/commit/76507a01c8579f587357bae478f7244d5c6a2e99))
* **deps:** Update actions/upload-pages-artifact action ( v3 ➔ v5.0.0 ) ([4a9df86](https://github.com/curlsops/ffo-bot/commit/4a9df86bd23bb88508ad93cb3590ef68ab81a02e))
* **pre-commit:** update hook psf/black ( 26.3.1 ➔ 26.5.1 ) ([#239](https://github.com/curlsops/ffo-bot/issues/239)) ([63d363d](https://github.com/curlsops/ffo-bot/commit/63d363d429876bb16c1aeea06b1f63e1221c644a))
* **python:** update dependency black ( 26.3.1 ➔ 26.5.1 ) ([#240](https://github.com/curlsops/ffo-bot/issues/240)) ([8c3603a](https://github.com/curlsops/ffo-bot/commit/8c3603a36a3fc69b0f3b8894297eaf12703d2d6c))
* **python:** Update dependency zipp ( 3.23.1 ➔ 4.1.0 ) ([e228dda](https://github.com/curlsops/ffo-bot/commit/e228ddab035d6953a34b819da80dde0df633f7e4))
* **spotify:** SpotAPI catalog + docs ([d8f89d4](https://github.com/curlsops/ffo-bot/commit/d8f89d4be2658dbb7fbe4a5a180e05ee623ea8fd))
* **spotify:** use SpotAPI public catalog for URLs ([7306967](https://github.com/curlsops/ffo-bot/commit/7306967a6db19a8577db1c03c00f1b65163c0b8e))
* **telemetry:** add log context, verbose logging, and OTEL spans ([8f74cd1](https://github.com/curlsops/ffo-bot/commit/8f74cd1ccf2c10266ffe3e957cf9b661cadb7833))


### Bug Fixes

* **ci:** add gcompat for SpotAPI tls_client on Alpine ([5503122](https://github.com/curlsops/ffo-bot/commit/5503122df4047c63fde2704cc09b9f6155a3bf4a))
* **music:** show full playlist track count in play feedback ([ac79040](https://github.com/curlsops/ffo-bot/commit/ac790404772c3214a73f8046c2278e794ac2c6a1))
* **python:** update dependency types-aiofiles ( 25.1.0.20260508 ➔ 25.1.0.20260518 ) ([#237](https://github.com/curlsops/ffo-bot/issues/237)) ([89ccc47](https://github.com/curlsops/ffo-bot/commit/89ccc47be373349dddbe22481a94a4d5e6ea3d3a))
* **python:** update dependency types-python-dateutil ( 2.9.0.20260508 ➔ 2.9.0.20260518 ) ([#238](https://github.com/curlsops/ffo-bot/issues/238)) ([34874d7](https://github.com/curlsops/ffo-bot/commit/34874d7b9abd4a339999f405fa85e9a151d91f21))
* **python:** update opentelemetry-python ([#246](https://github.com/curlsops/ffo-bot/issues/246)) ([7a7de82](https://github.com/curlsops/ffo-bot/commit/7a7de828a76d49128d76ad97fac19c8c06426568))
* **spotify:** drop unused random test import ([db22f6d](https://github.com/curlsops/ffo-bot/commit/db22f6dcd773c7ece6c8a22bc33c27f4f5c70bdf))
* **spotify:** handle tls_client.cffi without __file__ in tests ([947fc9f](https://github.com/curlsops/ffo-bot/commit/947fc9f8d617e2409ea44a0e7912d23db5400094))
* **spotify:** prevent SpotAPI SIGSEGV on Debian slim ([3a484f9](https://github.com/curlsops/ffo-bot/commit/3a484f9cf8842b996d20dfcfaebce65a1275bca6))
* **voice:** add davey and harden Lavalink voice on Alpine ([e93686c](https://github.com/curlsops/ffo-bot/commit/e93686c932605585f80a627d7b8e48fb2bdf18ab))

## [4.2.1](https://github.com/curlsops/ffo-bot/compare/v4.2.0...v4.2.1) (2026-04-14)


### Bug Fixes

* **docker:** align runtime user with Kubernetes for migrations ([eee8545](https://github.com/curlsops/ffo-bot/commit/eee8545e3e2e87f39519a8c21ed11758d601e807))
* **docker:** align runtime user with Kubernetes for migrations ([1ce2096](https://github.com/curlsops/ffo-bot/commit/1ce20969497f41334e9249a326ff5096be6e60ae))
* **github-action:** update action actions/upload-artifact ( v7.0.0 ➔ v7.0.1 ) ([#186](https://github.com/curlsops/ffo-bot/issues/186)) ([7ad2d16](https://github.com/curlsops/ffo-bot/commit/7ad2d16206769e72cdd965e0b158a56341a84136))
* **minecraft_rcon:** narrow broadcast response before append for mypy ([a3d77eb](https://github.com/curlsops/ffo-bot/commit/a3d77ebe0e274ff4f0f608745c8fdb68609236dd))
* **python:** update dependency authlib ( 1.6.9 ➔ 1.6.10 ) ([#183](https://github.com/curlsops/ffo-bot/issues/183)) ([8f9f522](https://github.com/curlsops/ffo-bot/commit/8f9f522c2f1a709a4de0271d2a6be6b1e9b874f6))
* **python:** update dependency zipp ( 3.23.0 ➔ 3.23.1 ) ([#184](https://github.com/curlsops/ffo-bot/issues/184)) ([e666249](https://github.com/curlsops/ffo-bot/commit/e6662491cd5f3db22cced61b1db565beb14aff68))

## [4.2.0](https://github.com/curlsops/ffo-bot/compare/v4.1.0...v4.2.0) (2026-04-12)


### Features

* **python:** update dependency prometheus-client ( 0.24.1 ➔ 0.25.0 ) ([#181](https://github.com/curlsops/ffo-bot/issues/181)) ([294a559](https://github.com/curlsops/ffo-bot/commit/294a559085b9a0299aead1219f3125c93018132a))


### Bug Fixes

* **python:** update dependency cryptography ( 46.0.6 ➔ 46.0.7 ) ([#172](https://github.com/curlsops/ffo-bot/issues/172)) ([97a7941](https://github.com/curlsops/ffo-bot/commit/97a79412a8a68125fcf0da95ff81386dda65d973))
* **python:** update dependency pytest ( 9.0.2 ➔ 9.0.3 ) ([#174](https://github.com/curlsops/ffo-bot/issues/174)) ([2e6e2a5](https://github.com/curlsops/ffo-bot/commit/2e6e2a568bc9a8ed5ab096c9eb5dacace079fe02))
* **python:** update dependency types-aiofiles ( 25.1.0.20251011 ➔ 25.1.0.20260408 ) ([#175](https://github.com/curlsops/ffo-bot/issues/175)) ([9646020](https://github.com/curlsops/ffo-bot/commit/9646020fd440ca2bdc931c82ff6e848b0fabaed9))
* **python:** update dependency types-aiofiles ( 25.1.0.20260408 ➔ 25.1.0.20260409 ) ([#179](https://github.com/curlsops/ffo-bot/issues/179)) ([31fc2b7](https://github.com/curlsops/ffo-bot/commit/31fc2b72bea246fb809b12758d923c11ecb756da))
* **python:** update dependency types-python-dateutil ( 2.9.0.20260402 ➔ 2.9.0.20260408 ) ([#176](https://github.com/curlsops/ffo-bot/issues/176)) ([18564a4](https://github.com/curlsops/ffo-bot/commit/18564a41ec4fbee5de5363f4e1588faf6b3c0e6b))

## [4.1.0](https://github.com/curlsops/ffo-bot/compare/v4.0.0...v4.1.0) (2026-04-07)


### Features

* **python:** update dependency marshmallow ( 4.2.2 ➔ 4.3.0 ) ([#158](https://github.com/curlsops/ffo-bot/issues/158)) ([3829476](https://github.com/curlsops/ffo-bot/commit/382947607ea02baf174631059a28655729bd9c08))
* **python:** update dependency pytest-cov ( 7.0.0 ➔ 7.1.0 ) ([#166](https://github.com/curlsops/ffo-bot/issues/166)) ([b508175](https://github.com/curlsops/ffo-bot/commit/b5081750f908f496fbae6474d37defbea045a8d5))
* **python:** update dependency requests ( 2.32.5 ➔ 2.33.1 ) ([#159](https://github.com/curlsops/ffo-bot/issues/159)) ([973335b](https://github.com/curlsops/ffo-bot/commit/973335b76fef7fdd4582c8161d6ba73f69b6f3e0))
* **python:** update linting ([07618ed](https://github.com/curlsops/ffo-bot/commit/07618edcefef0fe62b45b85425e3202c4a20e722))
* **python:** update linting ([245becc](https://github.com/curlsops/ffo-bot/commit/245becc59788b7daf726b8042e699a8d1838506c))


### Bug Fixes

* **python:** update dependency aiohttp ( 3.13.3 ➔ 3.13.5 ) ([5892b51](https://github.com/curlsops/ffo-bot/commit/5892b51979566cbc500cd9d26b95712f1cfdbbff))
* **python:** update dependency aiohttp ( 3.13.3 ➔ 3.13.5 ) ([d214846](https://github.com/curlsops/ffo-bot/commit/d21484633a1c663a660f469e725e36bd7eeaaad1))
* **python:** update dependency cryptography ( 46.0.5 ➔ 46.0.6 ) ([e46f3c3](https://github.com/curlsops/ffo-bot/commit/e46f3c32ba115c2aac3c4300e9b487bd5e3fb792))
* **python:** update dependency cryptography ( 46.0.5 ➔ 46.0.6 ) ([62b53eb](https://github.com/curlsops/ffo-bot/commit/62b53eb220211884a5cff81702370471e9f76597))
* **python:** update dependency filelock ( 3.25.1 ➔ 3.25.2 ) ([e37260c](https://github.com/curlsops/ffo-bot/commit/e37260c68d5e10dc01fa47e1d7ad397df62f6ad9))
* **python:** update dependency filelock ( 3.25.1 ➔ 3.25.2 ) ([732c172](https://github.com/curlsops/ffo-bot/commit/732c172c2c893e598ad11f9bd3436e6bf25a3645))
* **python:** update dependency spacy ( 3.8.11 ➔ 3.8.14 ) ([5d684e0](https://github.com/curlsops/ffo-bot/commit/5d684e001429693d865e9b0607b8e89cba43dd9e))
* **python:** update dependency spacy ( 3.8.11 ➔ 3.8.14 ) ([c9e1137](https://github.com/curlsops/ffo-bot/commit/c9e11373ba61d25734dc1e41a45d54e3423181e2))
* **python:** update dependency sqlalchemy ( 2.0.48 ➔ 2.0.49 ) ([0e18ee7](https://github.com/curlsops/ffo-bot/commit/0e18ee73f9e5de305e21547c39e23af4e9f34787))
* **python:** update dependency sqlalchemy ( 2.0.48 ➔ 2.0.49 ) ([af15ebd](https://github.com/curlsops/ffo-bot/commit/af15ebd8061a32b4b9765211152ea6f84a22012c))
* **python:** update dependency testcontainers ( 4.14.1 ➔ 4.14.2 ) ([da7a3ec](https://github.com/curlsops/ffo-bot/commit/da7a3ec0b0070f5c45228c6e343276a0cfb67f91))
* **python:** update dependency testcontainers ( 4.14.1 ➔ 4.14.2 ) ([a64796d](https://github.com/curlsops/ffo-bot/commit/a64796d29ab994c02659d02fd2f0f1229497b953))
* **python:** update dependency types-python-dateutil ( 2.9.0.20260305 ➔ 2.9.0.20260402 ) ([#165](https://github.com/curlsops/ffo-bot/issues/165)) ([b0811fe](https://github.com/curlsops/ffo-bot/commit/b0811fe78865a7098afc5af6804a55703d8c4a0d))
* **test:** resolve anonymize_mod NameError in xdist CI ([f32bd75](https://github.com/curlsops/ffo-bot/commit/f32bd75d344fa8cf4ae1ec5cf2c7979ca8386650))

## [4.0.0](https://github.com/curlsops/ffo-bot/compare/v3.1.0...v4.0.0) (2026-04-06)


### ⚠ BREAKING CHANGES

* remove media download feature
* **deps:** Update codecov/codecov-action action ( v5 ➔ v6 )

### Features

* **bot:** add opt-in Discord gateway sharding ([f4d0cba](https://github.com/curlsops/ffo-bot/commit/f4d0cba067b6551a47913cca72e395aa50b6f96f))
* **deps:** Update codecov/codecov-action action ( v5 ➔ v6 ) ([6be76b3](https://github.com/curlsops/ffo-bot/commit/6be76b393432035f3b90c0ad28d9f5b1ff7b6383))
* per-command /help, whitelist cache reconcile, anon destination channel ([2e100b2](https://github.com/curlsops/ffo-bot/commit/2e100b276d66976fdd2154f2a3b6d3f616ac0dcc))
* **python:** update dependency python-json-logger ( 4.0.0 ➔ 4.1.0 ) ([#151](https://github.com/curlsops/ffo-bot/issues/151)) ([3a91ab8](https://github.com/curlsops/ffo-bot/commit/3a91ab884e5568bae2b05d8e206e0f90d6f1b31c))
* remove media download feature ([0b37e38](https://github.com/curlsops/ffo-bot/commit/0b37e38f37fa808b1edfd0cb24db9353d9dfefe0))
* **telemetry:** add OTLP tracing and message flood test ([358b280](https://github.com/curlsops/ffo-bot/commit/358b2809cf3f30e1572637e38df25bf587a87be9))


### Bug Fixes

* **test:** resolve anonymize_mod NameError in xdist CI ([f32bd75](https://github.com/curlsops/ffo-bot/commit/f32bd75d344fa8cf4ae1ec5cf2c7979ca8386650))

## [3.0.1](https://github.com/curlsops/ffo-bot/compare/v3.0.0...v3.0.1) (2026-03-18)


### Bug Fixes

* **moderation:** use timed_out_until, mute, deaf for Discord API compatibility ([a622c70](https://github.com/curlsops/ffo-bot/commit/a622c706635d6587a48c817eea976710bdb7a81b))

## [3.0.0](https://github.com/curlsops/ffo-bot/compare/v2.0.0...v3.0.0) (2026-03-16)


### ⚠ BREAKING CHANGES

* **deps:** Update github/codeql-action action ( v3 ➔ v4 )

### Features

* **deps:** Update github/codeql-action action ( v3 ➔ v4 ) ([d4942af](https://github.com/curlsops/ffo-bot/commit/d4942af5da64953336708d7cc3b207a20066728a))
* help permission filter, whitelist notify, quotebook import, moderation fixes ([74b56c8](https://github.com/curlsops/ffo-bot/commit/74b56c8d972ff75feef990971cc19785461fc031))


### Bug Fixes

* **ci:** add Postgres service for integration tests ([bc74263](https://github.com/curlsops/ffo-bot/commit/bc74263affc237843fbf234ee16893a2a0260802))
* **codeql:** address statement-has-no-effect and unused-import alerts ([69a2942](https://github.com/curlsops/ffo-bot/commit/69a2942ac9cf56ab61c3df415980486b2a5b7227))
* **database:** metrics, migrations, and index hygiene ([117309a](https://github.com/curlsops/ffo-bot/commit/117309a933fbc1f213d6a8fcf8741cbe8d90365c))
* **deps:** pin transitive dependencies ([d0d1f59](https://github.com/curlsops/ffo-bot/commit/d0d1f59ffb62e9faf2192926987465e9618c858d))
* **migration:** resolve CodeQL unused global variable findings ([04839f7](https://github.com/curlsops/ffo-bot/commit/04839f7c1ecf2675800d744c0712d0181dcf8304))
* **mypy:** resolve type errors in auth, privacy, whitelist ([5340f2c](https://github.com/curlsops/ffo-bot/commit/5340f2c2a67485bce80feb98b1bc4b7b00abf89d))
* **mypy:** revert _ = await in http_session to fix func-returns-value ([690c31d](https://github.com/curlsops/ffo-bot/commit/690c31df8744d4d9b6ec534fda05e24c72fb1e68))
* **test:** patch session_scope/get_session to avoid event loop closed under xdist ([f0c9905](https://github.com/curlsops/ffo-bot/commit/f0c99051bdcb71a495032db6ed5de6900b5e695d))
* **tests:** patch get_session to fix event loop closed in spotify/status_rotator ([63094f0](https://github.com/curlsops/ffo-bot/commit/63094f0bc89cc3e492b320d66d95eb1275bcc1f2))
* **tests:** rename test_giveaway_greroll to test_giveaway_reroll ([b2566f9](https://github.com/curlsops/ffo-bot/commit/b2566f9bacad1089e85fe610183183836eb77a2b))


### Performance Improvements

* **runtime:** tighten hot-path handlers and add query indexes ([1148c23](https://github.com/curlsops/ffo-bot/commit/1148c23ab42f314e13149d9330c764259b6e84bf))

## [2.0.0](https://github.com/curlsops/ffo-bot/compare/v1.7.0...v2.0.0) (2026-03-14)


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

* address CodeQL findings and CI git ownership ([b00ce6c](https://github.com/curlsops/ffo-bot/commit/b00ce6c01ef44691d5d2f34d7c66f91ff431706c))
* **admin:** correct clear_commands usage - sync method, not async ([92d6741](https://github.com/curlsops/ffo-bot/commit/92d6741b70e9e08bc8a704d919376d6d5bb5d8eb))
* **ci:** use codecov_yml_path for Codecov config ([7af8f34](https://github.com/curlsops/ffo-bot/commit/7af8f34e3349edc158358094bac80295a0c59e45))
* **github-action:** update action dorny/paths-filter ( v3.0.2 ➔ v3.0.3 ) ([#122](https://github.com/curlsops/ffo-bot/issues/122)) ([7137c03](https://github.com/curlsops/ffo-bot/commit/7137c03f5a7d711f283f0e3b5c9d6d1e02ff3ed4))
* **github-action:** update action dorny/paths-filter ( v4.0.0 ➔ v4.0.1 ) ([#127](https://github.com/curlsops/ffo-bot/issues/127)) ([13f74e9](https://github.com/curlsops/ffo-bot/commit/13f74e9d3fc3db87723de1ebeaf318f6ee1655fc))
* **giveaway:** exclude previous winners from reroll pool ([cb807dc](https://github.com/curlsops/ffo-bot/commit/cb807dc6e8a6509c9365b11a044f8d68f44dd438))
* **help:** cap embed fields at 25 to avoid Discord API limit ([a6f3ef6](https://github.com/curlsops/ffo-bot/commit/a6f3ef6a9556b0ebb707c9afbd6fc191dabf15d2))
* **pre-commit:** update hook psf/black ( 26.3.0 ➔ 26.3.1 ) ([9ef0ecb](https://github.com/curlsops/ffo-bot/commit/9ef0ecb1348eb9025fd374813fafa43f41855292))
* **pre-commit:** update hook psf/black ( 26.3.0 ➔ 26.3.1 ) ([adc1ea7](https://github.com/curlsops/ffo-bot/commit/adc1ea73b08e0fd792f0947fc798256c57865511))
* **pre-commit:** update hook pycqa/isort ( 8.0.0 ➔ 8.0.1 ) ([#111](https://github.com/curlsops/ffo-bot/issues/111)) ([fb69da0](https://github.com/curlsops/ffo-bot/commit/fb69da038522860007a2e1dc4a85e142c623ff33))
* URL parsing for music links and secure health response ([9945cab](https://github.com/curlsops/ffo-bot/commit/9945cab64dd70bd0ae17234021c0239f00faffd2))
