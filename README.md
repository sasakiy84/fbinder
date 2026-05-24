# fbinder

`fbinder` は、任意の入力ディレクトリに置いた Markdown / CSV / 静的ファイルを、JavaScript なしで読める静的 HTML サイトへ変換する軽量 CLI です。

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

## サーバー運用

生成した出力ディレクトリを nginx で静的配信できます。次の例では `watch` コマンドの出力先を `/var/www/wiki-public/` にして、nginx がそのディレクトリを読む構成にします。

```nginx
server {
    listen 80;
    server_name example.com;

    root /var/www/wiki-public;
    index index.html;

    location / {
        auth_basic "fbinder";
        auth_basic_user_file /etc/nginx/fbinder.htpasswd;
        try_files $uri $uri/ =404;
    }
}
```

basic auth のパスワードファイルは、nginx から読める場所に作ります。Debian / Ubuntu では `htpasswd` コマンドは `apache2-utils` に含まれます。

```sh
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/fbinder.htpasswd fbinder-user
sudo nginx -t
sudo systemctl reload nginx
```

`watch` コマンドを user systemd で常駐させる場合は、次の unit を `~/.config/systemd/user/fbinder-watch.service` に置きます。`WorkingDirectory`、`--source`、`--output` は実際の配置に合わせて変更してください。

```systemd
# fbinder の watch コマンドを user systemd で常駐させる unit。
# 利用時は ~/.config/systemd/user/ に配置し、systemctl --user enable --now で起動する。
[Unit]
Description=fbinder static site watcher
After=default.target

[Service]
Type=simple
WorkingDirectory=/home/fbinder-user/fbinder
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/fbinder-user/.local/bin/uv run python main.py watch --source /home/fbinder-user/ObsidianVault/ --output /var/www/wiki-public/
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
```

user systemd の unit は次のように反映して起動します。

```sh
systemctl --user daemon-reload
systemctl --user enable --now fbinder-watch.service
systemctl --user status fbinder-watch.service
```

## 入出力

- `*.md` は HTML ページへ変換します。front matter の `title`、最初の `# 見出し`、ファイル名の順でページタイトルを決めます。
- `*.csv` は `<table>` を持つ HTML ページへ変換します。`http://` または `https://` で始まるセルはリンクにします。
- Markdown / CSV 由来のページは `search-index.json` に収録され、生成ページ上の検索フォームから全文検索できます。検索状態は URL の `q` と `page` で表します。
- Markdown / CSV の詳細ページには生成日、Markdown コピーボタン、元ファイルの相対パスをコピーするボタンを表示します。Markdown ページでは本文見出しから目次も生成します。
- その他のファイルは相対パスを保ってコピーします。
- 回復可能なエラーがある場合は、生成を継続し、`errors.html` に一覧を出します。
- `--output` が `--source` の配下にある構成は、生成物を再帰的に読み込む危険があるため拒否します。

## フォルダ

- `templates/page.html`: 生成 HTML の共通テンプレートです。
- `static/style.css`: 生成先の `static/style.css` へコピーする既定 CSS です。
- `static/script.js`: 生成先の `static/script.js` へコピーする、Markdown コピー用の JavaScript です。
- `tests/`: 静的サイト生成の振る舞いを確認する unit test です。
