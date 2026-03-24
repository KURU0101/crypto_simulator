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
  - 現在は「研究用の実行基盤を固める前段」であり、本格的な外部取得・simulation 実行・comparison 実行にはまだ入っていない
  - 直近では `matching_baseline_exit_relaxed` の最小改善を入れた後、複数期間 × 複数パラメータ検証に向けた dry-run 基盤を段階的に実装していた
  - 現在の主成果は `periods.csv` / `grids.csv` から run directory、`manifest.csv`、`results_index.csv`、`acquisition_manifest.csv`、`case_acquisition_links.csv`、`unresolved_acquisitions.csv` を生成できること
  - 共有 cache metadata 実体は `var/cache/external_signals/cache_metadata.csv` に固定され、run 側はその snapshot を保持する構造まで完了している
- 方針:
  - 目的に対する現在位置は「取得前の最終 dry-run レイヤをほぼ固めた段階」
  - 次の自然な段階は、shared cache metadata を使って acquisition 1件を claim / 完了 / 失敗へ更新する取得前提の最小フローを実装すること
- 推測:
  - 取得本体に入る前に、shared metadata の排他や stale `running` 回収方針を決める必要が高い

### 現在の構造・前提（確定事項）

- 事実:
  - `simulate` は `returns`、`entry_signals`、`exit_signals` を受ける純粋な評価器として維持する
  - trading path は `OHLCV -> returns -> signals -> simulate -> comparison / replay / live decision`
  - external signal path は `fetch -> adapter -> normalize -> save -> observe`
  - 研究用の新規実装は `src/trade_simulator/research_manifest.py` とその CLI に閉じ、既存 CLI の置き換えにはしない
  - `period_signature`、`grid_signature`、`case_signature` は役割分離済みで、`note` や `enabled` など非本質項目は signature から除外する
  - CSV null 仕様は固定済み
  - 空欄は `null`
  - 数値 `0` はゼロ値
  - 文字列 `"null"` は禁止
  - 必須数値列の空欄は validation error
  - optional 数値列の空欄は `null`
  - `results_index.csv` の status は `pending`, `running`, `completed`, `failed` に固定済み
  - `error_code` は `validation_error`, `runtime_error`, `internal_error` と空欄だけを許容する
  - acquisition 単位は `source_family × symbol × period_signature` をベースに `cache_key` を作る
  - `source_family` の現行 allowed values は `news`, `sns`
  - shared cache metadata の保存先は `var/cache/external_signals/cache_metadata.csv` に固定済み
  - run directory 側の `cache_metadata.csv` は shared metadata の snapshot であり、再利用の実体ではない
- 制約:
  - `simulate` の入出力契約を変えない
  - I/O とロジックを混ぜない
  - external signal の責務分離を壊さない
  - 研究用 dry-run 基盤を comparison / feature / simulate 層へ侵食させない
  - まだ外部取得本体、cache 本体保存、bundle 生成、simulation 実行、comparison 実行、並列取得は行わない

### 進行中の内容

- 事実:
  - dry-run manifest generator は実装済みで、`periods.csv` と `grids.csv` から run directory 一式を出力できる
  - `acquisition_manifest.csv` は `source_family × symbol × period` 単位で生成済み
  - `case_acquisition_links.csv` により case と acquisition の依存が分離済み
  - `cache_metadata.csv` の schema は固定済みで、shared metadata repository の `load / validate / find / upsert / status update / save` が実装済み
  - acquisition 状態遷移は `pending -> running -> completed|failed` のみ許容し、それ以外はエラーに固定済み
  - `unresolved_acquisitions.csv` は shared metadata を参照して生成される
- 方針:
  - 次は shared metadata を使った acquisition 1件の最小 claim/update フロー、または取得前の CLI 導線追加が候補
  - `running` は unresolved から除外する前提なので、今後は stale `running` の扱いを決める必要がある
- 未確定:
  - `running` の TTL や回収条件
  - 共有 metadata 更新時のロック方針
  - 取得失敗後の retry 方針

### 重要な整理事項

- 事実:
  - `matching_baseline_exit_relaxed` は sample 上で baseline より改善したが、一般化検証はまだ未着手
  - 現在の開発重心は strategy 改善そのものではなく、複数期間 × 複数パラメータ検証を安全に回すための研究用基盤整備に移っている
  - `project_context.md` の前回 handoff は古い strategy planning 段階の記述だったため、今回更新が必要になった
  - `cache_key` は `source_family + symbol + period_signature + input_schema_version + cache_key_version` を元に生成する first usable version で固定済み
  - shared metadata と run snapshot の役割分離は完了している
- 注意点:
  - `run_dir/cache_metadata.csv` を shared metadata の実体と誤解しないこと
  - `unresolved_acquisitions.csv` は shared metadata snapshot を見て作る run 固有の判断結果であり、shared 実体ではない
  - `running` は未完了ではあるが、unresolved には含めない
  - `pending` と `failed` と不存在だけが unresolved に残る
- 不明:
  - 今後 shared metadata を run ごとにロックするのか、acquisition 単位でロックするのかは未実装

### スコープ管理

- 今やること:
  - shared cache metadata を前提に acquisition 1件の最小更新フローへ進める
  - 取得前提の state machine と snapshot の整合を壊さないように保つ
  - 研究用 dry-run 基盤の仕様を先に固める
- 今はやらないこと:
  - 外部 API 取得本体
  - cache 本体データ保存
  - bundle 生成
  - simulate 実行
  - comparison 実行
  - summary 集計
  - 並列取得
  - retry 実装
  - strategy 改善の追加実装を再開すること

### 次セッションでのタスク候補

- 最も自然に進む次の作業:
  - acquisition 1件に対して shared cache metadata を `pending -> running -> completed|failed` へ更新する取得前処理の最小導線を CLI 付きで追加する
  - 更新後の shared metadata を見て、新しい run が unresolved を再計算できることを通しで確認する
- 他に考えられる選択肢:
  - shared metadata の lock file 方針だけ先に決める
  - stale `running` 回収や手動解除コマンドの設計から入る
  - 推測:
    - acquisition claim 用の小さな CLI を先に作る方が、取得本体より先に状態遷移の破綻を検出しやすい

### 未確定事項 / 論点

- 未確定:
  - shared metadata 更新時の排他方式
  - stale `running` の定義と回収手段
  - `failed` を次 run で自動再取得対象にするだけで十分か
  - acquisition 実行ログを shared metadata と分けるか同一 run 内で持つか
- 論点:
  - shared metadata の更新 API を CLI 中心にするか、関数呼び出し中心にするか
  - `pending -> completed` を今後も禁止し続けるか
  - `running` を unresolved から除外する現在ルールに TTL を組み合わせるか

### リスク / 懸念

- 事実:
  - shared metadata は現在 CSV 全体読み書きの最小実装であり、並列更新には未対応
  - `running` を unresolved から除外したため、異常終了時に stale 状態が残ると取得が止まる可能性がある
  - run snapshot と shared 実体の差分が大きくなると、後から見たときに「なぜ unresolved だったか」を見誤りやすい
- 推測:
  - 取得本体を先に作るより、lock と stale `running` 対策を先に決めないと将来の再実行で詰まりやすい
  - strategy 改善タスクへ早く戻りすぎると、研究用実行基盤の土台が中途半端なままになり、複数期間検証で手戻りが増える
