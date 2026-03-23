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

## Minimal SNS Collector

今回の collector は `reddit_subreddit_new_json`、`youtube_channel_rss`、`hacker_news_public_api` を対象にします。いずれも公開 JSON / RSS endpoint への GET のみで、raw payload は保存しません。

採用した 1 本目:

- `reddit_subreddit_new_json`
- listing URL: `https://www.reddit.com/r/CryptoCurrency/new.json`
- 選定理由: 無料公開 JSON で取得でき、post 単位の timestamp / title / comment count / score を持つため、`sns_signals` の最小 schema と observation を検証しやすいため

採用した 2 本目:

- `youtube_channel_rss`
- feed URL pattern: `https://www.youtube.com/feeds/videos.xml?channel_id=<channel_id>`
- 選定理由: コメントではなく発信者側の upload を直接拾え、複数 channel を 1 source run に束ねても `sns_signals` と observation が崩れないかを検証しやすいため

採用した 3 本目:

- `hacker_news_public_api`
- list URL: `https://hacker-news.firebaseio.com/v0/topstories.json`
- item URL pattern: `https://hacker-news.firebaseio.com/v0/item/<id>.json`
- 選定理由: listing 型でも RSS 型でもない `一覧ID -> item` の二段取得であり、source 差分に対する collector / adapter / observation の最小構造を検証しやすいため

今回の割り切り:

- 取得対象は 1 subreddit の `new` listing に固定
- `mention_count` は `num_comments` を採用
- sentiment / activity / anomaly は収集導線確認用の簡易ヒューリスティクス
- BTC / ETH だけ symbol 推定し、それ以外は topic-only を基本にする

YouTube 側のデータ構造:

- `group_theme`: 何の分野を見る group か
- `publisher_type`: どういう主体が発信しているか
- `groups[]`: source run で束ねる channel 群
- `channels[]`: `channel_id` / `channel_label` / `publisher_type` / `theme_tags` / `enabled`

`group_theme` と `publisher_type` を分ける理由:

- 同じ分野でも、政府・大学・企業・メディアで発信の意味が異なるため
- 今後 group を増やしても、分野軸と主体軸を別々に観測できるため
- channel 単位で publisher_type を変えても、group 側の大きな分野分類を維持できるため

YouTube 側の最初の group:

- `crypto_investing_finance`: 市場・暗号資産・金融の空気を広く拾う
- `public_institutions`: 制度・政策・研究の原始的発信を見る
- `enterprises`: 大企業と成長企業の技術・クラウド・基盤投資を見る

YouTube 側の partial failure 方針:

- 一部 channel が失敗しても、他 channel から正規化済み record を作れた場合は run 全体を `completed` とする
- 失敗 channel は `warnings` と `errors` に残す
- 全 channel が取得失敗した場合のみ run 全体を `failed` とする

Hacker News 側の割り切り:

- 初期実装では `topstories` / `newstories` / `beststories` のみを対象にする
- 一覧から取った先頭 N 件だけ item を取得する
- 1 item = 1 signal とし、`mention_count` は `descendants` を採用する
- `score` / `descendants` / `story_type` は `metadata` と summary に残す

責務分離:

- collector: Reddit listing JSON / YouTube channel RSS / Hacker News list+item JSON の GET と item 抽出
- adapter: Reddit post / YouTube upload / Hacker News story を `sns_signals` schema へ正規化
- save: 正規化後 bundle と観測 summary のみ保存
- observe: 実行時間、取得件数、正規化成功/失敗、保存件数、欠損、source/group/group_theme/publisher_type/channel/symbol/topic 分布、mention_count 要約、timestamp 分布、warning、error を集計

source ごとの切り分け:

- 共通: fetch、保存、run_id 生成、observation 集計
- Reddit 固有: listing URL、JSON parse、post adapter
- YouTube 固有: channel feed URL、Atom feed parse、upload adapter、group/channel config 解釈
- Hacker News 固有: story list URL、item URL template、一覧 ID 取得、item JSON parse、story adapter
- source 固有で吸収しきれない差分は `metadata` に逃がす

adapter 境界:

- 共通 collector 本体: [src/trade_simulator/sns_collector.py](/home/kuru0101/crypto_simulator/crypto_simulator/src/trade_simulator/sns_collector.py)
- source adapter 群: [src/trade_simulator/sns_adapters.py](/home/kuru0101/crypto_simulator/crypto_simulator/src/trade_simulator/sns_adapters.py)
- Reddit の `created_utc` 正規化、topic/symbol 推定、`mention_count` / score 群の簡易生成は adapter 側で吸収する
- YouTube の `published` 正規化、group/channel metadata 付与、topic/symbol 推定、簡易 score 生成も adapter 側で吸収する
- Hacker News の `time` 正規化、`score` / `descendants` / `story_type` の写像、topic/symbol 推定も adapter 側で吸収する
- collector 側は source registry を見て adapter を呼び、共通保存と observation 集計だけを担当する

dedup key の生成規則:

