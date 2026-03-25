# Task

## Current Official Task

1. original planning baseline: merged 12 × extended actual run

## Goal

- original planning baseline の次段として、merged periods 12 × extended 18225 = 218700 rows を実施する
- minimal tradability の 6 軸を維持したまま、`price_spike_limit` と `volume_multiplier` の 2 軸を low / mid / high で追加する
- dry run と actual run の結果を README / task に記録し、次の original 系 run へ進む判断材料を整える

## In Scope

- merged periods 12 は前回定義をそのまま使う
- extended 用の template / grid / config を original 系命名で追加する
- dry run で `total_periods=12`、`total_cases=18225`、`planned_rows=218700` を確認し、問題なければ actual run を 1 回だけ行う
- CSV / DB / run メタ / artifact / reuse / fetch / failure 分類を確認し、README / task に反映する

## Out of Scope

- raw candidate periods 24 を使う actual run
- original planning baseline / ceiling baseline の larger run
- 並列化の本格導入
- acquisition key 同時実行制御の完成
- schema version 運用ルールの完成
- DB 主体運用への最終切替
- OHLCV artifact の再設計
- 戦略改善
- パラメータ最適化

## Execution Constraints

- comparison / simulate の責務は増やさない
- market data reuse の既存方針を崩さない
- period ごとに market data を 1 回だけ解決し、returns を 1 回だけ生成する
- case 準備も含めて全件一括メモリ展開しない
- case_name の一意性を入力展開側で保証する
- 結果は CSV / DB に逐次保存し、途中成果を失わない
- 外部通信 actual run として、通信先 / 取得方式 / 保存範囲 / failure 分類 / 承認経路の観測可能範囲 / run_id を残す
- dry_run 用 config と actual run 用 config は分ける
- output_csv_path / results_db_path は current-stack の official scale と共有しない
- dry run が `planned_rows=218700` にならない場合は actual run しない
- 既存の run 記録は run_id 単位で保持し、superseded completed run と partial run を混同しない

## Current Plan

- merged periods 12 は前回定義をそのまま使う
- extended 18225 cases / period の template / grid / config を original 系命名で作る
- dry run で `12 periods × 18225 cases = 218700 rows` を確認し、成立した場合のみ actual run を 1 回行う
- README / task に extended の追加 2 軸、dry run 結果、actual run 結果、reuse / fetch 内訳を追記する

## Open Questions

- original planning baseline の次段を raw periods × signal-only にするか、raw periods × minimal にするかを判断する
- original planning baseline でも merged period の定義を今後固定するか、候補差し替え余地を残すか
- original 系 run の次段で fresh fetch 比率をどの程度重視するか

## Risks

- current batch runner は external-signal planning grid をそのまま runnable config としては扱っていない
- 通信許可の承認経路は Codex から完全には観測できない
- case_name 一意性が崩れると CSV / DB の追跡が曖昧になる
- 中断時と再実行時の扱いが曖昧だと run 単位分析が難しくなる
- original planning baseline の external-signal case は summary 定義との差異があると prepare 時点で失敗する
- original 系の series 名が feature 側の許容集合とずれると、grid が成立していても actual run で失敗する

## Progress / Done

