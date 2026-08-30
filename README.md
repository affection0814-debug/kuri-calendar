# 栗林みな実カレンダー GitHub運用パッケージ

> **【2026-08-30 非推奨】このリポジトリはもう使っていません。**
> 「公開先はマロンレコード一つにしたい」という方針により、この仕組みは
> `marron-record`リポジトリに統合された。サイト・ICS生成・Googleカレンダー
> 同期は現在すべて`marron-record`側で行っている。詳細は
> `marron-record/運用メモ_2026-08-30_カレンダー統合.md`を参照。
> 以下は統合前の設計メモとして残す。

データベースからカレンダーを生成し、GitHub Pagesで公開したうえで、
Googleカレンダーへ自動反映するための一式。

---

## 全体像

```
  GitHub Actions（リポジトリ内で完結・認証情報なし）
    data/kuribayashi_minami.db
            ↓  scripts/build_calendar.py
    docs/calendar/index.html    公開ページ
    docs/calendar/calendar.ics  購読用ICS
    docs/calendar/events.json   他用途向け
            ↓  git push → GitHub Pages
                    ↓
  Google Apps Script（Googleの中で完結・鍵を外に出さない）
    calendar.ics を取得 → Googleカレンダーへ反映
                    ↓
          既存の購読URLはそのまま
```

**購読URLを変えないこと**が設計の前提。既存の栗家族の皆さんが
登録し直さずに済むよう、Googleカレンダーを更新する方式をとっている。

---

## 1. リポジトリへの配置

```
リポジトリ/
├ data/
│   ├ kuribayashi_minami.db     ← 正本のデータベース
│   ├ event_links.json          ← 直近イベントに付ける公式リンク
│   └ uid_map.json              ← 登録済みUIDの対応表【重要・消さない】
├ templates/
│   └ calendar.html             ← ページの雛形
├ scripts/
│   └ build_calendar.py
├ docs/calendar/                ← 生成物（Actionsが更新）
└ .github/workflows/calendar.yml
```

GitHub Pages の公開元を **`main` ブランチの `/docs`** に設定する。
公開先は `https://<ユーザー名>.github.io/<リポジトリ名>/calendar/` になる。

### uid_map.json について

Googleカレンダーの日カード325件は `h1`〜`h325` という連番UIDで登録済み。
この連番は月日と対応しておらず、**再計算では復元できない**。
このファイルが唯一の対応表で、失うと全325件が重複する。

新しい月日が増えたときはビルド時に最大値+1で自動採番され、
ファイルに追記される。Actionsがコミットに含めるので手作業は不要。

---

## 2. GitHub Actions

`.github/workflows/calendar.yml` がそのまま使える。起動条件は3つ。

| 条件 | 用途 |
|---|---|
| `data/` `templates/` `scripts/` への push | データベースを更新したとき |
| 毎日 16:30 UTC（日本時間 深夜1:30） | 日付が変わると「今後の予定」が「その日の出来事」へ移るため、データが変わらなくても必要 |
| 手動実行 | 確認したいとき |

生成後に検証ステップが走り、旧形式のUIDが混ざっていたら失敗する。

---

## 3. Google Apps Script の設定

一度だけ行う。GCPコンソールは触らない。

1. [script.google.com](https://script.google.com) で新しいプロジェクトを作る
2. `apps_script/sync_calendar.gs` の内容を貼り付ける
3. 冒頭の `ICS_URL` を実際の公開URLに書き換える
4. 左メニューの「サービス」で **Google Calendar API** を追加する
   （識別子は `Calendar` のまま）
5. `syncCalendar` を一度手動実行し、権限を承認する
6. `createTrigger` を一度実行する
   → 毎日深夜2時台に自動同期するトリガーができる

### 動作の仕組み

`Calendar.Events.import()` は **iCalUID を指定して登録できる**ため、
同じUIDなら上書き、無ければ新規になる。手作業のICSインポートと同じ挙動を
自動化したもので、これまでのUID設計をそのまま活かせる。

### 削除について

既定では **削除しない**。ICSに無くなったイベントはログに記録するだけ。
元データの不具合でイベントが消えたときに、公開情報が巻き添えで
消えるのを防ぐため。自動削除したい場合は `DELETE_MISSING` を `true` にする。

なお、予定日が過ぎた単発イベントは日カードへ合流するため、
ICSから消える。これはログに出るので、必要なら手動で消す。

### 失敗したとき

`syncCalendar` は失敗があると例外を投げる。Apps Scriptは実行エラーを
プロジェクト所有者にメール通知するので、気づける。

---

## 4. 動作確認

ローカルで試す場合。

```bash
python3 scripts/build_calendar.py
```

確認する点

- 件数が想定どおりか
- `docs/calendar/calendar.ics` の UID が `h`（日カード）と `f`（今後の予定）だけか
- `docs/calendar/index.html` に `__EVENTS_JSON__` が残っていないか
- 購読URLがページ内に維持されているか

---

## 5. 移行の手順

1. このパッケージをリポジトリに配置し、GitHub Pages を有効にする
2. Actions を手動実行し、ページとICSが公開されることを確認する
3. Apps Script を設定し、`syncCalendar` を手動実行する
4. Googleカレンダーを開き、重複が発生していないか確認する
5. 問題なければ `createTrigger` でトリガーを作る
6. 既存のアーティファクトを、新しいページへの案内に差し替える

**4番は必ず目視で確認すること。** 過去にUIDの食い違いで
イベントが重複した事例がある。

---

## 6. これまでの経緯

カレンダーの運用ルール、過去の事故と対策、UID管理の詳細は
プロジェクト「栗林みな実」の `claude/カレンダー運用ルール_再発防止.md` に記録がある。
データベース統合の経緯は `claude/DB統合_引き継ぎ.md` を参照。
