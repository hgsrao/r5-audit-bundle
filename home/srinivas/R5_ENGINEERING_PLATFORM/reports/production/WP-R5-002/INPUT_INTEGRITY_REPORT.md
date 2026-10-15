# WP-R5-002 — Input Integrity Report

Campaign R5-PRODUCTION-001 · scope TRAIN_REPLAY_DIAGNOSTIC · 2026-10-07. Hashing and `stat` only; no replay, test, backtest or Block-1/holdout run; no market-data row was parsed (only the header line of one file, `timestamp,open,high,low,close,volume`, was displayed). Companion files: `INPUT_QUALIFICATION_REPORT.md`, `REPLAY_INPUT_MATRIX.csv`.

## 1. Baseline-001 hash chain — recomputed now

`sha256sum -c SHA256SUMS.txt` run in `reports/production/WP-R5-001C/` at the time of this package:

| File | Size (bytes) | SHA-256 | Result |
|---|---|---|---|
| `raw/kite_connect_instruments_NSE.csv` (Baseline-001) | 686,374 | `536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f` | OK |
| `raw/kite_connect_instruments_NSE.csv.headers.json` | 769 | `e0b597b36f9c6694a3b7758ebc3598fcbeca846a46dca9e8e471ed1825e10e4e` | OK |
| `raw/ACQUISITION_RECORD.json` | 817 | `03ea8f75ad2ba55185802e8f8da702b7273123ac46429118a151190257a27338` | OK |
| `raw/SHA256SUMS.txt` | 301 | `e2ee5c5afe6467f9c7e1d6cd65821e03cd16746f0403bcb049cf2800b71c2f54` | OK |
| `AUTHORITATIVE_METADATA_INDEX.csv` | 17,025 | `f66200c92ba019bdc8135e3c1a4354d2078115de0866890fb02b5cd7208afc12` | OK |
| `METADATA_QUALIFICATION_REPORT.md` | — | `2b7ca64092ab0c84ec4cbb05cba65eeb16fab4964d4945f60d79cfb8176a572f` | OK |
| `MISMATCHES.csv` | — | `d4e6b46fd31aab88b840d0182744ef10b7c0e1764cfa9a5ce5091f00ebd8d10e` | OK |
| `PROVENANCE_RECEIPT.md` | — | `dcbd65e2ace0fb48cee994be0d6557c76acac659c9eb9c23d1b06b6b26b9364a` | OK |
| `analysis_results.json` | — | `d3a74c6c99625b6fdce0c8df179138b7eee50ce1a72b924598c0b4efaa516b79` | OK |
| `build_wp_r5_001c.py` | — | `78022c9aa8b9c65e9697cfbddf8939484476ac7ab7d65bc4698c0a2c7bedd502` | OK |

All 10 entries OK; 0 mismatches. `ACQUISITION_RECORD.json` records `sha256 = 536809…6401f`, `size_bytes = 686374`, `instrument_rows = 10324`, endpoint `https://api.kite.trade/instruments/NSE`, finished 2026-10-07T06:31:56.758356+00:00, `access_token_stored=false`, `api_secret_stored=false`, `session_invalidated=true` — the recomputed file hash and size equal them. Chain: ACQUISITION_RECORD → raw file → raw/SHA256SUMS → 001C SHA256SUMS → index/report. The baseline directory was not written to.

Baseline-001 content re-opened (metadata, not market data): filtering `exchange=NSE, segment=NSE, instrument_type=EQ, tradingsymbol ∈ 48 file-name symbols` gives 48 rows, 48 distinct symbols; tick 0.01 ×4, 0.05 ×16, 0.1 ×23, 0.5 ×2, 1 ×3; lot 1 ×48 — identical to the WP-R5-001C figures.

NSE Security Master `reports/production/WP-R5-001B/raw/NSE_CM_security_06102026.csv.gz`: 1,259,539 bytes, SHA-256 `0a9022e4e93f3be91df3196d0127d2d79031795f21e180f4b3b89fb39e99c803` — equals the 001B/001C recorded value.