- step1 と step2 は完了済みとして承認された
- period 単位 market data reuse、case chunk 実行、CSV / DB 逐次保存の batch runner 基盤は実装済み
- 大量ケース実行のための入力接続と段階的実行は完了済みとして承認された
- 今回の正式タスクとして、初版実験 input 作成と dry run / 小規模実データ run を実施する
- 初版実験 input として `config/evaluation_batch_initial.*` を追加した
- `case_limit` は global case 上限であり、grid は period ごとに再走査してメモリ安全を優先する前提を README に明記した
- full dry run を `config/evaluation_batch_initial.full.json` で実行し、`total_periods=4`、`total_cases=8`、`planned_rows=32`、`case_chunk_size=4` を確認した
- 小規模実データ run を `config/evaluation_batch_initial.small.json` で実行し、`run_id=20260325T053230Z_37b9bbef`、`total_rows=3`、`succeeded_rows=3`、`failed_rows=0` を確認した
- 小規模 run の CSV と DB は latest run でともに 3 row となり、artifact path 一致、status 全件 completed を確認した
- 実データ run では `var/cache/market_data/ohlcv/binance_spot/btcusdt/73421dc6d7c2facf48c5eecb88262e590cfe79e8b0a1eedeff33e789e7edaecb.csv` が生成され、market data fetch が成功した
- sandbox 内の最初の small run は DNS 名前解決失敗で `MarketDataFetchError` となり、CSV / DB には failed row が保存された
- 同じ small run コマンドを通信許可付きで再実行すると `completed` になり、コード変更なしで market data fetch が成功した
- current initial input の full 規模は `periods=4`、`cases=8`、`planned_rows=32`、`case_chunk_size=4`、`1 period あたり 2 chunk` である
- 定義案として、small は `period_limit=1, case_limit=3, planned_rows=3, chunks=2`、medium は `period_limit=2, case_limit=4, planned_rows=8, chunks=4`、full は `period_limit=null, case_limit=null, planned_rows=32, chunks=8` を置く
- dry run -> small -> medium -> full の順で進め、small と medium の各完了後に停止判断を入れる方針を置く
- 出力先は `var/evaluation_batch/<scale>_*.csv|sqlite3` の scale 別ファイルで分離し、SQLite では `run_id` で run を追跡する方針を置く
- 追加確認として、再実行時に変えた実行条件は `exec_command` の `sandbox_permissions=require_escalated` だけであり、コマンド文字列と config は同一だったことを整理した
- Codex から確認できるのは「通常 sandbox では失敗し、escalated 実行では成功した」という事実までであり、承認 UI の内訳までは不明である
- 通信先は `https://api.binance.com/api/v3/klines` の公開 JSON、HTTP GET、1 period 1 week / 1h では 169 rows だったため成功 run のリクエスト回数は 1 回と推定できる
- 1 回目失敗時の failure row は `error_code=MarketDataFetchError`、`error_message=failed to fetch klines: [Errno -3] Temporary failure in name resolution` で、実装例外やデータ不備は混ざっていない
- raw response body 保存は行わず、保存されたのは normalized OHLCV CSV artifact、shared state DB の取得状態、evaluation CSV、evaluation results DB である
- 直ちに違反確定ではないが、次の external communication actual run 前に運用 fix が必要、という位置づけを明記する
- raw candidate periods は original planning では `24 件前後`、merged periods は `10〜14 件前後` を baseline とし、current-stack では既存 merged 11 件を conservative な代表値として扱う
- current initial full=32 rows は seed / smoke 相当であり、本命 full ではない
- original planning baseline の自然な一例として、`5 × 5 × 3 × 3 × 3 × 3 × 3 × 3` の刻み方から `signal-only ≈ 75 / period`、`minimal ≈ 2025 / period`、`extended ≈ 18225 / period` を説明できる形に整理する
- merged 12 periods を baseline とした original planning baseline は `signal-only ≈ 900`、`minimal ≈ 24300`、`extended ≈ 218700` と整理する
- raw 24 periods を baseline とした original ceiling baseline は `signal-only ≈ 1800`、`minimal ≈ 48600`、`extended ≈ 437400` と整理する
- current-stack 側では、medium は merged periods 全件 × representative 12 cases = 132 rows、operational pilot full は merged periods 全件 × runnable 48 cases = 528 rows、current-stack planning は merged periods 全件 × conservative extended 384 cases = 4224 rows、current-stack ceiling は raw candidate 24 periods 相当に広げると `24 × 384 = 9216 rows` と整理する
- 運用修正として、外部通信 run は事前承認を必須にし、通信先、取得方式、保存範囲、failure 分類、実行条件変更、承認経路の観測可能範囲を task.md に残す方針へ更新する
- scale は `seed/smoke`、`small`、`medium`、`operational pilot full`、`planning full`、`ceiling full` に分けて整理する
- runnable scale は current runner が直接扱える trade-strategy grid で作り、planning / ceiling は original planning numbers として件数整理を分離する
- medium は merged periods 全件 × representative 12 cases = 132 rows を候補とし、72 rows より代表性を上げる
- operational pilot full は merged periods 全件 × runnable 48 cases = 528 rows を current runner 上の conservative operational pilot として置く
- original planning numbers は merged periods × extended = 4224 rows、raw periods × extended = 5376 rows を維持し、直ちに runnable config 化しない
- runnable config として `config/evaluation_batch_operational.medium.json` と `config/evaluation_batch_operational.pilot_full.json` を追加した
- medium dry run は `total_periods=11`、`total_cases=12`、`planned_rows=132`、`case_chunk_size=6`、想定 chunks `22` を確認した
- operational pilot full dry run は `total_periods=11`、`total_cases=48`、`planned_rows=528`、`case_chunk_size=12`、想定 chunks `44` を確認した
- planning full は merged periods × original extended = `4224 rows`、ceiling full は raw periods × original extended = `5376 rows` の件数整理に留め、今回 runnable config にはしなかった
- `config/evaluation_batch_operational.medium.json` の `dry_run` を `false` に切り替え、medium actual run を `python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_operational.medium.json` で実行した
- medium actual run は `run_id=20260325T072931Z_d858f57c`、`run_status=completed`、`total_rows=132`、`succeeded_rows=132`、`failed_rows=0` だった
- medium の CSV は `var/evaluation_batch/medium_results.csv`、SQLite は `var/evaluation_batch/medium_results.sqlite3` で、ともに 132 row を保持し、run メタも `planned_rows=132`、`succeeded_rows=132`、`failed_rows=0` で一致した
- medium run では 11 period すべてで 12 row ずつ生成され、artifact path は 11 個で period ごとに 1 個だった
- medium run の result row では `fetched=True`、`reused_existing_artifact=False` が 132 row で記録され、既存 cache 再利用ではなく当該 run で period ごとに market data を取得したことを確認した
- 同一 period 配下の 12 case は同一 artifact path を共有しており、period 単位で 1 回解決した market data を case 群へ再利用している
- medium actual run では network 制約由来の failure は発生せず、通信先は `https://api.binance.com/api/v3/klines`、取得方式は公開 JSON の HTTP GET だった
- medium actual run の開始から終了までは約 1.34 秒で、132 row 規模では current runner の実行感触は軽い
- operational pilot full actual run 用に `config/evaluation_batch_operational.pilot_full.actual.json` を追加し、dry run 用 config と actual run 用 config を分離した
- operational pilot full actual run を `python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_operational.pilot_full.actual.json` で実行した
- operational pilot full actual run は `run_id=20260325T074029Z_f26bed88`、`run_status=completed`、`planned_rows=528`、`total_rows=528`、`succeeded_rows=528`、`failed_rows=0` だった
- operational pilot full の CSV は `var/evaluation_batch/operational_pilot_full_results.csv`、SQLite は `var/evaluation_batch/operational_pilot_full_results.sqlite3` で、ともに 528 row を保持し、run メタも `planned_rows=528`、`succeeded_rows=528`、`failed_rows=0` で一致した
- operational pilot full run では 11 period すべてで 48 row ずつ生成され、artifact path は 11 個で period ごとに 1 個だった
- operational pilot full run の result row では `reused_existing_artifact=True` が 528 row、`fetched=True` が 0 row で記録され、medium run で生成済みの market data cache を cross-run reuse したことを確認した
- medium と operational pilot full は 11 shared periods すべてで artifact path が一致し、same artifact path count は 11 / 11 だった
- operational pilot full actual run では network 制約由来の failure は発生せず、通信先は `https://api.binance.com/api/v3/klines`、取得方式は公開 JSON の HTTP GET だった
- operational pilot full actual run の開始から終了までは約 0.97 秒で、528 row 規模でも cross-run reuse が効く場合の実行感触は軽い
- current-stack planning 用に `config/evaluation_batch_operational.planning.grids.csv`、`config/evaluation_batch_operational.planning.json`、`config/evaluation_batch_operational.planning.actual.json` を追加し、dry run 用 config と actual run 用 config を分離した
- current-stack planning actual run を `python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_operational.planning.actual.json` で実行した
- current-stack planning actual run は `run_id=20260325T080033Z_f58d07fc`、`run_status=completed`、`planned_rows=4224`、`total_rows=4224`、`succeeded_rows=4224`、`failed_rows=0` だった
- current-stack planning の CSV は `var/evaluation_batch/current_stack_planning_results.csv`、SQLite は `var/evaluation_batch/current_stack_planning_results.sqlite3` で、ともに 4224 row を保持し、run メタも `planned_rows=4224`、`succeeded_rows=4224`、`failed_rows=0` で一致した
- current-stack planning run では 11 period すべてで 384 row ずつ生成され、artifact path は 11 個で period ごとに 1 個だった
- current-stack planning run の result row では `reused_existing_artifact=True` が 4224 row、`fetched=True` が 0 row で記録され、medium / pilot run で生成済みの market data cache を cross-run reuse したことを確認した
- pilot と current-stack planning は 11 shared periods すべてで artifact path が一致し、same artifact path count は 11 / 11 だった
- current-stack planning actual run の実行前には `var/evaluation_batch/current_stack_planning_results.csv` と `.sqlite3` は存在せず、partial run 残留はなかった
- current-stack planning actual run の後は latest run_id が `20260325T080033Z_f58d07fc` の 1 run だけで、CSV / DB 行数は planned_rows と一致しており partial run 残留は確認されなかった
- current-stack planning actual run では network 制約由来の failure は発生せず、通信先は `https://api.binance.com/api/v3/klines`、取得方式は公開 JSON の HTTP GET だった
- current-stack planning actual run の開始から終了までは約 3.76 秒で、4224 row 規模でも cross-run reuse が効く場合の実行感触はまだ軽い
- current-stack planning actual run は、4224 rows 規模の評価・保存・整合性確認と cross-run reuse 確認には成功したが、fresh fetch を伴う 4224 rows 規模の検証ではなく cache-backed execution validation だった
- current-stack ceiling 用に `config/evaluation_batch_operational.ceiling.periods.csv`、`config/evaluation_batch_operational.ceiling.json`、`config/evaluation_batch_operational.ceiling.actual.json` を追加し、dry run 用 config と actual run 用 config を分離した
- current-stack ceiling actual run は latest run として `python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_operational.ceiling.actual.json` を実行し、`run_id=20260325T081754Z_a3d1d089`、`run_status=completed`、`planned_rows=9216`、`total_rows=9216`、`succeeded_rows=9216`、`failed_rows=0` を確認した
- current-stack ceiling の CSV は `var/evaluation_batch/current_stack_ceiling_results.csv`、SQLite は `var/evaluation_batch/current_stack_ceiling_results.sqlite3` で、ともに latest run で 9216 row を保持し、run メタも `planned_rows=9216`、`succeeded_rows=9216`、`failed_rows=0` で一致した
- current-stack ceiling latest run では 24 period すべてで 384 row ずつ生成され、artifact path は 24 個で period ごとに 1 個だった
- current-stack ceiling latest run の result row では `reused_existing_artifact=True` が 4224 row、`fetched=True` が 4992 row で記録され、shared 11 periods は cross-run reuse、new 13 periods は fresh fetch になった
- planning と current-stack ceiling の shared 11 periods では artifact path が 11 / 11 で一致した
- current-stack ceiling latest run では network 制約由来の failure は発生せず、通信先は `https://api.binance.com/api/v3/klines`、取得方式は公開 JSON の HTTP GET だった
- current-stack ceiling 用 CSV / DB は実行前には存在せず partial run 残留はなかった
- current-stack ceiling 用 SQLite には、latest run の前に `20260325T081535Z_98fcda3c` と `20260325T081607Z_d760f224` の completed run が残っているが、いずれも中断 partial ではなく superseded completed run である
- current-stack ceiling latest run の開始から終了までは約 8.65 秒で、9216 row 規模でも reuse 4224 / fetch 4992 の混在で完走した
- original planning baseline 用に `config/original_planning_baseline.raw_candidates.csv`、`config/original_planning_baseline.raw_to_merged.csv`、`config/original_planning_baseline.merged_periods.csv` を追加し、raw 24 と merged 12 の対応関係と merge 理由を再利用可能な形で整理した
- original planning signal-only 用に `config/original_planning_signal_only.case_templates.json`、`config/original_planning_signal_only.grids.csv`、`config/original_planning_signal_only.dry_run.json`、`config/original_planning_signal_only.actual.json` を追加した
- signal-only 75 は `consumption_series_name=5`、`entry_count_threshold=5`、`exit_after_inactive_periods=3` の軸 × 刻み方で定義し、`5 × 5 × 3 = 75 cases / period` とした
- batch runner に external-signal case の period ごと prepare 導線を追加し、return timestamps と保存済み summary を使って `prepare_external_signal_manual_case()` を呼べるようにした
- external signal feature の許容 series 名に `matching_signal_count` を追加し、original signal-only baseline の 5 series を受けられるようにした
- `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_signal_only.dry_run.json` を実行し、`total_periods=12`、`total_cases=75`、`planned_rows=900`、`case_chunk_size=25` を確認した
- initial actual run `run_id=20260325T181438Z_51157164` は `matching_signal_count` 未許容と例外経路不備のため failed になり、SQLite に superseded failed run record が残った
- 修正後の actual run `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_signal_only.actual.json` は `run_id=20260325T181535Z_d3b84d67`、`planned_rows=900`、`total_rows=900`、`succeeded_rows=900`、`failed_rows=0` で completed した
- latest original planning signal-only run の CSV は `var/evaluation_batch/original_planning_signal_only_results.csv`、SQLite は `var/evaluation_batch/original_planning_signal_only_results.sqlite3` で、ともに 900 row を保持し、run メタも `planned_rows=900`、`succeeded_rows=900`、`failed_rows=0` で一致した
- latest original planning signal-only run では 12 period すべてで 75 row ずつ生成され、artifact path は 12 個で period ごとに 1 個だった
- latest original planning signal-only run の row 内訳は `reused_existing_artifact=True = 225`、`fetched=True = 675` で、current-stack ceiling と window が一致する 3 merged periods は cross-run reuse、残り 9 periods は fresh fetch だった
- original planning signal-only latest run では network 制約由来の failure は発生せず、通信先は `https://api.binance.com/api/v3/klines`、取得方式は公開 JSON の HTTP GET だった
- original planning signal-only latest run の開始から終了までは約 2.15 秒で、900 row 規模でも reuse と fresh fetch が混在したまま完走した
- original planning minimal tradability 用に `config/original_planning_minimal_tradability.case_templates.json`、`config/original_planning_minimal_tradability.grids.csv`、`config/original_planning_minimal_tradability.dry_run.json`、`config/original_planning_minimal_tradability.actual.json` を追加した
- minimal tradability は signal-only の 3 軸を維持したまま、`take_profit = 0.02 / 0.04 / 0.06`、`stop_loss = -0.01 / -0.02 / -0.03`、`max_hold_minutes = 720 / 1440 / 2880` を追加し、`75 × 3 × 3 × 3 = 2025 cases / period` とした
- `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_minimal_tradability.dry_run.json` を実行し、`total_periods=12`、`total_cases=2025`、`planned_rows=24300`、`case_chunk_size=75` を確認した
- `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_minimal_tradability.actual.json` を実行し、latest run `run_id=20260325T183155Z_f4c390a1`、`planned_rows=24300`、`total_rows=24300`、`succeeded_rows=24300`、`failed_rows=0` を確認した
- latest original planning minimal tradability run の CSV は `var/evaluation_batch/original_planning_minimal_tradability_results.csv`、SQLite は `var/evaluation_batch/original_planning_minimal_tradability_results.sqlite3` で、ともに 24300 row を保持し、run メタも `planned_rows=24300`、`succeeded_rows=24300`、`failed_rows=0` で一致した
- latest original planning minimal tradability run では 12 period すべてで 2025 row ずつ生成され、artifact path は 12 個で period ごとに 1 個だった
- latest original planning minimal tradability run の row 内訳は `reused_existing_artifact=True = 24300`、`fetched=True = 0` で、signal-only 900-row run と shared window 12 / 12、same artifact path 12 / 12 を確認した
- original planning minimal tradability latest run では network 制約由来の failure は発生せず、通信先は `https://api.binance.com/api/v3/klines`、取得方式は公開 JSON の HTTP GET だった
- original planning minimal tradability latest run の開始から終了までは約 25.98 秒で、24300 row 規模の cache-backed execution validation を完了した
- original planning extended 用に `config/original_planning_extended.case_templates.json`、`config/original_planning_extended.grids.csv`、`config/original_planning_extended.dry_run.json`、`config/original_planning_extended.actual.json` を追加した
- extended は minimal tradability の 6 軸を維持したまま、`price_spike_limit = 0.03 / 0.05 / 0.07` と `volume_multiplier = 1.0 / 1.5 / 2.0` を追加し、`2025 × 3 × 3 = 18225 cases / period` とした
- `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_extended.dry_run.json` を実行し、`total_periods=12`、`total_cases=18225`、`planned_rows=218700`、`case_chunk_size=225` を確認した
- `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_extended.actual.json` を実行し、latest run `run_id=20260325T183929Z_62c407b6`、`planned_rows=218700`、`total_rows=218700`、`succeeded_rows=218700`、`failed_rows=0` を確認した
- latest original planning extended run の CSV は `var/evaluation_batch/original_planning_extended_results.csv`、SQLite は `var/evaluation_batch/original_planning_extended_results.sqlite3` で、ともに 218700 row を保持し、run メタも `planned_rows=218700`、`succeeded_rows=218700`、`failed_rows=0` で一致した
- latest original planning extended run では 12 period すべてで 18225 row ずつ生成され、artifact path は 12 個で period ごとに 1 個だった
- latest original planning extended run の row 内訳は `reused_existing_artifact=True = 218700`、`fetched=True = 0` で、minimal 24300-row run と shared window 12 / 12、same artifact path 12 / 12 を確認した
- original planning extended latest run では network 制約由来の failure は発生せず、通信先は `https://api.binance.com/api/v3/klines`、取得方式は公開 JSON の HTTP GET だった
- original planning extended latest run の開始から終了までは約 207.74 秒で、218700 row 規模の cache-backed execution validation を完了した

