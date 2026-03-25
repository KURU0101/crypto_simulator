# Session Handover

## セッションの目的・意図

- ユーザーの主目的は、`current-stack` 側の実行確認を終えたあと、`original planning baseline` 側へ段階的に入ることだった。
- 背景意図は、「単発の最良ケース」ではなく、「どの period 群・どの parameter 帯・どの signal series が再現性を持って有望か」を見極めることだった。
- そのため、period 側の拡張より先に parameter 次元を広げ、`signal-only -> minimal -> extended` の比較をきれいに取る流れが重視された。
- 実行そのものよりも、毎回 `dry run -> actual run -> 保存整合確認 -> 文書反映` の運用を明確に残すことが意図されていた。

## ユーザーからの主な指示・制約

- 外部通信を伴う `actual run` は事前承認対象として扱うこと。
- `dry_run` 用 config と `actual run` 用 config を分けること。
- `current-stack` 側と `original planning` 側の命名・保存先を混線させないこと。
- `comparison / simulate` の責務を増やさないこと。
- `task.md` は進行記録の主文書なので、引継ぎファイルには進捗そのものを書き込まないこと。
- 追加実行が必要でも、勝手に進めず提案に留めること。
- 分析では勝率を第1優先に置くが、利益が残ること、取引回数が少なすぎないこと、安定性があることを必ず併せて見ること。

## このセッションで行った判断

- `official scale` は `small / medium / full` に整理し、`seed/smoke`、`pilot`、`planning`、`ceiling` は移行期の内部呼称に下げた。
- `original planning` 側へ入る際は、`raw 24` より先に `merged 12` を固定して parameter 次元を広げる方針を採った。
- 理由は、ユーザーが「period 数を増やすことより parameter 探索を優先する」と明示していたため。
- `signal-only -> minimal -> extended` の順で進めたのは、同じ merged 12 上で差分比較しやすくするため。
- `minimal` と `extended` の追加軸は、今の実行結果では実質 no-op に見える、という分析判断に至った。
- 次候補として `raw 24 × signal-only` が高情報価値と判断したのは、追加 5 軸が効いていない一方で period 依存が強く、event 単位差の方が次の情報量が大きいと見えたため。

## 出力内容の要点

- `original planning baseline` 用の raw 24 / merged 12 の period 定義と対応表を追加した。
- `signal-only`、`minimal tradability`、`extended` の original 系 config / grid / template 群を追加した。
- `original planning baseline` 側の `merged 12 × signal-only`、`merged 12 × minimal`、`merged 12 × extended` を actual run まで通し、README と task に記録した。
- original 系分析として、3 run 群の分布、軸別比較、period 別比較、安定性評価、次アクション候補を整理した。
- `session_handover.md` は今回新規作成で、文脈のみを残す役割にする。

## 文脈上重要なポイント

- `task.md` には進行内容が入っている前提なので、次セッションではまず `task.md` で状態を確認し、`session_handover.md` では「なぜそう進めているか」を掴む使い方が前提。
- `current-stack full=9216` は official scale の最終規模だが、これは `original planning baseline` とは別系統の整理である。
- `original planning baseline` の件数は固定値ではなく、「軸 × 刻み方」から自然にそうなる、という理解が重要。
- 分析上、追加 5 軸が no-op に見えるのは「今の実行経路・現データ上の観測結果」であり、理論上不要と確定したわけではない。
- 高勝率 row は存在するが、安定して利益が残る条件帯はまだ見つかっていない、という認識を崩さないこと。
- `zero-trade` を損失回避として過大評価しない、という前提が暗黙共有されている。

## 変更・転換点

- 当初は `current-stack` の scale 整理と実行確認が中心だったが、途中で `original planning baseline` 側の run と分析へ主眼が移った。
- `small / medium / full` の公式呼称整理後、`original planning baseline` は別枠として切り出された。
- `merged 12 × signal-only` 完了後、次は `raw 24 × signal-only` ではなく `merged 12 × minimal` へ進む判断が入った。
- さらに `merged 12 × minimal` 完了後、同じ理由で `merged 12 × extended` へ進んだ。
- 分析段階で、parameter 拡張より period 拡張の方が次の情報価値が高そうだ、という見立てに転換した。

## 未解決の文脈的な違和感

- `price_spike_limit` と `volume_multiplier` が結果上 no-op に見える理由は、仕様として未使用なのか、今回のケース定義では効かないだけなのか、未確定。
- `take_profit`、`stop_loss`、`max_hold_minutes` も同様に no-op に見えており、parameter 探索の見かけ上の広がりと実際の有効自由度にずれがある可能性がある。
- `merged 12` の period 定義を今後固定するのか、候補差し替え余地を残すのかは未確定。
- 分析では `raw 24 × signal-only` が次候補に見えるが、ユーザーが次に period 拡張を本当に優先するかは未確定。
- 推測: external signal の topic / summary source 側の反応範囲が狭く、period 差のかなりの部分を支配している可能性がある。

## 次セッションへの引き継ぎ方（文脈面）

- まず [task.md](/home/kuru0101/crypto_simulator/crypto_simulator/task.md) を確認し、直近の正式タスクと latest run / 分析結果を把握する。
- そのうえで、この `session_handover.md` を読み、なぜ `raw 24 × signal-only` が次候補として浮いているのか、なぜ追加軸をすぐ増やす流れではないのかを確認する。
- 次の思考は、「period を増やすべきか」「追加軸が no-op に見える点を先に詰めるべきか」の比較から始めるのが自然。
- もし次セッションで追加実行に進むなら、外部通信 actual run の事前承認、config 名分離、保存先分離、run 記録必須、という運用前提を最初に確認する。
- 分析を継続するなら、「勝率最優先だが、利益が残ること・取引回数が少なすぎないこと・安定性があること」を評価軸として維持する。
