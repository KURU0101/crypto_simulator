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

追加された共通項目:

- `dedup_key`: 軽量 dedup 用の識別子

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

今回の collector は `coindesk_rss` と `sec_press_releases_rss` の 2 ソースを対象にします。利用は公開 RSS の GET のみで、raw XML は保存しません。

採用した 2 本目:

- `sec_press_releases_rss`
- feed URL: `https://www.sec.gov/news/pressreleases.rss`
- 選定理由: 無料公開 RSS で、CoinDesk と比べて「暗号資産専門メディア」ではなく「規制当局の公式発表」であり、topic 中心・symbol 未割当・source 固有 metadata の扱いを検証しやすいため

CoinDesk との差分:

- CoinDesk は crypto media 記事で、category が市場/政策など記事寄り
- SEC は press release で、category が enforcement/rulemaking など制度寄り
- CoinDesk は BTC / ETH など symbol 推定しやすい記事が比較的多い
- SEC は symbol 未割当の topic-only 正規化が主になりやすい
- `source_id` はどちらも RSS `guid` を優先するが、SEC は link 末尾 fallback を持たせている

責務分離:

- collector: RSS GET と XML item 抽出
- adapter: item を `news_signals` schema へ正規化
- save: 正規化後 bundle と観測 summary のみ保存
- observe: 実行時間、取得件数、正規化成功/失敗、保存件数、欠損、source/symbol/asset/topic/category 分布、published_at 分布、warning、error を集計

source ごとの切り分け:

- 共通: fetch、RSS parse、保存、run_id 生成、observation 集計
- source 固有: default feed URL、item adapter、date/guid/link の解釈、簡易 topic/symbol 分類
- source 固有で吸収しきれない差分は `metadata` に逃がす

adapter 境界:

- 共通 collector 本体: [src/trade_simulator/news_collector.py](/home/kuru0101/crypto_simulator/crypto_simulator/src/trade_simulator/news_collector.py)
- source adapter 群: [src/trade_simulator/news_adapters.py](/home/kuru0101/crypto_simulator/crypto_simulator/src/trade_simulator/news_adapters.py)
- `pubDate` の UTC 正規化、`guid` / `link` fallback、source 固有分類は adapter 側で吸収する
- collector 側は source registry を見て adapter を呼び、共通保存と observation 集計だけを担当する

dedup key の生成規則:

- record ごとに `dedup_key` を持つ
- 生成種別は `source:sha1(prefix)` 形式
- seed は `source | published_at | locator_kind | locator_value | normalized_headline`
- `locator_kind` は `source_id` を優先し、無ければ `url`、さらに無ければ `headline`
- これは軽量 dedup 用であり、cross-source の完全な同一性保証は行わない

実行:

- `python3 scripts/run_news_collector.py --config config/news_collector.example.json`
- `python3 scripts/run_news_collector.py --config config/news_collector.sec.example.json`

保存:

- `var/news_signals/coindesk_rss/<run_id>/normalized.json`
- `var/news_signals/coindesk_rss/<run_id>/summary.json`
- `var/news_signals/sec_press_releases_rss/<run_id>/normalized.json`
- `var/news_signals/sec_press_releases_rss/<run_id>/summary.json`

観測できる項目:

- `run_id`
- `started_at`
- `ended_at`
- `duration_seconds`
- `source`
- `feed_url`
- `fetched_item_count`
- `normalized_success_count`
- `normalized_failure_count`
- `validation_failure_count`
- `saved_record_count`
- `missing_field_counts`
- `source_distribution`
- `symbol_distribution`
- `asset_distribution`
- `topic_distribution`
- `category_distribution`
- `published_at_by_date`
- `published_at_by_hour_utc`
- `warnings`
- `errors`
- `saved_paths`

source 増加で見えた制約:

- collector 設定はまだ 1 run 1 source 固定で、複数 source 同時収集は未対応
- RSS item 抽出は共通化できたが、topic / symbol / impact の推定は source 依存が強い
- `missing_field_counts` は source 固有 required field 定義に依存する
- dedup key は軽量比較用で、source 横断の同一イベント統合は次段に分離が必要

3 本目以降の前に入れるとよい最小修正:

- source ごとの item parser 差分が出た場合は adapter と同じ粒度で parser も source 側へ寄せる
- summary に dedup key の重複件数を追加する
- source 横断比較用の低コストな canonical topic ルールを追加する

adapter の score は今回は収集導線確認用の固定/簡易ヒューリスティクスです。高度な sentiment や impact 推定は次段に分離します。
