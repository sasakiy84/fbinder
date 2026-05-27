---
title: サンプル図書館サイト
tags: [sample, library]
---

# サンプル図書館サイト

これは `fbinder` の動作確認用コンテンツです。

Markdown、CSV、静的ファイルがそれぞれ HTML サイトとして出力されることを確認できます。

## 確認すること

- Markdown の見出しと本文が読めること。
- CSV が表として表示されること。
- 静的ファイルへのリンクが index から辿れること。
- 列数が多い Markdown 表を横スクロールで確認できること。

```text
sample-content/
  index.md
  reports/reading-notes.md
  data/books.csv
  files/reference.txt
```

## 多列テーブルの確認

| 資料ID | タイトル | 著者 | 出版年 | 分類 | 所蔵館 | 請求記号 | 状態 | 予約数 | メモ |
|---|---|---|---|---|---|---|---|---|---|
| BK-001 | Digital Libraries | Smith, A. | 2024 | 情報学 | 中央館 | 010.4-SM | 貸出可 | 2 | 列数が多い表でも横スクロールで確認できます |
| BK-002 | Metadata Practice | Yamada, Sato | 2026 | メタデータ | 分館 | 014.3-YA | 貸出中 | 5 | 長めのメモが入っても列幅が極端に潰れないことを確認します |
| BK-003 | Community Archive Operations | K. Tanaka | 2025 | アーカイブ | 地域資料室 | 018.09-TA | 整理中 | 0 | セルの文字数が多い場合は、セル幅の上限を超えたところで折り返し、表全体は必要に応じて横スクロールします。長い URL のような連続文字列 https://example.com/reports/community-archive-operations/very-long-reference-name も確認用に入れています |
