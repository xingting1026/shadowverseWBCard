// 收藏（擁有數量）只存在這台瀏覽器的 localStorage，永遠不會上傳伺服器。
// 其餘（缺哪些卡、補完成本、排行榜）都在瀏覽器即時計算。
const SVE_OWNED_KEY = "sve_owned";

function sveGetOwned() {
  try { return JSON.parse(localStorage.getItem(SVE_OWNED_KEY)) || {}; }
  catch (e) { return {}; }
}

function sveSaveOwned(map) {
  localStorage.setItem(SVE_OWNED_KEY, JSON.stringify(map));
}

// 設定單張數量（夾在 0–3；0 就移除）
function sveSetOwned(cn, q) {
  const m = sveGetOwned();
  q = Math.max(0, Math.min(3, q | 0));
  if (q > 0) m[cn] = q; else delete m[cn];
  sveSaveOwned(m);
  return q;
}

// 匯入 CSV（卡號,擁有數量）→ 取代整份收藏；回傳匯入筆數
function sveImportCSV(text) {
  const map = {};
  let imported = 0;
  for (const line of text.split(/\r?\n/)) {
    const parts = line.split(",");
    if (parts.length < 2) continue;
    const cn = parts[0].trim().replace(/^﻿/, "");      // 去 BOM
    const q = parseInt(String(parts[1]).trim(), 10);
    if (!cn || isNaN(q)) continue;                          // 跳過標題列／壞行
    const c = Math.max(0, Math.min(3, q));                  // 夾 0–3
    if (c > 0) { map[cn] = c; imported++; }
  }
  sveSaveOwned(map);
  return imported;
}

// 匯出目前收藏成 CSV 字串
function sveToCSV() {
  const m = sveGetOwned();
  let out = "卡號,擁有數量\n";
  for (const cn of Object.keys(m).sort()) out += cn + "," + m[cn] + "\n";
  return out;
}