## Original Planning Baseline Run

- merged periods 12:
  - 定義ファイルは `config/original_planning_baseline.merged_periods.csv`
  - raw candidate 24 は `config/original_planning_baseline.raw_candidates.csv`
  - raw 24 と merged 12 の対応は `config/original_planning_baseline.raw_to_merged.csv`
  - merged period は `period_id,source,symbol,interval,start,end` に加え、`short_name`、`merge_reason`、`raw_period_ids` を持つ
- raw 24 と merged 12 の対応方針:
  - 近接する event window を overlap_group ベースでまとめる
  - 規制 / ETF / price discovery / macro shock のように近接イベントが同一ボラティリティ局面を構成する場合は merged に吸収する
  - raw 側の event 単位記録は保持しつつ、actual run は merged 側 12 periods を使う
- signal-only 75:
  - `consumption_series_name`: `matching_signal_count`、`weighted_matching_signal_count`、`blended_signal_count_s07_t03`、`blended_signal_count_s05_t05`、`blended_signal_count_s03_t07`
  - `entry_count_threshold`: `1.0`、`1.2`、`1.4`、`1.6`、`1.8`
  - `exit_after_inactive_periods`: `1`、`2`、`3`
  - 上記 3 軸だけを展開し、`5 × 5 × 3 = 75 cases / period`
  - `take_profit`、`stop_loss`、`max_hold_minutes`、`price_spike_limit`、`volume_multiplier` は original planning baseline の parameter 軸として残すが、この run では展開しない
