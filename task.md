# Task

## Current Official Task

1. 既存 runner を使って、大量ケースを現実的なメモリ制約の中で実行できるようにする
2. 結果テーブルだけを DB 化して、後分析しやすくする

## Goal

- 既存の evaluation runner / batch runner の責務分離を崩さず、大量ケース実行に耐える orchestration と結果保存導線を整える
- `1 period × 1 case` 粒度の結果を途中失敗込みで保持し、後分析しやすい形へ整理する

## In Scope

- period ごとに market data を 1 回だけ解決し、returns を 1 回だけ生成する構造を守る
- `period × case` の全件一括メモリ展開を避ける実行入口を設計・実装する
- case を小さな単位で流し、結果を逐次保存する
- run 単位メタ情報と `1 period × 1 case` 結果行を DB 保存できるようにする
- 既存 runner から再利用できる case 実行ロジックを活かす

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
- 今回 DB 化するのは結果だけとする
- period 失敗時は、その period 配下の全 case に failed row を出し、他 period は続行する
- 1 case 失敗で全体停止させず、failed row を保存して続行する
- 結果は逐次保存し、途中成果を失わない

## Current Plan

- ステップ1:
  - batch 実行の入力展開を period 単位 / case チャンク単位へ寄せる
  - period ごとに market data 解決と returns 生成を 1 回だけ行う
  - case 実行は既存 runner から切り出した helper を再利用し、結果は逐次保存する
- ステップ2:
  - 結果保存用の SQLite を追加する
  - run 単位メタ情報と `1 period × 1 case` 行を保存する
  - CSV との役割関係を整理し、後分析導線を安定化する

## Open Questions

- case チャンクサイズを固定値にするか設定値にするか
- CSV を主保存に残すか、DB を主保存にして CSV を副出力にするか
- result テーブルの一意性を `run_id + period_id + case_name` にするか、別の case 識別子を導入するか
- 再実行時に新しい `run_id` で積み増すだけにするか、部分再開も考慮するか

## Risks

- 全件を先に巨大配列化するとメモリ制約を破る
- orchestration が肥大化すると comparison との責務境界が崩れる
- DB と CSV の二重保存が複雑化すると保守負荷が上がる
- run 管理が曖昧だと後分析で結果の切り分けが難しくなる

## Progress / Done

- market data reuse 導線を実装済み
- 単一 case runner を実装済み
- 複数 period × 複数 case batch runner を実装済み
- batch runner は `1 period × 1 case = 1 row` の CSV を出力し、最小 JSON summary を返す
- 正式タスク 2 件にスコープを限定した
- 本時点では、文書責務を `AGENTS.md` / `project_context.md` / `task.md` に再整理した

## Not Yet Implemented

- 大量ケース向けの period 単位 / case チャンク単位の逐次実行入口
- 結果テーブルの DB 保存
- DB 主体運用時の CSV との最終的な役割整理
- 部分再開方針

## Next Candidate Tasks

- ステップ1として、全件一括メモリ展開を避ける batch 実行入口を実装する
- ステップ2として、結果 DB を追加し、逐次保存へ切り替える
- 必要なら、ステップ1完了後に保存形式の主従関係を明確化する

## Next Approval Gate

- 現在の公式タスクは上記 2 件のままとする
- 次の承認待ちは、文書整理後に提示する実装・実行計画の承認である
- この承認を得るまでは、runner 改修や DB 実装には着手しない
