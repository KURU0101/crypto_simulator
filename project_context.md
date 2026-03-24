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
  - 現在は、market data reuse 導線、単一 case runner、複数 period × 複数 case batch runner までが実装済みの段階である
  - batch runner は `1 period × 1 case = 1 row` で CSV を出力し、最小 JSON summary も返す
  - 直近で行っていたことは、次の正式タスク 2 件だけにスコープを絞った実装・実行計画の整理である
  - 正式タスクは「1. 今の runner で本当に大量ケースを回せるようにする」「2. 結果テーブルだけ DB 化する」の 2 件に限定されている
- 方針:
  - 目的に対する現在位置は「最小 batch runner は動くが、大量ケースを安全に流す実行入口と、結果 DB 保存はまだ未実装」という段階である
  - 次の実作業は、未定義タスクを増やさず、上記 2 件だけに集中する
- 推測:
  - 推測として、次のセッションでは batch runner を period 単位 / case チャンク単位の逐次処理へ寄せ、結果保存を DB 主体に切り替えるのが自然である

### 現在の構造・前提（確定事項）

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
  - OHLCV artifact と market data shared truth の全面再設計は今回の正式タスク外である
  - 今回 DB 化するのは結果だけである
  - `period × case` の全件を一括でメモリ展開してはいけない
  - 一度にメモリへ載せる単位を明示し、結果は逐次保存する必要がある

### 進行中の内容

- 事実:
  - 進行中の内容は、正式タスク 2 件についての実装・実行計画整理までであり、まだ実装には着手していない
  - ステップ1は「今の runner で大量ケースを回せるようにする」ことで、period ごとの market data 解決と returns 共有は維持しつつ、全件メモリ展開を避ける実行入口が必要である
  - ステップ2は「結果テーブルだけ DB 化する」ことで、run 単位メタ情報と `1 period × 1 case` 結果行を SQLite へ逐次保存する想定である
- 完了:
  - 完了しているのは計画整理までである
- 次にやる予定:
  - 次はステップ1の実装として、batch 実行の入力展開と保存を period 単位 / case チャンク単位へ寄せる
  - その後にステップ2として、結果 DB を追加し、CSV と DB の関係を整理する

### 重要な整理事項

- 事実:
  - 最近整理された最重要ポイントは「正式タスクを 2 件に限定し、それ以外を勝手にタスク化しない」方針である
  - `evaluation_runner` は単発 runner として残すが、大量実行では market data 解決まで含めて period × case 回数だけ呼ばない前提である
  - 大量実行では `evaluation_runner` から切り出した case 実行 helper だけを再利用する想定である
  - returns は同一 period 内で 1 回だけ生成し、case ごとに再生成しない
  - batch CSV の必須カラムには `returns_count` と `price_basis` を含める前提で整理済みである
- 注意点:
  - 誤解されやすい点として、今の batch runner が「動く」ことと、「大量ケースを安全に回せる」ことは別である
  - もう 1 つの注意点として、今回 DB 化の対象は結果だけであり、OHLCV artifact や market data shared truth を DB へ寄せる話ではない
- 不明:
  - 不明な点は、最終的に CSV を副出力として残すか、DB 主体に切り替えるかの細部実装順である

### スコープ管理

- 今やること:
  - 正式タスク 1: runner を大量ケース向けに寄せる
  - 正式タスク 2: 結果テーブルだけ DB 化する
  - period ごとに market data を 1 回だけ解決し、returns を 1 回だけ生成する構造を守る
  - 結果を逐次保存し、途中失敗でも途中成果を残す
- 今はやらないこと:
  - OHLCV artifact の全面 DB 化
  - market data shared truth の再設計
  - research_manifest との全面統合
  - 並列化の本格導入
  - acquisition key 同時実行制御の完成
  - schema_version 運用ルールの完成
  - 戦略改善
  - パラメータ最適化

### 次セッションでのタスク候補

- 最も自然に進む次の作業:
  - ステップ1として、全件一括メモリ展開を避ける batch 実行入口を実装する
  - 具体的には、period を逐次処理し、period 内 case をチャンクで流し、結果を逐次保存する
- 他に考えられる選択肢:
  - ステップ2を先に着手して結果 DB だけを先に作る選択肢はある
- 推測:
  - 推測として、先にステップ1を実装して保存単位を安定させてから、ステップ2で DB を主保存へ切り替える方が変更範囲を抑えやすい

### 未確定事項 / 論点

- 未確定:
  - 一度にメモリへ載せる case チャンクサイズを固定値にするか設定値にするかは未確定である
  - CSV を主保存に残すか、DB を主保存にして CSV を副出力にするかの最終方針は未確定である
  - result テーブルの一意性を `run_id + period_id + case_name` にするか、別の case 識別子を導入するかは未確定である
- 論点:
  - batch 実行の入力を `periods.csv + cases/grids` へどこまで自然接続させるか
  - 再実行時に新しい `run_id` で積み増すだけにするか、部分再開を考慮するか

### リスク / 懸念

- 事実:
  - 大量ケースを流す段階では、全件を先に巨大配列化するとメモリ制約を破る可能性がある
  - 今の batch runner は小中規模の逐次実行には使えるが、正式に「大量ケース向け」と言い切るには入力展開と逐次保存の強化が必要である
- 懸念:
  - orchestration が肥大化すると責務が崩れやすい
  - DB と CSV の二重保存が複雑化すると保守が重くなる
  - 再実行時の run 管理を曖昧にすると分析結果の切り分けが難しくなる
- 推測:
  - 推測として、period 単位 + case チャンク単位へ処理粒度を固定すれば、メモリ制約と途中保存の両立はしやすい
