# Task

## Current Official Task

1. operational pilot full actual run

## Goal

- operational pilot full actual run を再現可能な形で実行し、CSV / DB / run メタ / artifact / cross-run reuse 挙動を確認する
- 外部通信 run の承認と記録ルールに沿って、実行条件・通信先・保存範囲・failure 分類を task.md に残す
- 次の actual run 判断に向けて、operational pilot full の結果を current-stack scale 定義に結び付ける

## In Scope

- operational pilot full actual run を `config/evaluation_batch_operational.pilot_full.actual.json` で実行する
- 実行結果の CSV / DB 整合、run メタ、artifact 生成、cross-run reuse を確認する
- 通信先、取得方式、実行条件変更、保存先、failure 分類、run_id を具体記録として残す
- 次の actual run 候補を operational pilot full の結果に基づいて整理する

## Out of Scope

- OHLCV artifact の全面 DB 化
- market data shared truth の再設計
- research manifest との全面統合
- 並列化の本格導入
- acquisition key 同時実行制御の完成
- schema version 運用ルールの完成
- 戦略改善
- パラメータ最適化

## Execution Constraints

- comparison / simulate の責務は増やさない
- market data reuse の既存方針を崩さない
- period ごとに market data を 1 回だけ解決し、returns を 1 回だけ生成する
- case 準備も含めて全件一括メモリ展開しない
- case_name の一意性を入力展開側で保証する
- 結果は CSV / DB に逐次保存し、途中成果を失わない
- 今回 actual run の対象は operational pilot full だけに限定する
- current-stack planning 以降の actual run は行わない
- 外部通信 actual run は事前承認済みコマンドだけを使う

## Current Plan

- `config/evaluation_batch_operational.pilot_full.actual.json` を actual run 用 config として使い、pilot full を 1 回だけ実行する
- 実行後に CSV / DB / run メタ / artifact / cross-run reuse を確認する
- task.md に実行コマンド、run_id、通信先、保存先、failure 分類、結果件数を残す
- 次の actual run 候補を operational pilot full の結果に基づいて絞る

## Open Questions

- raw candidate periods のうち 2025 系候補をどこまで残すか
- 部分再開を後続タスクで扱うか、run 単位積み増しを原則に固定するか
- original planning baseline の periods を merged 12 固定にするか、10〜14 のレンジとして残すか

## Risks

- current batch runner は external-signal planning grid をそのまま runnable config としては扱っていない
- 通信許可の承認経路は Codex から完全には観測できない
- case_name 一意性が崩れると CSV / DB の追跡が曖昧になる
- 中断時と再実行時の扱いが曖昧だと run 単位分析が難しくなる

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

## Scale Definition

- `seed/smoke`:
  - 目的: adapter / runner / CSV / DB / artifact の最小確認
  - periods: 1
  - cases: 3
  - planned_rows: 3
  - case_chunk_size: 2
  - chunks: 2
  - 実行条件: config 変更後の最初の実データ確認だけ
  - 出力先: `var/evaluation_batch/seed_smoke_*`
- `small`:
  - 目的: 複数 case family と複数 chunk の確認
  - periods: 2
  - cases: 6
  - planned_rows: 12
  - case_chunk_size: 6
  - chunks: 2
  - 実行条件: seed/smoke 成功後
  - 出力先: `var/evaluation_batch/small_*`
- `medium`:
  - 目的: merged periods 全件と signal-only full 近傍の representative cases による代表性確認
  - periods: 11
  - cases: 12
  - planned_rows: 132
  - case_chunk_size: 6
  - chunks: 22
  - 実行条件: 外部通信 run ルール fix 後
  - 出力先: `var/evaluation_batch/medium_*`
- `operational pilot full`:
  - 目的: current runner 上で実際に回す最初の大きめ run
  - periods: 11
  - cases: 48
  - planned_rows: 528
  - case_chunk_size: 12
  - chunks: 44
  - 実行条件: medium 成功後
  - 出力先: `var/evaluation_batch/operational_pilot_full_*`
- `current-stack planning`:
  - 目的: current-stack 上で conservative extended を掛けた planning 値
  - periods: 11 merged periods
  - cases: 384 extended
  - planned_rows: 4224
  - case_chunk_size: 50
  - chunks: 88
  - 実行条件: 直ちに実行しない
  - 出力先: planning 用命名だけ定義
- `current-stack ceiling`:
  - 目的: current-stack の conservative extended を raw candidate 24 periods 相当まで広げた ceiling
  - periods: 24 raw candidate periods 相当
  - cases: 384 extended
  - planned_rows: 9216
  - case_chunk_size: 50
  - chunks: 192
  - 実行条件: 直ちに実行しない
  - 出力先: planning 用命名だけ定義
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

- operational pilot full actual run の結果を確認し、current-stack planning actual run に進むかを判断する
- current-stack planning / ceiling と original planning baseline / ceiling baseline のどこまでを今後 runnable 化するかを別タスクで判断する
- 必要なら builder / manifest との限定的な接続を再評価する

## Next Approval Gate

- operational pilot full actual run の結果確認後、current-stack planning actual run に進むかを承認待ちにする
