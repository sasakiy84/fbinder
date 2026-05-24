# 静的サイト生成ツールの設計案

この文書は、このリポジトリを単体で使える軽量な静的サイト生成ツールとして成立させるための設計と実装方針をまとめる。特定の入力ディレクトリに置かれた Markdown / CSV / 静的ファイルを HTML に変換し、出力ディレクトリへ配置する。

2026-05-24 時点では、P1 から P3 のうち `build` / `check` / `watch`、Markdown / CSV 変換、静的ファイルコピー、トップページとディレクトリ別 index、回復可能なエラー一覧、HTML テンプレート、単一 CSS のコピー、検索インデックス生成とブラウザ側全文検索を実装済みである。設定ファイル導入は未実装であり、P4 以降の対象とする。

## 目的

このツールは、ファイルベースで管理される情報を、軽量な静的 HTML サイトとして公開・閲覧できるようにする。

中心に置く性質は次の通り。

- 入力は通常のディレクトリであり、名前は利用者が指定できる。
- Markdown と CSV を主要な入力形式として扱う。
- 生成物は静的 HTML / CSS / 添付ファイルであり、Nginx などの静的ファイルサーバーで配信できる。
- watch コマンドで入力ディレクトリを OS のファイル通知により監視し、変更時に再生成できる。
- 重いフレームワークを使わず、依存は最小限にする。
- JavaScript なしでも読める HTML を生成する。
- 変換できないファイルがあっても生成全体は止めず、エラー一覧を HTML として出力する。

このツールは特定の業務フローやエージェントシステムに閉じない。研究メモ、資料一覧、CSV 台帳、調査レポート、エージェントの成果公開など、同じ「ファイルを置くと読めるサイトになる」用途に広く使えることを目指す。

## 対象範囲

対象に含める。

- 入力ディレクトリ配下の Markdown / CSV / 静的ファイルの走査。
- Markdown から HTML への変換。
- CSV から HTML table への変換。
- トップページとディレクトリ別 index の生成。
- Markdown / CSV 由来ページの検索インデックス生成。
- CSS などサイト共通ファイルの生成またはコピー。
- ファイル変更を検知して再生成する watch 処理。
- 入力の基本検証を行う check 処理。
- 変換・コピーに失敗したファイルを集約したエラー一覧ページの生成。

対象から外す。

- Slack Bot やブラウザ拡張など、入力ファイルを作る側の実装。
- Google Drive / rclone など、同期の実行責務。
- Nginx の reload や OS サービス管理。
- PDF など添付ファイルの内容解析。
- 調査タスクや要約タスクを実行するエージェント本体。

外部ツールとの連携は、ファイル境界で行う。外部プロセスが入力ディレクトリにファイルを書き、このツールが HTML として出力する。

## 基本モデル

```text
source_dir/
  -> Markdown / CSV / assets を配置
    -> fbinder build または watch
      -> output_dir/
        -> HTML / CSS / copied assets を生成
          -> file server / Nginx alias / local browser で閲覧
```

`source_dir` と `output_dir` は CLI オプションで指定する。特定のフォルダ名を前提にしない。

```text
uv run python main.py build --source ./content --output ./public
uv run python main.py watch --source ./content --output ./public --interval 1.0
uv run python main.py check --source ./content
```

## 想定ユースケース

### Markdown レポート公開

利用者が `source_dir/reports/202605231215_trip_plan.md` のような Markdown を保存する。ツールは HTML に変換し、出力側では `reports/202605231215_trip_plan.html` として閲覧できるようにする。

### CSV 台帳の閲覧

利用者が `source_dir/data/books.csv` や `source_dir/data/papers.csv` のような CSV を保存する。ツールは `<table>` を持つ HTML に変換し、ブラウザで一覧できるようにする。

### エージェントの成果公開

外部のエージェントが調査結果、要約、抽出データ、確認済みリンクを Markdown / CSV として入力ディレクトリに保存する。ツールはそれを静的サイトとして生成し、ユーザーがブラウザで確認できるようにする。エージェントの推論や検索処理はこのツールの責務に含めない。

### 静的ファイル置き場

PDF、画像、BibTeX、テキストファイルなどを入力ディレクトリに置く。ツールは内容を解析せず、出力ディレクトリへコピーし、index からリンクできるようにする。

## ディレクトリ構成

入力ディレクトリは任意の名前でよい。以下は例であり、固定仕様ではない。

