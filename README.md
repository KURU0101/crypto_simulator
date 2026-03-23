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
```

疑似リアルタイム再生の最小実行例:

```bash
source .venv/bin/activate
python3 scripts/run_pseudo_realtime_replay.py --config config/pseudo_realtime_replay.example.json
```

リアルタイム判定ランナーの最小実行例:

```bash
source .venv/bin/activate
python3 scripts/run_live_decision_runner.py --config config/live_decision_runner.example.json
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

`Makefile` を使う場合:

```bash
source .venv/bin/activate
make test
```

comparison summary では、既存の `final_value` / `trade_count` / `win_rate` に加えて、`completed_trade_count`、`open_trade_count`、`average_pnl_per_completed_trade`、`total_realized_pnl`、`total_cost_amount` を確認できます。
comparison summary では、既存の `final_value` / `trade_count` / `win_rate` に加えて、`completed_trade_count`、`open_trade_count`、`average_pnl_per_completed_trade`、`total_realized_pnl`、`total_cost_amount` を確認できます。

## 実データフェーズ

実データフェーズは `OHLCV -> returns -> simulate -> comparison` の順で扱います。
`simulate` に渡すのは常に `returns` と signals であり、生の OHLCV は直接渡しません。
returns は close-to-close 定義で計算し、各 return はひとつ前の close から当該 timestamp の close までの変化率です。
生成された returns の timestamp は後ろ側の close timestamp に揃えます。

現在の最小構成では `BTC/USDT` のローカルサンプル OHLCV を [data/btcusdt_1h_sample.csv](/home/kuru0101/crypto_simulator/crypto_simulator/data/btcusdt_1h_sample.csv) に同梱しています。
実データ comparison 用の設定例は [config/real_data_comparison.example.json](/home/kuru0101/crypto_simulator/crypto_simulator/config/real_data_comparison.example.json) です。

## 疑似リアルタイム再生

疑似リアルタイム再生は、元の OHLCV CSV からワークCSVへ1行ずつ追記し、その時点のワークCSV全量を毎 tick 読み直して再評価します。
初回実装では増分更新最適化は行わず、将来の外部入力追加時にも流れが揃うように I/O 境界込みで確認することを優先しています。

`warmup_rows` は、起動直後に売買判断をせずデータ取得だけを行う行数です。
判断開始後も warmup 中の履歴は strategy 計算の文脈として使えますが、warmup 対象期間の signal は無効化して、warmup 中に売買が始まらないようにしています。

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

## ディレクトリ方針

- `scripts/` には実行入口のみを置く
- `src/trade_simulator/` にはアプリケーションのロジック本体を置く
- `config/` には管理対象の設定例を置く
- `tests/` には `src/` の振る舞いを確認するテストを置く

## 開発手順

1. `origin/main` の最新を前提に作業する
2. `main` 以外の feature branch で作業する
3. `.venv` を有効化してから実行・テストする
4. 変更後は最低限 `python3 -m pytest` を実行する

## 構成方針

- 変更は最小限にする
- 指示されていないリファクタはしない
- 実データ、秘密情報、ログ、生成物は Git 管理対象から除外する
