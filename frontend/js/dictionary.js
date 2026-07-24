/* Личный словарь: список слов, добавление вручную и каталог готовых слов. */

import { $, api, toast, esc, highlight, spk, dueLabel } from "./core.js";
import { billing, openPremium } from "./billing.js";
import { refresh } from "./app.js";

// Бесплатных генераций фразы на слово (совпадает с FREE_REGEN_LIMIT на бэке).
const REGEN_LIMIT=5;

// SRS: максимальный уровень (совпадает с SRS_MAX_LEVEL на бэке).
const SRS_MAX_LEVEL=5;

export function renderList(items){
  const box=$("#list");
  if(!items.length){ box.innerHTML='<div class="empty">Пока нет слов. Добавьте первое сверху ☝️</div>'; return; }
  const premium = billing && billing.is_premium;
  box.innerHTML = items.map(w=>{
    const lvl=w.srs_level||0;
    const pct=Math.min(100, lvl/SRS_MAX_LEVEL*100);
    // Остаток бесплатных генераций фразы по слову (Premium — без лимита).
    const regenLeft = Math.max(0, REGEN_LIMIT - (w.regen_count||0));
    const regenLabel = premium ? "Другая фраза"
      : regenLeft>0 ? `Другая фраза · ${regenLeft}` : "Другая фраза · лимит";
    const badge = w.is_learned ? 'выучено ✓' : `ур. ${lvl}/${SRS_MAX_LEVEL} · ${dueLabel(w.due_at)}`;
    const fresh = lvl===0 && !w.is_learned && (w.review_count||0)===0;
    return `<div class="word ${w.is_learned?'learned':''}" data-id="${w.id}">
      <div class="head">
        <span class="en">${esc(w.text)}</span>${spk(w.text)}
        <span class="ru">— ${esc(w.translation)}</span>
        <span class="badge">${badge}</span>
      </div>
      <div class="phrase-row">
        ${w.image_url?`<img class="thumb" src="${esc(w.image_url)}" alt="" loading="lazy">`:''}
        <div class="phrase">${highlight(w.phrase||'—', w.text)} ${w.phrase?spk(w.phrase):''}</div>
      </div>
      <div class="progress"><i style="width:${pct}%"></i></div>
      <div class="actions">
        <button class="btn sm" data-act="review">Повторить</button>
        <button class="btn ghost sm" data-act="regen">${regenLabel}</button>
        <button class="btn ghost sm" data-act="learned">${w.is_learned?'Вернуть в учёбу':'Отметить выученным'}</button>
        <button class="btn ghost sm" data-act="reset" ${fresh?'disabled style="opacity:.4"':''}>Сбросить</button>
        <button class="btn ghost sm" data-act="del" style="margin-left:auto;color:var(--danger)">Удалить</button>
      </div>
    </div>`;
  }).join("");
}

/* Делегирование кликов по карточкам */
$("#list").onclick = async (e)=>{
  const btn=e.target.closest("button[data-act]"); if(!btn) return;
  const id=e.target.closest(".word").dataset.id;
  const act=btn.dataset.act;
  try{
    if(act==="review"){ await api(`/words/${id}/review`,{method:"PATCH"}); toast("Повторили ✓"); }
    else if(act==="regen"){ await api(`/words/${id}/regenerate-phrase`,{method:"PATCH"}); toast("Новая фраза"); }
    // (402 по регенерации ловим ниже в catch — предлагаем Premium)
    else if(act==="learned"){
      const w=btn.closest(".word"); const isLearned=w.classList.contains("learned");
      await api(`/words/${id}/learned`,{method:"PATCH",body:{is_learned:!isLearned}});
    }
    else if(act==="reset"){ await api(`/words/${id}/reset`,{method:"PATCH"}); toast("Прогресс сброшен"); }
    else if(act==="del"){ await api(`/words/${id}`,{method:"DELETE"}); toast("Удалено"); }
    await refresh();
  }catch(err){
    toast(err.message);
    if(err.status===402) openPremium(); // лимит генераций фразы — предлагаем Premium
  }
};

