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

### Current responsibility boundary

- timeline:
  - `external_signal_features` が返す `feature_timeline`
  - 正式責務は基礎系列のみ
  - 現在の `series` は `symbol_signal_count`, `topic_signal_count`, `weighted_symbol_signal_count`, `weighted_topic_signal_count`
  - matching 系列や activity 系列は持たない
- consumption_features:
  - `external_signal_consumption_features` が返す消費前処理結果
  - matching 系列の正式参照先
  - 現在の正式な派生系列は `matching_signal_count`, `weighted_matching_signal_count`, `matching_run_count`, `weighted_matching_run_count`, `has_activity`, `has_weighted_activity`
  - signal 判定はここを読む
- observability:
  - `adjustments.applied_runs`, `raw_contribution`, `period_contributions` などの説明用ログ
  - matching 関連の説明値はここに残してよい
  - timeline `series` の一部ではない

### External signal consumption stage status

- Stage 1 完了:
  - `timeline -> consumption_features -> signals` の流れを導入
  - consumption_features 側で matching を再生成可能にした
- Stage 2 完了:
  - matching 派生の正式参照先を `external_signal_consumption_features.series` に移行
  - timeline 側の matching 派生を一時隔離した
- Stage 3 完了:
  - timeline から matching 派生の移行層を完全削除
  - timeline の責務を基礎系列中心で確定
  - matching 派生は consumption_features 側に一本化
- 次は Stage 4 を検討する段階:
  - 合成導入が主タスク

### Matching status

- matching 系は timeline から除去済み
- matching 系の正式参照先は `external_signal_consumption_features.series`
- timeline から消した対象:
  - `matching_signal_count`
  - `weighted_matching_signal_count`
  - `matching_run_count`
  - `weighted_matching_run_count`
  - `has_activity`
  - `has_weighted_activity`
- signal 判定と real-data 導線は consumption_features ベースで動作済み

### Next task candidates

- 主タスクは合成導入
- 具体的には、基礎系列をどう消費用にまとめるかを `consumption_features` 側で扱う設計を進める
- まずは matching の延長ではなく、合成仕様の明文化と比較可能性の設計が必要

### Not doing now

- DSL
- 複数条件評価器
- source別本格分岐
- `simulate` 側変更

### Questions for next session

- 合成仕様:
  - symbol / topic / run_count / weighted 系列をどう合成するか
- matching をどう扱うか:
  - matching を今後も単純加算の基準系列として残すか
  - あるいは比較用の 1 つの派生系列として扱うか
- どこまで比較可能にするか:
  - 単一合成系列だけ比較するのか
  - 複数候補合成を並べて比較できるようにするのか

### Implementation notes

- timeline は feature timeline、consumption_features は消費用派生系列、observability は説明用ログ、という境界を維持する
- matching 系の run count は timeline から直接持たず、consumption_features 側で `applied_runs` から再構成している
- observability の matching 関連値は残しているため、説明可能性は維持されている