- dry run:
  - config: `config/original_planning_signal_only.dry_run.json`
  - 結果: `total_periods=12`、`total_cases=75`、`planned_rows=900`、`case_chunk_size=25`
- actual run:
  - config: `config/original_planning_signal_only.actual.json`
  - latest run_id: `20260325T181535Z_d3b84d67`
  - status: `completed`
  - `planned_rows=900`、`total_rows=900`、`succeeded_rows=900`、`failed_rows=0`
  - 保存先: `var/evaluation_batch/original_planning_signal_only_results.csv`、`var/evaluation_batch/original_planning_signal_only_results.sqlite3`
- superseded failed run:
  - run_id: `20260325T181438Z_51157164`
  - 種別: latest run の partial 残留ではなく、修正前実装による superseded failed run record
  - 原因: `matching_signal_count` 未許容と、case prepare 失敗時の例外経路不備

## Original Planning Minimal Tradability Run

- periods:
  - merged periods 12 は `config/original_planning_baseline.merged_periods.csv` をそのまま使う
- minimal tradability 2025:
  - signal-only の 3 軸は前回と同一
  - 追加軸は `take_profit`、`stop_loss`、`max_hold_minutes` の 3 つだけ
  - 刻みは `take_profit = 0.02 / 0.04 / 0.06`、`stop_loss = -0.01 / -0.02 / -0.03`、`max_hold_minutes = 720 / 1440 / 2880`
  - 上記により `5 × 5 × 3 × 3 × 3 × 3 = 2025 cases / period`
