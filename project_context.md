# Project Context

## Purpose

このリポジトリは、トレード戦略の検証を安全に反復するための個人用研究基盤です。
中心は `simulate` によるバックテストであり、実データ入力、疑似リアルタイム再生、外部シグナル入力、統合観測はその周辺レイヤとして整理しています。

## Current Structure

- `simulate`: `returns`、`entry_signals`、`exit_signals` を受けて損益推移を計算する最小コア
- comparison / real data pipeline: OHLCV から returns を作り、strategy ごとの差分を比較する導線
- evaluation runners: 単一 case 実行と複数 case 実行を行う外側の orchestration 層
- pseudo realtime replay / live decision runner: OHLCV 系データを逐次評価する外側レイヤ
- external signal inputs: SNS / News を正規化済みシグナルとして受け取り、保存と観測までを行う層
- integrated observer: 保存済み external signal summary を横断して読む読み取り専用層
- result artifacts: 評価結果を表形式で保存し、後分析へ渡すための出力層

## Data Flow

### Trading path

`OHLCV -> returns -> signals -> simulate -> comparison / evaluation / replay / live decision`

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
- `simulate` と comparison は、実行 orchestration や永続化の責務を持たない
- external signal の raw payload は保存しない
- collector / adapter / normalize / save / observe の責務分離を崩さない
- source 固有差分は adapter と `source_specific` へ寄せ、共通 schema に無理に押し込まない
- integrated observer は共通 summary 項目と `source_specific` の有無だけに依存する
- 互換維持のために source 固有項目がトップレベルに残っていても、observer 側の新規依存先にしない
- テストは外部ネットワークへ依存せず、固定 payload と関数差し替えで確認する
- 市場データの再利用と評価結果の保存は、ロジック本体とは分離した外側レイヤで扱う

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

- 評価結果保存の改善
- 大量ケース実行の orchestration 改善
- external signal の feature 化レイヤ追加
- simulate へ外部シグナルを統合する前段処理
- cross-source dedup
- scheduler
- data retention / accumulation strategy
- topic / symbol 推定の高度化

## Do Not Break

- `simulate` の入力境界
- comparison / orchestration / 保存の責務分離
- external signal の raw 非保存方針
- integrated observer の「共通項目のみ依存」
- `source_specific` を使った source 差分の隔離
- `.venv/bin/python3 -m pytest` で再現できるテスト運用

## Session Handoff

### 現在の全体状況（要約）

- 事実:
  - 現在は、market data reuse 導線、単一 case runner、複数 period × 複数 case batch runner までが実装済みの段階である
  - batch runner は `1 period × 1 case = 1 row` で CSV を出力し、最小 JSON summary も返す
- 方針:
  - 現在進行中の公式タスク、実行計画、リスク、未確定事項の主記録場所は `task.md` とする

### 構造・前提の引継ぎ

- 事実:
  - `simulate` は純粋関数であり、`returns`、`entry_signals`、`exit_signals` を受ける
  - comparison の責務は case 実行と summary 生成に限定し、I/O、fetch、cache、保存は持たせない
  - market data reuse は external signal 系と分離した別 DB を runtime truth として使う
  - market data の primary artifact は normalized OHLCV CSV であり、returns は primary artifact ではない
  - completed 更新条件は「OHLCV CSV 保存成功」「保存済み CSV 再読込成功」「最小妥当性確認成功」の 3 条件である
  - 単一 case runner は、保存済みまたは reuse された OHLCV から returns を生成し、comparison の既存責務だけを使って end-to-end 評価する
  - batch runner は、period ごとに market data 解決を 1 回、returns 生成を 1 回だけ行い、その returns を同一 period 配下の複数 case で共有する
  - batch CSV の粒度は `1 period × 1 case` に固定済みである
  - period 失敗時は、その period 配下の全 case に failed row を出し、他 period は続行する
  - 1 case 失敗では全体停止せず、failed row を保存して続行する
- 制約:
  - comparison / simulate の責務を増やしてはいけない
  - runtime truth と market data reuse の既存方針を崩してはいけない
  - 結果保存の改善を行っても、OHLCV artifact と market data shared truth の全面再設計には踏み込まない
  - `period × case` の全件を一括でメモリ展開してはいけない
  - 一度にメモリへ載せる単位を明示し、結果は逐次保存する必要がある
