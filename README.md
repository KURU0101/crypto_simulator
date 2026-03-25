# 投資研究

個人用の投資研究・バックテストプロジェクトです。

## 前提

- Ubuntu / WSL を標準環境とする
- Python 実行コマンドは `python3` を使用する
- 仮想環境はリポジトリ直下の `.venv` を使用する

## 対象前提

- 現段階では最終対象は未確定のままにする
- ただし今後の実装は、高流動性・低コスト寄りのメジャー現物を想定して進める
- 第一候補は `BTC/USDT` 現物、第二候補は `ETH/USDT` 現物とする
- ミームコイン、中小アルト、個別株、先物、perpetual futures、オプション、低流動性商品はいったん対象外とする
- `fee_rate` や `slippage_rate` は仮値を許容し、将来調整可能な前提で持つ

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-dev.txt
```

## 実行

標準の実行コマンド:

```bash
source .venv/bin/activate
python3 scripts/run_simulation.py --config config/simulation.example.json
```

実データ returns パイプラインの最小実行例:

```bash
source .venv/bin/activate
python3 scripts/run_real_data_comparisons.py --config config/real_data_comparison.example.json
python3 scripts/run_real_data_comparisons.py --config config/real_data_external_signal_series_comparison.example.json
```

`config/real_data_external_signal_series_comparison.example.json` は external signal comparison の標準 8 ケースです。現時点の第一候補は `matching_baseline` (`weighted_matching_signal_count` + `entry_count_threshold=1.4`) ですが、これは比較上の主戦略候補であり、ロジック既定値として固定したものではありません。

疑似リアルタイム再生の最小実行例:

```bash
source .venv/bin/activate
python3 scripts/run_pseudo_realtime_replay.py --config config/pseudo_realtime_replay.example.json
```

複数銘柄データ設定の要約確認:

```bash
source .venv/bin/activate
python3 scripts/summarize_market_data.py --config config/real_data_comparison.example.json
```

リアルタイム判定ランナーの最小実行例:

```bash
source .venv/bin/activate
python3 scripts/run_live_decision_runner.py --config config/live_decision_runner.example.json
```

SNS signal 入力の要約確認:

```bash
source .venv/bin/activate
python3 scripts/summarize_sns_signals.py --input data/signals/sns/sample.json
```

News signal 入力の要約確認:

```bash
source .venv/bin/activate
python3 scripts/summarize_news_signals.py --input data/signals/news/sample.json
```

無料ニュースソースの最小収集例:

```bash
source .venv/bin/activate
python3 scripts/run_news_collector.py --config config/news_collector.example.json
python3 scripts/run_news_collector.py --config config/news_collector.sec.example.json
python3 scripts/run_news_collector.py --config config/news_collector.federal_reserve.example.json
```

無料 SNS ソースの最小収集例:

```bash
source .venv/bin/activate
python3 scripts/run_sns_collector.py --config config/sns_collector.reddit.example.json
python3 scripts/run_sns_collector.py --config config/sns_collector.youtube.example.json
python3 scripts/run_sns_collector.py --config config/sns_collector.hacker_news.example.json
```

`Makefile` を使う場合:

```bash
source .venv/bin/activate
make run
```

comparison を実行する場合:

```bash
source .venv/bin/activate
python3 scripts/run_comparisons.py --config config/comparison.example.json
```

実データ returns パイプラインを `Makefile` から呼ぶ場合:

```bash
source .venv/bin/activate
make run-real-data
```

疑似リアルタイム再生を `Makefile` から呼ぶ場合:

```bash
source .venv/bin/activate
make run-pseudo-realtime
```

リアルタイム判定ランナーを `Makefile` から呼ぶ場合:

```bash
source .venv/bin/activate
make run-live-decision
```

単一 period の market data 取得 / 再利用確認の最小実行例:

```bash
source .venv/bin/activate
python3 scripts/run_evaluation_market_data.py --source binance_spot --symbol BTCUSDT --start 2024-01-01T00:00:00Z --end 2024-01-01T02:00:00Z --interval 1h
```

単一 period × 単一 case の最小評価実行例:

```bash
source .venv/bin/activate
python3 scripts/run_evaluation_case.py --source binance_spot --symbol BTCUSDT --start 2024-01-01T00:00:00Z --end 2024-01-01T03:00:00Z --interval 1h --case-config path/to/case.json
```

複数 period × 複数 case の最小 batch 実行例:

```bash
source .venv/bin/activate
python3 scripts/run_evaluation_batch.py --config config/evaluation_batch.example.json
```

periods CSV + case templates + grids から batch runner へ接続する入力 adapter 実行例:

```bash
source .venv/bin/activate
python3 scripts/run_evaluation_batch_from_inputs.py --config config/evaluation_batch_input.example.json
```

batch runner は CSV を維持したまま、結果 DB を追加保存先として持てます。period ごとに market data 解決と returns 生成を 1 回だけ行い、同一 period 配下の case を `case_chunk_size` 単位で流して CSV と SQLite へ逐次保存します。SQLite には run メタ情報と `1 period × 1 case = 1 row` の結果テーブルを保存し、`results_db_path` を省略した場合は `output_csv_path` と同じ場所に `*.sqlite3` を自動生成します。`dry_run: true` にすると fetch / case prepare / CSV 書き込み / DB 書き込みを行わずに、period 数、case 数、想定 row 数、使用 chunk サイズだけを確認できます。中規模 run を行うときは period と case を代表 subset に絞った設定ファイルを別途用意し、同じ実行入口でチャンク挙動と CSV / DB 整合を先に確認できます。

入力 adapter では `periods_csv_path`、`case_templates_json_path`、`grids_csv_path` を使って batch runner の内部表現へ変換します。`periods.csv` は `period_id,source,symbol,interval,start,end` を必須列とし、`grids.csv` は `grid_id,template_name,overrides_json` を必須列とします。生成される case 名は `template_name__grid_id` で固定し、重複が出た場合は実行前にエラーにします。`period_limit` と `case_limit` を使うと dry run や小規模 subset 実行を同じ入口で行えます。

CSV / DB の二重保存は run ごとに append ではなく新しい `run_id` を切る前提です。中断時はその時点までの CSV 行と DB 行を残し、再実行では既存 run を上書きせず新しい run として追跡します。部分再開や旧 run への追記ルールは未実装で、後続タスクで扱います。

## 手動確認

`python3 scripts/run_simulation.py --config config/simulation.example.json` を実行し、出力 JSON の以下を確認します。

- `returns`
- `entry_signals`
- `exit_signals`
- `position`
- `equity_curve`
- `final_value`

例の設定では 2 期間目は `exit_signals` により非保有となるため資産は据え置きになり、`position` は `[true, false, true, true]`、`final_value` は `1050703.0` になります。

## Simulation Input Boundary

- `simulate` は `returns` 系列と、同じ長さの `entry_signals` / `exit_signals` を受ける層とする
- raw OHLCV、取引所レスポンス、外部 API の生データは `simulate` に直接渡さない
- 実データ取得処理は `simulate` の前段に置き、前処理で `returns` 系列や必要な配列を作ってから渡す
- strategy 実装は、その前処理済み系列から signal を作るか、comparison で signal 生成付き simulation を呼ぶ想定とする

## テスト

標準のテストコマンド:

```bash
source .venv/bin/activate
python3 -m pytest
```

`.venv` を有効化せずに直接実行する場合は、`.venv/bin/python3 -m pytest` を優先します。

`Makefile` を使う場合:

```bash
source .venv/bin/activate
make test
```

comparison summary では、既存の `final_value` / `trade_count` / `win_rate` に加えて、`completed_trade_count`、`open_trade_count`、`average_pnl_per_completed_trade`、`total_realized_pnl`、`total_cost_amount` を確認できます。

## 実データフェーズ

実データフェーズは `OHLCV -> returns -> simulate -> comparison` の順で扱います。
`simulate` に渡すのは常に `returns` と signals であり、生の OHLCV は直接渡しません。
returns は close-to-close 定義で計算し、各 return はひとつ前の close から当該 timestamp の close までの変化率です。
生成された returns の timestamp は後ろ側の close timestamp に揃えます。

複数銘柄の価格データ土台では `data_sources.default_symbol` と `data_sources.symbols` を使い、ローカル配置は `data/market/<symbol_slug>/...csv` を標準例とします。
現在の最小構成では `BTC/USDT` と `ETH/USDT` のローカルサンプル OHLCV を [data/market/btcusdt/1h_sample.csv](/home/kuru0101/crypto_simulator/crypto_simulator/data/market/btcusdt/1h_sample.csv) と [data/market/ethusdt/1h_sample.csv](/home/kuru0101/crypto_simulator/crypto_simulator/data/market/ethusdt/1h_sample.csv) に同梱しています。
実データ comparison 用の設定例は [config/real_data_comparison.example.json](/home/kuru0101/crypto_simulator/crypto_simulator/config/real_data_comparison.example.json) です。
comparison は `--symbol` で対象銘柄を切り替えられます。

## 疑似リアルタイム再生

疑似リアルタイム再生は、元の OHLCV CSV からワークCSVへ1行ずつ追記し、その時点のワークCSV全量を毎 tick 読み直して再評価します。
初回実装では増分更新最適化は行わず、将来の外部入力追加時にも流れが揃うように I/O 境界込みで確認することを優先しています。

`warmup_rows` は、起動直後に売買判断をせずデータ取得だけを行う行数です。
判断開始後も warmup 中の履歴は strategy 計算の文脈として使えますが、warmup 対象期間の signal は無効化して、warmup 中に売買が始まらないようにしています。
複数銘柄設定では `replay.work_dir` から `<symbol_slug>_replay_work.csv` を導出し、`--symbol` で再生対象を切り替えられます。

decision log の理由コードは以下の2系統に分けます。

- `signal_reason_code`: signal の発生理由を表す。例: `threshold_entry_signal`, `cumulative_drop_exit_signal`, `no_signal`, `warmup_pending`
- `action_reason_code`: その tick の状態変化を表す。例: `enter_position`, `exit_position`, `hold_position`, `stay_flat`, `warmup_skip`

出力は初回実装では標準出力 JSON のみです。
`trade_log` は最終 tick 時点の `simulate` 出力、`decision_log` と `equity_history` は各 tick ごとの再生ログです。

## リアルタイム判定ランナー

リアルタイム判定ランナーは Binance Spot REST `/api/v3/klines` を一定間隔で poll し、1 分足の確定足だけで戦略判断を継続する外側レイヤです。
注文送信や実売買は行わず、`OHLCV -> returns -> signals -> simulate` の責務分離を維持します。

live runner は起動直後には判断せず、`warmup_candles` 分の confirmed candle を観測だけ行ってから初回判断を開始します。
warmup 中の candle は売買判断には使わず、履歴コンテキストとしてだけ保持します。warmup 完了後の初回判断はその時点で利用可能な confirmed candle 全体を文脈にして行いますが、保有状態・損益・trade count は warmup から持ち越しません。
以後は `last_confirmed_timestamp` を保持し、同一 timestamp の足では再判断せず、新しく確定した 1 分足だけを順次評価します。

標準出力は実行中には 1 分ごとの progress summary を短い JSON で出し、終了時には `summary` と `decision_log` の先頭 / 末尾の一部だけを表示します。
progress summary の `trade_count` は live session 中に新規発生した trade 数だけを表し、`equity` / `cash` はフラット初期状態から始まる live session のその時点の絶対値です。全量ログは stdout に戻しません。

終了時の summary でも `trade_count` / `winning_trades` / `losing_trades` / `realized_pnl_total` / `final_value` / `final_cash` / `open_position_at_end` はすべて warmup 後の live session だけを対象にします。
`session_start_state` は常にフラットな初期状態で、`trade_log` も live session 中に発生した trade だけを保存します。

保存先は `output_dir/<run_id>/` 形式の run directory で実行ごとに分離します。
既定では run directory を最大 10 件保持し、超過時は最も古い run directory から削除します。

標準出力の full history 抑制方針は維持し、詳細は run directory 配下の JSON ファイルで確認します。
429 受信時は最小限の retry / backoff を行い、`X-MBX-USED-WEIGHT-1M` が返る場合は decision / progress 文脈と summary に残します。
複数銘柄設定では `data_sources.default_symbol` と `data_sources.symbols[]` を使い、`--symbol ETHUSDT` のように対象銘柄を切り替えられます。summary には `symbol` / `default_symbol` / `available_symbols` を残し、progress stdout にも `symbol` を含めます。

## External Signal Inputs

SNS / News は今回 `simulate` に直結せず、分析済みシグナルの受け取り口だけを追加しています。
保存形式は JSON array または NDJSON、時刻は timezone 付き ISO8601 を受けて UTC `Z` に正規化します。

SNS は `source` / `timestamp` / `mention_count` / `positive_score` / `negative_score` / `neutral_score` / `activity_score` / `anomaly_score` と、`symbol` または `topic` を持つ最小 schema です。内部表現は `records` と `by_symbol` / `by_topic` を返し、topic-only データも保持できます。

News は `source` / `published_at` / `headline` / `relevance_score` / `sentiment_score` / `impact_score` / `category` と、`url` または `source_id`、さらに `symbol` / `asset` / `topic` のいずれかを持つ最小 schema です。内部表現は `records` と `by_symbol` / `by_asset` / `by_topic` を返します。

最小 news collector は `coindesk_rss`、`sec_press_releases_rss`、`federal_reserve_press_releases_rss` をサポートし、いずれも RSS GET のみを行います。source ごとの adapter は collector 本体から分離し、保存は raw ではなく正規化済み `normalized.json` と run 単位の `summary.json` のみで、出力先は `var/news_signals/<collector_source>/<run_id>/` です。record には軽量 dedup 用の `dedup_key` を持たせ、summary では `signal_type`、`category_distribution`、`duplicate_count`、`source_specific.feed_url` を含む観測を残します。

最小 SNS collector は `reddit_subreddit_new_json` をサポートし、Reddit の公開 listing JSON を GET して `sns_signals` schema に正規化します。保存は raw ではなく正規化済み `normalized.json` と run 単位の `summary.json` のみで、出力先は `var/sns_signals/<collector_source>/<run_id>/` です。record には軽量 dedup 用の `dedup_key` を持たせ、summary では `mention_count_summary` と `duplicate_count` を含む観測を残します。

YouTube 側の最小 collector は `youtube_channel_rss` をサポートし、複数 channel の公開 RSS を 1 run に束ねて `sns_signals` schema に正規化します。config では `groups[]` に `group_id` / `group_label` / `group_theme` / `publisher_type` / `channels[]` を持たせ、channel 単位では `channel_id` / `channel_label` / `publisher_type` / `theme_tags` を管理します。record の group/channel 情報は `metadata` に残し、summary では `group_distribution` / `group_theme_distribution` / `publisher_type_distribution` / `channel_distribution` を観測できます。

Hacker News 側の最小 collector は `hacker_news_public_api` をサポートし、`topstories` などの一覧 ID を取得してから `item/{id}` を最小件数だけ引き、1件 = 1 signal で正規化します。record には `score` / `descendants` / `story_type` / `url` / `id` を `metadata` に残し、summary では `score_summary` / `comment_count_summary` / `story_type_distribution` を観測できます。

SNS summary は、共通項目をトップレベルに維持しつつ、source 固有観測を `source_specific` にもまとめます。`mention_count` の意味は source ごとに異なり、Reddit は `num_comments`、YouTube は `1動画=1`、Hacker News は `descendants` を使います。topic / symbol 推定ルールは共通 normalize ではなく source ごとの adapter 側に寄せています。

サンプルは [data/signals/sns/sample.json](/home/kuru0101/crypto_simulator/crypto_simulator/data/signals/sns/sample.json) と [data/signals/news/sample.json](/home/kuru0101/crypto_simulator/crypto_simulator/data/signals/news/sample.json) に置いています。
設計メモと無料公開データ候補は [docs/external_signals.md](/home/kuru0101/crypto_simulator/crypto_simulator/docs/external_signals.md) に整理しています。

ニュース collector でも `collector -> adapter -> save -> observe` を分離しています。各 example config は 1 source ごとの最小構成で、raw RSS は保存せず、正規化後の bundle と観測 summary だけを `var/news_signals/<source>/<run_id>/` に保存します。

統合観測導線として `python3 scripts/observe_external_signals.py` を追加し、保存済み `var/news_signals/**/summary.json` と `var/sns_signals/**/summary.json` を横断して読めるようにしました。これは読み取り専用で、外部再取得も `simulate` 連携も行いません。

既定の `condensed` 表示では collector ごとの最新状況を一覧でき、`--group-by overall|signal_type|source`、`--signal-type news|sns`、`--source <collector_source>`、`--latest-only` で見方を切り替えられます。`--format verbose` では `source_specific` と topic / symbol 分布の詳細、`--format json` では集約結果全体を JSON で確認できます。

統合観測が見る共通項目は `signal_type` / `source` / `run_id` / `started_at` / `ended_at` / `status` / `fetched_item_count` / `normalized_success_count` / `validation_failure_count` / `saved_record_count` / `duplicate_count` / `warnings` / `errors` / `saved_paths` です。`source_specific` は無理に共通化せず、存在有無を一覧に出したうえで verbose 時だけ分けて表示します。

互換維持のために一部 source 固有項目が summary トップレベルに残る場合がありますが、統合観測はそれらへ依存せず、共通項目と `source_specific` を優先して読みます。

`summary.json` が欠損している run directory や、JSON として壊れている summary も観測結果に残します。今の制約は、集約対象が保存済み summary 中心であること、source ごとの差分は `source_specific` に残したまま最小限しか吸収しないこと、topic / symbol 分布は summary 側の既存集計に依存することです。

## ディレクトリ方針

- `scripts/` には実行入口のみを置く
- `src/trade_simulator/` にはアプリケーションのロジック本体を置く
- `config/` には管理対象の設定例を置く
- `tests/` には `src/` の振る舞いを確認するテストを置く

## 開発手順

1. `origin/main` の最新を前提に作業する
2. `main` 以外の作業ブランチで作業する
3. `.venv` を有効化してから実行・テストする
4. 変更後は最低限 `python3 -m pytest` を実行する

## 構成方針

- 変更は最小限にする
- 指示されていないリファクタはしない
- 実データ、秘密情報、ログ、生成物は Git 管理対象から除外する