/* Предпросмотр фразы при вводе слова или перевода */
let previewTimer=null;
export function schedulePreview(){
  clearTimeout(previewTimer);
  const text=$("#wText").value.trim();
  const translation=$("#wTrans").value.trim();
  const box=$("#previewBox");
  if(!text){ box.classList.add("hidden"); return; }
  previewTimer=setTimeout(async ()=>{
    try{
      const r=await api("/words/preview-phrase",{method:"POST",body:{text,translation}});
      box.classList.remove("hidden");
      box.innerHTML="Пример фразы: "+highlight(r.phrases[0], text)+" "+spk(r.phrases[0]);
    }catch(e){ box.classList.add("hidden"); }
  },350);
}
$("#wText").addEventListener("input", schedulePreview);
$("#wTrans").addEventListener("input", schedulePreview);

$("#addBtn").onclick = async ()=>{
  const text=$("#wText").value.trim(), translation=$("#wTrans").value.trim();
  const msg=$("#addMsg"); msg.textContent="";
  if(!text||!translation){ msg.textContent="Введите слово и перевод."; return; }
  try{
    await api("/words",{method:"POST",body:{text,translation}});
    $("#wText").value=""; $("#wTrans").value=""; $("#previewBox").classList.add("hidden");
    await refresh(); toast("Слово добавлено");
  }catch(e){
    msg.textContent=e.message;
    if(e.status===402) openPremium(); // лимит бесплатного тарифа — предлагаем Premium
  }
};
[$("#wText"),$("#wTrans")].forEach(i=>i.addEventListener("keydown",e=>{ if(e.key==="Enter") $("#addBtn").click(); }));

/* ---------- Каталог готовых слов ----------
   Второй способ наполнить словарь, рядом с ручным вводом. Последовательность
   та же, что в задумке: уровень → категория → список → массовое добавление. */
const catalog = {
  level:null, category:"", page:0, size:20, hideAdded:false,
  items:[], total:0, pages:0, selected:new Set(),
  loading:false, sending:false, error:null, loaded:false, result:null,
};

// Переключение вкладок «вручную / каталог». Селектор сужен до [data-tab]:
// класс .tab носят ещё и вкладки входа/регистрации, и без уточнения этот
// обработчик перетирал бы их собственный.
document.querySelectorAll(".tab[data-tab]").forEach(tab=>{
  tab.onclick = ()=>{
    document.querySelectorAll(".tab[data-tab]").forEach(t=>t.classList.toggle("active", t===tab));
    const isCatalog = tab.dataset.tab==="catalog";
    $("#manualPane").classList.toggle("hidden", isCatalog);
    $("#catalogPane").classList.toggle("hidden", !isCatalog);
    if(isCatalog && !catalog.loaded) initCatalog();
  };
});

// Первое открытие: тянем справочники, дальше только список слов.
async function initCatalog(){
  catalog.loaded = true;
  try{
    const levels = await api("/catalog/levels");
    // Уровень берём из селектора профиля в шапке — он уже заполнен из /auth/me.
    const profileLevel = ($("#levelSel") && $("#levelSel").value) || "A1";
    // Уровень из профиля — по умолчанию; если каталог для него не наполнен,
    // сервер всё равно вернёт ближайший доступный, поэтому просто выбираем
    // профильный, когда он есть в списке.
    catalog.level = levels.some(l=>l.code===profileLevel) ? profileLevel : levels[0].code;
    $("#catLevel").innerHTML = levels.map(l=>
      `<option value="${esc(l.code)}"${l.code===catalog.level?" selected":""}>${esc(l.title)}</option>`
    ).join("");
    await loadCategories();
    await loadCatalogWords();
  }catch(e){
    catalog.error = e.message;
    renderCatalog();
  }
}

