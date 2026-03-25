# Task

## Current Official Task

1. 大量ケース実行のための入力接続と段階的実行

## Goal

- periods / cases / parameter grids などの入力資産を既存 batch runner へ薄く接続し、dry run から小規模 run、本実行準備まで同じ導線で扱えるようにする
- 既存の period 単位 market data reuse、case chunk 実行、CSV / DB 逐次保存を維持したまま、大量ケース実行の入口を整える

## In Scope

- periods / case templates / grids を batch runner 入力へ変換する薄い adapter 層を作る
- period 単位 + case chunk 単位の実行方針を維持する
- case 展開時に一意な `case_name` を保証する
- dry run、period / case subset 実行、本実行準備の導線を明確にする
- CSV / DB 二重保存時の中断・再実行の最小運用ルールを明文化する

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

## Current Plan

- periods CSV と case templates / grids から batch runner 入力を組み立てる adapter を追加する
- 既存 JSON batch config 入口は維持し、新しい入力資産用の入口を別で用意する
- grid は遅延走査し、period ごとに fresh iterator を取り直して case chunk 単位に prepare / 実行する
- `period_limit` / `case_limit` / `dry_run` を使って小規模確認と本実行準備を分ける
- CSV / DB の中断・再実行は「新しい run_id を発行して積み増す」前提を明文化する

## Open Questions

- 既存 builder / manifest 資産を将来どこまで入力生成に流用するか
- 部分再開を後続タスクで扱うか、run 単位積み増しを原則に固定するか

## Risks

- grids 展開を先に巨大配列化するとメモリ制約を破る
- 入力 adapter が runner 本体へ食い込むと責務境界が崩れる
- case_name 一意性が崩れると CSV / DB の追跡が曖昧になる
- 中断時と再実行時の扱いが曖昧だと run 単位分析が難しくなる

## Progress / Done

- step1 と step2 は完了済みとして承認された
- period 単位 market data reuse、case chunk 実行、CSV / DB 逐次保存の batch runner 基盤は実装済み
- 次の正式タスクとして、大量ケース実行のための入力接続と段階的実行へ切り替えた
- 本タスクでは、periods / case templates / grids から batch runner へ接続する薄い adapter 入口を追加する

## Not Yet Implemented

- builder / manifest の部分流用ルール
- 部分再開方針
- DB 主体運用への最終切替

## Next Candidate Tasks

- 実運用前に中規模 subset と本実行前設定を確認する
- 必要なら builder / manifest との限定的な接続を再評価する

## Next Approval Gate

- 入力 adapter、dry run、小規模 run 導線、README / task 更新の実装結果を確認したうえで承認待ちに入る
