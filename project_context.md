# Project Context

## Project Overview

このリポジトリは、投資シミュレーションの最小構成を提供するためのものです。
現在は、最小シミュレーションが実行できる初期段階を維持しながら、今後の拡張に備えて構造と運用ルールを固めることを優先します。

## Current Phase

- 現在の段階は「最小シミュレーションが動作する初期段階」
- 実行入口、設定読込、シミュレーション実行、テストの最小構成を保持する
- ロジック改善は次フェーズで扱い、この段階では運用基準と構造整備を優先する

## Current Scope

- `scripts/run_simulation.py` を入口にする
- 設定は JSON を採用する
- ロジックは `src/trade_simulator/` に集約する
- 初期段階では標準ライブラリ中心で構成する
- 出力は標準出力のみとする

## Working Market Assumption

- 現段階では最終対象は未確定のままとする
- ただし今後の simulation 実装は、高流動性のメジャー現物を前提に進める
- 第一候補は `BTC/USDT` spot、第二候補は `ETH/USDT` spot
- 目的は低コスト・低利益を小さく積む運用を想定し、前提をぶらしにくくすること
- ミームコイン、中小アルト、個別株、先物、perpetual futures、オプション、低流動性商品は今回の想定から外す
- `fee_rate` や `slippage_rate` などのパラメータは仮値を許容し、将来調整する前提で保持する

## Structure Policy

- `scripts/` は実行入口のみを持つ
- `src/` はロジック本体を持つ
- 実行レイヤとロジックレイヤを分離し、将来の拡張時もこの方針を維持する

## Execution And Validation Baseline

標準環境:

- Ubuntu / WSL
- Python 実行は `python3`
- 仮想環境は `.venv`

## Execution Baseline

```bash
python3 scripts/run_simulation.py --config config/simulation.example.json
```

## Test Baseline

```bash
python3 -m pytest
```

## Development Flow

1. 調査
2. 計画
3. 実装
4. 実行確認
5. テスト確認

作業時は、まず既存構成と制約を確認し、その後に最小変更で対応する。

## Test Expansion Policy

- 現時点では最小テストを維持する
- 今後のロジック拡張に応じて `tests/` を段階的に拡張する
- テスト追加時も、標準コマンドは `python3 -m pytest` に統一する

## Future Expansion

- シミュレーション条件の拡張
- 検証観点の追加
- 設定項目と出力項目の拡張
- 段階的なテスト拡充

## Out Of Scope For This Phase

- ロジック改善
- 大規模リファクタ
- 機能追加を伴う構造変更
- 実運用向けの高度な最適化
