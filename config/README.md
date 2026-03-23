# Config

設定ファイルは example のみを管理します。
example は、最終対象未確定の間も `BTC/USDT` spot と `ETH/USDT` spot のような高流動性メジャー現物を想定した仮設定として扱います。初期資本の代表値は `100000`（10万円）です。
比較実行の最小例として `comparison.example.json` を置き、複数 case を name 付き list で並べる形式を採用します。
comparison example は threshold / cumulative-drop / consecutive-drop を含み、`python3 scripts/run_comparisons.py --config config/comparison.example.json` を実行すると `final_value` / `trade_count` / `win_rate` と strategy パラメータをまとめて比較できます。
comparison example には `threshold_with_cost` も含め、低利益戦略でコスト差分が summary にどう出るかを最小ケースで確認できるようにします。
違いの見方は、threshold が単発変化、cumulative-drop が直近合計、consecutive-drop が連続性に反応する、で揃えています。
比較実行は `python3 scripts/run_comparisons.py --config config/comparison.example.json` で確認できます。
`real_data_comparison.example.json` はローカル OHLCV CSV から returns を生成して comparison に渡す例です。`data_source.ohlcv_csv_path` で入力 CSV を指定し、各 case には `returns` を書かず strategy パラメータだけを持たせます。
OHLCV からの returns は close-to-close で計算し、生 OHLCV を simulate に直接渡さない構成を維持します。
実データ comparison は `python3 scripts/run_real_data_comparisons.py --config config/real_data_comparison.example.json` で確認できます。
`pseudo_realtime_replay.example.json` は元 OHLCV CSV をワークCSVへ1行ずつ追記し、各 tick でワークCSV全量を読み直して再評価する例です。`replay.work_csv_path` が追記先、`replay.warmup_rows` が起動直後に判断しない行数です。
疑似リアルタイム再生は `python3 scripts/run_pseudo_realtime_replay.py --config config/pseudo_realtime_replay.example.json` で確認できます。
`live_decision_runner.example.json` は Binance Spot REST `/api/v3/klines` を 1 分ごとに poll し、1 分足の確定足だけで戦略判断を継続する例です。`data_source.interval` は初期実装では `1m` 固定、`runtime.duration_seconds` は既定で 600、`runtime.warmup_candles` は起動直後に観測だけ行う confirmed candle 数です。
live runner は起動直後には判断せず、warmup 完了後に初回判断を行います。保存先は `output.output_dir/<run_id>/` 形式の run directory で分離し、その配下に `summary.json` / `decision_log.json` / `trade_log.json` / `equity_history.json` / `progress_log.json` を保存します。`output.max_run_directories` を超える場合は最も古い run directory から削除します。
warmup は観測専用で、trade / pnl / position を作りません。live runner の summary と progress は warmup 後の live session だけを対象にし、`session_start_state` は常に `initial_cash` ベースのフラット初期状態です。
リアルタイム判定ランナーは `python3 scripts/run_live_decision_runner.py --config config/live_decision_runner.example.json` で確認できます。
