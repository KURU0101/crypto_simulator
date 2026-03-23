# External Signal Inputs

今回の SNS / News 入口は、収集基盤ではなく「分析済みシグナルの受け取り口」です。`simulate` には接続せず、外部 I/O を評価器へ持ち込まない前提を維持します。

## 共通方針

- 保存形式は JSON array または NDJSON を受け付ける
- 正規化後は時刻を UTC `Z` に揃える
- `source` は小文字化する
- `symbol` は英数字だけを残して大文字化する
- `topic` は前後空白除去、連続空白圧縮、小文字化で扱う
- `metadata` は source 固有差分の逃がし先とし、schema では最小限しか吸収しない

## SNS schema

必須:

- `source`
- `timestamp`
- `mention_count`
- `positive_score`
- `negative_score`
- `neutral_score`
- `activity_score`
- `anomaly_score`
- `symbol` または `topic`

任意:

- `symbol`
- `topic`
- `metadata`

内部表現:

- `records`: 正規化済み list
- `by_symbol`: `dict[symbol] -> list[signal]`
- `by_topic`: `dict[topic] -> list[signal]`

## News schema

必須:

- `source`
- `published_at`
- `headline`
- `relevance_score`
- `sentiment_score`
- `impact_score`
- `category`
- `url` または `source_id`
- `symbol` または `asset` または `topic`

任意:

- `symbol`
- `asset`
- `topic`
- `url`
- `source_id`
- `metadata`

内部表現:

- `records`: 正規化済み list
- `by_symbol`: `dict[symbol] -> list[signal]`
- `by_asset`: `dict[asset] -> list[signal]`
- `by_topic`: `dict[topic] -> list[signal]`

## topic-only の扱い

- `symbol` がなくても `topic` があれば受け入れる
- grouping は `entity_kind` と `entity_key` で判別する
- 後段で symbol 紐付けが必要になった時点で、別レイヤで topic-to-symbol 解決を追加する

## 欠損値

- 必須項目の欠損は validation error
- `metadata` は省略時 `{}` に正規化する
- News の `url` / `source_id` はどちらか一方があればよい

## 無料公開データ候補

SNS 候補:

- Reddit: subreddit / search 結果を topic または symbol 集計に落とし込みやすい
- YouTube: チャンネル動画メタデータやコメント集計を topic ベースで流し込みやすい
- GitHub Discussions / Discord export などの手動集計: `metadata` に原系列情報を残しやすい

News 候補:

- CoinDesk RSS
- Cointelegraph RSS
- The Block などの公開 RSS / sitemap
- SEC / FRB / CFTC / 日銀などの公式発表ページ

最初の接続先としては、RSS や公開 JSON を持つ News ソースが最も軽く、次に Reddit の手動・定期集計が妥当です。今回の形式には、取得後に source ごとの生項目を `metadata` に残しつつ、本文側は `source` / `symbol|topic` / `time` / score 群へ写像して流し込みます。

## Minimal News Collector

初回 collector は CoinDesk RSS を 1 ソースだけ対象にします。利用は公開 RSS の GET のみで、raw XML は保存しません。

責務分離:

- collector: RSS GET と XML item 抽出
- adapter: item を `news_signals` schema へ正規化
- save: 正規化後 bundle と観測 summary のみ保存
- observe: 実行時間、取得件数、正規化成功/失敗、保存件数、欠損、symbol/topic 分布、published_at 分布、エラーを集計

実行:

- `python3 scripts/run_news_collector.py --config config/news_collector.example.json`

保存:

- `var/news_signals/coindesk_rss/<run_id>/normalized.json`
- `var/news_signals/coindesk_rss/<run_id>/summary.json`

adapter の score は今回は収集導線確認用の固定/簡易ヒューリスティクスです。高度な sentiment や impact 推定は次段に分離します。
