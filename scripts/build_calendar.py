"""栗林みな実カレンダー ビルド

  データベース → イベントJSON → 公開ページ + .ics

使い方:
    python3 scripts/build_calendar.py

入力（リポジトリ内）:
    data/kuribayashi_minami.db          正本のデータベース
    data/event_links.json               直近イベントに付ける公式リンク
    data/uid_map.json                   Googleカレンダー登録済みUIDの対応表
    templates/calendar.html             ページの雛形

出力:
    docs/calendar/index.html            公開ページ
    docs/calendar/calendar.ics          購読用ICS
    docs/calendar/events.json           他から使う場合用
"""
import sqlite3, json, re, os, datetime, collections

DB        = 'data/kuribayashi_minami.db'
LINKS     = 'data/event_links.json'
UID_MAP   = 'data/uid_map.json'
TEMPLATE  = 'templates/calendar.html'
OUT_DIR   = 'docs/calendar'

# カレンダーに載せる楽曲の媒体（YouTube・提供・その他・テレビは除外）
GAKKYOKU_MEDIA = {'CD', '配信', 'BD', 'DVD', 'ゲーム'}
SUB_TO_KUBUN = {'シングル': 'シングル', 'EP': 'EP',
                'オリジナルアルバム': 'アルバム', 'ベストアルバム': 'ベスト'}
EMOJI = {'シングル':'🎵','アルバム':'💿','ベスト':'⭐','EP':'🎶','CD':'💽','配信リリース':'🎧',
         'ライブ':'🎤','DVD':'🎬','BD':'📀','ラジオ':'📻','テレビ':'📺','アニメ関連':'🎞️',
         'リリイベ':'🛍️','サイン会':'✍️','ファンミ':'🎉','配信':'📡','ゲーム':'🎮','その他':'📌'}

CLOSED = re.compile(r'[（(][^（）()]*(?:閉店|閉館|閉鎖|営業終了|廃業|取り壊し)[^（）()]*[）)]')

def clean(s):
    if not s: return ''
    s = CLOSED.sub('', s)
    s = re.sub(r'[\s　]+', ' ', s).strip(' 　・')
    return s if re.search(r'[0-9A-Za-zぁ-ゖァ-ヺ一-鿿]', s) else ''

def unwrap(t):
    """年表の楽曲タイトルは「〇〇」発売 というイベント文なので中身だけ取り出す"""
    m = re.fullmatch(r'「(.+)」発売', (t or '').strip())
    return m.group(1) if m else t

