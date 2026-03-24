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

### 今回採用した標準比較セット

- matching:
  - `matching_low`
  - `matching_baseline`
  - `matching_high`
- blended:
  - `blended_s07_t03_low`
  - `blended_s07_t03_baseline`
  - `blended_s05_t05_low`
  - `blended_s05_t05_baseline`
  - `blended_s03_t07_baseline`

### この 8 ケースを残した理由

- 事実:
  - current sample では threshold が主因で、weight は threshold 境界付近でだけ効いた
  - matching は `1.0 / 1.4 / 2.2` の全帯で entry し、blended は high threshold で no-trade に寄った
- matching を 3 ケース残す理由:
  - threshold 感度を low / baseline / high で継続監視するため
  - `matching_baseline` を第一候補に据えても、`1.0` と `2.2` を消すと threshold 主因の監視が弱くなるため
- blended を 5 ケースに絞る理由:
  - 主戦略ではないが、threshold 境界付近で weight 差が効く比較対象としては残す価値があるため
  - `0.7/0.3`, `0.5/0.5`, `0.3/0.7` を low / baseline 帯で最低限追える構成に絞ると、比較軸を増やしすぎずに weight 差を観測できるため
- 外したケース:
  - `blended_s07_t03_high`
  - `blended_s05_t05_high`
  - `blended_s03_t07_low`
  - `blended_s03_t07_high`
- 外した理由:
  - blended high 群は current sample で no-trade 側に寄りやすく、標準セットで優先監視する意味が薄い
  - `blended_s03_t07_low` は weight の広がりとしては読めるが、標準セットでは low / baseline の両帯を全 weight で持つ必要はなく、baseline 側の比較価値を優先した

### 現時点の位置づけ

- `matching_baseline`:
  - `weighted_matching_signal_count` + `entry_count_threshold=1.4`
  - 現時点の第一候補
  - ただしロジック既定値ではなく、比較上の主戦略候補
- blended:
  - 主軸ではない
  - threshold 境界付近で weight が効くかを観測する比較対象
- weight:
  - 最適化対象ではない
  - 比較観測対象として保持する

### 今回ロジック本体を変更しなかった理由

- sample 数がまだ少なく、series や threshold の優先順位は比較で見る段階だから
- `simulate` の純粋性、timeline と consumption_features の責務分離、observability 境界を崩す必要がないから
- 今回の目的は「標準比較セットの整理」であり、signal 計算ロジックを書き換える段階ではないから

### 今回反映した最小変更

- `config/real_data_external_signal_series_comparison.example.json` を 8 ケース標準セットに整理
- matching 3 ケースも `consumption_series_name` を明示し、series / threshold / weight の見え方を揃えた
- docs に以下を反映:
  - `matching_baseline` が第一候補
  - ただし既定値固定ではない
  - blended は比較対象として残す
  - blended high 群は標準セットから外す
  - weight は最適化ではなく観測対象
- tests は config 解釈、case metadata、no-trade summary 形状を確認する最小追加に留めた

### 次に進むなら何を検証するべきか

- sample を 1 本追加して、`matching_baseline` を第一候補とする判断が再現するか
- low / baseline 帯で残した blended 5 ケースが、別 sample でも比較対象として有効か
- standard 8 ケースのままで十分か、それとも full comparison 用の別 config を追加すべきか
