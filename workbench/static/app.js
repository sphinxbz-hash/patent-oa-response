"use strict";

const $ = (id) => document.getElementById(id);
const state = { cases: [], current: null, tab: "research", busy: false, dirty: false, drafts: new Map(), metadataDrafts: new Map(), poll: null, loadToken: 0, retry: null, previewId: null, outputCase: null, outputKey: null, outputAbort: null };
const roleNames = { oa: "审查意见", response: "答复", claims: "权利要求", publication: "公开文本", original: "原始申请", other: "其他" };
const versionNames = { unknown: "未确认", pending: "当前待审", granted: "授权版本", reference: "参考版本", publication: "公开版本", not_entered: "未进入审查", auxiliary: "辅助请求" };
const statusNames = { new: "待研究", created: "待研究", idle: "待处理", researching: "研究中", researched: "研究完成", ready: "可处理", generating: "生成中", generated: "已生成", complete: "已完成", completed: "已完成", error: "处理失败", failed: "处理失败", partial: "待补充材料", needs_documents: "待补充材料" };
const sourceFields = { "selected-response": "selected_response_id", "selected-claims": "selected_claims_id", "pending-claims": "pending_claims_id", "target-oa": "target_oa_id", "original-document": "original_id" };
const acceptedRoles = { selected_response_id: ["response"], selected_claims_id: ["claims"], pending_claims_id: ["claims"], target_oa_id: ["oa"], original_id: ["original"] };
statusNames.ocr = "正在识别文字";
const working = () => ["researching", "generating", "ocr"].includes(state.current?.status);
const hasExports = (item) => Boolean(item?.has_exports || (Array.isArray(item?.exports) ? item.exports.length : item?.exports && Object.keys(item.exports).length));
const caseStatusLabel = (item) => item?.status === "idle" && hasExports(item) ? (item.exports_stale ? "待重新生成" : "已生成") : statusNames[item?.status] || item?.status || "待处理";
const text = (value) => value == null ? "" : typeof value === "string" ? value : typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
const elt = (tag, className, content) => { const node = document.createElement(tag); if (className) node.className = className; if (content != null) node.textContent = text(content); return node; };
const casePath = (id = state.current?.id) => `/api/cases/${encodeURIComponent(id)}`;
const docs = () => Array.isArray(state.current?.documents) ? state.current.documents : [];
const hasOriginal = (doc) => doc.status === "downloaded" || doc.status === "imported" || doc.downloaded === true;
const fileURL = (doc) => `${casePath()}/files/${encodeURIComponent(doc.id)}`;
const safeURL = (value) => { try { const url = new URL(value, window.location.origin); return ["http:", "https:"].includes(url.protocol) ? url.href : null; } catch { return null; } };
const appendLink = (container, label, url, className = "", download = false) => { const safe = safeURL(url); if (!safe) return; const link = elt("a", className, label); link.href = safe; if (download) link.setAttribute("download", ""); else { link.target = "_blank"; link.rel = "noopener noreferrer"; } container.append(link); };
const dateLabel = (value, withTime = false) => { if (!value) return "日期未知"; const date = new Date(value); if (Number.isNaN(date.getTime())) return text(value); return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", ...(withTime ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}) }).format(date); };

async function request(path, payload) {
  let response;
  try { response = await fetch(path, { method: payload === undefined ? "GET" : "POST", headers: payload === undefined ? {} : { "Content-Type": "application/json" }, body: payload === undefined ? undefined : JSON.stringify(payload), credentials: "same-origin" }); }
  catch { throw new Error("无法连接本地工作台。请确认服务仍在运行，然后重新加载。当前输入会保留。"); }
  let result;
  try { result = await response.json(); } catch { throw new Error(`服务返回了无法读取的内容（${response.status}）。请重新加载案件后再试。`); }
  if (!response.ok) throw new Error(result.error || `操作失败（${response.status}），请检查材料与输入后再试。`);
  return result;
}

function showError(error, retry = refreshCurrent) {
  $("error-text").textContent = error.message || text(error);
  state.retry = retry;
  $("retry-button").hidden = !retry;
  $("retry-button").textContent = "重新加载";
  $("error-banner").hidden = false;
}
function notice(message) { $("notice").textContent = message; $("notice").hidden = false; }
function clearMessages() { $("error-banner").hidden = true; $("notice").hidden = true; }
function updateControls() {
  for (const id of ["create-button", "demo-button", "upload-button", "save-button", "refresh-cases"]) $(id).disabled = state.busy;
  $("research-button").disabled = state.busy || working();
  $("ocr-button").disabled = state.busy || working() || !docs().some((d) => hasOriginal(d) && /\.pdf$/i.test(d.local_path || d.filename || ""));
  $("generate-button").disabled = state.busy || working();
  document.querySelectorAll(".case-item").forEach((button) => { button.disabled = state.busy; });
  document.querySelectorAll("#settings-form input, #settings-form select, #settings-form textarea, #settings-form button, #upload-form input, #upload-form select, #upload-form textarea, #upload-form button").forEach((control) => { control.disabled = state.busy; });
  document.querySelectorAll("#document-metadata-form input, #document-metadata-form select, #document-metadata-form button").forEach((control) => { control.disabled = state.busy || state.current?.status === "generating"; });
  $("generate-button").disabled = state.busy || working();
  $("settings-form").setAttribute("aria-busy", String(state.busy));
  $("ocr-engine").disabled = state.busy || working();
}
async function perform(task, buttonId, busyText) {
  if (state.busy) return;
  state.busy = true;
  clearMessages();
  const button = buttonId ? $(buttonId) : null;
  const originalText = button?.textContent;
  if (button && busyText) button.textContent = busyText;
  updateControls();
  try { await task(); }
  catch (error) { showError(error); }
  finally { state.busy = false; if (button && originalText) button.textContent = originalText; updateControls(); }
}

function renderCaseList() {
  const list = $("case-list"); list.replaceChildren();
  if (!state.cases.length) { list.append(elt("p", "sidebar-empty", "尚无案件。输入申请号开始，或打开虚构示例体验流程。")); return; }
  state.cases.forEach((item) => {
    const button = elt("button", "case-item"); button.type = "button"; button.setAttribute("aria-current", String(item.id === state.current?.id));
    button.append(elt("strong", "", item.input_number || item.target_application || "未命名案件"));
    button.append(elt("span", "", `${item.target_country || "目标待定"} · ${dateLabel(item.updated_at || item.created_at)}`));
    button.append(elt("span", "case-item-state", `${item.is_demo ? "虚构示例 · " : ""}${caseStatusLabel(item.id === state.current?.id ? state.current : item)}`));
    button.addEventListener("click", () => { if (!state.busy) selectCase(item.id); }); list.append(button);
  });
  updateControls();
}
function upsertCase(item) { const index = state.cases.findIndex((row) => row.id === item.id); if (index < 0) state.cases.unshift(item); else state.cases[index] = item; renderCaseList(); }
async function loadCases() { const result = await request("/api/cases"); state.cases = result.cases || []; renderCaseList(); }
function rememberSelection(id) { try { localStorage.setItem("family-workbench:selected-case", id); } catch { /* Local storage can be unavailable in privacy mode. */ } }
function collapseSidebar() { document.querySelector(".sidebar").classList.add("is-collapsed"); $("mobile-sidebar-toggle").setAttribute("aria-expanded", "false"); $("mobile-sidebar-toggle").textContent = "案件管理"; }
function rememberDraft() { if (state.current && state.dirty) state.drafts.set(state.current.id, readSettings()); }
async function selectCase(id) {
  rememberDraft();
  const token = ++state.loadToken;
  clearTimeout(state.poll);
  try {
    const item = await request(casePath(id));
    if (token !== state.loadToken) return;
    state.current = item; state.previewId = null; state.dirty = state.drafts.has(id); rememberSelection(id);
    $("document-preview").hidden = true; $("upload-form").hidden = true; clearMessages(); renderCase(true); setTab("research"); collapseSidebar(); schedulePoll();
  } catch (error) { if (token === state.loadToken) { showError(error, () => selectCase(id)); schedulePoll(); } }
}
function applyCase(item, resetSettings = false) { const changed = state.current?.id !== item.id; state.current = item; upsertCase(item); renderCase(resetSettings); if (changed) collapseSidebar(); schedulePoll(); }
async function refreshCurrent() {
  clearMessages();
  try { await loadCases(); if (state.current) { const id = state.current.id; const item = await request(casePath(id)); if (state.current?.id === id) applyCase(item, !state.dirty); } }
  catch (error) { showError(error); }
}
function schedulePoll() {
  clearTimeout(state.poll);
  if (!working()) return;
  state.poll = setTimeout(async () => {
    if (state.busy) { schedulePoll(); return; }
    const id = state.current?.id;
    try { const item = await request(casePath(id)); if (state.current?.id === id) applyCase(item, !state.dirty); }
    catch (error) { if (state.current?.id === id) showError(error); }
  }, 1800);
}
function setTab(name) {
  state.tab = name;
  document.querySelectorAll("[role=tab]").forEach((tab) => { const selected = tab.dataset.tab === name; tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1; });
  ["research", "selection", "output"].forEach((value) => { $(`panel-${value}`).hidden = value !== name; });
  if (name === "output") loadOutputPreview();
}
function renderCase(resetSettings = false) {
  const item = state.current; if (!item) return;
  $("welcome").hidden = true; $("case-workspace").hidden = false;
  $("case-number").textContent = item.input_number || item.target_application || "未命名案件";
  $("case-title").textContent = item.title || "申请名称尚未取得";
  $("case-status").textContent = caseStatusLabel(item);
  $("case-status").className = `badge ${working() ? "busy" : ["error", "failed"].includes(item.status) ? "error-state" : item.exports_stale ? "warning" : hasExports(item) || ["generated", "complete", "completed"].includes(item.status) ? "success" : ""}`;
  $("demo-badge").hidden = !(item.is_demo || item.demo);
  $("case-meta").replaceChildren(elt("span", "", `目标：${item.target_country || "未指定"} ${item.target_application || "· 申请号待确认"}`), elt("span", "", "输出：英文 / 中文摘要"), elt("span", "", `更新 ${dateLabel(item.updated_at, true)}`));
  $("family-history-link").href = `${casePath()}/reports/01-同族审查历史报告.md`;
  $("upload-country").placeholder = `例如 ${item.target_country || "BR"} / EP`;
  renderProgress(); renderFamily(); renderDocuments(); renderGaps(); renderEvents(); renderOutputs();
  if (resetSettings || !state.dirty) renderSettings();
  if (state.previewId) previewDocument(state.previewId, false);
  updateControls();
}
function eventText(event) { return typeof event === "string" ? event : event.message || event.detail || event.description || text(event); }
function renderProgress() {
  const events = state.current.events || [];
  $("job-progress").hidden = !working();
  $("progress-label").textContent = state.current.status === "ocr" ? "正在识别扫描材料" : state.current.status === "generating" ? "正在生成英文答复包" : "正在研究同族与审查材料";
  $("progress-detail").textContent = events.length ? eventText(events[events.length - 1]) : "任务已开始，正在等待来源返回。";
}
function emptyTable(tbody, message, columns) { const row = elt("tr"); const cell = elt("td", "table-empty", message); cell.colSpan = columns; row.append(cell); tbody.append(row); }
function renderFamily() {
  const family = Array.isArray(state.current.family) ? state.current.family : state.current.family?.members || [];
  const rows = $("family-rows"); rows.replaceChildren(); $("family-count").textContent = `${family.length} 条同族记录`;
  $("family-options").replaceChildren();
  if (!family.length) emptyTable(rows, working() ? "正在检索同族记录，可先补充已有材料。" : "尚未取得同族记录。可以重新研究，或先导入已知同族的原件。", 4);
  family.forEach((member) => {
    const row = elt("tr"); const number = elt("td"); number.append(elt("span", "table-title", member.application || member.publication || "号码未取得"));
    if (member.application && member.publication) number.append(elt("span", "table-sub", member.publication));
    const status = elt("td"); status.append(elt("span", "", member.status || "状态未核实")); if (member.status_source) status.append(elt("span", "table-sub", member.status_source));
    const source = elt("td"); if (member.url) appendLink(source, "查看来源", member.url); else source.textContent = "未提供";
    row.append(elt("td", "", member.country || "未知"), number, status, source); rows.append(row);
    const option = document.createElement("option"); option.value = member.application || member.publication || member.country || ""; option.label = `${member.country || ""} ${member.publication || ""}`; $("family-options").append(option);
  });
}
function documentStatus(doc) {
  if (doc.status === "imported") return ["已导入", "success"];
  if (doc.status === "downloaded" || doc.downloaded === true) return ["已下载原件", "success"];
  if (doc.status === "manual_required") return ["需手动补充", "warning"];
  return ["仅来源记录", ""];
}
function renderDocuments() {
  const rows = $("document-rows"); rows.replaceChildren();
  if (!docs().length) { emptyTable(rows, "尚无材料。点击“补充材料”导入原件，或等待研究取得可访问文件。", 5); return; }
  docs().forEach((doc) => {
    const row = elt("tr"); const title = elt("td"); title.append(elt("span", "table-title", doc.title || doc.filename || "未命名材料"), elt("span", "table-sub", dateLabel(doc.date)));
    const kind = elt("td"); kind.append(elt("span", "", `${doc.country || "未知"} · ${roleNames[doc.role] || doc.role || "其他"}`)); if (doc.language) kind.append(elt("span", "table-sub", `语言 ${doc.language}`));
    const status = elt("td"); const [label, tone] = documentStatus(doc); status.append(elt("span", `badge ${tone}`, label));
    if (hasOriginal(doc) && !text(doc.text).trim()) status.append(elt("p", "status-note", "未提取到文字，需补充可读文本"));
    const actions = elt("td"); const links = elt("div", "inline-links"); const preview = elt("button", "text-button", "详情"); preview.type = "button"; preview.addEventListener("click", () => previewDocument(doc.id)); links.append(preview);
    if (hasOriginal(doc)) appendLink(links, doc.status === "imported" ? "导入原件" : "原件", fileURL(doc), "", true);
    if (doc.ocr) { const ocrStatus = doc.ocr.status === "not_needed" ? "文字已提取" : doc.ocr.status === "complete" ? `OCR ${doc.ocr.ocr_pages} 页` : "文字识别待完成"; title.append(elt("span", "table-sub", ocrStatus + (doc.ocr.review_pages?.length ? " · 部分页面需核对" : ""))); }
    if (doc.url || doc.source_url) appendLink(links, "来源", doc.url || doc.source_url);
    actions.append(links); row.append(title, kind, elt("td", "", versionNames[doc.version_status] || doc.version_status || "未确认"), status, actions); rows.append(row);
  });
}
function previewDocument(id, scroll = true) {
  const doc = docs().find((item) => item.id === id); if (!doc) return;
  const previous = state.previewId;
  state.previewId = id;
  $("document-preview").hidden = false; $("preview-title").textContent = doc.title || doc.filename || "材料详情";
  $("preview-meta").textContent = `${doc.country || "法域未知"} · ${roleNames[doc.role] || doc.role || "其他"} · ${versionNames[doc.version_status] || "版本未确认"} · ${dateLabel(doc.date)}`;
  $("preview-links").replaceChildren();
  if (hasOriginal(doc)) appendLink($("preview-links"), "下载保存的原件", fileURL(doc), "", true);
  if (doc.pages?.length) appendLink($("preview-links"), "下载分页文字 TXT", `${casePath()}/text/${encodeURIComponent(doc.id)}`, "", true);
  if (doc.url || doc.source_url) appendLink($("preview-links"), "打开原始来源", doc.url || doc.source_url);
  $("preview-notes").textContent = Array.isArray(doc.notes) ? doc.notes.map(text).join("\n") : text(doc.notes);
  const bodyView = $("preview-text-view").value === "body";
  $("preview-text").textContent = doc.pages?.length ? doc.pages.map((page) => `--- 第 ${page.number || "?"} 页 · ${page.method === "ocr" ? "OCR" : page.method === "failed" ? "识别失败" : page.method === "unavailable" ? "待 OCR" : "原文提取"} ---\n${text(bodyView ? page.body_text || page.text : page.text).trim() || "[未取得文字]"}${bodyView && page.excluded_blocks?.length ? `\n[已排除 ${page.excluded_blocks.length} 个版面元素，完整文字可切换查看]` : ""}`).join("\n\n") : text(bodyView ? doc.draft_text || doc.text : doc.text).trim() || (hasOriginal(doc) ? "未取得可读取的正文。可以点击“识别扫描材料”重试，或补充经过核对的文字。" : "当前仅有来源记录，尚未取得原件。请通过来源链接下载后导入。") ;
  const key = `${state.current.id}/${id}`; const draft = state.metadataDrafts.get(key);
  if (previous !== id || !draft) {
    const values = draft || doc;
    $("metadata-title").value = values.title || values.filename || ""; $("metadata-role").value = values.role || "other"; $("metadata-country").value = values.country || ""; $("metadata-date").value = values.date || ""; $("metadata-version").value = values.version_status || "unknown"; $("metadata-application").value = values.application || "";
    const language = values.language || "unknown"; const languageSelect = $("metadata-language");
    languageSelect.querySelectorAll("[data-extra-language]").forEach((option) => option.remove());
    if (![...languageSelect.options].some((option) => option.value === language)) { const option = elt("option", "", language); option.value = language; option.dataset.extraLanguage = "true"; languageSelect.append(option); }
    languageSelect.value = language;
  }
  $("metadata-save-state").textContent = draft ? "有未保存修改" : "";
  if (previous !== id) $("document-metadata-details").open = Boolean(draft);
  updateControls();
  if (scroll) $("document-preview").scrollIntoView({ behavior: "auto", block: "nearest" });
}
function readDocumentMetadata() { return { title: $("metadata-title").value.trim(), role: $("metadata-role").value, country: $("metadata-country").value.trim().toUpperCase(), date: $("metadata-date").value, language: $("metadata-language").value, version_status: $("metadata-version").value, application: $("metadata-application").value.trim() }; }
function markMetadataDirty() { if (!state.current || !state.previewId) return; state.metadataDrafts.set(`${state.current.id}/${state.previewId}`, readDocumentMetadata()); $("metadata-save-state").textContent = "有未保存修改"; }
async function saveDocumentMetadata() {
  if (!state.current || !state.previewId) return;
  const id = state.previewId; const caseId = state.current.id; rememberDraft();
  const item = await request(`${casePath(caseId)}/documents/${encodeURIComponent(id)}`, readDocumentMetadata());
  state.metadataDrafts.delete(`${caseId}/${id}`); applyCase(item, true);
  notice("文件信息已更新，原始文件已保留。已有答复包需重新生成以应用这些信息。");
}
function gapLabel(value) {
  const message = text(value);
  const known = {
    "Missing usable English family response.": "缺少可用的英文同族答复。",
    "Missing usable English grant or response cycle claims.": "缺少可用的英文授权权项，或与答复轮次对应的权项。",
    "Missing usable target pending claims baseline.": "缺少目标申请的当前待审权项，尚不能建立修订比较底稿。",
    "Missing usable target Office Action.": "缺少目标申请可读取的审查意见。",
    "Missing usable target original filing.": "缺少目标申请的原始申请文件，修改依据尚待核查。",
    "Selected claims and response belong to different known family members; response reuse is disabled.": "所选权项与答复属于不同同族申请，本次未复用该答复。",
    "Selected claims and response belong to different response cycles; response reuse is disabled.": "所选权项与答复属于不同答复轮次，本次未复用该答复。",
    "Source country matches, but the response and claims application member pairing is unverified.": "答复与权项的所属法域一致，但尚未核实是否对应同一件同族申请。",
    "The target pending claims are not identified as English; no cross language target redline is produced.": "目标待审权项未标识为英文，本次未生成跨语言的修订比较。",
    "The selected pending baseline is not the latest supplied pending version; immediate prior version is unverified.": "所选底稿不是已提供材料中最新的待审版本，尚需确认紧邻本次修改前的有效版本。",
    "No supported OA heading or patent citation pattern was detected; the full OA requires review.": "尚未从审查意见中识别出支持的标题或专利引证，请核对完整原文。",
    "Amendment support in the target original remains unverified.": "修改内容在目标原始申请中的依据尚未核验。",
    "Filing deadline and fees remain unverified.": "答复期限与适用费用尚未核验。",
    "Target application identity is missing; foreign response identifiers have not been adapted.": "目标申请号尚未填写，参考答复中的原申请标识未作替换。",
    "Unable to parse proposed claims as one numbered claim set. Check duplicate claim numbers and version boundaries.": "拟复用权项未能识别为一套完整的编号权项，请检查重复编号及版本边界。",
    "Unable to parse target pending claims as one numbered claim set. No target redline is produced.": "目标待审权项未能识别为一套完整的编号权项，本次未生成目标修订比较。",
    "The selected claim text has no recognised numbered claims; no claim listing was fabricated.": "所选权项文本中未识别出编号权项，本次未据此编造权项清单。",
    "No proposed numbered English claims are available.": "尚无可用的编号英文权项。",
    "The target pending text has no recognised numbered claims; no target redline was produced.": "目标待审文本中未识别出编号权项，本次未生成修订比较。",
    "A proposed new US claim number is not above every supplied prior claim number; verify the full claim numbering history.": "拟新增的美国权项编号未高于已提供的全部历史编号，请核对完整编号历史。",
    "尚未锁定本案当前有效待审权项；不会将公开文本自动升级为 pending claims": "尚未锁定本案当前有效待审权项；公开文本不会自动视为待审版本。"
  };
  if (known[message]) return known[message];
  const missing = message.match(/^Selected (response|claims|target pending claims|target OA|target original) .+ is missing; no substitute was selected\.$/);
  const incompatible = message.match(/^Selected (response|claims|target pending claims|target OA|target original) .+ has an incompatible role, member, version, language, status, or no extracted text\.$/);
  const names = { response: "参考答复", claims: "拟复用权项", "target pending claims": "目标待审权项", "target OA": "目标审查意见", "target original": "目标原始申请" };
  if (missing) return `所选${names[missing[1]]}已不可用，本次未自动替换为其他材料。`;
  if (incompatible) return `所选${names[incompatible[1]]}的类型、同族、版本、语言或取得状态不符合要求，或未提取到文字。请核对材料。`;
  const scan = message.match(/^(.+) has no extracted text; a scan may require OCR or manual text entry\.$/);
  const ocrGap = message.match(/^OCR source (.+):/);
  if (ocrGap) { const doc = docs().find((item) => item.id === ocrGap[1]); return `${doc?.title || "来源材料"}：部分页面未识别或置信度较低，请查看材料详情并对照原件核对。`; }
  if (scan) { const doc = docs().find((item) => item.id === scan[1]); return `${doc?.title || doc?.filename || "已取得的材料"}未提取到文字；扫描件需补充识别后的文本或手动录入。`; }
  const foreign = message.match(/^Foreign legal or procedural references remain unresolved: (.+)\. No local law substitution was made\.$/);
  if (foreign) return `以下外国法律或程序引述尚待处理：${foreign[1]}。本次未将其替换为目标法域法律。`;
  const historical = message.match(/^US historical claim statuses require verification for claims (.+)\.$/);
  if (historical) return `美国权项 ${historical[1]} 的历史状态尚待核验。`;
  return message;
}
function renderGaps() {
  const gaps = Array.isArray(state.current.gaps) ? state.current.gaps : [];
  const manual = docs().filter((doc) => doc.status === "manual_required");
  const area = $("gaps"); area.replaceChildren();
  if (!gaps.length && !manual.length) area.append(elt("p", "empty-inline", working() ? "研究完成后会列出尚未取得的材料与补充方式。" : "当前没有已记录的缺件。材料是否完整仍以目标申请审查记录为准。"));
  const list = elt("ul", "gap-list");
  gaps.forEach((gap) => { const row = elt("li"); if (typeof gap === "string") row.append(elt("strong", "", gapLabel(gap))); else { row.append(elt("strong", "", gapLabel(gap.title || gap.message || "待补充事项"))); const detail = gap.detail || gap.description || gap.guidance || gap.instructions; if (detail) row.append(elt("p", "", gapLabel(detail))); if (gap.url || gap.source_url) { const links = elt("div", "inline-links"); appendLink(links, "前往来源补充", gap.url || gap.source_url); row.append(links); } } list.append(row); });
  manual.forEach((doc) => { const row = elt("li"); row.append(elt("strong", "", `${doc.title || doc.filename || roleNames[doc.role] || "来源材料"}：尚未取得原件`)); const instructions = Array.isArray(doc.notes) ? doc.notes.join("\n") : doc.notes; row.append(elt("p", "", instructions || "打开来源页面，找到对应申请的审查档案，下载文件后通过“补充材料”导入。")); const links = elt("div", "inline-links"); if (doc.url || doc.source_url) appendLink(links, "打开来源入口", doc.url || doc.source_url); const upload = elt("button", "text-button", "导入取得的材料"); upload.type = "button"; upload.addEventListener("click", () => { showUpload(); $("upload-role").value = doc.role || "other"; $("upload-country").value = doc.country || ""; $("upload-url").value = doc.url || doc.source_url || ""; $("upload-title").value = doc.title || ""; }); links.append(upload); row.append(links); list.append(row); });
  if (list.children.length) area.append(list);
  (state.current.manual_guides || []).forEach((guide) => {
    const section = elt("section", "manual-guide"); section.append(elt("h3", "", `${guide.country || "来源"} · ${guide.application || "申请号待确认"}`));
    if (guide.instruction) section.append(elt("p", "guide-instruction", guide.instruction));
    const links = elt("div", "inline-links"); if (guide.url) appendLink(links, "打开官方 / 来源入口", guide.url); const upload = elt("button", "text-button", "补传取得的文件"); upload.type = "button"; upload.addEventListener("click", () => { showUpload(); $("upload-country").value = guide.country || ""; $("upload-url").value = guide.url || ""; }); links.append(upload); section.append(links);
    if (Array.isArray(guide.files) && guide.files.length) { const table = compactTable(["目录中的文件", "文件日期", "取得情况", "来源"]); guide.files.forEach((file) => { const row = elt("tr"); const status = documentStatus(file); const statusCell = elt("td"); statusCell.append(elt("span", `badge ${status[1]}`, status[0])); const source = elt("td"); if (file.url) appendLink(source, "查看来源", file.url); else source.textContent = "请从入口查找"; row.append(elt("td", "", file.title || "未命名材料"), elt("td", "", dateLabel(file.date)), statusCell, source); table.body.append(row); }); section.append(table.wrap); }
    else section.append(elt("p", "hint", "尚未取得可核验的文件目录；请在来源系统核对具体文件与日期。"));
    area.append(section);
  });
}
function renderEvents() { const events = state.current.events || []; $("event-count").textContent = `（${events.length}）`; $("event-rows").replaceChildren(); events.slice().reverse().forEach((event) => { const item = elt("li"); const time = event.time || event.at || event.created_at; if (time) item.append(elt("time", "", dateLabel(time, true))); item.append(document.createTextNode(eventText(event))); $("event-rows").append(item); }); }

function fillSourceSelect(select, key, selected) {
  select.replaceChildren(); const empty = elt("option", "", "未指定 · 生成时按规则选择"); empty.value = ""; select.append(empty);
  const targetField = ["pending_claims_id", "target_oa_id", "original_id"].includes(key);
  const candidates = docs().filter((doc) => ((acceptedRoles[key] || []).includes(doc.role) && (!targetField || doc.country === state.current.target_country)) || doc.id === selected);
  candidates.forEach((doc) => { const option = elt("option", "", `${doc.country || "未知"} · ${doc.title || doc.filename || roleNames[doc.role]} · ${versionNames[doc.version_status] || "版本未确认"} · ${documentStatus(doc)[0]}`); option.value = doc.id; select.append(option); });
  if (selected && !candidates.some((doc) => doc.id === selected)) { const missing = elt("option", "", `所选材料已不可用 (${selected})`); missing.value = selected; select.append(missing); }
  select.value = selected || "";
}
function renderSettings() {
  const saved = state.drafts.get(state.current.id) || { ...(state.current.settings || {}), target_application: state.current.target_application || "" };
  $("target-application").value = saved.target_application || ""; $("source-member").value = saved.source_member || "";
  for (const [id, key] of Object.entries(sourceFields)) fillSourceSelect($(id), key, saved[key]);
  $("review-enabled").checked = Boolean(saved.review_enabled);
  $("ocr-engine").value = saved.ocr_engine || "rapidocr";
  const options = state.current.parser_options || [];
  for (const option of $("ocr-engine").options) { const available = options.find((item) => item.id === option.value); option.disabled = available ? !available.installed : false; }
  $("parser-status").textContent = "保存后，生成前会应用所选解析方式。未安装选项不可选；已有文字与原件保留。";
  for (const kind of ["response", "claims"]) { const override = saved[`${kind}_override`]; $(`edit-${kind}`).checked = Boolean(text(override).trim()); $(`${kind}-override`).value = text(override); updateEditor(kind, true); }
  $("support-rows").replaceChildren(); (saved.support_rows || []).forEach((row) => addSupportRow(row, false)); updateSupportEmpty();
  const deadline = saved.deadline || {}; $("deadline-rule").value = deadline.rule_id || ""; $("deadline-trigger").value = deadline.trigger_date || ""; $("deadline-source").value = deadline.source_url || ""; $("deadline-holidays").value = Array.isArray(deadline.extra_holidays) ? deadline.extra_holidays.join(", ") : deadline.extra_holidays || ""; $("deadline-entity").value = deadline.entity_status || "";
  updateDirtyIndicator();
}
function updateEditor(kind, preserve = false) {
  const sourceId = $(kind === "response" ? "selected-response" : "selected-claims").value;
  const doc = docs().find((item) => item.id === sourceId); const editing = $(`edit-${kind}`).checked; const textarea = $(`${kind}-override`);
  textarea.readOnly = !editing;
    if (!editing || (!preserve && !textarea.value)) textarea.value = doc?.draft_text || doc?.text || "";
  $(`${kind}-edit-note`).textContent = editing ? "当前使用编辑稿。保存后用于生成，原始材料保持不变。" : "当前使用所选材料原文。勾选“使用编辑稿”可修改。";
  $(`${kind}-source-note`).textContent = doc ? `${documentStatus(doc)[0]} · ${dateLabel(doc.date)}${doc.language ? ` · ${doc.language}` : ""}${!text(doc.text).trim() ? " · 无可读取正文" : ""}` : "生成时按规则选择可用材料，并在答复包中标明来源；也可手动指定。";
}
function readSettings() {
  const result = { target_application: $("target-application").value.trim(), source_member: $("source-member").value.trim(), review_enabled: $("review-enabled").checked, response_override: $("edit-response").checked ? $("response-override").value : "", claims_override: $("edit-claims").checked ? $("claims-override").value : "", support_rows: [], deadline: { rule_id: $("deadline-rule").value.trim(), trigger_date: $("deadline-trigger").value, source_url: $("deadline-source").value.trim(), extra_holidays: $("deadline-holidays").value.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean), entity_status: $("deadline-entity").value.trim() } };
  result.ocr_engine = $("ocr-engine").value;
  for (const [id, key] of Object.entries(sourceFields)) result[key] = $(id).value;
  $("support-rows").querySelectorAll("tr").forEach((row) => { const entry = {}; row.querySelectorAll("[data-support]").forEach((input) => { entry[input.dataset.support] = input.value; }); if (Object.values(entry).some((value) => value.trim())) result.support_rows.push(entry); });
  return result;
}
function markDirty() { if (!state.current) return; state.dirty = true; state.drafts.set(state.current.id, readSettings()); updateDirtyIndicator(); }
function updateDirtyIndicator() { $("save-indicator").textContent = state.dirty ? "有未保存修改" : "已保存"; $("save-indicator").classList.toggle("dirty", state.dirty); $("settings-footer-state").textContent = state.dirty ? "当前修改尚未保存" : "材料选择已保存"; }
function updateSupportEmpty() { const hasRows = $("support-rows").children.length > 0; $("support-table").hidden = !hasRows; $("support-empty").hidden = hasRows; }
function addSupportRow(values = {}, dirty = true) {
  const row = elt("tr");
  for (const [key, label] of [["claim", "权项编号"], ["change", "修改内容"], ["basis", "原始记载"], ["source_id", "依据来源材料"], ["page", "依据页码"]]) {
    const cell = elt("td"); const input = elt(key === "source_id" ? "select" : ["change", "basis"].includes(key) ? "textarea" : "input"); input.dataset.support = key; input.setAttribute("aria-label", label);
    if (key === "source_id") { const blank = elt("option", "", "未指定 · 待核查"); blank.value = ""; input.append(blank); docs().forEach((doc) => { const option = elt("option", "", `${doc.country || ""} ${doc.title || doc.filename || doc.id}`); option.value = doc.id; input.append(option); }); }
    else input.placeholder = key === "claim" ? "1" : key === "page" ? "段落 / 页" : label;
    if (input.tagName === "TEXTAREA") input.rows = 2;
    input.value = text(values[key]); cell.append(input); row.append(cell);
  }
  const actions = elt("td"); const remove = elt("button", "text-button", "删除"); remove.type = "button"; remove.setAttribute("aria-label", "删除本行修改依据"); remove.addEventListener("click", () => { row.remove(); updateSupportEmpty(); markDirty(); }); actions.append(remove); row.append(actions); $("support-rows").append(row); updateSupportEmpty(); if (dirty) { markDirty(); row.querySelector("input")?.focus(); }
}
async function saveSettings(silent = false) {
  if (!$("settings-form").reportValidity()) return false;
  const id = state.current.id; const values = readSettings();
  if ($("edit-response").checked && !values.response_override.trim()) throw new Error("已勾选“使用编辑稿”，但答复正文为空。请填写正文，或取消勾选以使用原文。");
  if ($("edit-claims").checked && !values.claims_override.trim()) throw new Error("已勾选“使用编辑稿”，但权利要求正文为空。请填写正文，或取消勾选以使用原文。");
  if (values.deadline.extra_holidays.some((date) => !/^\d{4}-\d{2}-\d{2}$/.test(date))) throw new Error("额外休假日期请使用 YYYY-MM-DD 格式，多个日期用逗号分隔。");
  const item = await request(`${casePath(id)}/settings`, values);
  state.dirty = false; state.drafts.delete(id); applyCase(item, true);
  if (!silent) notice("材料选择与编辑稿已保存。");
  return true;
}