async function loadCategories(){
  const cats = await api(`/catalog/categories?level=${encodeURIComponent(catalog.level)}`);
  $("#catCategory").innerHTML =
    `<option value="">Все категории</option>` +
    cats.map(c=>`<option value="${esc(c.slug)}"${c.slug===catalog.category?" selected":""}>`
      + `${esc(c.title)} (${c.words_count})</option>`).join("");
}

async function loadCatalogWords(){
  catalog.loading = true; catalog.error = null;
  renderCatalog();
  try{
    const params = new URLSearchParams({
      level: catalog.level,
      skip: catalog.page * catalog.size,
      limit: catalog.size,
    });
    if(catalog.category) params.set("category", catalog.category);
    if(catalog.hideAdded) params.set("hide_added", "true");

    const data = await api(`/catalog/words?${params.toString()}`);
    catalog.items = data.items;
    catalog.total = data.total;
    catalog.pages = data.pages;
  }catch(e){
    catalog.error = e.message;
    catalog.items = [];
  }finally{
    catalog.loading = false;
    renderCatalog();
  }
}

function renderCatalog(){
  const body = $("#catBody"), bar = $("#catBar");

  // Результат предыдущего добавления показываем над списком.
  const resultHtml = catalog.result ? renderCatalogResult(catalog.result) : "";

  if(catalog.loading){
    body.innerHTML = resultHtml + `<div class="catalog-state">Загружаем слова…</div>`;
    bar.classList.add("hidden"); return;
  }
  if(catalog.error){
    body.innerHTML = resultHtml + `<div class="catalog-state"><b>Не удалось загрузить каталог</b>
      ${esc(catalog.error)}<br><br>
      <button class="btn ghost sm" id="catRetry">Повторить</button></div>`;
    const retry = $("#catRetry"); if(retry) retry.onclick = ()=>loadCatalogWords();
    bar.classList.add("hidden"); return;
  }
  if(!catalog.items.length){
    // Пустой каталог и пустая выборка — разные ситуации, и подсказки разные.
    const emptyCatalog = catalog.total===0 && !catalog.category && !catalog.hideAdded;
    body.innerHTML = resultHtml + `<div class="catalog-state">
      <b>${emptyCatalog ? "Каталог пока пуст" : "Здесь пока ничего нет"}</b>
      ${emptyCatalog
        ? "Наполните его командой <code>python -m app.seed_catalog</code>."
        : "Попробуйте другой уровень или категорию."}</div>`;
    bar.classList.add("hidden"); return;
  }

  body.innerHTML = resultHtml + catalog.items.map(w=>{
    const picked = catalog.selected.has(w.id);
    const cls = "cat-word" + (w.in_dictionary ? " added" : (picked ? " picked" : ""));
    const tags = [w.part_of_speech, w.level].filter(Boolean)
      .map(t=>`<span class="cw-tag">${esc(t)}</span>`).join("");
    return `<label class="${cls}" data-id="${w.id}">
      <input type="checkbox" ${picked?"checked":""} ${w.in_dictionary?"disabled":""}>
      <div class="cw-main">
        <div class="cw-head">
          <span class="cw-en">${esc(w.text)}</span>
          ${w.transcription?`<span class="cw-ru">[${esc(w.transcription)}]</span>`:""}
          <span class="cw-ru">— ${esc(w.translation)}</span>
          ${tags}
        </div>
        ${w.example_en?`<div class="cw-example">${esc(w.example_en)}</div>`:""}
      </div>
      ${w.in_dictionary?`<span class="cw-status">✓ уже в словаре</span>`:""}
    </label>`;
  }).join("") + renderCatalogPages();

  bar.classList.remove("hidden");
  $("#catCount").textContent = `Выбрано: ${catalog.selected.size}`;
  $("#catAdd").disabled = catalog.selected.size===0 || catalog.sending;
  $("#catAdd").textContent = catalog.sending ? "Добавляем…" : "Добавить выбранные";
}