- record ごとに `dedup_key` を持つ
- 生成種別は `source:sha1(prefix)` 形式
- seed は `source | timestamp | entity_key | locator_kind | locator_value`
- `locator_kind` は `source_id` を優先し、無ければ `permalink`
- これは軽量 dedup 用であり、cross-source の完全な同一性保証は行わない
- run summary の `duplicate_count` は、同一 run 内で `dedup_key` が重複した 2 件目以降の件数

実行:

- `python3 scripts/run_sns_collector.py --config config/sns_collector.reddit.example.json`
- `python3 scripts/run_sns_collector.py --config config/sns_collector.youtube.example.json`
- `python3 scripts/run_sns_collector.py --config config/sns_collector.hacker_news.example.json`

保存:

- `var/sns_signals/reddit_subreddit_new_json/<run_id>/normalized.json`
- `var/sns_signals/reddit_subreddit_new_json/<run_id>/summary.json`
- `var/sns_signals/youtube_channel_rss/<run_id>/normalized.json`
- `var/sns_signals/youtube_channel_rss/<run_id>/summary.json`
- `var/sns_signals/hacker_news_public_api/<run_id>/normalized.json`
- `var/sns_signals/hacker_news_public_api/<run_id>/summary.json`

観測できる項目:

- `run_id`
- `started_at`
- `ended_at`
- `duration_seconds`
- `signal_type`
- `source`
- `listing_url`
- `fetched_item_count`
- `normalized_success_count`
- `normalized_failure_count`
- `validation_failure_count`
- `saved_record_count`
- `duplicate_count`
- `missing_field_counts`
- `source_distribution`
- `group_distribution`
- `group_theme_distribution`
- `publisher_type_distribution`
- `channel_distribution`
- `symbol_distribution`
- `topic_distribution`
- `mention_count_summary`
- `score_summary`
- `comment_count_summary`
- `story_type_distribution`
- `timestamp_by_date`
- `timestamp_by_hour_utc`
- `warnings`
- `errors`
- `saved_paths`

source 増加で見えた制約:

- collector 設定はまだ 1 run 1 source 固定で、複数 source 同時収集は未対応
- topic / symbol 推定は source 依存が強く、今回は BTC / ETH 以外を topic-only に寄せている
- sentiment / activity / anomaly は簡易ヒューリスティクスであり、分析用スコアの完成形ではない
- Reddit 固有の rate limit や listing 粒度差分を吸収する共通抽象はまだ持たない
- YouTube では channel upload 自体を 1 mention とみなしており、視聴者反応や動画性能は使っていない
- group は config 主導なので、group_theme の粒度がぶれると observation の比較軸もぶれる
- Hacker News は story list と item の二段取得なので、item fetch 数と latency が source ごとに増えやすい
- `descendants` を `mention_count` とみなすのは近似であり、コメント内容の分析はしていない

## Minimal News Collector

今回の collector は `coindesk_rss`、`sec_press_releases_rss`、`federal_reserve_press_releases_rss` の 3 ソースを対象にします。利用は公開 RSS の GET のみで、raw XML は保存しません。

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

採用した 3 本目:

- `federal_reserve_press_releases_rss`
- feed URL: `https://www.federalreserve.gov/feeds/press_all.xml`
- 選定理由: Federal Reserve の公式 RSS で、SEC と同じ公的発表でも金融政策・銀行規制寄りの category を持ち、CoinDesk / SEC と異なる topic 分布を確認しやすいため

既存 2 source との差分:

- CoinDesk は crypto media の記事で、asset / symbol 推定しやすい
- SEC は規制当局の執行・ルール系発表で、crypto regulation topic に寄りやすい
- Federal Reserve は中央銀行の monetary policy / banking policy 系 category を持ち、crypto 非依存 topic-only 正規化が中心になりやすい
- Federal Reserve は `guid` に URL が入るケースを想定し、adapter 側でそのまま locator に使える

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
- run summary の `duplicate_count` は、同一 run 内で `dedup_key` が重複した 2 件目以降の件数

実行:

- `python3 scripts/run_news_collector.py --config config/news_collector.example.json`
- `python3 scripts/run_news_collector.py --config config/news_collector.sec.example.json`
- `python3 scripts/run_news_collector.py --config config/news_collector.federal_reserve.example.json`

保存:

- `var/news_signals/coindesk_rss/<run_id>/normalized.json`
- `var/news_signals/coindesk_rss/<run_id>/summary.json`
- `var/news_signals/sec_press_releases_rss/<run_id>/normalized.json`
- `var/news_signals/sec_press_releases_rss/<run_id>/summary.json`
- `var/news_signals/federal_reserve_press_releases_rss/<run_id>/normalized.json`
- `var/news_signals/federal_reserve_press_releases_rss/<run_id>/summary.json`

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
- `duplicate_count`
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
- 同じ RSS でも item の追加フィールド差分が大きくなった場合は、共通 parser のままでは追従しづらくなる可能性がある

次の最小整理候補:

- source ごとの item parser 差分が出た場合は adapter と同じ粒度で parser も source 側へ寄せる
- source 横断比較用の低コストな canonical topic ルールを追加する
- duplicate key の分布を summary に残す

adapter の score は今回は収集導線確認用の固定/簡易ヒューリスティクスです。高度な sentiment や impact 推定は次段に分離します。
