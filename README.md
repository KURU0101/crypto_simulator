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
