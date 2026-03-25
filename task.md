# Task

## Current Official Task

1. ネットワーク運用ルールの fix
2. scale 定義の修正
3. medium / operational pilot full 実行直前までの config / dry run / 出力先設計の準備

## Goal

- 外部通信 run の承認と記録ルールを曖昧なままにせず、抽象ルール・常設運用・今回の具体記録を分離して fix する
- seed/small/medium/operational pilot full/planning full/ceiling full を、現在の実装で runnable なものと planning 上の件数整理に分けて再定義する
- actual run に入る直前までの config、dry run、出力先設計を揃える

## In Scope

- AGENTS / README / task の役割分担を守りつつ、外部通信 run の運用ルールを fix する
- seed / smoke、small、medium、operational pilot full、planning full、ceiling full を再定義する
- runnable な medium / operational pilot full 用 config と出力先を準備する
- medium と operational pilot full の dry run を実行して planned_rows と chunk 数を確認する
- planning full / ceiling full は件数整理と命名方針だけを残す

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
- medium 実行や full 実行はまだ開始しない
- 外部通信を伴う新しい run は行わない
- dry run だけを行う

## Current Plan

- AGENTS には外部通信 run の抽象ルールだけを追加する
- README には常設運用と runnable scale の入口説明だけを置く
- task.md には今回の具体 run 記録欄、留保点、scale 定義、dry run 結果を残す
- runnable scale は current runner が直接扱える trade-strategy grid で medium と operational pilot full を準備する
- planning full と ceiling full は original planning numbers として件数整理を残す

## Open Questions

- raw candidate periods のうち 2025 系候補をどこまで残すか
- 部分再開を後続タスクで扱うか、run 単位積み増しを原則に固定するか
- planning full を raw baseline で保持するか、merged baseline を併記するか

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
- 本命 full 再定義のための raw candidate periods 案は 14 件、merged periods 案は 11 件とした
- grid 件数は signal-only 12、minimal tradability 8、extended 384、optional execution 1152 の案を置いた
- raw periods × grid 件数は signal-only 168、minimal 112、extended 5376、optional 16128 rows である
- merged periods × grid 件数は signal-only 132、minimal 88、extended 4224、optional 12672 rows である
- 再定義案として、small は `period_limit=2, case_limit=6, planned_rows=12`、medium は `period_limit=6, case_limit=12, planned_rows=72`、full は merged operational `period_limit=11, case_limit=384, planned_rows=4224`、raw ceiling は `period_limit=14, case_limit=384, planned_rows=5376` とした
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
  - 目的: merged periods 全件と representative cases による代表性確認
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
- `planning full`:
  - 目的: original planning numbers の baseline
  - periods: 11 merged periods
  - cases: 384 extended
  - planned_rows: 4224
  - case_chunk_size: 50
  - chunks: 88
  - 実行条件: 直ちに実行しない
  - 出力先: planning 用命名だけ定義
- `ceiling full`:
  - 目的: raw candidate periods × original extended の上限計画値
  - periods: 14 raw periods
  - cases: 384 extended
  - planned_rows: 5376
  - case_chunk_size: 50
  - chunks: 112
  - 実行条件: 直ちに実行しない
  - 出力先: planning 用命名だけ定義

## Not Yet Implemented

- builder / manifest の部分流用ルール
- 部分再開方針
- DB 主体運用への最終切替
- 全量本実行

## Next Candidate Tasks

- medium dry run と operational pilot full dry run の結果を確認し、actual run 可否の承認を取る
- planning full / ceiling full を runnable 化する必要があるかを別タスクで判断する
- 必要なら builder / manifest との限定的な接続を再評価する

## Next Approval Gate

- ネットワーク運用 fix、scale 定義修正、medium / operational pilot full dry run、出力先設計を確認したうえで、actual run 可否の承認待ちに入る
