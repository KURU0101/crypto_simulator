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
  - external signal consumption 設計は、単体テスト中心の段階を超えて、real-data comparison で通し比較できる段階に入っている
  - `timeline -> consumption_features -> signals -> real-data comparison` の導線は稼働済み
  - `weighted_matching_signal_count` と `blended_weighted_signal_count` の比較を 12 ケースで実行できる sample config まで入っている
- 事実:
  - 直近で行っていたことは、`consumption series`、`blended_weights`、`entry_count_threshold` の差を real-data comparison で読める状態にすること
  - comparison summary に external signal 比較用メタデータを追加し、12 ケース config と sample summary を整備した
- 方針:
  - 現在位置は「consumption_features 設計を実験に乗せて、傾向観察を始めた段階」
  - まだ consumption logic 自体の高度化には進まず、比較結果を見ながら次の設計判断をする位置にいる

### 現在の構造・前提（確定事項）

- 事実:
  - `feature_timeline.series` の正式責務は基礎系列のみ
  - 現在の基礎系列は `symbol_signal_count`, `topic_signal_count`, `weighted_symbol_signal_count`, `weighted_topic_signal_count`
- 事実:
  - `external_signal_consumption_features.series` が消費用派生系列の正式参照先
  - matching 系は `matching_signal_count`, `weighted_matching_signal_count`, `matching_run_count`, `weighted_matching_run_count`, `has_activity`, `has_weighted_activity`
  - blended 系は `blended_weighted_signal_count`
- 事実:
  - signal 判定の候補系列は 2 つだけ
  - `weighted_matching_signal_count`
  - `blended_weighted_signal_count`
  - デフォルトは `weighted_matching_signal_count`
- 事実:
  - `blended_weighted_signal_count = weighted_symbol_signal_count * symbol_weight + weighted_topic_signal_count * topic_weight`
  - `blended_weights` は case ごとに `external_signal.blended_weights.symbol/topic` で指定可能
  - 未指定または不正値は `0.7 / 0.3` にフォールバックする
  - 正規化はしていない。正の数値はそのまま使う
- 事実:
  - comparison summary には external signal 比較用メタデータを載せている
  - `external_signal.consumption_series_name`
  - `external_signal.entry_count_threshold`
  - `external_signal.blended_weights`（指定時）
  - `external_signal.blended_definition`
  - `signal_summary.entry_signal_count`, `exit_signal_count`, index, timestamp
- 制約:
  - timeline に matching/blended を逆流させない
  - matching の意味は変更しない
  - signal 判定の候補系列を 2 択以上へ一般化しない
  - `simulate` 側は変更しない

### 進行中の内容

- 事実:
  - 12 ケース比較 sample は実装・テスト・通し実行まで完了している
  - config は `config/real_data_external_signal_series_comparison.example.json`
  - sample summary は `data/external_signal_compare/.../summary.json`
- 事実:
  - 12 ケースの内訳は以下
  - matching 3 ケース: `low`, `baseline`, `high`
  - blended 9 ケース: weight 3 パターン (`0.7/0.3`, `0.5/0.5`, `0.3/0.7`) x threshold 3 パターン
- 事実:
  - threshold は現在 `1.0 / 1.4 / 2.2` を使用している
  - この sample では差が出る値として採用済み
- 方針:
  - 次にやる自然な作業は、この 12 ケース比較結果を前提に、どの consumption series / weight / threshold 帯を次の標準候補にするかを整理すること

### 重要な整理事項

- 事実:
  - `_coerce_consumption_features()` は、custom blended を持つ `consumption_features` を再構築で潰さない順序に修正済み
  - これを崩すと custom blended 比較が silently default に戻る
- 事実:
  - comparison summary の external signal メタデータは case 由来であり、新しい strategy framework ではない
  - `run_comparisons()` の骨格は維持したまま、summary に補助情報を足しているだけ
- 注意点:
  - sample summary は `2024-01-01T01:30:00Z` 終了の 1 run で、`BTCUSDT:1`, `policy:2` の分布を持つ
  - return timestamps との位置関係で `2024-01-01T02:00:00Z` から signal が立つ前提になっている
- 注意点:
  - current sample では一部ケースの `final_value` が同じでも、保有期間や exit timestamp は異なる
  - final だけでなく `signal_summary` と `periods_in_position` も見る必要がある

### スコープ管理

- 今やること:
  - 12 ケース比較結果の解釈を固める
  - matching と blended のどちらを次段で主比較軸に置くかを検討する
  - blended weight の探索範囲をこのまま固定値比較で広げるか、ここで止めるかを判断する
- 今はやらないこと:
  - consumption logic の新規高度化
  - source 別分岐
  - 複数条件評価
  - DSL 化
  - aggregation 見直し
  - `simulate` 側変更
  - comparison framework の大規模改造

### 次セッションでのタスク候補

- 最も自然な次の作業:
  - 12 ケース結果を踏まえて、次に固定したい標準比較セットを決める
  - 具体的には「matching を基準系列として残し続けるか」「blended のどの weight を主候補にするか」「threshold をどの帯で見るか」を整理する
- 他に考えられる選択肢:
  - 既存 12 ケースを保ったまま、別 sample summary を 1 本追加して感度の再現性を見る
  - comparison 出力の並び替えや圧縮表示だけを少し整えて、比較読み取りをしやすくする

### 未確定事項 / 論点

- 未確定:
  - 次段で正式に比較対象として押すべき consumption series が matching か blended か
- 未確定:
  - blended weight の初期推奨値を `0.7/0.3`, `0.5/0.5`, `0.3/0.7` のどこに置くか
- 未確定:
  - threshold の低/中/高を今の `1.0 / 1.4 / 2.2` で維持するか、sample 追加後に再調整するか
- 推測:
  - もし次に比較ケースを増やすなら、weight より先に sample を増やした方が過学習を避けやすい可能性がある

### リスク / 懸念

- 事実:
  - 現在の比較は sample 1 本だけなので、weight や threshold の良し悪しを一般化するにはまだ弱い
- 懸念:
  - blended weight と threshold を同時に広げすぎると、比較軸が増えて interpretation が先に破綻する
- 懸念:
  - comparison summary に補助情報を足し続けると、summary が肥大化しやすい
  - 今は最小限だが、次も増やすなら整理方針を意識した方がよい
- 懸念:
  - custom blended を扱う都合で `consumption_features` の再構築境界は少し繊細になっている
  - 将来ここを雑に触ると、比較結果が silently 変わるリスクがある
