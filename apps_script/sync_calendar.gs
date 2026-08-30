/**
 * 栗林みな実カレンダー Googleカレンダー同期
 *
 * GitHub Pages に公開された calendar.ics を取得し、Googleカレンダーへ反映する。
 * 購読URLを変えずに済ませるため、既存のカレンダーを更新する方式をとる。
 *
 * 仕組み:
 *   Calendar.Events.import() は iCalUID を指定して登録できる。
 *   同じ UID なら上書き、無ければ新規になるため、重複しない。
 *
 * 設定手順は README を参照。
 */

// ==== 設定 ====================================================
const ICS_URL = 'https://affection0814-debug.github.io/kuri-calendar/calendar/calendar.ics';
const CALENDAR_ID = '6fd8ce1adfe43f69c90fe148fc4d9c88f60b88dae6c4251c95b00b4abaefbadc@group.calendar.google.com';

// 元データから消えた予定を自動削除するか。false = 記録に残すだけ（推奨）
const DELETE_MISSING = false;
// ==============================================================

function syncCalendar() {
  const res = UrlFetchApp.fetch(ICS_URL, { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    throw new Error('ICSを取得できません: HTTP ' + res.getResponseCode());
  }
  const events = parseIcs(res.getContentText());
  if (events.length === 0) throw new Error('ICSにイベントがありません。中断します');

  Logger.log('取得: %s件', events.length);

  let created = 0, updated = 0, failed = 0;
  const seenUids = {};

  events.forEach(function (ev) {
    seenUids[ev.uid] = true;
    const resource = {
      iCalUID: ev.uid,
      summary: ev.summary,
      description: ev.description,
      start: { date: ev.start },
      end:   { date: ev.end },
      status: 'confirmed'
    };
    if (ev.rrule)  resource.recurrence = ['RRULE:' + ev.rrule];
    if (ev.url)    resource.source = { title: '公式情報', url: ev.url };

    try {
      const existing = Calendar.Events.list(CALENDAR_ID, { iCalUID: ev.uid, showDeleted: false });
      const had = existing.items && existing.items.length > 0;
      Calendar.Events.import(resource, CALENDAR_ID);
      had ? updated++ : created++;
    } catch (e) {
      failed++;
      Logger.log('失敗 %s: %s', ev.uid, e.message);
    }
  });

  // ICSから消えたもの（予定日が過ぎて日カードへ移ったものなど）
  const gone = findGone(seenUids);
  if (gone.length > 0) {
    Logger.log('ICSに無いイベント %s件: %s', gone.length,
               gone.map(function (g) { return g.uid; }).join(', '));
    if (DELETE_MISSING) {
      gone.forEach(function (g) {
        try { Calendar.Events.remove(CALENDAR_ID, g.id); } catch (e) { Logger.log(e.message); }
      });
    }
  }

  const msg = Utilities.formatString(
    '同期完了 — 新規 %s / 更新 %s / 失敗 %s / ICSに無い %s',
    created, updated, failed, gone.length);
  Logger.log(msg);

  if (failed > 0) throw new Error(msg);   // 失敗があれば実行エラーとして通知される
  return msg;
}

/** カレンダー上にあって ICS に無いイベントを探す（kn.local のUIDのみ対象） */
function findGone(seenUids) {
  const out = [];
  let pageToken = null;
  do {
    const list = Calendar.Events.list(CALENDAR_ID, {
      maxResults: 250, showDeleted: false, singleEvents: false, pageToken: pageToken
    });
    (list.items || []).forEach(function (it) {
      const uid = it.iCalUID || '';
      if (uid.indexOf('@kn.local') !== -1 && !seenUids[uid]) {
        out.push({ uid: uid, id: it.id, summary: it.summary });
      }
    });
    pageToken = list.nextPageToken;
  } while (pageToken);
  return out;
}

/** 自前で出力したICSを読む簡易パーサ（汎用ではない） */
function parseIcs(text) {
  const lines = text.replace(/\r\n[ \t]/g, '').split(/\r?\n/);   // 折り返しを戻す
  const events = [];
  let cur = null;
  lines.forEach(function (line) {
    if (line === 'BEGIN:VEVENT') { cur = {}; return; }
    if (line === 'END:VEVENT')   { if (cur && cur.uid) events.push(cur); cur = null; return; }
    if (!cur) return;
    const i = line.indexOf(':');
    if (i < 0) return;
    const key = line.substring(0, i);
    const val = line.substring(i + 1);
    if (key === 'UID')                       cur.uid = val;
    else if (key === 'SUMMARY')              cur.summary = unesc(val);
    else if (key === 'DESCRIPTION')          cur.description = unesc(val);
    else if (key === 'RRULE')                cur.rrule = val;
    else if (key === 'URL')                  cur.url = val;
    else if (key.indexOf('DTSTART') === 0)   cur.start = dashed(val);
    else if (key.indexOf('DTEND') === 0)     cur.end = dashed(val);
  });
  return events;
}

function unesc(s) {
  return s.replace(/\\n/g, '\n').replace(/\\,/g, ',').replace(/\;/g, ';').replace(/\\\\/g, '\\');
}
function dashed(v) {
  return v.substring(0, 4) + '-' + v.substring(4, 6) + '-' + v.substring(6, 8);
}

/** 初回だけ実行する。毎日 深夜2:00〜3:00 に同期するトリガーを作る */
function createTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'syncCalendar') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('syncCalendar').timeBased().atHour(2).everyDays(1).create();
  Logger.log('毎日2時台に実行するトリガーを作成しました');
}