- dry run:
  - config: `config/original_planning_minimal_tradability.dry_run.json`
  - 結果: `total_periods=12`、`total_cases=2025`、`planned_rows=24300`、`case_chunk_size=75`
- actual run:
  - config: `config/original_planning_minimal_tradability.actual.json`
  - latest run_id: `20260325T183155Z_f4c390a1`
  - status: `completed`
  - `planned_rows=24300`、`total_rows=24300`、`succeeded_rows=24300`、`failed_rows=0`
  - 保存先: `var/evaluation_batch/original_planning_minimal_tradability_results.csv`、`var/evaluation_batch/original_planning_minimal_tradability_results.sqlite3`
- reuse / fetch:
  - `reused_existing_artifact=True = 24300`
  - `fetched=True = 0`
  - signal-only 900-row run と shared window 12 / 12、artifact path 一致 12 / 12

## Original Planning Extended Run

- periods:
  - merged periods 12 は `config/original_planning_baseline.merged_periods.csv` をそのまま使う
- extended 18225:
  - minimal tradability の 6 軸は前回と同一
  - 追加軸は `price_spike_limit` と `volume_multiplier` の 2 つだけ
  - 刻みは `price_spike_limit = 0.03 / 0.05 / 0.07`、`volume_multiplier = 1.0 / 1.5 / 2.0`
  - 上記により `5 × 5 × 3 × 3 × 3 × 3 × 3 × 3 = 18225 cases / period`
