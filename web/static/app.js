// SVE Meta 靜態站前端：依 body[data-page] 分派，資料全部來自 data/*.json。
// 職業固定色（圓餅/圖例用）；沒列到的職業（聯動等）用後備色輪流配
const CLASS_COLORS = {
  "ウィッチ": "#4363d8",      // 藍
  "ナイトメア": "#e6194b",    // 紅
  "ドラゴン": "#f58231",      // 橘
  "ロイヤル": "#ffe119",      // 黃
  "ビショップ": "#f2f0e6",    // 白
  "エルフ": "#3cb44b",        // 綠
  "ネメシス": "#46f0f0",      // 青
  "ニュートラル": "#9b97b4",  // 灰
};
const PALETTE = ["#911eb4", "#f032e6", "#9a6324", "#808080", "#57d9a3"];
const P = new URLSearchParams(location.search);
const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const yen = n => "¥" + (+n).toLocaleString();
const J = async url => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
};

// ---- 懶載入卡圖 ----
const _io = ("IntersectionObserver" in window)
  ? new IntersectionObserver((entries, obs) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.src = e.target.dataset.src;
        e.target.removeAttribute("data-src");
        obs.unobserve(e.target);
      }
    }, { rootMargin: "400px" })
  : null;
function lazyImgs(root) {
  root.querySelectorAll("img[data-src]").forEach(img => {
    if (_io) _io.observe(img);
    else { img.src = img.dataset.src; img.removeAttribute("data-src"); }
  });
}

function monthChips(el, months, sel, extra = "") {
  el.innerHTML = months.map(m =>
    `<a class="mchip ${m === sel ? "on" : ""}" href="?m=${m}${extra}">${m}</a>`).join("");
}

function cardTile(cn, name, sub, cls = "") {
  return `<div class="card ${cls}" data-cn="${esc(cn)}">
    <img data-src="img/${encodeURIComponent(cn)}.jpg" alt="${esc(cn)}" loading="lazy">
    <div class="name">${esc(name)}</div>${sub}</div>`;
}

// ---- 牌效彈窗：點卡片（非連結的）顯示大圖＋牌效（中/日可切換，中文缺卡自動退日文）----
let CARDS = null;                                   // 各頁載入 cards.json 後掛在這
let EFFLANG = localStorage.getItem("efflang") || "zh";
const _effCache = {};
const loadEffects = lang =>
  (_effCache[lang] ||= J(`data/effects.${lang}.json`).catch(() => ({})));

async function effHTML(name, evo) {
  let entry = ((await loadEffects(EFFLANG))[name] || {})[evo ? "E" : "B"];
  let note = "";
  if (!entry && EFFLANG !== "ja") {
    entry = ((await loadEffects("ja"))[name] || {})[evo ? "E" : "B"];
    if (entry) note = `<p class="hint">（此卡尚無中文翻譯，顯示日文原文）</p>`;
  }
  if (!entry) return `<p class="hint">（暫無牌效資料）</p>`;
  return note + `<div class="efftext">${esc(entry[0]).replace(/\n/g, "<br>")}</div>` +
    (entry[1] ? `<div class="flavor">${esc(entry[1]).replace(/\n/g, "<br>")}</div>` : "");
}

