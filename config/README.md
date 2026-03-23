# Config

設定ファイルは example のみを管理します。
example は、最終対象未確定の間も `BTC/USDT` spot と `ETH/USDT` spot のような高流動性メジャー現物を想定した仮設定として扱います。初期資本の代表値は `100000`（10万円）です。
比較実行の最小例として `comparison.example.json` を置き、複数 case を name 付き list で並べる形式を採用します。
comparison example は threshold と cumulative-drop の両方を含み、`python3 scripts/run_comparisons.py --config config/comparison.example.json` を実行すると `final_value` / `trade_count` / `win_rate` と strategy パラメータをまとめて比較できます。
比較実行は `python3 scripts/run_comparisons.py --config config/comparison.example.json` で確認できます。