- dry run:
  - config: `config/original_planning_extended.dry_run.json`
  - 結果: `total_periods=12`、`total_cases=18225`、`planned_rows=218700`、`case_chunk_size=225`
- actual run:
  - config: `config/original_planning_extended.actual.json`
  - latest run_id: `20260325T183929Z_62c407b6`
  - status: `completed`
  - `planned_rows=218700`、`total_rows=218700`、`succeeded_rows=218700`、`failed_rows=0`
  - 保存先: `var/evaluation_batch/original_planning_extended_results.csv`、`var/evaluation_batch/original_planning_extended_results.sqlite3`
- reuse / fetch:
  - `reused_existing_artifact=True = 218700`
  - `fetched=True = 0`
  - minimal 24300-row run と shared window 12 / 12、artifact path 一致 12 / 12

## Network Run Recording

- 記録項目:
  - 実行コマンド
  - config path
  - 通信先 URL / domain
  - 取得方式
  - 実行条件変更の有無
  - Codex 視点で確認できた承認事実 / 不明
  - 保存先一覧
  - raw body 保存の有無
  - failure 分類
  - run_id
- 既知事実:
  - `python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_initial.small.json` は通常 sandbox で DNS 名前解決失敗となった
  - 同じコマンドを `sandbox_permissions=require_escalated` 付きで再実行すると成功した
  - Codex から観測できたのは「通常 sandbox では失敗、escalated 実行では成功」までで、承認 UI の内訳は不明である
  - 現時点では即違反認定ではないが、次の external communication actual run 前に運用 fix を入れる必要がある
  - medium actual run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_operational.medium.json` を `sandbox_permissions=require_escalated` で実行した
  - medium actual run の config path は `config/evaluation_batch_operational.medium.json`、run_id は `20260325T072931Z_d858f57c`、通信先は `https://api.binance.com/api/v3/klines`、domain は `api.binance.com` である
  - 取得方式は公開 JSON の HTTP GET で、Codex から確認できた承認事実は「escalated 実行としてコマンドが実行できた」までで、承認 UI の内訳は不明である
  - 保存先は `var/evaluation_batch/medium_results.csv`、`var/evaluation_batch/medium_results.sqlite3`、`var/cache/market_data/ohlcv/...` の正規化済み OHLCV cache、`var/cache/market_data/shared_state.sqlite3` である
  - raw body 保存は行っておらず、failure 分類は今回の medium actual run では該当なし、run status は `completed` である
  - operational pilot full actual run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_operational.pilot_full.actual.json` を `sandbox_permissions=require_escalated` で実行した
  - operational pilot full actual run の config path は `config/evaluation_batch_operational.pilot_full.actual.json`、run_id は `20260325T074029Z_f26bed88`、通信先は `https://api.binance.com/api/v3/klines`、domain は `api.binance.com` である
  - 取得方式は公開 JSON の HTTP GET で、Codex から確認できた承認事実は「escalated 実行としてコマンドが実行できた」までで、承認 UI の内訳は不明である
  - 保存先は `var/evaluation_batch/operational_pilot_full_results.csv`、`var/evaluation_batch/operational_pilot_full_results.sqlite3`、`var/cache/market_data/ohlcv/...` の正規化済み OHLCV cache、`var/cache/market_data/shared_state.sqlite3` である
  - raw body 保存は行っておらず、failure 分類は今回の operational pilot full actual run では該当なし、run status は `completed` である
  - current-stack planning actual run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_operational.planning.actual.json` を `sandbox_permissions=require_escalated` で実行した
  - current-stack planning actual run の config path は `config/evaluation_batch_operational.planning.actual.json`、run_id は `20260325T080033Z_f58d07fc`、通信先は `https://api.binance.com/api/v3/klines`、domain は `api.binance.com` である
  - 取得方式は公開 JSON の HTTP GET で、Codex から確認できた承認事実は「escalated 実行としてコマンドが実行できた」までで、承認 UI の内訳は不明である
  - 保存先は `var/evaluation_batch/current_stack_planning_results.csv`、`var/evaluation_batch/current_stack_planning_results.sqlite3`、`var/cache/market_data/ohlcv/...` の正規化済み OHLCV cache、`var/cache/market_data/shared_state.sqlite3` である
  - raw body 保存は行っておらず、failure 分類は今回の current-stack planning actual run では該当なし、run status は `completed` である
  - current-stack ceiling actual run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_operational.ceiling.actual.json` を `sandbox_permissions=require_escalated` で実行した
  - current-stack ceiling actual run の latest config path は `config/evaluation_batch_operational.ceiling.actual.json`、latest run_id は `20260325T081754Z_a3d1d089`、通信先は `https://api.binance.com/api/v3/klines`、domain は `api.binance.com` である
  - 取得方式は公開 JSON の HTTP GET で、Codex から確認できた承認事実は「escalated 実行としてコマンドが実行できた」までで、承認 UI の内訳は不明である
  - 保存先は `var/evaluation_batch/current_stack_ceiling_results.csv`、`var/evaluation_batch/current_stack_ceiling_results.sqlite3`、`var/cache/market_data/ohlcv/...` の正規化済み OHLCV cache、`var/cache/market_data/shared_state.sqlite3` である
  - raw body 保存は行っておらず、failure 分類は今回の current-stack ceiling latest run では該当なし、run status は `completed` である
  - original planning signal-only dry run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_signal_only.dry_run.json` を実行し、`total_periods=12`、`total_cases=75`、`planned_rows=900` を確認した
  - original planning signal-only actual run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_signal_only.actual.json` を `sandbox_permissions=require_escalated` で実行した
  - original planning signal-only actual run の latest config path は `config/original_planning_signal_only.actual.json`、latest run_id は `20260325T181535Z_d3b84d67`、通信先は `https://api.binance.com/api/v3/klines`、domain は `api.binance.com` である
  - 取得方式は公開 JSON の HTTP GET で、Codex から確認できた承認事実は「escalated 実行としてコマンドが実行できた」までで、承認 UI の内訳は不明である
  - 保存先は `var/evaluation_batch/original_planning_signal_only_results.csv`、`var/evaluation_batch/original_planning_signal_only_results.sqlite3`、`var/cache/market_data/ohlcv/...` の正規化済み OHLCV cache、`var/cache/market_data/shared_state.sqlite3` である
  - raw body 保存は行っておらず、latest run の failure 分類は該当なし、run status は `completed` である
  - 先行 failed run `20260325T181438Z_51157164` は implementation mismatch で、`matching_signal_count` 未許容と例外経路不備が原因だった
  - original planning minimal tradability dry run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_minimal_tradability.dry_run.json` を実行し、`total_periods=12`、`total_cases=2025`、`planned_rows=24300` を確認した
  - original planning minimal tradability actual run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_minimal_tradability.actual.json` を `sandbox_permissions=require_escalated` で実行した
  - original planning minimal tradability actual run の latest config path は `config/original_planning_minimal_tradability.actual.json`、latest run_id は `20260325T183155Z_f4c390a1`、通信先は `https://api.binance.com/api/v3/klines`、domain は `api.binance.com` である
  - 取得方式は公開 JSON の HTTP GET で、Codex から確認できた承認事実は「escalated 実行としてコマンドが実行できた」までで、承認 UI の内訳は不明である
  - 保存先は `var/evaluation_batch/original_planning_minimal_tradability_results.csv`、`var/evaluation_batch/original_planning_minimal_tradability_results.sqlite3`、`var/cache/market_data/ohlcv/...` の正規化済み OHLCV cache、`var/cache/market_data/shared_state.sqlite3` である
  - raw body 保存は行っておらず、latest run の failure 分類は該当なし、run status は `completed` である
  - original planning extended dry run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_extended.dry_run.json` を実行し、`total_periods=12`、`total_cases=18225`、`planned_rows=218700` を確認した
  - original planning extended actual run では `python3 scripts/run_evaluation_batch_from_inputs.py --config config/original_planning_extended.actual.json` を `sandbox_permissions=require_escalated` で実行した
  - original planning extended actual run の latest config path は `config/original_planning_extended.actual.json`、latest run_id は `20260325T183929Z_62c407b6`、通信先は `https://api.binance.com/api/v3/klines`、domain は `api.binance.com` である
  - 取得方式は公開 JSON の HTTP GET で、Codex から確認できた承認事実は「escalated 実行としてコマンドが実行できた」までで、承認 UI の内訳は不明である
  - 保存先は `var/evaluation_batch/original_planning_extended_results.csv`、`var/evaluation_batch/original_planning_extended_results.sqlite3`、`var/cache/market_data/ohlcv/...` の正規化済み OHLCV cache、`var/cache/market_data/shared_state.sqlite3` である
  - raw body 保存は行っておらず、latest run の failure 分類は該当なし、run status は `completed` である