```text
content/
  index.md
  reports/
    202605231215_trip_plan.md
  data/
    books.csv
    papers.csv
  pages/
    library_science.md
  files/
    2024_Yamada_Digital_Libraries.pdf
    references.bib
  assets/
    images/

public/
  index.html
  search-index.json
  reports/
  data/
  pages/
  files/
  assets/
  static/
    style.css
```

入力ディレクトリは人間や外部エージェントが編集する場所、出力ディレクトリは生成物だけを置く場所とする。出力ディレクトリは原則として手で編集しない。

出力ディレクトリが入力ディレクトリ配下にあると再帰的に生成物を拾う危険があるため、`check` と `build` で禁止する。

## 入力ファイル

### Markdown

Markdown は通常の記事、レポート、説明ページの基本形式とする。

front matter は任意とする。

```md
---
title: ポーランド旅行計画
date: 2026-05-23 12:15
tags: [travel, report]
---

# ポーランド旅行計画
```

title の決定順。

1. front matter の `title`
2. 最初の `# 見出し`
3. ファイル名から作った表示名

最初の実装では、front matter は簡易 parser で扱う。YAML の完全な仕様は実装しない。`key: value` と、必要なら `tags: [a, b]` 程度に絞る。

Markdown の raw HTML は初期実装では無効化またはエスケープする。外部プロセスが生成したファイルを入力にできるため、XSS を避けることを優先する。

### CSV

CSV は一覧性が重要なデータに使う。

```csv
title,authors,year,url,notes
Example Paper,"Yamada, Sato",2026,https://example.com,確認済み
```

CSV の扱い。

- Python 標準ライブラリの `csv` で読む。
- 1 行目を header とする。
- HTML では `<table>`、`<caption>`、`<th scope="col">` を使う。
- セルの値は HTML エスケープする。
- `http://` または `https://` で始まる値は自動リンクにする。
- カラム名の意味はツール側で固定しない。

### 静的ファイル

Markdown / CSV 以外のファイルは、原則としてそのままコピーする。

対象例。

- PDF
- 画像
- BibTeX
- plain text
- JSON

初期実装では内容を解析しない。必要になったら、拡張子別のレンダラーを追加する。

コピーには Python 標準ライブラリの `shutil.copy2` を使う。ファイル内容とともに mtime などのメタデータを可能な範囲で保持でき、今回の用途では外部コマンドや追加ライブラリを使う理由が薄い。ディレクトリ単位のコピーは、出力パス衝突やエラー記録を扱いやすくするため、再帰走査した各ファイルを個別に `copy2` する。

## 出力 HTML

生成 HTML は、軽量で読みやすい静的ドキュメントにする。

必須方針。

- `<!DOCTYPE html>` を出す。
- `<html lang="ja">` を既定とし、将来設定で変更可能にする。
- `<meta charset="utf-8">` と `<meta name="viewport" content="width=device-width, initial-scale=1.0">` を出す。
- `<header>`、`<nav>`、`<main>` を使う。
- 各ページの `<h1>` は 1 つにする。
- 見出し階層を不自然に飛ばさない。
- 一覧は `<ul>`、CSV は `<table>` を使う。
- CSV table には `<caption>` を付ける。
- JavaScript なしで全ページを閲覧可能にする。
- CSS は `static/style.css` に置き、生成時に出力先の `static/style.css` へコピーする。
- Markdown コピー用の JavaScript は `static/script.js` に置き、生成時に出力先の `static/script.js` へコピーする。
- Markdown / CSV 由来ページを検索するための `search-index.json` を出力ディレクトリ直下に生成する。
- 共通の HTML 外枠は `templates/page.html` に置き、ページごとの title、nav、本文を差し込む。
- Markdown / CSV の詳細ページには、build 時点の生成日を `<time>` で表示する。
- Markdown / CSV の詳細ページには、Markdown としてコピーするボタンを表示する。Markdown 入力は front matter を除いた本文をコピーし、CSV 入力は Markdown table に変換した内容をコピーする。JavaScript が動かない環境でも本文閲覧は成立させる。
- Markdown の詳細ページには、本文見出しから目次を生成し、見出しへのページ内リンクを出す。
- 変換・コピー時の回復可能なエラーは `errors.html` に一覧表示する。

初期実装では検索や絞り込みは入れない。静的 HTML とブラウザ標準のページ内検索で足りる状態を先に作る。

## デザイン方針

見た目はシンプルにし、読むときの負荷を下げる。装飾で印象を作るより、長い Markdown レポート、CSV table、エラー一覧、添付ファイル一覧を疲れずに確認できることを優先する。

基本方針。

