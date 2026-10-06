/**
 * Receives answers from the persona-evaluation form and appends them to a Google Sheet.
 *
 * Setup (about 5 minutes) -- see ../README.md:
 *   1. Create a Google Sheet. Extensions > Apps Script. Paste this file in as Code.gs.
 *   2. Deploy > New deployment > type "Web app" > Execute as: Me > Who has access: Anyone.
 *   3. Copy the web-app URL (ends in /exec) into public/evaluate/config.json as "sheetEndpoint".
 *
 * One row per (evaluator, item). If an evaluator goes back and re-saves an item, that row is
 * updated in place instead of duplicated.
 */

var SHEET_NAME = "Responses";
var COLUMNS = [
  "submitted_at", "form_version", "evaluator_id", "evaluator_name", "evaluator_email", "evaluator_role",
  "kannada_fluency", "karnataka_experience",
  "item_id", "region_id", "persona_gender", "persona_version", "query", "item_position", "ab_order",
  "region_familiarity", "fidelity", "authenticity", "accuracy", "stereotyping", "insight", "overall",
  "cmp_more_likely_persona", "cmp_better_represents", "flags", "comment", "seconds_on_item", "user_agent"
];
var MAX_CELL = 5000; // never store an unbounded string from the open internet

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var data = JSON.parse(e.postData.contents);
    if (data.website) return reply_({ ok: true });                  // honeypot: bots fill it, people don't
    if (!data.evaluator_id || !data.item_id) return reply_({ ok: false, error: "missing ids" });

    var sheet = sheet_();
    var row = COLUMNS.map(function (c) { return clip_(data[c]); });

    // update in place if this evaluator already saved this item
    var last = sheet.getLastRow();
    if (last > 1) {
      var idCol = COLUMNS.indexOf("evaluator_id") + 1, itemCol = COLUMNS.indexOf("item_id") + 1;
      var ids = sheet.getRange(2, idCol, last - 1, 1).getValues();
      var items = sheet.getRange(2, itemCol, last - 1, 1).getValues();
      for (var i = 0; i < ids.length; i++) {
        if (ids[i][0] === data.evaluator_id && items[i][0] === data.item_id) {
          sheet.getRange(i + 2, 1, 1, COLUMNS.length).setValues([row]);
          return reply_({ ok: true, updated: true });
        }
      }
    }
    sheet.appendRow(row);
    return reply_({ ok: true });
  } catch (err) {
    return reply_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

function doGet() { return reply_({ ok: true, service: "persona-eval", columns: COLUMNS.length }); }

function sheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sh.getLastRow() === 0) {
    sh.appendRow(COLUMNS);
    sh.setFrozenRows(1);
  }
  return sh;
}
function clip_(v) {
  if (v === null || v === undefined) return "";
  var s = String(v);
  if (/^[=+\-@]/.test(s)) s = "'" + s;                                // stop spreadsheet-formula injection
  return s.length > MAX_CELL ? s.slice(0, MAX_CELL) : s;
}
function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
