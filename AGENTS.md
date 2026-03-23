# AGENTS.md

## Git rules
- main に直接コミットしない
- 作業開始前に origin/main の最新を前提にする
- 競合の可能性がある場合は、そのまま進めず報告する
- 新しい feature branch を作成して作業する

## Execution baseline
- 標準環境は Ubuntu / WSL とする
- Python 実行コマンドは `python3` に統一する
- 仮想環境はリポジトリ直下の `.venv` を使用する
- 必要に応じて `source .venv/bin/activate` を行う
- 依存追加・更新時も `python3 -m pip` を使用する
- 標準の実行コマンドは `python3 scripts/run_simulation.py --config config/simulation.example.json`
- 標準のテストコマンドは `python3 -m pytest`
- `Makefile` がある場合は、上記コマンドのエイリアスとして維持する

## Coding rules
- 変更は目的達成に必要な最小限にする
- 不要なリファクタはしない
- 不明点は仮説として扱い、明示する
- ユーザーが明示的に許可した場合を除き、大規模変更は行わない
- ロジック本体を変更しない指示がある場合は、README / AGENTS / Makefile など周辺ファイルのみに限定する
- 実行方法・テスト方法を追加する場合は、現存する入口とテストに一致させる
- 新しい実行ルールを追加する場合は、README と AGENTS の両方に反映して齟齬を作らない

## Directory roles
- `scripts/` は実行入口のみを置く
- `src/` はロジック本体を置く
- `tests/` は `src/` の確認を行う
- `config/` は管理対象の設定例を置く

## Decision rules
- 変更案は以下の観点で評価する
  - 安全性（既存挙動を壊さないか）
  - 最小変更（過剰な実装になっていないか）
  - 妥当性（目的に対して十分か）
  - 再現性（実行・検証手順が明確か）

## Commit rules
- ユーザーが明示的に許可した場合のみ commit する
- commit 前に変更ファイル一覧と要約を提示する
- commit メッセージは簡潔にする（conventional commits 風）
- main に直接 commit しない
- push は行わない

## Commit safety rules
- git add は対象ファイルを明示して行う（`git add .` は使用しない）
- git 操作は単一コマンドで実行し、シェルラップ（`bash -lc` など）を使用しない
- commit 後に作業ツリーが clean でない場合は、その理由を必ず報告する
- Git管理外（`/tmp` など）へ変更を退避しない
- 差分は必ず Git 管理下で保持する
- 差分整理が必要な場合は、別ブランチまたは `git stash` を優先する
- `git stash` が使用できない場合は、その理由を報告する