- レイアウトは 1 カラムを基本にする。
- 本文幅は広げすぎず、`max-width` で読みやすい行長に抑える。
- フォントはシステムフォントを使い、Web font は使わない。
- 行間はやや広めにし、段落間の余白を安定させる。
- 色数は少なくし、背景、本文、補助テキスト、リンク、罫線、エラー表示に用途を絞る。
- 白背景またはそれに近い明るい背景を既定にする。
- 見出しはサイズ差と余白で階層を示し、過度な太字や装飾を避ける。
- リンクは色だけに頼らず、本文中では下線を残す。
- 表は罫線を控えめにし、行の区切り、header、横スクロールの扱いを読みやすくする。
- コードブロックと `<pre>` は横スクロール可能にし、ページ全体の横幅を壊さない。
- エラー一覧は目立たせるが、全体のトーンから浮かせすぎない。
- アニメーション、装飾画像、カード風の多用、濃い背景、強いグラデーションは使わない。

CSS は最初からテーマ機構を持たせず、`static/style.css` に単一の落ち着いた既定スタイルを置く。将来的に必要になった場合だけ、`prefers-color-scheme` によるダークモードや設定ファイルによる色変更を検討する。

HTML の共通構造は `templates/page.html` に置く。テンプレートは生成ページの `<head>`、site nav、`<main>` を受け持ち、Markdown / CSV / index / errors の本文 HTML はツール側で HTML エスケープ済みの断片として差し込む。

ページ種別ごとの方針。

- Markdown ページ: 本文の可読性を最優先にし、見出し、段落、リスト、引用、コードブロックの余白を整える。
- CSV ページ: 表を主役にし、caption、列見出し、横スクロール、長い URL の折り返しを整える。
- 詳細ページ: 生成日と Markdown コピーボタンをタイトル直下に控えめに表示し、目次は本文を読む前の補助ナビゲーションとして置く。
- index ページ: ディレクトリとファイルを淡々と一覧し、階層と更新日時が分かるようにする。
- errors ページ: ファイル名、処理種別、エラー内容を表で確認できるようにする。
- 検索 UI: 全ページ共通で表示し、検索語 `q` とページ番号 `page` を URL query として扱う。

## CLI 設計

初期実装では package entry point を作らず、`uv run python main.py` で実行する。

```text
uv run python main.py build --source ./content --output ./public
uv run python main.py watch --source ./content --output ./public --interval 1.0
uv run python main.py check --source ./content
```

### build

`build` は入力ディレクトリ全体を読み、出力ディレクトリを生成する。

処理の流れ。

1. 入力ディレクトリを走査する。
2. Markdown / CSV / 静的ファイルを分類する。
3. Markdown を HTML に変換する。
4. CSV を HTML table に変換する。
5. ディレクトリ別 index とトップページを生成する。
6. `search-index.json` を生成する。
7. CSS と静的ファイルを出力する。
8. 回復可能なエラーがあれば `errors.html` を生成する。
9. 一時ディレクトリに生成してから出力ディレクトリと入れ替える。

出力途中の壊れた状態を配信しないため、生成は `output_dir.tmp` に行う。成功したら既存の `output_dir` と入れ替える。失敗した場合は既存の出力を残す。

Markdown の構文エラー、CSV の行不整合、静的ファイルのコピー失敗、出力パス衝突など、個別ファイルに閉じる問題は回復可能なエラーとして扱う。該当ファイルの出力はスキップし、他のファイルの生成は継続する。入力ディレクトリが存在しない、出力ディレクトリが入力ディレクトリ配下にある、一時ディレクトリを作れないなど、生成全体の安全性に関わる問題だけを fatal error として扱う。

### watch

`watch` は入力ディレクトリを監視し、変更があれば `build` を実行する。

初期実装から `watchfiles` を使う。`watchfiles` は Rust の Notify library を通じて OS のファイルシステム通知を扱うため、Linux の inotify、macOS の FSEvents、Windows の ReadDirectoryChangesW など、カーネル側の通知機構を活用できる。Python 3.13 に対応し、直近リリースも確認できるため、メンテナンス状況の面でも採用しやすい。

処理の流れ。

1. `watchfiles.watch(source_dir)` で変更イベントを受け取る。
2. 変更があれば短く debounce する。
3. 生成物や一時ディレクトリ由来のイベントは無視する。
4. `build` を実行する。
5. 成功、回復可能なエラー数、fatal error をログに出す。

`watchdog` も安定した選択肢だが、今回の用途では `watchfiles` の API が単純で、Python 3.13 以降の対応状況もよい。`watchfiles` が動かない特殊環境では、将来 `--watch-mode polling` のような明示的な fallback を追加する。

### check

