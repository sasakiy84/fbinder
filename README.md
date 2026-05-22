# library-presentator

`library-presentator` は、任意の入力ディレクトリに置いた Markdown / CSV / 静的ファイルを、JavaScript なしで読める静的 HTML サイトへ変換する軽量 CLI です。

## 使い方

依存関係を同期します。

```sh
uv sync
```

サイトを生成します。

```sh
uv run python main.py build --source ./content --output ./public
```

入力ファイルを検証します。

```sh
uv run python main.py check --source ./content
```

変更を監視して再生成します。

```sh
uv run python main.py watch --source ./content --output ./public --interval 1.0
```

生成結果は `public/index.html` から確認できます。ローカルで配信して確認する場合は、次のように Python の簡易サーバーを使えます。

```sh
python -m http.server 8000 --directory public
```

## 入出力

- `*.md` は HTML ページへ変換します。front matter の `title`、最初の `# 見出し`、ファイル名の順でページタイトルを決めます。
- `*.csv` は `<table>` を持つ HTML ページへ変換します。`http://` または `https://` で始まるセルはリンクにします。
- Markdown / CSV の詳細ページには生成日と Markdown コピーボタンを表示します。Markdown ページでは本文見出しから目次も生成します。
- その他のファイルは相対パスを保ってコピーします。
- 回復可能なエラーがある場合は、生成を継続し、`errors.html` に一覧を出します。
- `--output` が `--source` の配下にある構成は、生成物を再帰的に読み込む危険があるため拒否します。

## フォルダ

- `templates/page.html`: 生成 HTML の共通テンプレートです。
- `static/style.css`: 生成先の `static/style.css` へコピーする既定 CSS です。
- `static/script.js`: 生成先の `static/script.js` へコピーする、Markdown コピー用の JavaScript です。
- `tests/`: 静的サイト生成の振る舞いを確認する unit test です。
