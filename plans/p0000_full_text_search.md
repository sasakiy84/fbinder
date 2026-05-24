# 全文検索機能の実装計画

この文書は、fbinder が生成する静的サイトに全文検索機能を追加するための実装計画である。実装前に、対象範囲、設計方針、変更ファイル、検証方法を確認できるようにする。

## 目的

生成済みの静的 HTML サイト内で、Markdown と CSV 由来のページをブラウザから検索できるようにする。

fbinder は nginx などの静的ファイルサーバーで配信できることを前提にしているため、検索機能もサーバー側 API を必要としない構成にする。

## 方針

build 時に検索用 JSON を生成し、ブラウザ側 JavaScript で検索する。

この方式により、次の性質を保つ。

- nginx の設定を変更せずに動く。
- systemd の watch 運用を変えずに、再生成時に検索インデックスも更新できる。
- 外部検索サーバーや DB を追加しない。
- JavaScript が無効な環境でも、既存のページ閲覧は壊さない。

## 対象範囲

対象に含める。

- Markdown ページのタイトルと本文。
- CSV ページのタイトル、ヘッダー、セルの値。
- `search-index.json` の生成。
- 全ページ共通の検索フォームと検索結果表示。
- 検索 UI 用の CSS。
- 検索インデックス生成の unit test。
- README と関連 docs の更新。

対象から外す。

- PDF、画像、添付ファイル本体の内容検索。
- サーバー側検索 API。
- 形態素解析や外部検索ライブラリの導入。
- 検索結果の永続化やアクセスログ。

## 出力ファイル

検索インデックスは出力ディレクトリ直下に置く。

```text
public/
  index.html
  search-index.json
  static/
    script.js
    style.css
```

JSON の要素は次の形を基本にする。

```json
{
  "version": 1,
  "items": [
    {
      "title": "Trip Plan",
      "url": "report.html",
      "kind": "markdown",
      "updated": "2026-05-24",
      "text": "Trip Plan Body text."
    }
  ]
}
```

`url` は `search-index.json` から見た出力相対パスではなく、検索 UI を表示しているページから解決できるように JavaScript 側で相対 URL を作る。インデックス側には出力ルートからの相対パスを入れる。

## 検索対象テキスト

Markdown は front matter を除いた本文を検索対象にする。タイトルは別フィールドに保持し、検索対象にも含める。

CSV は header と cell を plain text として連結する。HTML table の markup は検索対象に入れない。

検索インデックスには HTML を入れない。検索結果の描画時に DOM API で text node を作り、HTML injection を避ける。

## 検索 UI

`templates/page.html` の header または main 冒頭に、全ページ共通の検索フォームを置く。

基本構造。

```html
<form class="site-search" role="search">
  <label for="site-search-input">検索</label>
  <input id="site-search-input" name="q" type="search" autocomplete="off">
  <p id="site-search-status" class="search-status" aria-live="polite"></p>
  <ul id="site-search-results" class="search-results"></ul>
</form>
```

実装では、既存の 1 カラム表示と読みやすさを優先する。検索 UI は補助機能であり、ページ本文を押しのけすぎない配置にする。

## JavaScript

`static/script.js` に既存の Markdown コピー処理を残したまま、検索処理を追加する。

処理方針。

- 初期表示時には `search-index.json` を fetch しない。
- 検索欄に入力されたタイミングで lazy load する。
- 入力イベントは debounce する。
- 検索語は `normalize("NFKC")` と `toLowerCase()` で正規化する。
- 空白区切りの複数語は AND 検索にする。
- 日本語のように空白区切りがない語は、全文の部分一致で検索する。
- 検索状態は URL のクエリパラメータを Single Source of Truth とする。
- 検索語は `q`、結果ページ番号は `page` で表す。
- 検索結果はページネーションで全件表示できるようにする。
- 結果件数は `aria-live="polite"` で通知する。

検索処理が重くなる場合は、ループ中に main thread へ yield する余地を残す。ただし初期実装では、依存ライブラリなしの単純検索を優先する。

## URL とページネーション