`check` は入力と設定の問題を検出する。

初期チェック項目。

- 入力ディレクトリが存在する。
- 出力ディレクトリが入力ディレクトリ配下ではない。
- CSV の header が空ではない。
- CSV の各行のカラム数が header と合っている。
- Markdown の title を決定できる。
- 同じ出力パスに複数の入力が衝突しない。
- コピー対象ファイルが出力先の予約パスと衝突しない。

`check` は検証専用なので、問題があれば non-zero exit code を返す。一方で `build` は回復可能なエラーがあってもサイト生成を継続し、`errors.html` を生成する。

## 設定

最初は CLI オプションだけで動くようにする。設定ファイルは P2 以降で追加する。

将来的な設定ファイル案。

```toml
[site]
title = "fbinder"
language = "ja"
base_url = "/"

[paths]
source = "content"
output = "public"

[rendering]
raw_html = false
```

設定ファイルを導入する場合も、CLI オプションで上書きできるようにする。

## 依存関係

基本は Python 標準ライブラリを使う。ただし、Markdown 変換とファイル監視は、実用性と保守性のために外部ライブラリを採用する。

標準ライブラリで足りるもの。

- ファイル走査: `pathlib`
- CSV: `csv`
- HTML エスケープ: `html`
- ファイルコピー: `shutil`
- CLI: `argparse`
- 日時: `datetime`
- ログ: `logging`
- 設定ファイル: `tomllib`

採用する外部ライブラリ。

- Markdown 変換: `markdown-it-py`
- ファイル監視: `watchfiles`

### Markdown 変換ライブラリ

Markdown 変換には `markdown-it-py` を採用する。

採用理由。

- 2026-05-22 時点で PyPI の最新リリースは 2026-05-07 の `4.2.0`。
- PyPI classifier が `Development Status :: 5 - Production/Stable`。
- Python 3.13 に対応している。
- CommonMark を基本にした parser で、セキュリティ設定もしやすい。
- `mistune` も直近リリースがあり有力だが、PyPI classifier は `Development Status :: 4 - Beta` であり、今回の「単体ツールの安定した既定値」としては `markdown-it-py` を優先する。

実装では raw HTML を無効にする設定を既定にする。front matter は依存を増やさず、ツール側の簡易 parser で処理する。

### ファイル監視ライブラリ

ファイル監視には `watchfiles` を採用する。

採用理由。

- 2026-05-22 時点で PyPI の最新リリースは 2026-05-18 の `1.2.0`。
- Python 3.13 に対応している。
- Rust の Notify library 経由で OS のファイル通知を扱う。
- API が単純で、今回必要な「変更を受けて build を再実行する」用途に合う。
- `watchdog` も `Production/Stable` で成熟しているが、最新リリースが 2024-11-01 で、今回の軽量な watch 用途では `watchfiles` のほうが小さく扱いやすい。

`watchfiles` は多くの環境で wheel が提供されるが、未対応環境では Rust toolchain が必要になる可能性がある。その場合に備え、将来の fallback として明示的な polling mode を設計余地として残す。

### 採用しない案: Markdown を限定仕様として自前変換する

メリット。

- 依存が増えない。
- 仕様を完全に制御できる。

デメリット。

- Markdown の期待挙動との差が大きくなりやすい。
- リンク、リスト、コードブロックの実装だけでも保守負荷が高い。
- 将来的に結局ライブラリを入れる可能性が高い。

### 採用しない案: Markdown は変換せず `<pre>` として表示する

メリット。

- 最小実装にできる。
- XSS のリスクを抑えやすい。

デメリット。

- レポートやメモの閲覧体験が弱い。
- 静的サイト生成ツールとしての価値が下がる。

## エラー処理

変換できないファイルがあっても、サイト全体の生成は止めない。ファイル単位で失敗を記録し、最後に `errors.html` を生成する。

エラー一覧に含める情報。

- 入力ファイルの相対パス。
- 処理種別: Markdown 変換、CSV 変換、静的ファイルコピー、出力パス解決など。
- エラー種別。
- 短い説明。
- 可能なら発生行番号。

`errors.html` 自体も通常の HTML テンプレートで生成し、トップページと nav からリンクする。エラーが 0 件の場合は `errors.html` を生成しない。

build の終了コードは、出力ディレクトリを更新できた場合は回復可能なエラーがあっても `0` とする。CI や厳格な運用向けには、将来 `--strict` を追加し、回復可能なエラーでも non-zero にできる余地を残す。

## 静的配信との境界

このツールは出力ディレクトリにファイルを置くだけにする。Nginx などのサーバー設定や reload は責務に含めない。