async function openCardModal(cn) {
  const [name, , evo] = (CARDS && CARDS[cn]) || [cn, null, 0];
  const back = document.createElement("div");
  back.className = "modal-back";
  back.innerHTML = `<div class="modal">
    <img src="img/${encodeURIComponent(cn)}.jpg" alt="${esc(cn)}">
    <div class="modal-txt">
      <h3>${esc(name)}${evo ? '<span class="badge" style="margin-left:.5rem">進化</span>' : ""}</h3>
      <div class="code">${esc(cn)}</div>
      <div class="seg efflang">
        <a data-l="zh" class="${EFFLANG === "zh" ? "on" : ""}">中文</a>
        <a data-l="ja" class="${EFFLANG === "ja" ? "on" : ""}">日文</a>
      </div>
      <div class="effbody"><p class="hint">載入中…</p></div>
    </div>
    <button class="modal-x" aria-label="關閉">✕</button></div>`;
  const body = back.querySelector(".effbody");
  const render = async () => { body.innerHTML = await effHTML(name, evo); };
  back.querySelectorAll(".efflang a").forEach(a => a.onclick = () => {
    EFFLANG = a.dataset.l;
    localStorage.setItem("efflang", EFFLANG);
    back.querySelectorAll(".efflang a").forEach(x =>
      x.classList.toggle("on", x.dataset.l === EFFLANG));
    render();
  });
  const close = () => { back.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = e => { if (e.key === "Escape") close(); };
  back.onclick = e => { if (e.target === back || e.target.className === "modal-x") close(); };
  document.addEventListener("keydown", onKey);
  document.body.appendChild(back);
  render();
}

document.addEventListener("click", e => {
  const card = e.target.closest(".card[data-cn]");
  if (card && !e.target.closest("a")) openCardModal(card.dataset.cn);
});

// ---- 圓餅（同舊版 engine.pie_slices 的 SVG 路徑作法）----
function pieHTML(counts) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (!total) return "";
  const items = Object.entries(counts).sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
  const cx = 110, cy = 110, r = 100;
  let start = -90, paths = "", legend = "", fb = 0;
  items.forEach(([label, n]) => {
    const frac = n / total, end = start + frac * 360;
    const color = CLASS_COLORS[label] || PALETTE[fb++ % PALETTE.length];
    let d;
    if (frac >= 0.99999) {
      d = `M ${cx - r} ${cy} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0 Z`;
    } else {
      const x1 = cx + r * Math.cos(start * Math.PI / 180), y1 = cy + r * Math.sin(start * Math.PI / 180);
      const x2 = cx + r * Math.cos(end * Math.PI / 180), y2 = cy + r * Math.sin(end * Math.PI / 180);
      d = `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${end - start > 180 ? 1 : 0} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
    }
    paths += `<path d="${d}" fill="${color}" stroke="var(--bg)" stroke-width="1.5"></path>`;
    legend += `<li><span class="sw" style="background:${color}"></span>${esc(label)} <span class="pc">${n}（${(frac * 100).toFixed(1)}%）</span></li>`;
    start = end;
  });
  return `<div class="pie-wrap"><svg viewBox="0 0 220 220" width="220" height="220" aria-label="職業占比">${paths}</svg><ul class="legend">${legend}</ul></div>`;
}

const deckLink = (m, code, cheapest) =>
  `deck.html?m=${m}&code=${encodeURIComponent(code)}${cheapest ? "&cheapest=1" : ""}`;

// 職業文字色（比圓餅色稍亮，深底上才好讀）；沒固定色的職業（聯動/雙職業）維持原樣
const CLASS_TEXT = {
  "ウィッチ": "#7d9aff", "ナイトメア": "#ff5570", "ドラゴン": "#ffa14f",
  "ロイヤル": "#ffe119", "ビショップ": "#f2f0e6", "エルフ": "#52d472",
  "ネメシス": "#46f0f0", "ニュートラル": "#b8b3d1",
};
const clsColor = cls => CLASS_TEXT[cls] ? ` style="color:${CLASS_TEXT[cls]}"` : "";
const clsBadge = cls => `<span class="badge"${clsColor(cls)}>${esc(cls)}</span>`;

// ================= Meta 總表 =================
async function pageMeta() {
  const idx = await J("data/index.json");
  const scope = P.get("scope") === "first" ? "first" : "top8";
  const from = P.get("from") || "", to = P.get("to") || "";
  const min = Math.max(0, +(P.get("min") || 0) || 0);
  const advanced = !!(from && to);
  const mode = advanced || P.get("mode") === "range" ? "range" : "month";
  const m = P.get("m") || idx.latest;
  document.getElementById("gen").textContent = `資料每日自動更新 · 產生於 ${idx.generated_at}`;

  // 模式切換：月份 / 自訂範圍
  document.getElementById("modeSeg").innerHTML =
    `<a class="${mode === "month" ? "on" : ""}" href="?m=${m || ""}&scope=${scope}">月份</a>
     <a class="${mode === "range" ? "on" : ""}" href="?${advanced
       ? `from=${from}&to=${to}&min=${min}` : "mode=range"}&scope=${scope}">自訂範圍</a>`;
  const monthsEl = document.getElementById("months");
  monthsEl.hidden = mode !== "month";
  if (mode === "month") monthChips(monthsEl, idx.months, m, `&scope=${scope}`);

  // 自訂範圍表單（預設近 30 天）
  const adv = document.getElementById("adv");
  adv.hidden = mode !== "range";
  const iso = d => d.toISOString().slice(0, 10);
  const today = new Date(), ago = new Date(today - 30 * 864e5);
  document.getElementById("advFrom").value = from || iso(ago);
  document.getElementById("advTo").value = to || iso(today);
  if (min) document.getElementById("advMin").value = min;
  document.getElementById("advGo").onclick = e => {
    e.preventDefault();
    let f = document.getElementById("advFrom").value;
    let t = document.getElementById("advTo").value;
    if (!f || !t) return;
    if (f > t) [f, t] = [t, f];
    const mn = +document.getElementById("advMin").value || 0;
    location.search = `?from=${f}&to=${t}&min=${mn}&scope=${scope}`;
  };
  if (mode === "range" && !advanced) {      // 還沒按套用：只顯示表單
    document.getElementById("pie").innerHTML =
      `<p class="hint">設定期間（可跨月）與最低人數後按「套用」。</p>`;
    return;
  }

  let events = [], nEvents = 0, periodLabel = m || "—";
  if (advanced) {
    const inRange = idx.months.filter(x => x >= from.slice(0, 7) && x <= to.slice(0, 7));
    const mds = await Promise.all(inRange.map(x =>
      J(`data/month/${x}.json`).catch(() => null)));
    for (const md of mds.filter(Boolean)) {
      for (const ev of md.events) {
        if (ev.date >= from && ev.date <= to && ev.players >= min) {
          events.push({ ...ev, _m: md.month });
        }
      }
    }
    events.sort((a, b) => (a.date < b.date ? 1 : -1));
    periodLabel = `${from}<br>～ ${to}${min ? `（≥${min} 人）` : ""}`;
  } else {
    if (!m) return;
    const md = await J(`data/month/${m}.json`);
    events = md.events.map(ev => ({ ...ev, _m: m }));
  }
  nEvents = events.length;

  const counts = {}; let decks = 0, players = 0;
  for (const ev of events) {
    players += ev.players;
    for (const r of ev.rankings) {
      if (scope === "first" && r.rank !== 1) continue;
      counts[r.cls] = (counts[r.cls] || 0) + 1;
      decks++;
    }
  }
  document.getElementById("stats").innerHTML = `
    <div class="stat"><div class="num">${nEvents}</div><div class="lbl">活動數</div></div>
    <div class="stat"><div class="num">${decks}</div><div class="lbl">納入牌組</div></div>
    <div class="stat"><div class="num">${players}</div><div class="lbl">總參賽</div></div>
    <div class="stat"><div class="lbl">${advanced ? "期間" : "月份"}</div><div>${periodLabel}</div></div>`;
  const base = advanced ? `?from=${from}&to=${to}&min=${min}` : `?m=${m}`;
  document.getElementById("seg").innerHTML =
    `<a class="${scope === "top8" ? "on" : ""}" href="${base}&scope=top8">前 8 強</a>
     <a class="${scope === "first" ? "on" : ""}" href="${base}&scope=first">僅第 1 名</a>`;
  document.getElementById("pie").innerHTML = pieHTML(counts) ||
    `<p class="hint">這個${advanced ? "期間" : "月"}沒有符合的資料。</p>`;

  document.getElementById("events").innerHTML = `<table>
    <thead><tr><th>日期</th><th>活動</th><th>店家</th><th>人數</th><th>名次／職業（點看單卡）</th></tr></thead>
    <tbody>${events.map(ev => `<tr>
      <td>${esc(ev.date)}</td><td>${esc(ev.title)}</td><td>${esc(ev.store)}</td><td>${ev.players}</td>
      <td>${ev.rankings.map(r => r.code
        ? `<a class="chip" href="${deckLink(ev._m, r.code)}"${clsColor(r.cls)}>#${r.rank} ${esc(r.cls)}</a>`
        : `<span class="chip hidden-deck"${clsColor(r.cls)}>#${r.rank} ${esc(r.cls)}·未公開</span>`).join("")}</td>
    </tr>`).join("")}</tbody></table>`;
}

// ================= 冠軍牌組·最省組件 =================
async function pageChampions() {
  const idx = await J("data/index.json");
  const m = P.get("m") || idx.latest;
  monthChips(document.getElementById("months"), idx.months, m);
  if (!m) return;
  const md = await J(`data/month/${m}.json`);
  const rows = md.champions.map((d, i) => `<tr>
    <td><span class="rankno">${i + 1}</span></td>
    <td class="cost">${yen(d.cost)}</td>
    <td>${clsBadge(d.cls)}</td>
    <td>${esc(d.event)}<div class="hint">${esc(d.date)} · ${d.players} 人</div></td>
    <td>${d.unpriced ? `<span class="warn">${d.unpriced} 張</span>` : "—"}</td>
    <td><a href="${deckLink(m, d.code, true)}">看單卡</a></td></tr>`).join("");
  document.getElementById("table").innerHTML = rows
    ? `<table><thead><tr><th>#</th><th>全新組建成本</th><th>職業</th><th>活動</th><th>無價卡</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
    : `<p class="hint">這個月沒有第 1 名牌組資料。</p>`;
}

// ================= 牌組單卡 =================
async function pageDeck() {
  const m = P.get("m"), code = P.get("code"), cheapest = P.get("cheapest") === "1";
  if (!m || !code) return;
  const [md, cards] = await Promise.all([J(`data/month/${m}.json`), J("data/cards.json")]);
  CARDS = cards;
  const nameOf = cn => (cards[cn] || [cn])[0];
  const priceOf = cn => (cards[cn] || [null, null])[1];
  const secEl = document.getElementById("sections");
  // 原始牌組在 DeckLog（Bushiroad 官方服務）的公開頁
  const dlBtn = `<a class="btn-ghost" style="margin-left:.5rem;font-size:.82rem;vertical-align:middle"
    target="_blank" rel="noopener"
    href="https://decklog.bushiroad.com/view/${encodeURIComponent(code)}">在 DeckLog 開啟 ↗</a>`;

  if (cheapest) {
    const d = md.cheapest[code];
    if (!d) { secEl.innerHTML = `<p class="hint">找不到這副牌組。</p>`; return; }
    document.getElementById("title").innerHTML =
      `牌組 ${esc(code)} ${clsBadge((md.decks[code] || {}).cls || "")}${dlBtn}`;
    document.getElementById("stats").innerHTML =
      `<div class="stat"><div class="num cost">${yen(d.cost)}</div><div class="lbl">全新組建（最便宜印刷）</div></div>` +
      (d.unpriced.length ? `<div class="stat"><div class="num warn">${d.unpriced.length}</div><div class="lbl">無價卡（未計入）</div></div>` : "");
    document.getElementById("note").innerHTML =
      "已把參賽的高稀有度卡換成<strong>同名最便宜印刷</strong>；主牌組與進化牌組分開比價。點卡片可看日文牌效。";
    secEl.innerHTML = [["主牌組", d.main], ["進化牌組", d.evo]].map(([t, rows]) => rows.length
      ? `<h2>${t}（${rows.reduce((a, r) => a + r.num, 0)} 張）</h2><div class="grid">` +
        rows.map(r => cardTile(r.cn, r.name,
          `<div class="code">${esc(r.cn)} ×${r.num}</div>` +
          (r.unit == null ? `<div class="warn">無價</div>` : `<div class="price">${yen(r.unit)}／張</div>`),
          r.unit == null ? "missing" : "")).join("") + "</div>"
      : "").join("");
  } else {
    const d = md.decks[code];
    if (!d) { secEl.innerHTML = `<p class="hint">找不到這副牌組。</p>`; return; }
    document.getElementById("title").innerHTML =
      `牌組 ${esc(code)} ${clsBadge(d.cls)}${dlBtn}`;
    document.getElementById("note").textContent = "點卡片可看日文牌效。";
    secEl.innerHTML = [["主牌組", d.main], ["進化牌組", d.evo]].map(([t, items]) => items.length
      ? `<h2>${t}（${items.reduce((a, [, n]) => a + n, 0)} 張）</h2><div class="grid">` +
        items.map(([cn, n]) => cardTile(cn, nameOf(cn),
          `<div class="code">${esc(cn)} ×${n}</div>` +
          (priceOf(cn) != null ? `<div class="price">${yen(priceOf(cn))}／張</div>` : ""))).join("") + "</div>"
      : "").join("");
  }
  lazyImgs(secEl);
}

// ================= 近期 Meta 牌組一覽 =================
const TIER_DESC = {
  0: "壓倒性表現：近期成績最突出的原型",
  1: "強勢：穩定大量入賞",
  2: "有競爭力：常見且有成績",
  3: "中堅：偶有好成績",
  4: "偶有佳績：入賞量少",
  5: "少量入賞：樣本不多，參考就好",
};

async function pageTiers() {
  const [tiers, cards] = await Promise.all([J("data/tiers.json"), J("data/cards.json")]);
  CARDS = cards;
  document.getElementById("win").textContent =
    `統計視窗：${tiers.window.start} ～ ${tiers.window.end}（近 ${tiers.window.days} 天）、` +
    `共 ${tiers.total_decks} 副公開入賞牌組`;
  if (tiers.others.decks) {
    document.getElementById("others").textContent =
      `另有 ${tiers.others.decks} 副入賞牌組因樣本太少（同型 <2 副）未列入檔位。`;
  }
  const byTier = {};
  for (const c of tiers.clusters) (byTier[c.tier] = byTier[c.tier] || []).push(c);

  document.getElementById("tiers").innerHTML = Object.keys(byTier).sort()
    .map(t => `<section class="tier-sec">
      <div class="tier-head"><span class="tier-tag t${t}">T${t}</span>
        <span class="hint">${TIER_DESC[t] || ""}</span></div>
      ${byTier[t].map(clusterHTML).join("")}</section>`).join("") ||
    `<p class="hint">視窗內沒有足夠資料。</p>`;
  lazyImgs(document.getElementById("tiers"));
}

function clusterHTML(c) {
  const grid = rows => rows.map(r => cardTile(r.cn, r.name,
    `<div class="code">${esc(r.cn)}</div>` +
    `<div class="code">×${r.num} · ${Math.round(r.p * 100)}%帶</div>`)).join("");
  const mainN = c.consensus.main.reduce((a, r) => a + r.num, 0);
  const evoN = c.consensus.evo.reduce((a, r) => a + r.num, 0);
  return `<div class="cluster">
    <div class="cluster-title">
      ${clsBadge(c.cls)}
      <strong>${esc(c.label)} 型</strong>
      <span class="hint">占比 ${c.share}% · 入賞 ${c.n} 副 · 冠軍 ${c.wins} 次</span>
    </div>
    <details><summary>共識牌表（主 ${mainN} 張核心 / 進化 ${evoN} 張）與範例牌組</summary>
      ${c.consensus.main.length ? `<h2>主牌組核心（張數取中位數）</h2><div class="grid">${grid(c.consensus.main)}</div>` : ""}
      ${c.consensus.evo.length ? `<h2>進化牌組核心</h2><div class="grid">${grid(c.consensus.evo)}</div>` : ""}
      ${c.flexible.length ? `<h2>彈性卡位（部分人帶）</h2><p>${c.flexible.map(n => `<span class="chip">${esc(n)}</span>`).join("")}</p>` : ""}
      <h2>實際範例牌組</h2>
      <p>${c.samples.map(s =>
        `<a class="chip" href="${deckLink(s.month, s.code)}">#${s.rank} · ${esc(s.event)}（${esc(s.date)}，${s.players} 人）</a>`).join("")}</p>
    </details></div>`;
}

// ================= 卡片查詢（以卡名為單位，不分印刷）=================
// 同名卡的代表印刷：優先非進化、卡號最小（通常是本體印刷而非閃卡/異畫）
function representativeCn(cns, cards) {
  return cns.slice().sort((a, b) =>
    ((cards[a] || [])[2] || 0) - ((cards[b] || [])[2] || 0) ||
    (a < b ? -1 : 1))[0];
}

async function pageSearch() {
  const form = document.getElementById("form"), input = document.getElementById("q");
  form.onsubmit = e => {
    e.preventDefault();
    location.search = "?q=" + encodeURIComponent(input.value.trim());
  };
  const exact = (P.get("n") || "").trim();          // 內部連結用：卡名精確查
  const q = exact || (P.get("q") || "").trim();
  if (!q) return;
  input.value = q;
  const out = document.getElementById("result");
  out.innerHTML = `<p class="hint">查詢中…</p>`;
  const cards = await J("data/cards.json");
  CARDS = cards;

  // 1) 卡號 → 反查名字；2) 名字（精確或模糊）→ 唯一命中直接查、多命中列名字選單
  let name = null;
  if (!exact && q.includes("-")) {
    const cn = Object.keys(cards).find(k => k.toLowerCase() === q.toLowerCase());
    if (!cn) {
      out.innerHTML = `<p class="hint">查無卡號「${esc(q)}」（只收錄入賞牌組用過的卡）。</p>`;
      return;
    }
    name = cards[cn][0];
  } else {
    const names = new Set(
      Object.values(cards).map(v => v[0])
            .filter(nm => nm && (exact ? nm === q : nm.includes(q))));
    if (!names.size) {
      out.innerHTML = `<p class="hint">沒有找到卡名含「${esc(q)}」的卡（只收錄入賞牌組用過的卡）。</p>`;
      return;
    }
    if (names.size > 1) {          // 多個不同卡名 → 每個名字一張代表卡，點了再查
      const list = [...names].sort().map(nm => {
        const cns = Object.keys(cards).filter(cn => cards[cn][0] === nm);
        const rep = representativeCn(cns, cards);
        return `<a href="?n=${encodeURIComponent(nm)}" style="text-decoration:none">` +
          cardTile(rep, nm, `<div class="code">${cns.length} 種印刷</div>`) + `</a>`;
      }).join("");
      out.innerHTML = `<h2>符合的卡名（${names.size} 個，點卡查用它的冠軍牌組）</h2>
        <div class="grid">${list}</div>`;
      lazyImgs(out);
      return;
    }
    name = [...names][0];
  }
  await renderUsageByName(out, name, cards);
}

async function renderUsageByName(out, name, cards) {
  const cns = Object.keys(cards).filter(cn => cards[cn][0] === name);
  const sets = [...new Set(cns.map(cn => cn.split("-")[0]))];
  const usages = await Promise.all(sets.map(s =>
    J(`data/usage/${encodeURIComponent(s)}.json`).catch(() => ({}))));
  const merged = new Map();      // 月份|牌組碼 → 合併所有印刷的張數（基本/進化分計）
  usages.forEach(u => {
    for (const cn of cns) {
      const evo = (cards[cn] || [])[2] === 1;
      for (const [m, code, event, date, players, num] of (u[cn] || [])) {
        const k = m + "|" + code;
        const e = merged.get(k) ||
          { m, code, event, date, players, main: 0, evo: 0 };
        e[evo ? "evo" : "main"] += num;
        merged.set(k, e);
      }
    }
  });
  const rows = [...merged.values()].sort((a, b) => (a.date < b.date ? 1 : -1));
  const rep = representativeCn(cns, cards);
  const head = `<div class="grid" style="max-width:140px;margin:.6rem 0">` +
    cardTile(rep, name, `<div class="code">${cns.length} 種印刷</div>`) + `</div>
    <p class="hint">已合併「${esc(name)}」的所有印刷（閃卡／異畫視為同一張卡）。</p>`;
  if (!rows.length) {
    out.innerHTML = head + `<p class="hint">沒有第 1 名牌組用過這張卡。</p>`;
    lazyImgs(out);
    return;
  }
  const copies = e => (e.main ? `×${e.main}` : "") +
    (e.evo ? `${e.main ? "，" : ""}進化×${e.evo}` : "");
  out.innerHTML = head +
    `<h2>用過它的冠軍牌組（${rows.length} 副，新到舊）</h2>
    <table><thead><tr><th>日期</th><th>活動</th><th>人數</th><th>帶幾張</th><th></th></tr></thead>
    <tbody>` + rows.map(e => `<tr>
      <td>${esc(e.date)}</td><td>${esc(e.event)}</td><td>${e.players}</td>
      <td>${copies(e)}</td>
      <td><a href="${deckLink(e.m, e.code)}">看單卡</a></td></tr>`).join("") +
    `</tbody></table>`;
  lazyImgs(out);
}

// ---- dispatch ----
const page = document.body.dataset.page;
({ meta: pageMeta, champions: pageChampions, deck: pageDeck, tiers: pageTiers,
   search: pageSearch }[page] || (() => {}))()
  .catch(e => {
    const el = document.createElement("p");
    el.className = "hint warn";
    el.textContent = "資料載入失敗：" + e.message;
    document.querySelector("main").prepend(el);
  });
