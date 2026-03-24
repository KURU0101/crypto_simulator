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
  - 現在は、研究用実行基盤の `A2 / B2 / C3` 最小実装に続く shared state 周辺リファクタリングが完了した段階である
  - A2 により shared truth は `var/cache/external_signals/shared_state.sqlite3` に移行済みである
  - B2 により lease / heartbeat / stale reclaim / 1回限定 auto retry を含む shared state 操作が実装済みである
  - C3 により、run snapshot は監査・再現用、実行判断は最新 shared truth 優先という境界がコード上で成立している
  - 直近では `src/trade_simulator/research_manifest.py` の shared state 周辺を整理し、旧 shared CSV helper 群の不要コード削除、shared state 更新 API の責務整理、`updated_at` と heartbeat/lease の意味整理を行った
- 方針:
  - 目的に対する現在位置は「shared state の責務境界と単一 acquisition 実行導線の最小骨格が揃い、周辺の曖昧さを一度解消した段階」である
  - 次の自然な段階は、fetch stub を source family 別の実取得境界へ差し替え、run 実行記録を必要最小限で残すことである
- 推測:
  - 次に複数 acquisition の batch 実行へ進む前に、単一 acquisition の実取得責務と run 側記録責務をもう一段明確にする可能性が高い

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
  - shared truth の保存先は `var/cache/external_signals/shared_state.sqlite3` に固定済みである
  - `shared_cache_entries` は `shared_state_v2` schema で、lease / heartbeat / retry 列を持つ
  - `updated_at` は shared truth の行更新時刻であり、stale 判定そのものには使わない
  - stale 判定の主軸は `lease_expires_at` であり、heartbeat の最新時刻は `last_heartbeat_at` で表す
  - run directory 側の `cache_metadata.csv` は shared truth の run-start snapshot であり、再利用の実体ではない
  - `unresolved_acquisitions.csv` は run-start 時点の判定記録であり、実行直前の claim 可否判断には使わない
  - `orchestrate_research_acquisition()` は `decision_source="shared_truth"` 以外を拒否し、shared truth を再確認してから claim を試みる
  - `claim / heartbeat / complete / fail` が shared state の正規の状態遷移入口であり、曖昧な汎用 status 更新 API は削除済みである
  - `cache_metadata.csv` は snapshot 出力としてのみ残し、旧 shared CSV を truth として更新する helper は削除済みである
  - stale 判定は `lease_expires_at < now` のときだけ成立する
  - `failed` は原則 stop であり、`retryable=1` かつ `auto_retry_count=0` の場合のみ 1回だけ自動再 claim できる
- 制約:
  - `simulate` の入出力契約を変えない
  - I/O とロジックを混ぜない
  - external signal の責務分離を壊さない
  - 研究用 dry-run 基盤を comparison / feature / simulate 層へ侵食させない
  - run snapshot と shared truth の境界を壊さない
  - claim / skip / retry / stale reclaim の判断を run snapshot ではなく shared truth で行う
  - まだ外部取得本体の本格実装、cache 本体保存、bundle 生成、simulation 実行、comparison 実行、並列取得は行わない

### 進行中の内容

- 事実:
  - dry-run manifest generator は実装済みで、`periods.csv` と `grids.csv` から run directory 一式を出力できる
  - `acquisition_manifest.csv` は `source_family × symbol × period` 単位で生成済みである
  - `case_acquisition_links.csv` により case と acquisition の依存が分離済みである
  - shared state repository には `claim / heartbeat / complete / fail / stale reclaim` が実装済みである
  - `generate_research_manifest_run()` は SQLite shared truth を読み、`run_dir/cache_metadata.csv` と `unresolved_acquisitions.csv` を snapshot として出力する
  - `orchestrate_research_acquisition()` は run directory から acquisition identity を取り、shared truth を再確認して claim / skip / completed / failed を処理する
  - shared state 周辺リファクタは完了しており、関連テストは `337 passed` で通過済みである
- 方針:
  - 次は C3 の最小入口を足場にして、fetch stub を source family 別の実取得境界へ置き換えるのが自然である
  - 取得結果を run artifact 側へどう最小記録するかは、shared truth と混ぜずに別責務で設計する
- 未確定:
  - 実 fetch 後の保存物をどの単位で run 側に残すか
  - 複数 acquisition 実行時の run-level orchestration 入口をどこに置くか
  - run 側の execution log を追加するか、summary ベースで済ませるか

### 重要な整理事項

- 事実:
  - `cache_key` は `source_family + symbol + period_signature + input_schema_version + cache_key_version` を元に生成する first usable version で固定済み
  - A2 により旧 shared CSV は truth として廃止済みである
  - B2 により shared state schema は `shared_state_v2` へ拡張済みである
  - C3 により `metadata.json` と CLI 出力に `shared_state_role` / `cache_metadata_snapshot_role` / `unresolved_acquisitions_role` が入る
  - C3 の最小 orchestrator は run snapshot を根拠に claim 判定せず、shared truth を再確認する
  - 今回のリファクタで、未使用だった旧 shared CSV helper 群と `update_shared_cache_entry_status()` は削除済みである
  - 今回のリファクタで、shared state 遷移ロジックは内部 helper で共通化した
