// Adapted for DA3 uploads on 2026-09-21; see NOTICE.md.
// room3dgs アップロード＆セット管理（バニラ JS, CDN 非依存）
const $ = (s) => document.querySelector(s);
let picked = [];      // 選択中の File[]
let MAX_SETS = 20;
let uploadedCount = 0;
let defaultDevice = "cpu";
function updateSaveButton() { saveBtn.disabled = picked.length < 2 || picked.length > 8 || !$("#set-name").value.trim() || uploadedCount >= MAX_SETS; }
let pollTimers = {};  // set_id -> interval

const STATUS_LABEL = {
  none: "未生成", running: "生成中…", done: "生成済み", error: "エラー",
};

// ---------- 新規セット作成 ----------
const drop = $("#drop");
const fileInput = $("#files");
const saveBtn = $("#save-btn");

drop.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => setPicked([...fileInput.files]));

["dragenter", "dragover"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
drop.addEventListener("drop", (e) => {
  const fs = [...e.dataTransfer.files].filter((f) => f.type.startsWith("image/") || /\.(hei[cf]|mpo)$/i.test(f.name));
  setPicked(fs);
});

function setPicked(files) {
  picked = files;
  $("#pick-count").textContent = files.length ? `${files.length} 枚を選択中` : "";
  updateSaveButton();
}
$("#set-name").addEventListener("input", () => {
  updateSaveButton();
});

$("#new-set-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#new-set-msg");
  msg.className = "msg";
  if (picked.length < 2 || picked.length > 8) { msg.textContent = "写真を2〜8枚選んでください"; return; }

  const fd = new FormData();
  fd.append("name", $("#set-name").value.trim());
  picked.forEach((f) => fd.append("files", f));

  saveBtn.disabled = true;
  msg.textContent = "アップロード中…";
  try {
    const res = await fetch("/api/sets", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    msg.className = "msg ok";
    msg.textContent = "保存しました";
    $("#new-set-form").reset();
    setPicked([]);
    await loadSets();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = "失敗: " + err.message;
  } finally {
    updateSaveButton();
  }
});

// ---------- 一覧描画 ----------
async function loadSets() {
  const res = await fetch("/api/sets");
  const data = await res.json();
  MAX_SETS = data.max;
  defaultDevice = data.default_device || "cpu";
  uploadedCount = data.sets.filter(s => !s.read_only).length;
  for (const timer of Object.values(pollTimers)) clearInterval(timer);
  pollTimers = {};
  $("#set-count").textContent = `（追加 ${uploadedCount}/${MAX_SETS}、既存 ${data.sets.length-uploadedCount}）`;
  updateSaveButton();

  const grid = $("#sets");
  grid.innerHTML = "";
  if (data.sets.length === 0) {
    grid.innerHTML = '<p class="empty">まだセットがありません。上から写真を追加してください。</p>';
    return;
  }
  for (const s of data.sets) grid.appendChild(renderCard(s));
}

function renderCard(s) {
  const card = document.createElement("div");
  card.className = "card";
  const photos = (s.images || []).map((name, index) => {
    const base = `/api/sets/${encodeURIComponent(s.id)}`;
    const filename = encodeURIComponent(name);
    const label = escapeHtml(`${s.name} — 写真${index + 1}を別タブで開く`);
    return `<a href="${base}/photo/${filename}" target="_blank" rel="noopener" aria-label="${label}" title="${label}"><img class="thumb" src="${base}/thumb/${filename}" alt="写真${index + 1}" loading="lazy"></a>`;
  }).join("");
  const gauss = s.num_gaussians ? ` ・ ${s.num_gaussians.toLocaleString()} ガウシアン` : "";
  card.innerHTML = `
    ${photos ? `<div class="photos">${photos}</div>` : ""}
    <div class="body">
      <div class="name">${escapeHtml(s.name)}</div>
      <div class="meta">${s.num_images} 枚${gauss}${s.elapsed_seconds ? ` ・ ${s.elapsed_seconds.toFixed(1)}秒` : ""}</div>
      <div><span class="badge ${s.status}" data-badge>${STATUS_LABEL[s.status] || s.status}</span></div>
      <div class="msg" data-msg>${escapeHtml(s.status === "error" ? s.message : "")}</div>
      <div class="actions">
        ${s.read_only ? "" : `<select data-device aria-label="実行環境"><option value="cpu">CPU</option><option value="rocm">GPU（ROCm）</option></select><button class="secondary" data-recon ${s.status === "running" ? "disabled" : ""}>
          ${s.has_ply ? "再生成" : "3Dを作成"}
        </button>`}
        ${s.has_ply ? `<a href="/viewer?set=${s.id}">3Dを見る</a>` : ""}
        ${s.read_only ? "" : `<button class="danger" data-del ${s.status === "running" ? "disabled" : ""}>一覧から削除</button>`}
      </div>
    </div>`;

  if (card.querySelector("[data-device]")) card.querySelector("[data-device]").value = s.device || defaultDevice;
  card.querySelector("[data-recon]")?.addEventListener("click", () => startRecon(s.id, card));
  card.querySelector("[data-del]")?.addEventListener("click", () => delSet(s.id, s.name));
  if (s.status === "running") pollStatus(s.id, card);
  return card;
}