Nginx alias の例。

```nginx
location /docs/ {
    alias /srv/fbinder/public/;
    index index.html;
}
```

ローカル確認では、出力された `index.html` をブラウザで開くか、Python の簡易サーバーで確認する。

```text
python -m http.server 8000 --directory public
```

## 外部同期との境界

Google Drive や他のストレージ同期は、このツールの外側で行う。

例。

- rclone が入力ディレクトリへファイルを同期する。
- 別プロセスが Markdown レポートを入力ディレクトリに保存する。
- このツールの watch が変更を検知して HTML を再生成する。

このツール自身は rclone を実行しない。同期失敗、認証、競合解決は同期側の責務とする。

## 実装計画

### P1: 最小の静的生成

- `build` コマンドを作る。
- `*.md` を HTML に変換する。
- `*.csv` を table HTML に変換する。
- その他のファイルをコピーする。
- トップページに全ページと静的ファイルへのリンク一覧を出す。
- 回復可能なエラーを集約して `errors.html` を生成する。
- CSS は最小の読みやすいスタイルだけにし、長文と表を読む負荷を下げる。
- `uv run python main.py build --source ./content --output ./public` で動かす。

### P2: watch と check

- `watchfiles` ベースの `watch` を追加する。
- `check` コマンドを追加する。
- 出力パス衝突、CSV 不正、title 欠落を検出する。
- build 失敗時に既存出力を壊さない。

### P3: index 生成の強化

- ディレクトリごとの index を生成する。
- 更新日時順の一覧を生成する。
- Markdown / CSV / 静的ファイルを分類して表示する。
- CSV ページから元 CSV へのリンクを出す。

### P4: 設定ファイルと運用ドキュメント

- `fbinder.toml` を導入する。
- Nginx alias 前提のサンプル設定を docs に追加する。
- 外部同期やエージェント出力を入力にする運用例を docs に追加する。

## 決定事項

- Markdown 変換は `markdown-it-py` を使う。
- ファイル監視は `watchfiles` を使う。
- 静的ファイルコピーは `shutil.copy2` を使う。
- 出力ディレクトリは生成物として扱い、リポジトリ管理対象にしない。
- slug は入力ファイル名を保ち、リンク生成時に URL encode する。
- CSV 内の `http://` / `https://` は自動リンクにする。
- 設定ファイルは P2 以降に導入し、P1 は CLI オプションだけで動かす。
- 初期実装の実行方法は `uv run python main.py` とする。必要になったら package entry point として `fbinder` を追加する。
- 出力パス衝突時は、ソート順で先に処理された入力を採用し、後続の衝突ファイルをスキップして `errors.html` に記録する。
- デザインはシンプルな 1 カラムを基本にし、システムフォント、控えめな色、読みやすい本文幅を既定にする。

## テスト方針

最初の実装では、変換ロジックに対して unit test を置く。

テストケース案。

- Markdown の `# title` から HTML title と h1 が決まる。
- front matter がある場合に title が優先される。
- CSV が `<table>`、`<caption>`、`<th scope="col">` に変換される。
- CSV 内の `http://` / `https://` がリンクになる。
- HTML 特殊文字がエスケープされる。
- 静的ファイルが相対パスを保ってコピーされる。
- 出力パス衝突を検出できる。
- 変換できない Markdown / CSV があっても他のページは生成され、`errors.html` に記録される。
- 出力ディレクトリが入力ディレクトリ配下の場合に失敗する。
- build 失敗時に既存出力を壊さない。
- `watchfiles` の変更イベントを受けて build が呼ばれる。
- `reports/202605231215_trip_plan.md` が期待する URL に変換される。
- 生成 HTML の本文幅、表の横スクロール、コードブロックの横スクロールが崩れない。

UI 変更が入った段階では、生成 HTML をブラウザで開き、見出し構造、キーボード操作、表の読みやすさを確認する。

## 推奨する初期方針

初期実装では、次の方針を推奨する。

- Python で実装する。
- Markdown 変換には `markdown-it-py` を使う。
- ファイル監視には `watchfiles` を使う。
- 静的ファイルコピーには `shutil.copy2` を使う。
- 入力ディレクトリと出力ディレクトリは CLI で指定する。
- 生成 HTML は JavaScript なしで閲覧可能にする。
- 変換できないファイルがあっても生成を継続し、`errors.html` に記録する。
- Nginx、rclone、外部エージェントはツールに組み込まず、ファイル境界で連携する。
- まずは `build`、次に `watch` / `check`、最後に index 強化と設定ファイルの順で進める。
