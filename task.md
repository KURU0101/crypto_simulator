# Task

## Current Official Task

1. ネットワーク再実行の事実確認と安全性整理
2. 本来想定していた full 規模の再定義と、それに基づく small / medium / full の再設計

## Goal

- ネットワーク再実行時の実行条件変更、通信実体、保存範囲、留保点を事実ベースで整理する
- initial input の full ではなく、本来想定していた raw candidate periods と merged periods を前提に full 規模を再定義し、small / medium / full の基準を置く

## In Scope

- ネットワーク再実行の追加確認を行う
- raw candidate periods と merged periods の案を置く
- signal-only / minimal tradability / extended / optional execution の grid 件数を整理する
- raw / merged 両方に対する planned_rows と small / medium / full 定義案を置く
- task.md に確認結果と次の承認ゲートを残す

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
- API 取得を伴う追加 run は行わない

## Current Plan

- 小規模実データ run の 1 回目失敗と 2 回目成功の差分を事実ベースで整理する
- raw candidate periods を 3 年分の市場インパクト候補として formalize する
- overlap_group ベースの merged periods 案を作る
- signal-only / minimal tradability / extended / optional execution の grid 件数を定義する
- raw ceiling と merged operational full の両方を算出し、そのうえで small / medium / full を再定義する

## Open Questions

- raw candidate periods のうち 2025 系候補をどこまで残すか
- 部分再開を後続タスクで扱うか、run 単位積み増しを原則に固定するか
- full を raw×extended の ceiling とみなすか、merged×extended の operational baseline とみなすか

## Risks

- 既存文書に具体 event 候補一覧が残っていないため、一部は今回の提案ベースになる
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

## Not Yet Implemented

- builder / manifest の部分流用ルール
- 部分再開方針
- DB 主体運用への最終切替
- 全量本実行

## Next Candidate Tasks

- raw candidate periods と merged periods のどちらを本実行基準にするか承認を取る
- medium 実行を行うかどうか承認を取り、必要なら `period_limit=6, case_limit=12` 前提で確認する
- 必要なら builder / manifest との限定的な接続を再評価する

## Next Approval Gate

- ネットワーク再実行の追加確認、raw / merged periods 案、本命 full planned_rows、small / medium / full 再定義、出力先運用方針を確認したうえで、medium 実行可否の承認待ちに入る
