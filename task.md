# Task

## Current Official Task

1. 実験入力の初版作成と、実データによる段階的実行

## Goal

- 実際に使う初版の periods / case templates / grids / adapter config を作り、dry run と小規模実データ run を通して実験入口を再現可能にする
- 既存の period 単位 market data reuse、case chunk 実行、CSV / DB 逐次保存の導線を実運用前提で確認する

## In Scope

- 実験用の初版 periods.csv を作る
- 実験用の初版 case_templates.json と grids.csv を作る
- full dry run と period_limit / case_limit を使った小規模実データ run を実行する
- CSV / DB の整合と run 集計を確認し、README / task に残す

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
- 巨大な本実行は行わず、今回は dry run と小規模実データ run に限定する

## Current Plan

- 初版実験入力として複数代表 period と既存 strategy ベースの template / grid を定義する
- full config で dry run を行い、planned_rows と case 上限の効き方を確認する
- subset config で小規模実データ run を行い、CSV / DB 整合と run 集計を確認する
- 実行コマンドと確認結果を README / task に記録する
- 小規模実データ run の再実行時に何が変わったかを事実ベースで整理する
- current initial input を前提に full planned_rows を算出し、small / medium / full の定義案を置く

## Open Questions

- 初版 input の次にどの粒度で period と grids を拡張するか
- 部分再開を後続タスクで扱うか、run 単位積み増しを原則に固定するか
- medium 規模を `period_limit=2, case_limit=4` で固定するか、`period_limit=2, case_limit=6` まで広げるか

## Risks

- 実験 input が過剰だと小規模確認の前に実行負荷が上がる
- 実データ取得が失敗すると run 検証が止まる
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

## Not Yet Implemented

- builder / manifest の部分流用ルール
- 部分再開方針
- DB 主体運用への最終切替
- 全量本実行

## Next Candidate Tasks

- 初版 input を基に medium 実行を行うかどうか承認を取り、必要なら `period_limit=2, case_limit=4` 前提で確認する
- 必要なら builder / manifest との限定的な接続を再評価する

## Next Approval Gate

- ネットワーク再実行の事実確認、full planned_rows 算出、small / medium / full 定義案、出力先運用方針を確認したうえで、medium 実行可否の承認待ちに入る