function renderCatalogPages(){
  if(catalog.pages<=1) return "";
  return `<div class="catalog-pages">
    <button class="btn ghost sm" data-page="prev" ${catalog.page===0?"disabled":""}>← Назад</button>
    <span>стр. ${catalog.page+1} из ${catalog.pages} · всего ${catalog.total}</span>
    <button class="btn ghost sm" data-page="next" ${catalog.page>=catalog.pages-1?"disabled":""}>Вперёд →</button>
  </div>`;
}

// Отчёт о массовом добавлении. Показываем все исходы, включая частичный успех.
function renderCatalogResult(r){
  const lines = [];
  if(r.added_count) lines.push(`добавлено: <b>${r.added_count}</b>`);
  if(r.skipped_count) lines.push(`пропущено как уже добавленные: ${r.skipped_count}`);
  if(r.limit_skipped_count) lines.push(`не поместилось в дневной лимит: ${r.limit_skipped_count}`);
  if(r.failed_count) lines.push(`не найдено в каталоге: ${r.failed_count}`);
  const warn = (r.limit_skipped_count || r.failed_count) ? " warn" : "";
  const errors = (r.errors||[]).length
    ? `<ul>${r.errors.map(e=>`<li>${esc(e)}</li>`).join("")}</ul>` : "";
  return `<div class="catalog-result${warn}">${lines.join(" · ")}${errors}</div>`;
}

// Клики по списку: выбор слова и переключение страниц.
$("#catBody").onclick = (e)=>{
  const pageBtn = e.target.closest("button[data-page]");
  if(pageBtn){
    catalog.page += pageBtn.dataset.page==="next" ? 1 : -1;
    loadCatalogWords();
    return;
  }
  const row = e.target.closest(".cat-word");
  if(!row || row.classList.contains("added")) return;
  const id = Number(row.dataset.id);
  if(catalog.selected.has(id)) catalog.selected.delete(id); else catalog.selected.add(id);
  renderCatalog();
};

$("#catLevel").onchange = async (e)=>{
  // Смена фильтра НЕ меняет уровень в профиле — это отдельное осознанное действие.
  catalog.level = e.target.value; catalog.page = 0; catalog.selected.clear();
  await loadCategories();
  loadCatalogWords();
};
$("#catCategory").onchange = (e)=>{
  catalog.category = e.target.value; catalog.page = 0; catalog.selected.clear();
  loadCatalogWords();
};
$("#catHideAdded").onchange = (e)=>{
  catalog.hideAdded = e.target.checked; catalog.page = 0;
  loadCatalogWords();
};

$("#catSelectAll").onclick = ()=>{
  // «Доступные» — только те, которых ещё нет в словаре, и только на этой странице.
  catalog.items.filter(w=>!w.in_dictionary).forEach(w=>catalog.selected.add(w.id));
  renderCatalog();
};

$("#catAdd").onclick = async ()=>{
  if(catalog.sending) return;                       // защита от повторной отправки
  const ids = [...catalog.selected];
  if(!ids.length){ toast("Сначала выберите слова"); return; }

  catalog.sending = true; renderCatalog();
  try{
    const r = await api("/catalog/words/add",{method:"POST",body:{word_ids:ids}});
    catalog.result = r;
    catalog.selected.clear();
    if(r.added_count) toast(`Добавлено слов: ${r.added_count}`);
    else if(r.skipped_count) toast("Все выбранные слова уже в словаре");
    if(r.limit_skipped_count) openPremium();        // упёрлись в дневной лимит
    await Promise.all([loadCatalogWords(), refresh()]);  // статусы и словарь без перезагрузки
  }catch(e){
    toast(e.message);
    if(e.status===402) openPremium();
  }finally{
    catalog.sending = false;
    renderCatalog();
  }
};