// ---------- 再構成 ----------
async function startRecon(id, card) {
  const btn = card.querySelector("[data-recon]");
  btn.disabled = true;
  card.querySelector("[data-del]").disabled = true;
  setBadge(card, "running", "生成中…");
  try {
    const res = await fetch(`/api/sets/${id}/reconstruct`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({device:card.querySelector("[data-device]").value}) });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    pollStatus(id, card);
  } catch (err) {
    setBadge(card, "error", "");
    card.querySelector("[data-msg]").textContent = "失敗: " + err.message;
    btn.disabled = false;
    card.querySelector("[data-del]").disabled = false;
  }
}

function pollStatus(id, card) {
  clearInterval(pollTimers[id]);
  pollTimers[id] = setInterval(async () => {
    try {
      const res = await fetch(`/api/sets/${id}/status`);
      const st = await res.json();
      if (st.status === "running") {
        setBadge(card, "running", "生成中…");
        return;
      }
      clearInterval(pollTimers[id]);
      if (st.status === "error") {
        setBadge(card, "error", "");
        card.querySelector("[data-msg]").textContent = st.message || "エラー";
        card.querySelector("[data-recon]").disabled = false;
        card.querySelector("[data-del]").disabled = false;
      } else {
        await loadSets(); // done → カード再描画（見るボタン出現）
      }
    } catch (_) { /* 継続 */ }
  }, 1000);
}

function setBadge(card, status, text) {
  const b = card.querySelector("[data-badge]");
  b.className = "badge " + status;
  b.textContent = text || (STATUS_LABEL[status] || status);
}

async function delSet(id, name) {
  if (!confirm(`セット「${name}」を一覧から取り除きますか？（写真と3Dは退避されます）`)) return;
  clearInterval(pollTimers[id]);
  const res = await fetch(`/api/sets/${id}`, { method: "DELETE" });
  if (!res.ok) { alert((await res.json()).detail || "削除できませんでした"); return; }
  await loadSets();
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

loadSets().catch(e => { $("#new-set-msg").textContent = "一覧の取得に失敗しました: " + e.message; });


// Update when the PC changes networks (for example, iPhone tethering).
async function refreshConnection() {
  const urls = document.getElementById('connection-urls');
  const note = document.getElementById('connection-note');
  try {
    const response = await fetch('/api/connection', {cache:'no-store'});
    if (!response.ok) throw new Error('IPアドレスを取得できませんでした');
    const data = await response.json();
    urls.replaceChildren();
    for (const entry of data.urls) {
      const item = document.createElement(data.local_only ? 'code' : 'a');
      item.textContent = entry.url;
      if (!data.local_only) item.href = entry.url;
      urls.append(item);
    }
    if (!data.urls.length) urls.textContent = data.error || 'ネットワーク接続が見つかりません';
    note.textContent = data.local_only
      ? '現在はこのPCのみ接続可能です。iPhoneから使う場合は外部接続を有効にして再起動してください。'
      : '同じネットワークのiPhoneなどで、このURLを入力してください。';
  } catch (error) {
    urls.textContent = error.message;
    note.textContent = '';
  }
}
refreshConnection();
window.addEventListener('focus', refreshConnection);
setInterval(() => { if (!document.hidden) refreshConnection(); }, 15000);
