# AGENTS.md

## Git rules
- main に直接コミットしない
- 作業開始前に origin/main の最新を前提にする
- 新しい feature branch を作成して作業する

## Coding rules
- 変更は最小限にする
- 指示されていないリファクタはしない
- 不明点は仮説として扱う

## Decision rules
- 変更案は以下の観点で評価する
  - 安全性（既存挙動を壊さないか）
  - 最小変更（過剰な実装になっていないか）
  - 妥当性（目的に対して十分か）
