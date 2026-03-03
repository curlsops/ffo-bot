# Changelog

## [1.6.0](https://github.com/curlsops/ffo-bot/compare/v1.5.5...v1.6.0) (2026-03-03)


### Features

* **cache:** add in-memory cache for FAQ, quotebook, reactbot, reaction roles, notifier ([ed53a1d](https://github.com/curlsops/ffo-bot/commit/ed53a1dc40fbc6dfb9789a87301687009864f743))
* **cache:** add in-memory whitelist cache ([5908e8f](https://github.com/curlsops/ffo-bot/commit/5908e8f4dfb911c1382e4f0a9dd5b43d0fb0b7e5))
* **config:** add feature flags and RCON settings ([e5895a9](https://github.com/curlsops/ffo-bot/commit/e5895a9ccb43b52b0a5d49f74ab6389816dd8ce8))
* **database:** add query duration metrics ([f58e794](https://github.com/curlsops/ffo-bot/commit/f58e794442a39d04959d13a57702b3cd32bf961e))
* **discord:** add FAQ command system ([bfd73b5](https://github.com/curlsops/ffo-bot/commit/bfd73b573ddf7147e73e58ff19001e77ff253fa2))
* **discord:** add quotebook feature ([b01b147](https://github.com/curlsops/ffo-bot/commit/b01b147632304fdff30592837973a3688cb07042))
* **discord:** add unit and currency conversion ([efeebd0](https://github.com/curlsops/ffo-bot/commit/efeebd0b131d83315670001b5783ba5622c9bffd))
* **discord:** integrate whitelist and conversion in message handlers ([9d41991](https://github.com/curlsops/ffo-bot/commit/9d4199128722bc7920cec0d6764c313f3b2e9894))
* **giveaway,auth,db:** prize thread, DB resilience, 100% coverage ([4a1178b](https://github.com/curlsops/ffo-bot/commit/4a1178b099b627cd3103917d3fafc985d784d051))
* **giveaway:** cache-aside with DB fallback, NotFound handling, prune expired ([e3db15b](https://github.com/curlsops/ffo-bot/commit/e3db15b4cf61912f2b46cc933fd7d8dc83c71b01))
* **giveaway:** expand who can close prize threads ([e10adc0](https://github.com/curlsops/ffo-bot/commit/e10adc0a99d072c1e07aa634e673f11b9afad02d))
* **metrics:** add global command instrumentation ([bf8574b](https://github.com/curlsops/ffo-bot/commit/bf8574b59d47bcdfff0864d815b31195b4315ede))
* **minecraft:** add whitelist management via RCON ([bd86437](https://github.com/curlsops/ffo-bot/commit/bd8643793f1072e84196b81ce3e2ba800706cc68))
* **minecraft:** store UUID from Mojang API with NameMC fallback ([2309693](https://github.com/curlsops/ffo-bot/commit/23096936b4c1725712464415b0cf25ec1d740419))
* **mojang:** add batch UUID lookup for whitelist sync ([a972ae7](https://github.com/curlsops/ffo-bot/commit/a972ae79e27350684817679b1a5c544355c1b42c))
* tests, refactors refactor refactor refactor ([c58179a](https://github.com/curlsops/ffo-bot/commit/c58179a730d9bc0d647a9efb3821d105d284dd8a))


### Bug Fixes

* **ci:** pass FFO_BOT_VERSION to edge Docker build ([cbd4ea6](https://github.com/curlsops/ffo-bot/commit/cbd4ea6d47c8c0acdbb29e42463d9dedf13a25a0))
* **convert:** show original message with unit replaced ([59679e8](https://github.com/curlsops/ffo-bot/commit/59679e80166cfb65b867e2e16f05f97d79361ed8))
* **db:** treat ConnectionRefusedError as transient ([1420d63](https://github.com/curlsops/ffo-bot/commit/1420d63242c615bd807e8be511f018a85da84ce5))
* **giveaway:** use prize name only for thread title, no 'Prize:' prefix ([a582424](https://github.com/curlsops/ffo-bot/commit/a582424b4182ef3938086c111f706db41f111319))
* **minecraft:** replace mcrcon with socket-based RCON implementation ([8c56bd6](https://github.com/curlsops/ffo-bot/commit/8c56bd607ca7ff3e0b0d14f03eb5b1b6a970c3ec))
* **test:** capture logs under pytest-xdist ([66ee12f](https://github.com/curlsops/ffo-bot/commit/66ee12f666d84ed11325431562e45aa91b8a615d))
* **test:** capture whitelist_channel logs under pytest-xdist ([057f088](https://github.com/curlsops/ffo-bot/commit/057f0889bb4ac907d3026dcf67e5a4a9cd00c39a))
* **tests:** correct MrCurlsTV username in integration tests ([d7aff2f](https://github.com/curlsops/ffo-bot/commit/d7aff2f54499673f31c74acf16c294db068b5a78))
* **tests:** expect invitable=False in create_thread assertions ([50f53c1](https://github.com/curlsops/ffo-bot/commit/50f53c18b1cbaabb349b5d237e87a96190802734))
* use timeout param for asyncpg create_pool (connect_kwargs not supported) ([35e04bf](https://github.com/curlsops/ffo-bot/commit/35e04bf5db9e154ad106a629255b2f9f6062ab24))


### Performance Improvements

* **bot:** defer imports until features are enabled ([4f61719](https://github.com/curlsops/ffo-bot/commit/4f61719c41433915d47201528f5e66941f6aaca3))

## [1.5.5](https://github.com/curlsops/ffo-bot/compare/v1.5.4...v1.5.5) (2026-03-01)


### Bug Fixes

* docker image race condition ([0cd4fae](https://github.com/curlsops/ffo-bot/commit/0cd4fae9239379ca6d5ef5debd33e7ea865c5d7e))
* duplicate commands, clear global ([7e5da61](https://github.com/curlsops/ffo-bot/commit/7e5da6100ef91b2c612d5cec039f68a2105df485))

## [1.5.4](https://github.com/curlsops/ffo-bot/compare/v1.5.3...v1.5.4) (2026-03-01)


### Bug Fixes

* remove button param from giveaway callbacks (manual assignment receives only interaction) ([7de8649](https://github.com/curlsops/ffo-bot/commit/7de8649b2f91fc25d49757fee7ce558b22591ffa))

## [1.5.3](https://github.com/curlsops/ffo-bot/compare/v1.5.2...v1.5.3) (2026-03-01)


### Bug Fixes

* giveaway embed footer, button callbacks, and participant list ([ce8eeec](https://github.com/curlsops/ffo-bot/commit/ce8eeec39e24dded821508e4cab834845d787763))

## [1.5.2](https://github.com/curlsops/ffo-bot/compare/v1.5.1...v1.5.2) (2026-03-01)


### Bug Fixes

* **notifier,giveaway:** already-set check, DB error handling, guild-only commands ([#85](https://github.com/curlsops/ffo-bot/issues/85)) ([7d156b0](https://github.com/curlsops/ffo-bot/commit/7d156b00741415631d885928622566c4561c08e3))
* remove loop.stop() to prevent event loop stopped before future c… ([e846739](https://github.com/curlsops/ffo-bot/commit/e846739a4675db8c2bddc0a7f53c330dc305aa3a))
* remove loop.stop() to prevent event loop stopped before future completed ([578b902](https://github.com/curlsops/ffo-bot/commit/578b9020ffa2896ad9b41312b6449ac9545b6563))
* remove loop.stop() to prevent event loop stopped before future completed ([#83](https://github.com/curlsops/ffo-bot/issues/83)) ([fbaa527](https://github.com/curlsops/ffo-bot/commit/fbaa527fad519fe033d2f9323bc262dfa3174d7c))

## [1.5.1](https://github.com/curlsops/ffo-bot/compare/v1.5.0...v1.5.1) (2026-03-01)


### Bug Fixes

* pass version to Docker build so /version shows correct release ([4db25c8](https://github.com/curlsops/ffo-bot/commit/4db25c86514c95e7acade73d0d9857f8d29cd4a7))
* pass version to Docker build so /version shows correct release ([14d6e4c](https://github.com/curlsops/ffo-bot/commit/14d6e4c63a3e086bfbcaab6ff460f9b7380f2ac3))
* remove entry count from giveaway participants and add button param to callbacks ([32daf0b](https://github.com/curlsops/ffo-bot/commit/32daf0b6ba5a7243ae8e49d535818bf65046e50f))
* sync slash commands only to guilds to avoid duplicates ([61d0d66](https://github.com/curlsops/ffo-bot/commit/61d0d66838ec864e8e5f2a7b9760b586dc75877f))

## [1.5.0](https://github.com/curlsops/ffo-bot/compare/v1.4.0...v1.5.0) (2026-03-01)


### Features

* **admin:** add /version command ([d978ca3](https://github.com/curlsops/ffo-bot/commit/d978ca3e017cf1a113a52af418ddd90b38d64e59))


### Bug Fixes

* **ci:** release build - provenance off, amd64 only ([9d47dce](https://github.com/curlsops/ffo-bot/commit/9d47dce2ddef3add409ddfd872e93996e8fb41f5))
* **commands:** guild-only sync, merge on_ready loop ([4079913](https://github.com/curlsops/ffo-bot/commit/407991338aa579da4a03a5caecddd49c87bae716))
* **giveaway:** add button param to leave_button for [@discord](https://github.com/discord).ui.button callback ([7320e59](https://github.com/curlsops/ffo-bot/commit/7320e5967127d27bf1cd416116a9f8e921351f88))
* **giveaway:** fix Join button callback, notifier config, and footer formatting ([5a219db](https://github.com/curlsops/ffo-bot/commit/5a219db82c82851f1f5e42ec5e952f22b5f001af))
* **giveaway:** fix Join button callback, notifier config, and footer formatting ([2390ec7](https://github.com/curlsops/ffo-bot/commit/2390ec74993d394f72f57a1b8484d17aba63dc80))

## [1.4.0](https://github.com/curlsops/ffo-bot/compare/v1.3.7...v1.4.0) (2026-03-01)


### Features

* **commands:** add polls and reaction role commands ([7d12be8](https://github.com/curlsops/ffo-bot/commit/7d12be80ac7e56a27c1d8aff205dd5d0eda55703))
* **voice:** add voice message transcription ([8359246](https://github.com/curlsops/ffo-bot/commit/835924656d5fb41606a4594496ec19e00a873fe3))


### Bug Fixes

* **giveaway:** restore entry count in persistent views and improve commands ([b9e9b14](https://github.com/curlsops/ffo-bot/commit/b9e9b1402e28895590988499bd5a679c387031b9))
* **logging:** resolve pythonjsonlogger deprecation warning ([d37c203](https://github.com/curlsops/ffo-bot/commit/d37c2039f1180108fe4d63a86bf2524777b3face))
* **media:** handle content_type None in media downloader ([bc332a5](https://github.com/curlsops/ffo-bot/commit/bc332a581a7aca4c10938c2f6e34cdcfa3cf677f))
* **notify:** ensure notify channel sends messages ([687ec88](https://github.com/curlsops/ffo-bot/commit/687ec88defbbe6f3040995e99babb555b0d4f043))
* sync slash commands to guilds to remove duplicate command entries ([41ec7fe](https://github.com/curlsops/ffo-bot/commit/41ec7fe830b65a3cbeee011114e09930924968ba))
* sync slash commands to guilds to remove duplicate command entries ([30c756d](https://github.com/curlsops/ffo-bot/commit/30c756dcf607c4443285aa1baab2c7639ec6614c))
* update README links and test count ([ef3d186](https://github.com/curlsops/ffo-bot/commit/ef3d186776670161d014a73db4fce9c8e2c02be2))

## [1.3.7](https://github.com/curlsops/ffo-bot/compare/v1.3.6...v1.3.7) (2026-03-01)


### Bug Fixes

* deslop tests and add edge case coverage ([58be57f](https://github.com/curlsops/ffo-bot/commit/58be57f3ad6ca2f92c5e4f44efedadcd1514b8ff))
* deslop tests and add edge case coverage ([6a48207](https://github.com/curlsops/ffo-bot/commit/6a48207fe445debabe2df60fc19623bd13ef25cf))

## [1.3.6](https://github.com/curlsops/ffo-bot/compare/v1.3.5...v1.3.6) (2026-03-01)


### Bug Fixes

* convert asyncpg Record to dict before mutating in giveaway manager ([8c4ecfb](https://github.com/curlsops/ffo-bot/commit/8c4ecfb370f0a09ed8585e15e9ad521a2058fb80))
* convert asyncpg Record to dict before mutating in giveaway manager ([054d14b](https://github.com/curlsops/ffo-bot/commit/054d14b4e800ecab65868d8c33729a2cffa3fa1b))
* deslop giveaway manager tests ([083c0fe](https://github.com/curlsops/ffo-bot/commit/083c0fe9df234827e745b358a29d7c38c66c5748))

## [1.3.5](https://github.com/curlsops/ffo-bot/compare/v1.3.4...v1.3.5) (2026-03-01)


### Bug Fixes

* remove double json.dumps for JSONB columns ([cf27e82](https://github.com/curlsops/ffo-bot/commit/cf27e82cf6f95cde3b4fb64c1cf784659fe4de62))
* remove double json.dumps for JSONB columns ([a0fd647](https://github.com/curlsops/ffo-bot/commit/a0fd647c38758eac743e86827822d7a882851f17))

## [1.3.4](https://github.com/curlsops/ffo-bot/compare/v1.3.3...v1.3.4) (2026-03-01)


### Bug Fixes

* trigger release 1.3.4 ([4b33244](https://github.com/curlsops/ffo-bot/commit/4b332449315dd2b6d0d69ca761579dff303f28d7))
* trigger release for CI changes ([4a6c1fd](https://github.com/curlsops/ffo-bot/commit/4a6c1fd35fec93580e914ea30d40375b24f766df))

## [1.3.3](https://github.com/curlsops/ffo-bot/compare/v1.3.2...v1.3.3) (2026-03-01)


### Bug Fixes

* pass JSON strings for JSONB params (asyncpg) ([#56](https://github.com/curlsops/ffo-bot/issues/56)) ([cab31a2](https://github.com/curlsops/ffo-bot/commit/cab31a21777c9d5ecd19d6cc3a0af590da489dea))

## [1.3.2](https://github.com/curlsops/ffo-bot/compare/v1.3.1...v1.3.2) (2026-03-01)


### Bug Fixes

* **client:** sync commands globally only ([#54](https://github.com/curlsops/ffo-bot/issues/54)) ([2e19cf0](https://github.com/curlsops/ffo-bot/commit/2e19cf0926e5a37e566d053e5605ece75a2c18ea))

## [1.3.1](https://github.com/curlsops/ffo-bot/compare/v1.3.0...v1.3.1) (2026-03-01)


### Bug Fixes

* **client:** sync commands globally only ([#52](https://github.com/curlsops/ffo-bot/issues/52)) ([0e38c64](https://github.com/curlsops/ffo-bot/commit/0e38c64415fb07ddca748cc08e8b17f345049503))

## [1.3.0](https://github.com/curlsops/ffo-bot/compare/v1.2.0...v1.3.0) (2026-03-01)


### Features

* **auth:** treat Discord server admins as super admin by default ([#50](https://github.com/curlsops/ffo-bot/issues/50)) ([3c65d7d](https://github.com/curlsops/ffo-bot/commit/3c65d7d5b29a2bf0e06e587939efb2e2a1160d7f))


### Bug Fixes

* **docker:** set execute permission on entrypoint.sh ([#48](https://github.com/curlsops/ffo-bot/issues/48)) ([82cf620](https://github.com/curlsops/ffo-bot/commit/82cf62002e6bcbbd49210fea501ab72fcd76908d))

## [1.2.0](https://github.com/curlsops/ffo-bot/compare/v1.1.0...v1.2.0) (2026-03-01)


### Features

* run database migrations on container startup ([#45](https://github.com/curlsops/ffo-bot/issues/45)) ([3b3d6b0](https://github.com/curlsops/ffo-bot/commit/3b3d6b0b123850902a1b4610c40f7a2699e4f8b1))

## [1.1.0](https://github.com/curlsops/ffo-bot/compare/v1.0.0...v1.1.0) (2026-03-01)


### Features

* add admin notification system for giveaway events ([#40](https://github.com/curlsops/ffo-bot/issues/40)) ([8161bba](https://github.com/curlsops/ffo-bot/commit/8161bbad0d1c857b956e0fa2ec132b1e105809f7))
* add error notifications to admin notification system ([#42](https://github.com/curlsops/ffo-bot/issues/42)) ([ff57431](https://github.com/curlsops/ffo-bot/commit/ff57431c66b72e0dc3204e3fcf6bb0ef621e3fc1))
* implement giveaway system ([#37](https://github.com/curlsops/ffo-bot/issues/37)) ([1110eaa](https://github.com/curlsops/ffo-bot/commit/1110eaa43ad15fe12058ac4750e7ad3e5c51e0e8))

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