function exportRows() {
  const exports = state.current.exports;
  if (!exports) return [];
  if (Array.isArray(exports)) return exports.map((item) => typeof item === "string" ? { name: item } : item);
  return Object.entries(exports).map(([key, value]) => typeof value === "string" ? { name: value, label: key } : { name: key, ...value });
}
function exportLabel(name) {
  const value = name.toLowerCase();
  if (/summary|摘要/.test(value)) return "中文摘要";
  if (/support|basis|依据/.test(value)) return "修改依据表";
  if (/marked|redline|修订/.test(value)) return "修订权利要求";
  if (/clean|清洁/.test(value)) return "清洁权利要求";
  if (/response|答复/.test(value)) return "英文答复草案";
  if (/family|research|report|同族/.test(value)) return "同族研究报告";
  return name;
}
const previewLabels = { "03-意见陈述书.docx": "意见陈述书 · 英文", "04-权利要求修改标记页.docx": "权利要求修改标记页", "05-修改后权利要求清洁稿.docx": "修改后清洁稿", "06-修改依据表.md": "修改依据表", "07-中文摘要.md": "中文摘要", "01-同族审查历史报告.md": "同族审查历史", "08-补充材料指南.md": "补充材料指南", "09-来源记录.json": "来源记录", "06-修改依据表.csv": "修改依据表 · CSV", "02-同族原件与目录说明.zip": "同族原件包", "00-完整答复包.zip": "完整答复包" };
function prepareOutputReader(exports) {
  const names = exports.map((file) => file.filename || file.name || file.path?.split(/[\\/]/).pop() || "");
  const order = Object.keys(previewLabels);
  const choices = names.filter((name) => /\.(docx|html|md|txt|csv|json)$/i.test(name) && !(/\.html$/i.test(name) && names.includes(name.replace(/\.html$/i, ".docx"))));
  choices.sort((a, b) => (order.includes(a) ? order.indexOf(a) : 99) - (order.includes(b) ? order.indexOf(b) : 99));
  const select = $("output-file"); const previous = state.outputCase === state.current.id ? select.value : "";
  select.replaceChildren(...choices.map((name) => { const option = elt("option", "", previewLabels[name] || exportLabel(name)); option.value = name; return option; }));
  select.value = choices.includes(previous) ? previous : choices[0] || "";
  state.outputCase = state.current.id;
  $("output-reader").hidden = !choices.length; $("all-exports").hidden = !exports.length;
  if (!choices.length) { state.outputAbort?.abort(); state.outputKey = null; $("output-frame").srcdoc = ""; }
  else if (state.tab === "output") loadOutputPreview();
}
async function loadOutputPreview(force = false) {
  if (!state.current || $("output-reader").hidden || !$("output-file").value) return;
  const name = $("output-file").value;
  const key = `${state.current.id}/${state.current.export_dir || "exports"}/${name}`;
  if (!force && state.outputKey === key) return;
  state.outputAbort?.abort();
  const controller = new AbortController(); state.outputAbort = controller; state.outputKey = key;
  const frame = $("output-frame"); frame.hidden = true; frame.srcdoc = "";
  frame.title = `${previewLabels[name] || exportLabel(name)}正文预览`;
  $("reader-download").href = `${casePath()}/exports/${encodeURIComponent(name)}`;
  $("reader-download").download = name;
  $("reader-note").textContent = /\.docx$/i.test(name) ? "正文与本次 Word 文件同步生成；修改标记保留，最终分页以下载的 Word 为准。" : "以下展示本次生成文件的内容；下载可保留原始格式。";
  $("reader-status").textContent = "正在载入文件…"; $("reader-status").hidden = false;
  $("reader-retry").hidden = true; $("output-reader").setAttribute("aria-busy", "true");
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`${casePath()}/preview/${encodeURIComponent(name)}`, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.error || "文件预览暂时不可用，请重试或下载查看。"); }
    const body = await response.text();
    if (state.outputAbort !== controller) return;
    frame.srcdoc = body; frame.hidden = false; $("reader-status").hidden = true;
  } catch (error) {
    if (state.outputAbort !== controller) return;
    $("reader-status").textContent = error.name === "AbortError" ? "预览载入超时，可以重试或下载当前文件。" : error.message;
    $("reader-retry").hidden = false;
  } finally {
    clearTimeout(timer);
    if (state.outputAbort === controller) $("output-reader").setAttribute("aria-busy", "false");
  }
}
function renderOutputs() {
  const exports = exportRows(); const list = $("export-list"); list.replaceChildren();
  $("output-empty").hidden = exports.length > 0 || state.current.status === "generating";
  $("bundle-link").hidden = !exports.length;
  $("bundle-link").href = `${casePath()}/bundle`;
  $("output-summary").replaceChildren();
  if (exports.length && state.current.exports_stale) { const stale = elt("div", "output-note stale-output"); stale.setAttribute("role", "status"); stale.append(elt("strong", "", "材料已更新，请重新生成；以下为上次结果"), elt("p", "", "上次文件与生成说明尚未包含最新材料或编辑。请返回“选择与编辑”，保存并生成新的答复包。")); $("output-summary").append(stale); }
  if (state.current.status === "generating") $("output-summary").append(elt("p", "output-note", "正在生成答复包。进度会自动更新；已有文件若仍显示，属于上一次生成结果。"));
  else if (exports.length && !state.current.exports_stale) { const count = Array.isArray(state.current.gaps) ? state.current.gaps.length : 0; $("output-summary").append(elt("p", "output-note", `${state.current.is_demo ? "当前为虚构示例。" : ""}可直接预览或下载本次文件。${count ? `当前记录 ${count} 项缺件或未核查事项，请一并查看中文摘要。` : "请结合原始材料审阅来源、版本与目标法域要求。"}`)); }
  exports.forEach((file) => {
    const name = file.filename || file.name || file.path?.split(/[\\/]/).pop() || "";
    if (!name && !file.url) return;
    const row = elt("div", "export-row"); const info = elt("div"); info.append(elt("strong", "", file.label || file.title || exportLabel(name)), elt("p", "", name || "生成文件")); row.append(info);
    const url = `${casePath()}/exports/${encodeURIComponent(name)}`; appendLink(row, "下载", url, "button secondary", true); list.append(row);
  });
  prepareOutputReader(exports);
  const analysis = state.current.analysis; $("analysis-section").hidden = !analysis || (typeof analysis === "object" && !Object.keys(analysis).length); const area = $("analysis-content"); area.replaceChildren();
  if (!analysis) return;
  if (typeof analysis === "string") { area.append(elt("p", "hint", analysis)); return; }
  renderAnalysis(area, analysis);
}

