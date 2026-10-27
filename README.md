# hk-news-rss

公式RSSのない香港メディアの港聞を、非公式のRSS 2.0フィードとして公開する。

| フィード | 出典 | ファイル |
|---|---|---|
| 香港01 港聞 | https://www.hk01.com/zone/1/港聞 （API） | `docs/hk01-news.xml` |
| 東網 港聞 | https://hk.on.cc/hk/news/index.html （`district="香港"` のみ） | `docs/oncc-news.xml` |

- GitHub Actions（`.github/workflows/build-feeds.yml`）が1時間ごとに `make_feeds.py` を実行し、変更があれば `docs/` をコミットする。
- GitHub Pages は `main` ブランチの `/docs` から配信する。
- 各記事は見出し・リンク・公開時刻と、短いリード文（香港01のみ、200字まで）だけを含む。本文は含めない。
- 取得に失敗したときは前回のXMLを残す。サイト構造が変わると0件になり、ワークフローのログにエラーが出る。

ローカルで試す:

```bash
python3 make_feeds.py --out docs
```