## Official Scale Definition

- `small`:
  - 対応: 旧 medium actual run
  - 目的: 代表性確認、CSV / DB / run メタ整合、period 単位 reuse の最小実運用規模
  - periods: 11
  - cases: 12
  - planned_rows: 132
  - case_chunk_size: 6
  - chunks: 22
  - 実績注記: market data fetch と保存導線の最小実運用確認として承認済み
  - 出力先: `var/evaluation_batch/medium_*`
- `medium`:
  - 対応: 旧 current-stack planning actual run
  - 目的: 4224 rows 規模の評価・保存・整合性確認
  - periods: 11
  - cases: 384
  - planned_rows: 4224
  - case_chunk_size: 50
  - chunks: 88
  - 実績注記: fresh fetch を伴う検証ではなく、cache-backed execution validation として承認済み
  - 出力先: `var/evaluation_batch/current_stack_planning_*`
- `full`:
  - 対応: 旧 current-stack ceiling actual run
  - 目的: 今の current-stack で回す最終公式規模
  - periods: 24
  - cases: 384
  - planned_rows: 9216
  - case_chunk_size: 50
  - chunks: 192
  - 実績注記: `reused_existing_artifact=True = 4224` と `fetched=True = 4992` の混在を確認済み
  - 出力先: `var/evaluation_batch/current_stack_ceiling_*`