function compactTable(headers) {
  const wrap = elt("div", "table-wrap analysis-table"); const table = elt("table"); const head = elt("thead"); const heading = elt("tr");
  headers.forEach((header) => { const cell = elt("th", "", header); cell.scope = "col"; heading.append(cell); }); head.append(heading); const body = elt("tbody"); table.append(head, body); wrap.append(table); return { wrap, body };
}
function analysisBlock(area, title, description) { const section = elt("section", "analysis-block"); section.append(elt("h3", "", title)); if (description) section.append(elt("p", "analysis-description", description)); area.append(section); return section; }
function issueLabel(value) { return ({ "Inventive step": "创造性", "Novelty": "新颖性", "Clarity": "清楚性", "Disclosure and support": "公开充分与支持", "Unity of invention": "单一性", "Subject matter eligibility": "可专利客体", "Formal requirements": "形式要求", "Cited patent document": "引证专利文件" })[value] || text(value) || "待核查问题"; }
function changeLabel(value) { return ({ "Proposed claim; target baseline unavailable": "拟提交权项，目标比较底稿缺失", "Canceled claim": "删除权项", "Added claim": "新增权项", "Changed wording": "修改权项文字" })[value] || text(value) || "待填写修改内容"; }
function appendExcerpt(cell, value, empty = "尚未提供原文") { const excerpt = text(value).trim(); if (!excerpt) { cell.textContent = empty; return; } if (excerpt.length <= 260) { cell.append(elt("p", "analysis-excerpt", excerpt)); return; } const details = elt("details", "excerpt-details"); details.append(elt("summary", "", `${excerpt.slice(0, 180)}… 查看完整摘录`), elt("p", "analysis-excerpt", excerpt)); cell.append(details); }
function renderAnalysis(area, analysis) {
  const sources = analysis.sources || {};
  if (Object.keys(sources).length) {
    const section = analysisBlock(area, "实际使用的材料", "以下为本次生成所用来源；正文请在材料详情或生成文件中查看。");
    const table = compactTable(["用途", "材料", "版本与日期"]);
    const names = { response: "参考答复", claims: "拟复用权项", pending: "目标待审权项", oa: "目标审查意见", original: "原始申请" };
    Object.entries(names).forEach(([key, name]) => { const doc = sources[key]; const row = elt("tr"); const material = elt("td"); const version = elt("td"); if (doc) { material.append(elt("span", "table-title", `${doc.country || ""} ${doc.title || doc.filename || "所选材料"}`)); if (doc.url || doc.source_url) appendLink(material, "查看原始来源", doc.url || doc.source_url); version.append(elt("span", "", versionNames[doc.version_status] || "版本未确认"), elt("span", "table-sub", dateLabel(doc.date))); } else { material.textContent = "未取得可用材料"; version.textContent = "—"; } row.append(elt("td", "", name), material, version); table.body.append(row); }); section.append(table.wrap);
    const baseline = analysis.baseline_usable ? (analysis.baseline_latest ? "修订比较使用当前已提供的最新英文待审权项。" : "修订比较底稿可用，但不是当前已提供的最新待审版本，请核对。") : "尚无可用的英文目标待审权项，目标修订比较未就绪。";
    section.append(elt("p", "hint", baseline));
  }
  if (Array.isArray(analysis.issues) && analysis.issues.length) {
    const section = analysisBlock(area, "审查意见要点", "按原文标题与引证提取，需结合完整审查意见理解。"); const table = compactTable(["问题", "原文摘录", "页码", "引证文件"]);
    analysis.issues.forEach((issue) => { const row = elt("tr"); const excerpt = elt("td"); appendExcerpt(excerpt, issue.excerpt); row.append(elt("td", "", issueLabel(issue.title)), excerpt, elt("td", "", issue.page ?? "未知"), elt("td", "", Array.isArray(issue.citations) && issue.citations.length ? issue.citations.join("\n") : "未提取到")); table.body.append(row); }); section.append(table.wrap);
  }
  if (Array.isArray(analysis.strategy) && analysis.strategy.length) {
    const section = analysisBlock(area, "答复安排", "以下为根据引证和文字重合提出的复用候选，适用性仍待核查。"); const table = compactTable(["审查问题", "处理方式", "对应依据"]);
    const labels = { reuse_argument: "复用论证", reuse_amendment: "复用修改", separate_response: "另行应对" };
    analysis.strategy.forEach((strategy) => { const row = elt("tr"); const mode = elt("td"); mode.append(elt("span", `badge ${strategy.status === "separate_response" ? "warning" : ""}`, labels[strategy.status] || "待核查")); const evidence = elt("td"); const matches = strategy.evidence || {};
      if (matches.shared_citations?.length) evidence.append(elt("p", "", `共同引证：${matches.shared_citations.join("、")}`));
      if (matches.shared_terms?.length) evidence.append(elt("p", "hint", `重合用语：${matches.shared_terms.join("、")}`));
      if (matches.changed_terms_in_objection?.length) evidence.append(elt("p", "", `修改与意见中的重合用语：${matches.changed_terms_in_objection.join("、")}`));
      if (!evidence.children.length) evidence.append(elt("p", "", "未找到可支持复用的引证或文字重合，请补充针对本项意见的论证。"));
      row.append(elt("td", "", `${issueLabel(strategy.issue)}${strategy.page != null ? ` · 第 ${strategy.page} 页` : ""}`), mode, evidence); table.body.append(row);
    }); section.append(table.wrap);
  }
  if (Array.isArray(analysis.support)) {
    const section = analysisBlock(area, "修改依据", "“已定位原文”仅表示所引文字出现在指定页，不代表修改已满足法律上的支持要求。");
    if (!analysis.support.length) section.append(elt("p", "hint", "尚未提供修改依据，请在“选择与编辑”中补充。"));
    else { const table = compactTable(["权项", "修改内容", "原始记载", "页码", "核查情况"]); analysis.support.forEach((support) => { const row = elt("tr"); const basis = elt("td"); appendExcerpt(basis, support.basis, "尚未提供原始记载"); const status = elt("td"); status.append(elt("span", `badge ${support.status === "source_located" ? "" : "warning"}`, support.status === "source_located" ? "已定位原文" : "待核查依据")); const source = docs().find((doc) => doc.id === support.source_id); if (source) status.append(elt("span", "table-sub", source.title || source.filename || "原始申请文件")); row.append(elt("td", "", support.claim || "待指定"), elt("td", "", changeLabel(support.change)), basis, elt("td", "", support.page || "未指定"), status); table.body.append(row); }); section.append(table.wrap); }
  }
  if (analysis.adaptation && typeof analysis.adaptation === "object") {
    const adaptation = analysis.adaptation; const section = analysisBlock(area, "目标申请文字调整");
    if (adaptation.origin === "user_authored") section.append(elt("p", "analysis-description", "采用已保存的编辑稿，未自动替换其中的申请号。"));
    else if (Array.isArray(adaptation.log) && adaptation.log.length) { const list = elt("ul", "analysis-notes"); adaptation.log.forEach((entry) => { if (entry.old != null && entry.new != null) list.append(elt("li", "", `${entry.old} → ${entry.new}${entry.occurrences ? `（${entry.occurrences} 处）` : ""}`)); }); section.append(list, elt("p", "hint", "仅替换已知同族申请标识，技术论证保留原文。")); }
    else section.append(elt("p", "analysis-description", "本次未进行申请号替换。"));
    if (Array.isArray(adaptation.foreign_legal_references) && adaptation.foreign_legal_references.length) section.append(elt("p", "analysis-warning", `仍保留的外国法律或程序引述：${adaptation.foreign_legal_references.join("、")}。请核对目标法域适用性；本次未作当地法律替换。`));
  }
  if (analysis.deadline && typeof analysis.deadline === "object") {
    const deadline = analysis.deadline; const section = analysisBlock(area, "期限与费用");
    const values = elt("dl", "analysis-list");
    const entries = [["名义答复日期", deadline.nominal_date ? `${dateLabel(deadline.nominal_date)} · 未核验` : "尚未计算 · 未核验"], ["提供的触发日期", deadline.trigger_date ? dateLabel(deadline.trigger_date) : "尚未提供"], ["适用费用", "尚未核验，未推测金额"]];
    entries.forEach(([name, value]) => { const row = elt("div"); row.append(elt("dt", "", name), elt("dd", "", value)); values.append(row); }); section.append(values);
    section.append(elt("p", "analysis-warning", deadline.nominal_date ? "名义日期按提供的日期加 90 个自然日计算。触发依据、规则适用性及节假日顺延尚未核验，不能直接作为已确认的法定期限。" : "尚未形成已核验的答复期限。请补充适用规则、官方触发日期及来源后核对。"));
    const links = elt("div", "inline-links"); if (deadline.source_url) appendLink(links, "查看提供的规则来源", deadline.source_url); if (deadline.rule_source_url && deadline.rule_source_url !== deadline.source_url) appendLink(links, "查看巴西初步审查期限指引", deadline.rule_source_url); if (links.children.length) section.append(links);
  }
  if (analysis.review_enabled) {
    const section = analysisBlock(area, "附加适用性核查"); section.append(elt("p", "analysis-description", "已启用附加核查。申请人的答复论证不等于审查机关已接受；后续授权记录也不能单独证明某项论证获采纳。具体接受情况仍待原始审查文件确认。"));
  }
  if (Array.isArray(analysis.gaps) && analysis.gaps.length) { const section = analysisBlock(area, "待补材料与核查事项"); const list = elt("ul", "analysis-notes"); analysis.gaps.forEach((gap) => list.append(elt("li", "", gapLabel(typeof gap === "string" ? gap : gap.message || gap.title || "待核查事项")))); section.append(list); }
}

