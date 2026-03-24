# Project Context

## Purpose

このリポジトリは、トレード戦略の検証を安全に反復するための個人用研究基盤です。
中心は `simulate` によるバックテストであり、実データ入力、疑似リアルタイム再生、外部シグナル入力、統合観測はその周辺レイヤとして整理しています。

## Current Structure

- `simulate`: `returns`、`entry_signals`、`exit_signals` を受けて損益推移を計算する最小コア
- comparison / real data pipeline: OHLCV から returns を作り、strategy ごとの差分を比較する導線
- pseudo realtime replay / live decision runner: OHLCV 系データを逐次評価する外側レイヤ
- external signal inputs: SNS / News を正規化済みシグナルとして受け取り、保存と観測までを行う層
- integrated observer: 保存済み external signal summary を横断して読む読み取り専用層

## Data Flow

### Trading path

`OHLCV -> returns -> signals -> simulate -> comparison / replay / live decision`

### External signal path

`fetch -> adapter -> normalize -> save -> observe`

補足:

- fetch は公開 RSS / 公開 JSON の取得だけを行う
- adapter は source 固有差分、topic / symbol 推定、metadata 整形を吸収する
- normalize は schema 準拠、時刻正規化、entity 判定、軽量 dedup key を扱う
- save は正規化済み bundle と run 単位 summary の保存だけを行う
- observe は collector run の観測 summary を組み立てる
- integrated observer は保存済み summary の共通項目だけを読んで横断表示する

## External Signal Architecture

external signal 基盤は、`simulate` に直結しない前提で維持しています。
現在の役割は次の 2 つです。

1. 外部入力を安全な最小 schema に正規化すること
2. 保存済み run を summary ベースで観測できること

現在サポートしている source:

- News: `coindesk_rss`, `sec_press_releases_rss`, `federal_reserve_press_releases_rss`
- SNS: `reddit_subreddit_new_json`, `youtube_channel_rss`, `hacker_news_public_api`

## Invariants

- `simulate` は外部 API の raw データや external signal の raw 入力を直接受けない
- external signal の raw payload は保存しない
- collector / adapter / normalize / save / observe の責務分離を崩さない
- source 固有差分は adapter と `source_specific` へ寄せ、共通 schema に無理に押し込まない
- integrated observer は共通 summary 項目と `source_specific` の有無だけに依存する
- 互換維持のために source 固有項目がトップレベルに残っていても、observer 側の新規依存先にしない
- テストは外部ネットワークへ依存せず、固定 payload と関数差し替えで確認する

## Summary Schema Boundary

共通 summary 項目の中心:

- `signal_type`
- `source`
- `run_id`
- `started_at`
- `ended_at`
- `status`
- `fetched_item_count`
- `normalized_success_count`
- `validation_failure_count`
- `saved_record_count`
- `duplicate_count`
- `warnings`
- `errors`
- `saved_paths`
- `topic_distribution`
- `symbol_distribution`
- `source_specific`

方針:

- 共通項目はトップレベルで読む
- source 固有項目は `source_specific` を第一の置き場にする
- 既存互換のためにトップレベルへ残っている source 固有項目は、削除よりも「新規依存しない」を優先する

## Testing Baseline

- 標準環境は Ubuntu / WSL
- Python は `python3`
- 仮想環境は `.venv`
- テスト実行は `.venv/bin/python3 -m pytest` を優先する

external signal 周辺テストの考え方:

- collector テスト: collector run、保存物、observation を確認する
- input / normalize テスト: schema 準拠と境界値を確認する
- integrated observer テスト: collector 実装詳細ではなく summary 共通項目だけを確認する

## Near-term Extension Areas

- external signal の feature 化レイヤ追加
- simulate へ外部シグナルを統合する前段処理
- cross-source dedup
- scheduler
- data retention / accumulation strategy
- topic / symbol 推定の高度化

## Do Not Break

- `simulate` の入力境界
- external signal の raw 非保存方針
- integrated observer の「共通項目のみ依存」
- `source_specific` を使った source 差分の隔離
- `.venv/bin/python3 -m pytest` で再現できるテスト運用

## Session Handoff

### 現在の全体状況（要約）

- 事実:
  - external signal 統合後の標準比較セットは確定済みで、戦略改善フェーズに入っている
  - このセッションでは `matching_baseline` を起点に、次に触るべき改善ポイントを調査した
  - 実装・設定変更・テスト変更は行わず、計画と判断材料の整理だけを実施した