## Transitional Internal Names

- `seed/smoke`:
  - 位置づけ: 初期確認用の内部呼称
  - 対応: `current initial full=32` はここに属し、公式 `full` ではない
- `operational pilot full`:
  - 位置づけ: 移行期の保守的な大きめ run 用内部呼称
  - 対応: `528 rows`
- `current-stack planning`:
  - 位置づけ: 現在の公式 `medium` に吸収された旧呼称
  - 対応: `4224 rows`
- `current-stack ceiling`:
  - 位置づけ: 現在の公式 `full` に吸収された旧呼称
  - 対応: `9216 rows`
- `original planning baseline`:
  - 目的: 元の構想どおり sufficiently fine parameter grid を掛けた baseline
  - periods: merged periods 10〜14、代表値 12
  - cases: signal-only ≈ 75 / period、minimal ≈ 2025 / period、extended ≈ 18225 / period
  - planned_rows: signal-only ≈ 900、minimal ≈ 24300、extended ≈ 218700
  - case_chunk_size: 50
  - chunks: signal-only ≈ 24、minimal ≈ 492、extended ≈ 4380
  - 実行条件: 直ちに実行しない
  - 出力先: planning 用命名だけ定義
- `original ceiling baseline`:
  - 目的: raw candidate periods 側へ広げた元構想の上限計画値
  - periods: raw candidate periods 前後 24
  - cases: signal-only ≈ 75 / period、minimal ≈ 2025 / period、extended ≈ 18225 / period
  - planned_rows: signal-only ≈ 1800、minimal ≈ 48600、extended ≈ 437400
  - case_chunk_size: 50
  - chunks: signal-only ≈ 48、minimal ≈ 984、extended ≈ 8760
  - 実行条件: 直ちに実行しない
  - 出力先: planning 用命名だけ定義

## Not Yet Implemented

- builder / manifest の部分流用ルール
- 部分再開方針
- DB 主体運用への最終切替
- 全量本実行

## Next Candidate Tasks

- original planning baseline の次段として、raw 24 × signal-only へ広げるか、raw 24 × minimal へ進むかを判断する
- original planning baseline の merged 12 定義をこのまま固定するか、後続候補入れ替え余地を残すかを判断する
- 必要なら external-signal summary root の複数系統対応を再評価する

## Next Approval Gate

- original planning baseline の extended actual run 結果を確認したうえで、次に raw 24 × signal-only へ進むか、raw 24 × minimal へ進むかの承認待ちにする