function showUpload() { $("upload-form").hidden = false; $("upload-form").scrollIntoView({ block: "nearest", behavior: "auto" }); }
function fileAsBase64(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(new Error("文件读取失败，请重新选择文件。")); reader.onload = () => resolve(String(reader.result).split(",", 2)[1]); reader.readAsDataURL(file); }); }
async function uploadMaterial() {
  const mode = document.querySelector("input[name=upload_mode]:checked").value;
  const payload = { title: $("upload-title").value.trim(), role: $("upload-role").value, country: $("upload-country").value.trim().toUpperCase(), date: $("upload-date").value, version_status: $("upload-version").value, language: $("upload-language").value, source_url: $("upload-url").value.trim() };
  if (mode === "file") {
    const file = $("upload-file").files[0];
    if (!file) throw new Error("请先选择一个 PDF、TXT、MD 或 DOCX 文件。");
    if (!/\.(pdf|txt|md|docx)$/i.test(file.name)) throw new Error("暂不支持此文件类型。请导入 PDF、TXT、MD 或 DOCX 文件。");
    if (file.size > 25 * 1024 * 1024) throw new Error("文件超过 25 MB。请拆分文件后重新导入。");
    if (!file.size) throw new Error("所选文件为空，请选择包含正文的材料。");
    payload.filename = file.name; payload.data_base64 = await fileAsBase64(file);
  } else { if (!$("upload-text").value.trim()) throw new Error("请先粘贴需要导入的材料正文。"); payload.text = $("upload-text").value; payload.filename = "pasted-material.txt"; if (!payload.title) payload.title = "粘贴的材料"; }
  rememberDraft(); const item = await request(`${casePath()}/documents`, payload); applyCase(item, true);
  $("upload-file").value = ""; $("upload-text").value = ""; $("upload-title").value = ""; $("upload-date").value = ""; $("upload-url").value = "";
  notice("材料已导入。可在列表查看原件与提取文字，并在“选择与编辑”中指定用途。");
}