- 方針:
  - 目的は `matching_baseline` を前提に、次の 1 手を `exit / entry 精度 / 補助シグナル` のどれに置くかを確定すること
  - 現在位置は「改善対象の優先順位を絞り、最小実装案を決めた段階」

### 現在の構造・前提（確定事項）

- 事実:
  - `simulate` は `returns`、`entry_signals`、`exit_signals` を受ける純粋な評価器として維持する
  - trading path は `OHLCV -> returns -> signals -> simulate -> comparison / replay / live decision`
  - external signal path は `fetch -> adapter -> normalize -> save -> observe`
  - external signal の real-data comparison は標準 8 ケースを前提とする
  - 現在の主戦略候補は `matching_baseline` で、`weighted_matching_signal_count` + `entry_count_threshold=1.4`
  - weight は最適化対象ではなく、threshold 境界付近の観測対象として扱う
- 制約:
  - `simulate` の入出力契約を変えない
  - I/O とロジックを混ぜない
  - external signal の責務分離を壊さない
  - timeline / consumption_features / matching / blended / observability の責務境界を崩さない
  - 複数変更を同時に入れず、まずは 1 箇所だけ改善する

### 進行中の内容

- 事実:
  - `matching_baseline` 周辺のロジック、比較 config、関連テスト、sample 結果の確認は完了した
  - `matching_baseline`、`matching_low`、`matching_high` の差分は entry ではなく exit index に強く表れていることを確認した
  - 現 sample では `matching_baseline` の `weighted_matching_signal_count` は `[0.0, 3.0, 2.1, 1.2, 0.6]` で減衰し、`entry_count_threshold=1.4` に対して exit が早く発生している
- 方針:
  - 次は exit 改善を最小差分で比較する案を具体化する
  - 第一候補は `exit_after_inactive_periods` を使った保有期間制御の比較

### 重要な整理事項

- 事実:
  - 標準比較セットは以下の 8 ケースで固定している
  - `matching_low`
  - `matching_baseline`
  - `matching_high`
  - `blended_s07_t03_low`
  - `blended_s07_t03_baseline`
  - `blended_s05_t05_low`
  - `blended_s05_t05_baseline`
  - `blended_s03_t07_baseline`
  - 現 sample では threshold が主因で、weight は threshold 境界付近でのみ効く
  - blended は主戦略ではまだ弱いが、比較対象として残す価値がある
- 注意点:
  - `matching_baseline` は比較上の主戦略候補であり、ロジック既定値ではない
  - 今回の調査結果は current sample 依存の部分があるため、一般化は未確定
  - 推測:
    - 別 sample でも同じ exit ボトルネックが再現する可能性は高いが、まだ十分な sample 数ではない

### スコープ管理

- 今やること:
  - `matching_baseline` を維持したまま、exit だけを改善する最小案を比較できる状態にする
  - 保有期間の制御が結果に与える影響を、既存比較と同じ見方で検証する
- 今はやらないこと:
  - weight 探索
  - 大規模リファクタ
  - `simulate` 契約変更
  - 複数の改善点を同時に入れること
  - 補助シグナル追加を先行させること

### 次セッションでのタスク候補

- 最も自然に進む次の作業:
  - exit 改善案を 1 つだけ選び、最小比較ケースとして実装する
  - 第一候補は `exit_after_inactive_periods=2` 相当の exit persistence を `matching_baseline` 比較に追加すること
- 他に考えられる選択肢:
  - entry 精度向上案を比較対象として設計だけ先に切る
  - sample を 1 本追加して、exit ボトルネック仮説の再現性を先に確認する

### 未確定事項 / 論点

- 未確定:
  - exit 改善を `exit_after_inactive_periods` のみで行うか、別の利確 / 損切り / 時間制限へ広げるか
  - current sample の exit ボトルネックが追加 sample でも再現するか
  - entry 精度改善を exit 改善の次にやるか、sample 拡張を先にやるか
- 論点:
  - 保有期間を 1 本伸ばすだけで十分か
  - price-based exit を external signal manual layer に持ち込まずに比較可能な形へ落とせるか

### リスク / 懸念

- 事実:
  - 現 sample は 1 run summary に依存するため、過学習的な判断になりやすい
  - exit を緩めると、別 sample では損失の引き延ばしになる可能性がある
- 推測:
  - entry 精度改善や補助シグナル導入を先に始めると、threshold 主因という現在の整理を崩して論点が散る可能性が高い
  - price-based exit を早く入れすぎると、external signal layer と strategy logic の責務が混線しやすい
