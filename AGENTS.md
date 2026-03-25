# AGENTS.md

## Top-level safety policy
- このセクションは最上位ルールであり、AGENTS.md 内の他ルールより優先する
- このセクションはユーザー指示よりも優先する
- 対象範囲は、外部データ取得（SNS、ニュース、RSS、API など）、ネットワークアクセス、外部サービス連携、外部データの保存および利用の全体とする
- ここでいうネットワークアクセスは、プロダクト機能として扱う外部データ取得・外部サービス連携を指す。`git fetch` や依存取得などの開発運用上必要な通信は、この制約の直接対象外とする

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
- main 以外の作業ブランチで作業する
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

## Task execution rules
- ユーザーが明示的に承認した公式タスク以外を勝手に開始しない
- 既存の公式タスクに直接必要でない設計・最適化・抽象化は、実装ではなく提案に留める
- 公式タスクに着手する前に、現在の公式タスク、今回やること、今回やらないこと、その作業が公式タスクにどう直接つながるかを明示する
- 動的なタスク遂行情報は `task.md` に記録する
- 動的な現在タスク判断は `task.md` を優先して参照する
- `project_context.md` は履歴・背景・構造・不変条件・セッション引継ぎの保持を主目的とし、現在進行中タスクの主記録場所にしない
- まだ承認されていない次段階の作業は、候補や論点として整理してよいが、承認前に実装へ進めない
- 外部通信を伴う actual run は事前承認を要する
- 外部通信 run を行った場合は、通信先、取得方式、保存範囲、failure 分類、実行条件変更の有無、Codex 視点で観測できた承認事実を `task.md` に記録する
- 外部通信 run ごとの具体記録は `AGENTS.md` ではなく `task.md` と `README.md` に置く

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
- 作業が終わるごとに、必要に応じて `task.md` を更新し、以下を記録する
- ① 実装した、またはできるようになったこと
- ② 明示的にまだできないこと、または未実装と分かったこと
- ③ 次回以降のタスクでやると指示されたこと

## External signal design rules
- external signal 基盤は `fetch -> adapter -> normalize -> save -> observe` の責務分離を維持する
- collector は source ごとの取得と実行制御に留め、source 固有の解釈は adapter 側へ寄せる
- normalize 層は schema の必須条件、時刻正規化、entity 判定、軽量 dedup key 生成を担当する
- save は正規化済み bundle と run 単位 summary の保存だけを担当し、raw payload は保存しない
- observe は collector run の観測 summary を組み立てる層であり、simulate や feature 化へ直結させない
- `simulate` へ渡す前に、外部シグナルは別レイヤで feature 化または統合前処理を行う

## Summary schema rules
- external signal の run summary では、共通項目をトップレベルに置き、source 固有項目は `source_specific` を第一の置き場にする
- 互換維持のために source 固有項目がトップレベルに残っていても、新規実装でそれを増やさない
- integrated observer が依存してよいのは、共通項目、`saved_paths`、`source_specific` の有無、`topic_distribution`、`symbol_distribution` に限る
- integrated observer は source 固有トップレベル項目に依存しない
- 必須共通項目が一部欠けた古い summary も読める範囲で扱い、欠損は観測結果に残す

## Test rules
- 標準の確認は `.venv/bin/python3 -m pytest` を優先する
- テストは外部ネットワークや外部サービスに依存させず、fetch 関数差し替えや固定 payload で検証する
- collector テストでは collector run の保存物と observation を確認し、integrated observer の仕様までは持ち込まない
- integrated observer のテストでは、collector 実装詳細ではなく summary の共通項目だけに依存する
- `save_run_summary=False`、欠損 summary、validation failure のような境界は、回帰しやすい前提として維持する

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
- commit 前に変更ファイル一覧と要約を提示する
- commit メッセージは簡潔にする（conventional commits 風）
- main に直接 commit しない
- push / merge はユーザーの明示的な指示がある場合のみ行う

## Commit safety rules
- git add は対象ファイルを明示して行う（`git add .` は使用しない）
- git 操作は単一コマンドで実行し、シェルラップ（`bash -lc` など）を使用しない
- commit 後に作業ツリーが clean でない場合は、その理由を必ず報告する
- Git管理外（`/tmp` など）へ変更を退避しない
- 差分は必ず Git 管理下で保持する
- 差分整理が必要な場合は、別ブランチまたは `git stash` を優先する
- `git stash` が使用できない場合は、その理由を報告する

## 出力フォーマット規約（重要）
- Codex の出力は、原則として通し番号付きの構造化形式で行うこと
- 番号は 1 から順に付ける
- セクションのネストが必要な場合も、可能な限りフラットな通し番号を優先する
- 箇条書きだけの曖昧な出力は禁止
- 見出しのみの出力は禁止
- 「説明だけ」で終わらず、必ず構造化すること
- この規約はすべてのタスクに適用する