def load(path, default):
    try:
        with open(path, encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError:
        return default

# ---------------------------------------------------------------- データ抽出
def build_events():
    c = sqlite3.connect(DB)
    rows = c.execute("""SELECT date, category, subcategory, title, remarks, media_type
                        FROM events
                        WHERE is_timeline = 1 AND category IN ('出演','楽曲')
                        ORDER BY date""").fetchall()
    out, seen = [], set()
    for date, cat, sub, title, remarks, media in rows:
        if cat == '楽曲' and media not in GAKKYOKU_MEDIA:
            continue
        y, m, d = (int(x) for x in date.split('-'))
        t = clean(unwrap(title))
        if not t or (y, m, d, t) in seen:
            continue
        seen.add((y, m, d, t))
        if cat == '楽曲':
            kubun = SUB_TO_KUBUN.get(sub) or ('配信リリース' if media == '配信' else media)
        else:
            kubun = media or 'その他'
        out.append({'mmdd': f'{m:02d}{d:02d}', 'month': m, 'day': d, 'year': y,
                    'kubun': kubun or 'その他', 'title': t, 'note': clean(remarks or '')})

    # 公式リンクを付与
    for r in load(LINKS, {}).get('links', []):
        links = r['links'] if 'links' in r else [{'label': r.get('label','公式情報'), 'url': r['url']}]
        for e in out:
            if (e['year'] == r['year'] and e['month'] == r['month']
                    and e['day'] == r['day'] and r['match'] in e['title']):
                e['links'] = links

    out.sort(key=lambda e: (e['month'], e['day'], e['year'], e['title']))
    return out

# ---------------------------------------------------------------- ICS 生成
def esc(s):
    return s.replace('\\', '\\\\').replace(';', r'\;').replace(',', r'\,').replace('\n', r'\n')

def fold(line):
    """RFC5545 の75オクテット折り返し"""
    b = line.encode('utf-8')
    if len(b) <= 73: return line
    parts, cur = [], b''
    for ch in line:
        e = ch.encode('utf-8')
        if len(cur) + len(e) > 73:
            parts.append(cur.decode('utf-8')); cur = b''
        cur += e
    parts.append(cur.decode('utf-8'))
    return '\r\n '.join(parts)

def build_ics(events, today):
    uid_map = load(UID_MAP, {'hist': {}, 'fut': {}})
    hist = uid_map.setdefault('hist', {})

    def hist_uid(mmdd):
        """日カードのUIDは既存の連番を維持する。新しい月日だけ最大値+1で採番"""
        if mmdd not in hist:
            nums = [int(v.split('@')[0][1:]) for v in hist.values() if v.startswith('h')]
            hist[mmdd] = f'h{(max(nums) if nums else 0) + 1}@kn.local'
        return hist[mmdd]

    future, by_day = [], collections.defaultdict(list)
    for e in events:
        try:
            d = datetime.date(e['year'], e['month'], e['day'])
        except ValueError:
            d = None                      # 2/29 など
        (future.append((d, e)) if d and d > today
         else by_day[f"{e['month']:02d}{e['day']:02d}"].append(e))
    future.sort(key=lambda x: x[0])
    for v in by_day.values():
        v.sort(key=lambda e: (e['year'], e['title']))

    stamp = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//栗林みな実 イベントカレンダー//JP',
         'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:栗林みな実カレンダー',
         'X-WR-TIMEZONE:Asia/Tokyo',
         'BEGIN:VTIMEZONE', 'TZID:Asia/Tokyo', 'BEGIN:STANDARD',
         'TZOFFSETFROM:+0900', 'TZOFFSETTO:+0900', 'TZNAME:JST',
         'DTSTART:19700101T000000', 'END:STANDARD', 'END:VTIMEZONE']

    def links_text(e):
        return ''.join(f"\n　{li['label']}：{li['url']}" for li in e.get('links', []))

    cnt = collections.Counter()
    for d, e in future:
        cnt[d] += 1
        uid = f'f{d:%Y%m%d}-{cnt[d]}@kn.local'
        desc = f"{d:%Y年%m月%d日}\n区分：{e['kubun']}\nタイトル：{e['title']}"
        if e['note']: desc += f"\n会場・備考：{e['note']}"
        for li in e.get('links', []): desc += f"\n{li['label']}：{li['url']}"
        ev = ['BEGIN:VEVENT', f'UID:{uid}', f'DTSTAMP:{stamp}',
              f'DTSTART;VALUE=DATE:{d:%Y%m%d}',
              f'DTEND;VALUE=DATE:{d + datetime.timedelta(days=1):%Y%m%d}',
              f"SUMMARY:{EMOJI.get(e['kubun'],'📌')} {d.year}年 {esc(e['kubun'])} {esc(e['title'])}",
              f'DESCRIPTION:{esc(desc)}']
        if e.get('links'): ev.append(f"URL:{e['links'][0]['url']}")
        L += ev + ['STATUS:CONFIRMED', 'END:VEVENT']

    for mmdd in sorted(by_day):
        items = by_day[mmdd]
        m, dd = int(mmdd[:2]), int(mmdd[2:])
        try:
            start = datetime.date(2026, m, dd)
        except ValueError:
            start = datetime.date(2028, m, dd)     # 2/29
        lines = []
        for e in items:
            s = f"{e['year']}年：{EMOJI.get(e['kubun'],'📌')}{e['kubun']}　{e['title']}"
            if e['note']: s += f"（{e['note']}）"
            lines.append(s + links_text(e))
        L += ['BEGIN:VEVENT', f'UID:{hist_uid(mmdd)}', f'DTSTAMP:{stamp}',
              f'DTSTART;VALUE=DATE:{start:%Y%m%d}',
              f'DTEND;VALUE=DATE:{start + datetime.timedelta(days=1):%Y%m%d}',
              'RRULE:FREQ=YEARLY',
              f'SUMMARY:🌰 {m}月{dd}日の出来事（{len(items)}件）',
              f'DESCRIPTION:{esc(chr(10).join(lines))}', 'STATUS:CONFIRMED', 'END:VEVENT']

    L.append('END:VCALENDAR')
    with open(UID_MAP, 'w', encoding='utf-8') as f:
        json.dump(uid_map, f, ensure_ascii=False, indent=1)
    return '\r\n'.join(fold(x) for x in L) + '\r\n', len(future), len(by_day)

# ---------------------------------------------------------------- 実行
def main():
    today = datetime.date.today()
    events = build_events()
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(f'{OUT_DIR}/events.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False, indent=0)

    ics, n_future, n_days = build_ics(events, today)
    with open(f'{OUT_DIR}/calendar.ics', 'w', encoding='utf-8', newline='') as f:
        f.write(ics)

    html = open(TEMPLATE, encoding='utf-8').read()
    html = html.replace('__EVENTS_JSON__', json.dumps(events, ensure_ascii=False))
    html = html.replace('__META_JSON__', json.dumps(
        {'updated': f'{today:%Y年%-m月%-d日}', 'total': len(events)}, ensure_ascii=False))
    with open(f'{OUT_DIR}/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'イベント {len(events)}件 / 今後の予定 {n_future}件 / 日カード {n_days}件')
    print(f'リンク付与 {sum(1 for e in events if e.get("links"))}件')
    for k, v in collections.Counter(e['kubun'] for e in events).most_common():
        print(f'  {k:<10}{v:>5}')

if __name__ == '__main__':
    main()
