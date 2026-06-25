// ---- 懶載入：展開系列才載入該系列圖片 ----
function sveLoadImgs(root) {
  root.querySelectorAll("img[data-src]").forEach(img => {
    img.src = img.dataset.src; img.removeAttribute("data-src");
  });
}
document.querySelectorAll("details.set").forEach(d =>
  d.addEventListener("toggle", () => { if (d.open) sveLoadImgs(d); }));
document.querySelectorAll(".grid").forEach(g => {
  if (!g.closest("details")) sveLoadImgs(g);          // 牌組頁等：直接載入
});

// ---- 收藏頁：計數器讀/寫 localStorage ----
document.querySelectorAll(".counter").forEach(c => {
  const cn = c.dataset.cn, span = c.querySelector(".qty");
  const q0 = sveGetOwned()[cn] || 0;
  span.textContent = q0; c.dataset.q = q0;
  const set = q => { const v = sveSetOwned(cn, q); span.textContent = v; c.dataset.q = v; };
  c.querySelector(".inc").onclick = () => set((+span.textContent) + 1);
  c.querySelector(".dec").onclick = () => set((+span.textContent) - 1);
});

// ---- 收藏頁：CSV 上傳（純瀏覽器）/ 下載 ----
const csvBtn = document.getElementById("csvBtn");
if (csvBtn) {
  csvBtn.onclick = () => {
    const inp = document.getElementById("csvFile"), msg = document.getElementById("csvMsg");
    if (!inp.files.length) { msg.textContent = "請先選一個 CSV 檔。"; return; }
    const reader = new FileReader();
    reader.onload = () => {
      const n = sveImportCSV(reader.result);
      msg.textContent = `已匯入 ${n} 筆到本機收藏（只存這台瀏覽器），重新整理中…`;
      setTimeout(() => location.reload(), 700);
    };
    reader.readAsText(inp.files[0]);
  };
  const exp = document.getElementById("csvExport");
  if (exp) exp.onclick = e => {
    e.preventDefault();
    const blob = new Blob([sveToCSV()], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "my_collection.csv"; a.click();
  };
}

// ---- 牌組一般模式：用 localStorage 收藏即時算 有/缺/補完成本 ----
const deckNormal = document.querySelector("[data-deck-normal]");
if (deckNormal) {
  const owned = sveGetOwned();
  let cost = 0, unpriced = 0;
  deckNormal.querySelectorAll(".card").forEach(card => {
    const cn = card.dataset.cn, num = +card.dataset.num, have = owned[cn] || 0;
    const miss = Math.max(0, num - have);
    const info = card.querySelector(".owninfo");
    if (info) info.textContent = `有 ${have}` + (miss ? `／缺 ${miss}` : "");
    if (miss > 0) {
      card.classList.add("missing");
      const p = card.dataset.price;
      if (p === "" || p == null) unpriced++; else cost += miss * (+p);
    }
  });
  const costEl = document.getElementById("deckCost");
  if (costEl) costEl.textContent = "¥" + cost.toLocaleString();
  const upEl = document.getElementById("deckUnpriced");
  if (upEl) upEl.textContent = unpriced ? `（${unpriced} 張無價未計入）` : "";
}

// ---- 排行榜·補完：用 localStorage 收藏即時算每副補完成本並排序 ----
const rankData = document.getElementById("rank-data");
if (rankData) {
  const { decks, prices } = JSON.parse(rankData.textContent);
  const owned = sveGetOwned();
  const rows = decks.map(d => {
    let cost = 0, unpriced = 0, miss = 0;
    for (const card of d.cards) {
      const m = Math.max(0, card.num - (owned[card.cn] || 0));
      if (!m) continue;
      miss += m;
      const p = prices[card.cn];
      if (p == null) unpriced++; else cost += m * p;
    }
    return { code: d.code, cls: d.cls, cost, unpriced, miss };
  }).sort((a, b) => a.cost - b.cost || a.unpriced - b.unpriced || a.code.localeCompare(b.code));
  const esc = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  document.getElementById("rank-body").innerHTML = rows.map((d, i) =>
    `<tr><td><span class="rankno">${i + 1}</span></td>` +
    `<td class="cost">¥${d.cost.toLocaleString()}${d.unpriced ? ` <span class="warn">＋${d.unpriced}無價</span>` : ""}</td>` +
    `<td><span class="badge">${esc(d.cls)}</span></td><td>${d.miss}</td>` +
    `<td><a href="/deck/${encodeURIComponent(d.code)}">看單卡</a></td></tr>`).join("")
    || `<tr><td colspan="5" class="hint">這個月沒有牌組資料。</td></tr>`;
}
