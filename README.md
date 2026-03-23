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

`Makefile` を使う場合:

```bash
source .venv/bin/activate
make run
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