検索 UI の表示状態は URL のクエリパラメータから復元する。DOM 内の入力値や JavaScript の変数は URL を反映した派生状態として扱う。

使うパラメータ。

- `q`: 検索語。
- `page`: 検索結果のページ番号。1 始まり。

例。

```text
/?q=旅行&page=2
/reports/?q=csv&page=1
```

動作方針。

- ページ読み込み時に `location.search` を読み、検索欄、結果、ページネーションを描画する。
- 検索欄の入力が変わったら、`page=1` に戻して `history.pushState` または `history.replaceState` で URL を更新する。
- ページネーションのリンクは通常の `<a href="?q=...&page=...">` として生成する。
- JavaScript 有効時はクリックを捕捉して `history.pushState` で遷移なしに更新してもよい。
- ブラウザの戻る / 進むでは `popstate` を受け、URL から検索状態を再描画する。
- `page` が不正値、0 以下、または最終ページを超える場合は 1 ページ目または最終ページに補正する。
- `q` が空の場合は検索結果とページネーションを表示しない。

1 ページあたりの件数は固定値を実装側で持つ。これは表示単位であり、検索結果の総数を制限するものではない。

## スニペット

検索結果にはタイトル、種類、更新日、短い本文スニペットを表示する。

スニペットは一致位置の前後を抜き出し、該当語を `<mark>` で強調する。HTML 文字列を直接連結せず、DOM API で構築する。

## CSS

`static/style.css` に検索 UI のスタイルを追加する。

追加する主な class。

- `.site-search`
- `.search-status`
- `.search-results`
- `.search-result`
- `.search-result-meta`
- `.search-snippet`
- `.search-pagination`

既存の色変数と余白設計を使い、検索 UI だけが強く目立ちすぎないようにする。

## 実装手順

1. `RenderedPage` に検索用 plain text を保持するフィールドを追加する。
2. Markdown 変換時に front matter を除いた本文テキストを保持する。
3. CSV 変換時に header と cell の plain text を保持する。
4. build 時に `search-index.json` を生成して出力する。
5. `templates/page.html` に検索フォームを追加する。
6. `static/script.js` に lazy load 型の検索処理を追加する。
7. `static/style.css` に検索 UI のスタイルを追加する。
8. unit test を追加する。
9. README に検索仕様を追記する。
10. 必要に応じて `docs/` に検索機能の設計文書を追加する。

## テスト方針

unit test で確認する。

- `search-index.json` が生成される。
- Markdown のタイトルと本文が検索インデックスに入る。
- Markdown の front matter は本文検索テキストに混ざらない。
- CSV の header と cell が検索インデックスに入る。
- static file 本体は検索インデックスに入らない。
- index ページや errors ページは検索対象に入らない。
- サブディレクトリのページ URL が正しく出力される。
- 検索 UI が `q` と `page` を使う設計になっている。

可能なら生成済みサンプルを使い、ブラウザ上で次も確認する。

- 検索欄に入力すると結果が表示される。
- 結果リンクから対象ページへ移動できる。
- 検索すると URL の `q` が更新される。
- ページネーションで URL の `page` が更新される。
- URL の `q` と `page` から検索状態が復元される。
- ブラウザの戻る / 進むで検索状態が復元される。
- 空検索では結果を表示しない。
- 該当なしの場合に状態文が表示される。
- キーボード操作で検索欄と結果リンクへ移動できる。

## 確認コマンド

```sh
uv run python -m unittest
uv run python main.py build --source ./sample-content --output ./public
```

UI の表示確認が必要な場合は、次でローカル配信する。

```sh
python -m http.server 8000 --directory public
```

## リスク

検索インデックスはサイト規模に比例して大きくなる。初期実装では全件を単一 JSON にするが、巨大化した場合は次の改善を別タスクとして検討する。

- ページごと、またはディレクトリごとの分割インデックス。
- 検索対象テキストの長さ制限。
- Web Worker への検索処理移動。
- 外部ライブラリによるランキング改善。

## 実装外の改善案

- S1: 添付ファイル名だけを検索対象にする。
- S2: PDF のテキスト抽出を別処理として追加する。
- S3: 検索結果のランキングをタイトル一致優先にする。