$("new-case-form").addEventListener("submit", (event) => { event.preventDefault(); perform(async () => { const number = $("application-number").value.trim(); if (!number) throw new Error("请输入申请号或公开号。"); let country = $("target-country").value; if (country === "OTHER") country = $("other-country").value.trim().toUpperCase(); rememberDraft(); const item = await request("/api/cases", { application_number: number, target_country: country, auto_research: true }); ++state.loadToken; state.dirty = false; state.previewId = null; rememberSelection(item.id); applyCase(item, true); setTab("research"); $("application-number").value = ""; $("upload-form").hidden = true; $("document-preview").hidden = true; }, "create-button", "正在新建…"); });
$("target-country").addEventListener("change", () => { const other = $("target-country").value === "OTHER"; $("other-country").hidden = !other; $("other-country-label").hidden = !other; $("other-country").required = other; });
$("demo-button").addEventListener("click", () => perform(async () => { rememberDraft(); const item = await request("/api/demo", {}); ++state.loadToken; state.dirty = false; state.previewId = null; rememberSelection(item.id); applyCase(item, true); setTab("research"); $("document-preview").hidden = true; notice("已打开虚构示例。这里的申请号、审查材料和输出仅用于演示流程。"); }, "demo-button", "正在准备示例…"));
$("refresh-cases").addEventListener("click", () => perform(refreshCurrent, "refresh-cases", "刷新中…"));
$("retry-button").addEventListener("click", () => { if (state.retry) state.retry(); });
$("dismiss-error").addEventListener("click", () => { $("error-banner").hidden = true; });
$("mobile-sidebar-toggle").addEventListener("click", () => { const sidebar = document.querySelector(".sidebar"); const collapsed = sidebar.classList.toggle("is-collapsed"); $("mobile-sidebar-toggle").setAttribute("aria-expanded", String(!collapsed)); $("mobile-sidebar-toggle").textContent = collapsed ? "案件管理" : "收起案件"; });
$("research-button").addEventListener("click", () => perform(async () => { rememberDraft(); const item = await request(`${casePath()}/research`, {}); applyCase(item, false); }, "research-button", "正在启动…"));
$("ocr-button").addEventListener("click", () => perform(async () => { rememberDraft(); const item = await request(`${casePath()}/ocr`, {}); applyCase(item, false); }, "ocr-button", "正在启动识别…"));
$("preview-text-view").addEventListener("change", () => { if (state.previewId) previewDocument(state.previewId, false); });
document.querySelectorAll("[data-tab]").forEach((tab) => { tab.addEventListener("click", () => setTab(tab.dataset.tab)); tab.addEventListener("keydown", (event) => { const order = ["research", "selection", "output"]; const index = order.indexOf(tab.dataset.tab); let next; if (event.key === "ArrowRight") next = (index + 1) % order.length; if (event.key === "ArrowLeft") next = (index + order.length - 1) % order.length; if (event.key === "Home") next = 0; if (event.key === "End") next = order.length - 1; if (next !== undefined) { event.preventDefault(); setTab(order[next]); $(`tab-${order[next]}`).focus(); } }); });
document.querySelectorAll("[data-go-tab]").forEach((button) => button.addEventListener("click", () => { setTab(button.dataset.goTab); $(`tab-${button.dataset.goTab}`).focus(); }));
$("show-upload").addEventListener("click", showUpload); $("hide-upload").addEventListener("click", () => { $("upload-form").hidden = true; });
$("close-preview").addEventListener("click", () => { state.previewId = null; $("document-preview").hidden = true; });
$("output-file").addEventListener("change", () => loadOutputPreview());
$("reader-retry").addEventListener("click", () => loadOutputPreview(true));
$("document-metadata-form").addEventListener("input", markMetadataDirty); $("document-metadata-form").addEventListener("change", markMetadataDirty);
$("document-metadata-form").addEventListener("submit", (event) => { event.preventDefault(); perform(saveDocumentMetadata, "metadata-save-button", "正在保存…"); });
document.querySelectorAll("input[name=upload_mode]").forEach((radio) => radio.addEventListener("change", () => { const file = document.querySelector("input[name=upload_mode]:checked").value === "file"; $("upload-file-area").hidden = !file; $("upload-text-area").hidden = file; }));
$("upload-form").addEventListener("submit", (event) => { event.preventDefault(); perform(uploadMaterial, "upload-button", "正在导入…"); });
$("settings-form").addEventListener("input", markDirty); $("settings-form").addEventListener("change", markDirty);
$("settings-form").addEventListener("submit", (event) => { event.preventDefault(); perform(() => saveSettings(), "save-button", "正在保存…"); });
for (const kind of ["response", "claims"]) {
  $(`edit-${kind}`).addEventListener("change", () => { updateEditor(kind, true); markDirty(); });
  $(kind === "response" ? "selected-response" : "selected-claims").addEventListener("change", () => { updateEditor(kind, true); markDirty(); });
}
$("add-support-row").addEventListener("click", () => addSupportRow());
$("generate-button").addEventListener("click", () => { if (!$("settings-form").reportValidity()) return; perform(async () => { if (!await saveSettings(true)) return; const item = await request(`${casePath()}/generate`, {}); applyCase(item, true); setTab("output"); }, "generate-button", "正在提交…"); });

(async () => {
  try { await loadCases(); let saved; try { saved = localStorage.getItem("family-workbench:selected-case"); } catch { /* Keep the workbench usable without storage. */ } const initial = state.cases.find((item) => item.id === saved) || state.cases[0]; if (initial) await selectCase(initial.id); }
  catch (error) { $("case-list").replaceChildren(elt("p", "sidebar-empty", "案件读取失败。请确认本地服务运行后点击刷新。")); showError(error); }
})();
