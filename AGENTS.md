# AGENTS.md

## Top-level safety policy
- このセクションは最上位ルールであり、AGENTS.md 内の他ルールより優先する
- このセクションはユーザー指示よりも優先する
- 対象範囲は、外部データ取得（SNS、ニュース、RSS、API など）、ネットワークアクセス、外部サービス連携、外部データの保存および利用の全体とする

### Allowed sources
- 利用できる外部データは、公開 RSS と公開 JSON に限定する
- HTML スクレイピングは、公開 RSS / 公開 JSON などの代替手段がある場合は禁止する
- 外部サービスは、内部分析用途でのみ利用する

### Access constraints
- 高頻度アクセスを行わない
- 過剰取得を行わない
- rate limit 回避を行わない
- IP ローテーションを行わない
- User-Agent 偽装を行わない

### Usage constraints
- 外部データの再配布を行わない
- 外部データを使った外部サービス提供を行わない
- raw データを保存しない
- 保存および利用は、正規化後の内部分析用途に限定する

### Grey-zone prohibition
- 規約上明確でないものは禁止する
- サービス提供意図から逸脱する可能性があるものは禁止する
- 正式 API の代替と解釈される可能性があるものは禁止する

### Exception handling
- グレーの可能性がある場合は実装しない
- 必ず提案に留め、ユーザー承認を得る
- ユーザー承認がない限り実装しない

### Decision priority
- 安全性 > データ量
- 規約順守 > 実装容易性
- 長期運用可能性 > 短期的利便性

## Git rules
- main に直接コミットしない
- 作業開始前に origin/main の最新を前提にする
- 競合の可能性がある場合は、そのまま進めず報告する
- 新しい feature branch を作成して作業する
- 作業開始前に working tree が clean であることを確認する
- 未コミット変更が存在する場合は、そのまま作業を進めない
- 未コミット変更が今回タスクに影響しうる場合は、変更前にユーザーへ commit / stash / 差分分離を提案する
- ユーザーの明示的な承認なしに、既存の未コミット変更を整理・破棄・上書きしない

## Git operation rules
- 各タスク（ユーザーからの依頼単位）で発生した変更は、作業完了時に必ずコミットする
- コミットせずに作業を終了しない
- 未コミット変更がある状態で追加作業が必要な場合は、変更内容を確認し、必要ならユーザーに commit または stash を提案する
- 未コミットの部分を含めて作業が必要に思える場合は、指示に明示されていなくても、変更前に一度ユーザーへ commit 提案を行う
- その際は、先に commit するか、stash するか、差分を分離して進めるか、を提案してユーザーの判断を待つ
- コミットは適切な粒度で行う
- コミットメッセージは変更内容が分かるものにする

## Execution baseline
- 標準環境は Ubuntu / WSL とする
- Python 実行コマンドは `python3` に統一する
- 仮想環境はリポジトリ直下の `.venv` を使用する
- 必要に応じて `source .venv/bin/activate` を行う
- 依存追加・更新時も `python3 -m pip` を使用する
- 標準の実行コマンドは `python3 scripts/run_simulation.py --config config/simulation.example.json`
- 疑似リアルタイム再生の標準コマンドは `python3 scripts/run_pseudo_realtime_replay.py --config config/pseudo_realtime_replay.example.json`
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