- 注意点:
  - `run_dir/cache_metadata.csv` は audit / repro 用 snapshot であり、runtime truth ではない
  - `unresolved_acquisitions.csv` は run-start 判定記録であり、実取得可否の最終根拠ではない
  - `running` は unresolved から除外されるが、実行時には lease 状態を shared truth で再確認する
  - fetch はまだ stub であり、外部 source 実装が入ったわけではない
  - `updated_at` は heartbeat 専用列ではなく、claim / heartbeat / complete / fail すべてで更新される行更新時刻である
  - stale 判定や所有権確認は `updated_at` ではなく `lease_expires_at` / `last_heartbeat_at` / `claimed_by` を見る必要がある
- 不明:
  - 実 source 実装をどの module 境界で差し込むかはまだ固定していない

### スコープ管理

- 今やること:
  - 単一 acquisition の C3 導線を土台に、source family 別の実 fetch 境界を差し込む
  - run 実行記録を shared truth と分離したまま最小追加する
  - batch 化や並列化の前に、単一 acquisition 実行の責務を明確に保つ
- 今はやらないこと:
  - A2/B2/C3 の大規模な再設計
  - snapshot への lease 情報追加
  - source family 実装の大規模拡張
  - 並列取得
  - 大規模 batch 実行
  - simulate 実行
  - comparison 実行
  - retry policy の高度化
  - shared state 周辺の大掃除

### 次セッションでのタスク候補

- 最も自然に進む次の作業:
  - `fetch_acquisition_payload()` の stub を `news` / `sns` の実取得境界へ差し替える
  - orchestration 結果を run 側に最小記録する仕組みを、shared truth と分離して追加する
- 他に考えられる選択肢:
  - 複数 acquisition を順次実行する batch 入口を追加する
  - acquisition 実行結果を summary だけ残すか、attempt log を残すかを先に決める
- 推測:
  - source family 別 fetch 境界を先に作った方が、batch 導線よりも責務分離を保ちやすい

### 未確定事項 / 論点

- 未確定:
  - 実 fetch 成功時に何を shared truth に保存し、何を run 側に残すか
  - `orchestrate_research_acquisition()` を CLI 化するか、別の batch CLI からだけ呼ぶか
  - `failed` の error code と retryable 判定を source family 実装側でどこまで揃えるか
- 論点:
  - run 側 execution record を `results_index.csv` に寄せるか、別 artifact を作るか
  - batch 実行時に unresolved snapshot を入力候補として使うか、毎回 acquisition_manifest 全体を見るか
  - fetch stub の差し替え境界を `research_manifest.py` 内に置き続けるか、別 module に分けるか

### リスク / 懸念

- 事実:
  - fetch はまだ stub なので、実運用の取得品質や source ごとの差分吸収は未着手である
  - `orchestrate_research_acquisition()` は 1 acquisition 前提であり、run 全体の順次実行や観測記録までは担っていない
  - run snapshot と shared truth の差分が大きくなると、後から見たときに「その run が何を見ていたか」と「実際にどう動いたか」を別記録で追う必要がある
- 推測:
  - 次に batch 実行へ進むと、run 記録責務を先に決めておかないと shared truth 更新と run 記録が混ざりやすい
  - source family 実装を急ぎすぎると、C3 の責務分離より先に I/O が膨らみ、後で整理コストが増える

## Implemented So Far

- フェーズ1の現状調査により、`simulate`、comparison、real-data comparison、research manifest、live runner fetch の実コード上の責務を `できる / できない / 不明` で再整理した
- market data 用の最小 shared truth を external signal 系と分離した別 DB で持つ方針を確定した
- 単一 period を明示引数で受け取り、market data acquisition key に基づいて fetch / reuse / normalized OHLCV 保存 / 再読込確認を行う最小導線を追加した
- primary artifact を returns ではなく normalized OHLCV CSV に固定し、completed 更新条件を「保存成功 + 再読込成功 + 最小妥当性確認成功」に限定した
- 単一 period × 単一 case について、保存済みまたは reuse された OHLCV から returns を生成し、既存 comparison の `run_case()` / `summarize_case_result()` を使って end-to-end 評価できる最小 runner を追加した
- 複数 period × 複数 case について、period ごとに market data 解決と returns 生成を 1 回だけ行い、その returns を複数 case で共有して CSV と最小 JSON summary を出す batch runner を追加した

## Explicitly Not Done

- `simulate` 実行との接続
- period CSV 本格統合
- 複数 period の重複最適化
- 大規模 batch orchestration
- research_manifest との接続拡張
- 同一 acquisition key の同時実行制御
- schema_version 運用ルールの確定

## Next Tasks

- market data 再利用導線を evaluation manifest / period CSV 入力へ接続する
- periods.csv / grids.csv と自然に接続できる入力設計へ拡張する
- 大規模 batch orchestration と並列化の境界を決める
- 同一 acquisition key の同時実行制御方針を決める
- schema_version をどの変更で上げるかの運用ルールを決める