## 2. Frozen 48-symbol 1-minute dataset vs manifests

Directory `/home/srinivas/projects/zerodha-phase1/data/frozen_48_1min_20230703_20260824` (48 `NSE_<SYMBOL>_minute_2023-07-03_2026-08-24.csv` files; the symbol set equals the manifest's `symbols` list). Hashes computed with `sha256sum` over the whole files (hash only; rows not read). Three-way comparison: physical file vs `acquisition_manifest.json` vs repo `revision2/DATASET_MANIFEST_48SYMBOL_1MIN.json`.

* Physical SHA-256 vs `acquisition_manifest.json`: **48/48 match**; sizes vs manifest `bytes`: **48/48 match**.
* Physical SHA-256 vs repo `DATASET_MANIFEST_48SYMBOL_1MIN.json`: **48/48 match**.
* `acquisition_manifest.json` sha256 `f0621e6ddc3ced5ec6748dc26b11169b6600dc75ef380aec4aa82be995d0e2ba` equals `acquisition_manifest.json.sha256`.
* Repo manifest `manifest_hash` `f724074ca45eb9380ba6e7cf18ae1da4d9c9d48be0cf78ca51b0faa8d8d8ff16`: RECOMPUTED now (sha256 of the sorted-key JSON of the 48 records, same construction as `revision2/dataset_manifest.py:96-97`) = the stored value = protocol `stock_dataset.manifest_hash` = PREREGISTRATION.json value.
* `full48_input_receipt.json` states `physical_fullfile_sha_verification: false` and "raw full SHA not newly certified": this package performs that physical verification (hash only) — **no mismatch**.
* **Mismatches: none.**
* Period: every file name/manifest spans 2023-07-03 → 2026-08-24, i.e. TRAIN (2023-09-01 ..< 2025-07-01) **and** VALIDATION (2025-07-01 ..< 2026-01-01) **and** selection-excluded (from 2026-01-01). Recorded by file name and hash only; the replay must restrict to TRAIN. No row was opened.

| # | Symbol | Size (bytes) | SHA-256 (recomputed) | = acquisition_manifest | = repo DATASET_MANIFEST |
|---|---|---|---|---|---|
| 1 | ADANIENT | 17113012 | `a40f917b8c823bbc545562a7ff700a46e8b2c78645318a5629b51b15e9fc2800` | match | match |
| 2 | ADANIPORTS | 17269669 | `899ea920ee73c6c44a9704a3676720ca71433419360e6ac9e8b16236a8c6156d` | match | match |
| 3 | APOLLOHOSP | 16645385 | `4b8bf264803efcffd3437e63633363c50b5881b7c52ea9660b4eff40ff6bde5b` | match | match |
| 4 | ASIANPAINT | 17171223 | `a64e56630608c86ed8b41b76aa82ccceeeef66a8d8b7649f0e1822777ec8d9c3` | match | match |
| 5 | AXISBANK | 17524700 | `19ffff7becdb42a8749dfd4c5cb674f5b2a2b6ee99f33dc3208b33600515cf71` | match | match |
| 6 | BAJAJ-AUTO | 16119339 | `abf32d6eb21c77cdaf2622670f3798b57715be5def553a9bd9a7ba55cca527ef` | match | match |
| 7 | BAJAJFINSV | 17265559 | `3f3f66908a86e08fcb8b2765864a69f78e0f49b9a34d04a97d7c869ea3057e4d` | match | match |
| 8 | BAJFINANCE | 15629211 | `d4a80eb0be6f77fba0845b3f22a92ba89f3ef62e4d76d7e256d86b9efa4c7e37` | match | match |
| 9 | BEL | 16952305 | `03ee7546b0097189e952621cd90d81b0864fbe5b4ed606fef1663dd17e83f173` | match | match |
| 10 | BHARTIARTL | 17406130 | `9a32ca39301437fe4a323c52f44a48bcc63d03b3296f0e8124328d502a4b75a1` | match | match |
| 11 | CIPLA | 17354730 | `b5c64f9e05e86acda060e71a81bd62572a911a4e29ec0a9b43592a955339218a` | match | match |
| 12 | COALINDIA | 16901451 | `593ecf68adce0443f8e3f7a7ef780f8478f8f0f660fa85a4a163b29ff2783662` | match | match |
| 13 | DRREDDY | 17319348 | `50b5242201250a6d4953f438e21cd12c8510ba095c63268c1893524dbfa94f29` | match | match |
| 14 | EICHERMOT | 16707146 | `48a1b5207f8e51498d3079721a15a5b5879049099ad8246f644724874b945834` | match | match |
| 15 | ETERNAL | 17105633 | `146d2b9c289984dc28423b1454eba14112c087b84eb67ff0ce75acd726a8051c` | match | match |
| 16 | GRASIM | 17203458 | `dfbcd26a7b623db43bfc8359752c9a76ca9840cff701735fac17406f42cd6b8e` | match | match |
| 17 | HCLTECH | 17460118 | `86672666f7a9add62c138f80ba4e9397e23daf92ed927cf979d8959dad00cf9f` | match | match |
| 18 | HDFCBANK | 16512635 | `c4edb5f299695136e1f90fd01df14fb7f24ec5e0cc45d83bc271e8e34bfcf8d9` | match | match |
| 19 | HDFCLIFE | 16655733 | `9596004e87084c3a727bac28352c55cffc4572deb35bfcc66d89c70cb585a9cc` | match | match |
| 20 | HINDALCO | 16787498 | `e2d61b10dc77c5e2fd7fdc3a4b7487cfdf1583dc811b4da14f9c9934fe6cbac3` | match | match |
| 21 | HINDUNILVR | 17270930 | `4e7ef313b2bf2475ce1c38488f21286128c23cfafc30516f00af1754c99869c7` | match | match |
| 22 | ICICIBANK | 17553547 | `a892ff9c3c2279f9b8d5643f04e70aa80db912350df13ac56b04a438512e8fe0` | match | match |
| 23 | INDIGO | 16908085 | `c3cb6348d247fe6efb0b0661097d82c1be86336a78470ddb59c4aa87e8ff83c0` | match | match |
| 24 | INFY | 17396180 | `4c6a3c9ca2dcc60c40aa221833424f706fa6b44a9d86258040bf2e00eb4e15b1` | match | match |
| 25 | ITC | 17017076 | `3d3ddcda7b6369a17c00b3b500f50714629b0f81284e0ce7d4a598f5edd44477` | match | match |
| 26 | JIOFIN | 16241789 | `882c6f52f922da4ce328c5ac52bb3282b79902baa68a2039649a643e2fd2f680` | match | match |
| 27 | JSWSTEEL | 16822838 | `c18d15960704305fb0d5023319dde0cb6ed59229d5a541538dc66711497aa765` | match | match |
| 28 | KOTAKBANK | 16389802 | `532f6d2503fa3033ca3bb96248405c3ce6f926d48d741994a1aea64703ad6f66` | match | match |
| 29 | LT | 17229979 | `c3f0dcad3c0069d88afdf9c2de75bf1e4ec3e5dc019a5495abe9476d4529db38` | match | match |
| 30 | MARUTI | 17276054 | `d19cb85736026a644bb496c2ce2ae9792f8561b5334f8deea168a3018c3cc07d` | match | match |
| 31 | MAXHEALTH | 16884527 | `f2717e479737e48ea3b4f1d3251c262ce6e2c3f084c500653c0b2cd342332156` | match | match |
| 32 | M&M | 17333517 | `3846ac14098924dd5bb09084163aba2ffce27058073c57fdf2a6b555e4157931` | match | match |
| 33 | NTPC | 16893364 | `7a884fa2aecb552716edef13e1360db917d809efc7f0c37b5db122a1b79198e3` | match | match |
| 34 | ONGC | 17032836 | `9d11435db7b696a1632e6ac0b57f9f9d9c38f28b9956b86517ae0afa9b7762a5` | match | match |
| 35 | POWERGRID | 16926940 | `a3e2022fad22fd9e6ee805604937a03d74be0f62b1234f4a40ea17620f9693fa` | match | match |
| 36 | RELIANCE | 17558675 | `6c1bcb1e4d53ac0716f6b07b5053dff8c974de2297982f13e9aa65715acf9276` | match | match |
| 37 | SBILIFE | 17316790 | `3dc390b2a2a151ea54782ee5e9aad45db281b77618c36a93cfbe51a2ff984de8` | match | match |
| 38 | SBIN | 16944918 | `4dfe72accbfa1d9295b378b1a1cd88aabb043557ef9bee7060e2245b74dd7e85` | match | match |
| 39 | SHRIRAMFIN | 16783130 | `b30bf48d42a5306a4ad983a9df69ef1704280c4d52db852b279fdde522a964a6` | match | match |
| 40 | SUNPHARMA | 17423815 | `110250a031422ade68408cb261ed04263a8e33fdd2ccf640e4ffd1c652997bc6` | match | match |
| 41 | TATACONSUM | 17151102 | `c8ec13b701b4967e1a023db613830cf7a5704563381809f98feecac55ae35410` | match | match |
| 42 | TATASTEEL | 17627416 | `2cf2d043f9031d8ed8270921e753211c5758158d097d05309c05bc38b708f286` | match | match |
| 43 | TCS | 17301943 | `8c247c182d2da35ba77430c28352be1319d6d26b6e2ed695573dbed919f8b917` | match | match |
| 44 | TECHM | 17221461 | `5f7672fb0786c8207ad5826763f41f568c5e1f6ac80e3df642a25df6d7dc1b5c` | match | match |
| 45 | TITAN | 17139548 | `f9b34afbceee6fc7269255fc4d2363a057d1ec5b8921e75b729b440b14533a1e` | match | match |
| 46 | TRENT | 16975225 | `881c7ceda9e8634748b2af9a6c3078a8353303210ba508e5f1ac2473be5a6be2` | match | match |
| 47 | ULTRACEMCO | 15717622 | `971825d9a27cdd0d12287f379b189980379a30047d114a4ef1c7b0e5ae73cce1` | match | match |
| 48 | WIPRO | 17075664 | `16f95629e96c17e8e785fb6b6e49c14004c09b437692dfe772dab504b394a000` | match | match |

## 3. Grid / context feeds, protocol, preregistration, parameters

| Artefact | Size (bytes) | SHA-256 | Compared against | Result |
|---|---|---|---|---|
| `frozen_grid_15min/NSE_NIFTY 50_15minute_2023-08-14_2026-08-13.csv` | 1,158,440 | `c2e78705f61b5bad66257890ed1ec0cd3703571e721c16e1b2d2128ee4ea5443` | protocol `grid_dataset.feeds.NIFTY_50_15MIN`, PREREGISTRATION, `grid-manifest-local.json` | match |
| `frozen_grid_15min/INDIA_VIX_15MIN_20160101_20260825.csv` | 3,385,943 | `9992deda85005fdb9ee2d6684f8a84a3cabd3f591655450207aeeaacbe7c1a8d` | protocol `…INDIA_VIX_15MIN`, PREREGISTRATION, `grid-manifest-local.json` | match |
| `zerodha-phase1/local_workspace/records/grid-manifest-local.json` | 1,004 | `8f61b03318707283352788a817aa344d1944735ef73f423361d98384965d88b4` | its `manifest_hash` a5ebf422…c0b2 (method not recomputed) | exists only under zerodha-phase1; **absent from the R5 repo checkout** |
| `revision5/step5_sealed_calibration_protocol_v2.json` | 13,689 | `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7` | PREREGISTRATION `source_protocol_sha256` | match |
| `campaign/PREREGISTRATION.json` | 4,326 | `2b16ce44e7ef113a33049f800777d0ece4fa2f513889fa369ff0ed9e3c28cf55` | `PREREGISTRATION_SHA256.txt` | match |
| `outputs/r5_step5_stage_a_v2_state/params/trial_000.json` | 168 | `7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d` | `full48_input_receipt.json` `params_sha256` | match |
| `UPDATED_PARAMETER_REGISTER.json` (WP-R5-001) | 646,154 | `0f07dc00b27bca1be33dc8b22743aa2b0065222e5056c021b21557704cb9c9fb` | no prior hash recorded in the package | hash recorded |
| `PRODUCTION_PARAMETER_CLOSURE_MATRIX.md` (WP-R5-001) | — | `684d9c18007cf9c99d85143a74d8cdb94d6ae80f0727b12b977d3725964aecfc` | no prior hash recorded | hash recorded |
| `acquisition_summary.json` | 55,250 | `0d074b7eee211532a01135453759531608a9daf0baa5cbfabb14a374659dac87` | no reference hash exists | hash recorded; not consumed by replay code |

Campaign receipts (NODE-001 checkout `…/campaign/wp01/`, read-only, ACCESSIBLE): `RECEIPT.md` `81113f2d03c794ef443bab0bed9e4bfc6fd9098dbf73ba8961255fd3e4518435`; `full48_input_receipt.json` `b550039861cbd2a519f0a2937e0cf7fb1f590906aa0a651319172d0c42be438f`; `historical_legacy_ledger_receipt.json` `d741abf9610003e0258ca1b071a37ed32f9be50bb8654b50674710e5486c44fe`; `checkpoint_receipt.json` `9066c5393e9d6c5b16bb65615da82a717b7329a9d854258d57f7f3ee52610dd4`. The historical legacy ledger (`outputs/r5_remediation/closure/c05/baseline/ledger.csv`, receipt sha `311b3a14…5b08d`, 52 trades) was **not re-hashed here** (not a replay input; it is a historical comparison artefact) and the corrected full ledger identity remains unavailable (WP01 acceptance stays BLOCKED).

## 4. Analysed code — working-tree SHA-256 pin

These are the working-tree files read for the CNC/GTT analysis. The R5 working tree is **dirty** (WP-R5-001 report); `git status/diff/show` need approval and were not run, so equality with commit 59371ff is **UNKNOWN**. The pin below identifies exactly what was analysed.

| File | Size | SHA-256 |
|---|---|---|
| `revision2_external/instrument_metadata.py` | 2,433 | `433cb058f10dfe594b7a60e79ae8cb2ae7ca644764f7d87a2aac5b3dd611d4bf` |
| `revision2_external/paper_execution.py` | 14,827 | `c2f53f9091f2628f3f66cb5e4d3165d001d1c34f91fa17880e44fc90fe7a246a` |
| `revision2_external/protection_policy.py` | 4,207 | `06b8e153ba4b1a47332089a08fb9a967e6c625d27b42a435b5d058c926a31194` |
| `revision2_external/orchestrator.py` | 193,907 | `6885bc41fd70a00cfb1794ebdd60e19e63c6dfd6a69edc44153e1719f6be3b5a` |
| `revision2_external/grid_context.py` | 11,573 | `903ea27aeb669f99008d64b17c3df3b65f8ef7ae0d3fd67c72210bf21e330931` |
| `revision2_external/regime_id_box.py` | 32,594 | `740a5ba898dedabb88e48547602091bb5aa34c0b05a846a9e7137c43f41fa5d3` |
| `revision2_external/regime_hmm.py` | — | `05e6a3f865cd2f9175645ab3ef25fdc4f35b7736fdc6c5313aafe16f61e8a1f3` |
| `revision2/transaction_costs.py` | 6,873 | `7a570e10d4dff454f77106a2525c9a2a7605dd441a5950a9504692e4a1d4f9b9` |
| `revision5/combined_cycle_runtime.py` | 29,715 | `af0e82cac7b71f6f4b94c99c9142db0d92c0592ecca52b67f77e690deefc86b4` |
| `revision5/handoff_manager.py` | — | `4cf6353bbada29a6292cd42556ae7ead6412e363796bb6edee4aa6979a66beda` |
| `revision5/morning_recovery.py` | 39,370 | `3c0560d722d01ce62319898c948043d31f3ec33f5f0b32a50c906df06397490c` |
| `runtime/operating_mode.py` | — | `1471d64698637ab643a5db7435bfc17625988e3fbfb8c4b03160969d1f0dbce9` |
| `canonical_parameter_registry.py` | 63,723 | `dc7cf0ead0df4459ea28616a0d1745f5b80fd88eac6019587c840dbe9f338025` |
| `market_data_loader.py` | — | `8e0433f9c3adcdd8699d7daa702452281190db2aa27d6145219630cd30bcc195` |
| `scripts/run_r5_step5_candidate.py` | 29,303 | `13c0fa46cf6ce38d4c4bab3b59d6eb407acc93135e0a39e93d3ff446a69f1a70` |
| `scripts/diagnostics/r5_block1_acceptance.py` | 12,442 | `76cb323d287443ba3802a0ae9267eddc338644b442208c7c8fc1623d97386b6f` |
| `scripts/diagnostics/block1_arm_worker.py` | — | `34b8f94b9026604fe51fa5159f5bfc9ebaff26b687f10711d592b0af8c8da5e3` |
| `scripts/run_r5_paper_replay.py` | — | `37c258d7e5dfad480ebca297f4c2f035aac7af861a047136804318df0cd3c412` |

HEAD pin: the worktree's HEAD file (`/home/srinivas/projects/zerodha-phase1/.git/worktrees/zerodha-r5-governor-refactor/HEAD`) reads `ref: refs/heads/feature/ir02a-parameter-closure`, and `refs/heads/feature/ir02a-parameter-closure` = `59371ff06d17b49d917a81aed294c2e254c97574` — matches the package. The protocol names engine parent `c0b4672fa45498d628f1646d60c75fd206803755`; whether HEAD is within the allowed drift of that parent was not checked (git needs approval).

## 5. Package / queue record (blocker removal)

| File | SHA-256 |
|---|---|
| `work/packages/WP-R5-002.json` (post-removal) | `48e7e39ee41536a00bc35c98801693f517e92ad00c20f4987cbe0ed8cbfbc04d` |
| `work/packages/WP-R5-002.before_blocker_removal.json` | `86ae7c2ca8a53ea313ffb61468bd93c1f1b38c647f3bbded6605dfe223a41212` |
| `queue/RUNNING/WP-R5-002.json` | `85685ad84af2709872c7230b130d9e766fc178b140561fec3a42ea29761db853` |

Verified: before-copy `depends_on = ["TRAIN-PERIOD-METADATA-EVIDENCE"]`; post-removal copy and the RUNNING queue copy `depends_on = []` (the id appears in the live files only in `metadata.removed_blocker`, never as a dependency). `queue/DONE/WP-R5-001C-QUAL.json` is present (decision AUTHORITATIVE_METADATA_QUALIFIED, scope TRAIN_REPLAY_DIAGNOSTIC, in CURRENT_STATE/CHECKPOINT_004). No queue or package file was edited by this package.

## 6. Verdict on integrity

Hash chain of Baseline-001 intact (10/10); frozen 48-file dataset 48/48 identical to both manifests and to the protocol seal; grid feeds identical to the protocol seal; no hash or size mismatch anywhere. Open integrity items: repo working-tree vs HEAD equality UNKNOWN; grid manifest missing from the R5 checkout (present under zerodha-phase1); registry frozen-identity and Python environment not verifiable without execution.
