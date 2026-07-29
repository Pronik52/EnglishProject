/* Личный словарь: список слов, добавление вручную и каталог готовых слов. */

import { $, api, toast, esc, highlight, spk, dueLabel } from "./core.js";
import { refresh, refreshStats } from "./app.js";

// Правила показа приходят с сервера вместе со статистикой (/words/stats).
// Держать их копию на клиенте нельзя: она разъезжается с бэкендом молча.
let rules = {srs_max_level:5, regen_limit:5};
export function setRules(stats){
  if(stats.srs_max_level) rules.srs_max_level = stats.srs_max_level;
  if(stats.regen_limit !== undefined) rules.regen_limit = stats.regen_limit;
}

// Разметка одной карточки. Отдельной функцией — её использует и полная
// отрисовка списка, и точечное обновление после действия.
function wordCardHtml(w){
  const maxLevel = rules.srs_max_level;
  const lvl=w.srs_level||0;
  const pct=Math.min(100, lvl/maxLevel*100);
  const regenLeft = Math.max(0, rules.regen_limit - (w.regen_count||0));
  const regenLabel = rules.regen_limit===-1 ? "Другая фраза"
    : regenLeft>0 ? `Другая фраза · ${regenLeft}` : "Другая фраза · лимит";
  const badge = w.is_learned ? 'выучено ✓' : `ур. ${lvl}/${maxLevel} · ${dueLabel(w.due_at)}`;
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
      <div class="more">
        <button class="btn ghost sm more-btn" data-act="more" aria-expanded="false"
                aria-label="Ещё действия">⋯</button>
        <div class="more-menu hidden">
          <button data-act="learned">${w.is_learned?'Вернуть в учёбу':'Отметить выученным'}</button>
          <button data-act="reset" ${fresh?'disabled':''}>Сбросить прогресс</button>
          <button data-act="del" class="danger">Удалить</button>
        </div>
      </div>
    </div>
  </div>`;
}

/* ---------- Список слов: поиск, фильтр, страницы ----------
   Раньше словарь грузился целиком (?limit=1000) и рисовался одним куском —
   при сотне слов это пятьсот кнопок на странице и заметная пауза на каждом
   действии. Параметры skip/limit/search/is_learned у GET /words были с самого
   начала, просто клиент ими не пользовался. */
const dict = {page:0, size:20, search:"", learned:"", total:0, pages:0};

export async function loadWords(){
  const params = new URLSearchParams({
    skip: dict.page * dict.size,
    limit: dict.size,
  });
  if(dict.search) params.set("search", dict.search);
  if(dict.learned) params.set("is_learned", dict.learned);

  try{
    const data = await api(`/words?${params.toString()}`);
    dict.total = data.total;
    dict.pages = data.pages;
    // Слова могли закончиться на текущей странице (удаление, фильтр) —
    // отступаем назад, иначе человек видит пустой экран вместо списка.
    if(!data.items.length && dict.page>0){
      dict.page = Math.max(0, dict.pages-1);
      return loadWords();
    }
    renderList(data.items);
    renderPages();
  }catch(e){ toast(e.message); }
}

function renderList(items){
  const box=$("#list");
  if(!items.length){
    const filtered = dict.search || dict.learned;
    box.innerHTML = filtered
      ? '<div class="empty">Ничего не нашлось. Измените поиск или фильтр.</div>'
      : '<div class="empty">Пока нет слов. Добавьте первое сверху ☝️</div>';
    return;
  }
  box.innerHTML = items.map(wordCardHtml).join("");
}

function renderPages(){
  const box=$("#dictPages");
  if(dict.pages<=1){ box.classList.add("hidden"); box.innerHTML=""; return; }
  box.classList.remove("hidden");
  box.innerHTML = `
    <button class="btn ghost sm" data-dpage="prev" ${dict.page===0?"disabled":""}>← Назад</button>
    <span>стр. ${dict.page+1} из ${dict.pages} · всего ${dict.total}</span>
    <button class="btn ghost sm" data-dpage="next" ${dict.page>=dict.pages-1?"disabled":""}>Вперёд →</button>`;
}

$("#dictPages").onclick = (e)=>{
  const btn=e.target.closest("button[data-dpage]"); if(!btn) return;
  dict.page += btn.dataset.dpage==="next" ? 1 : -1;
  loadWords();
};

let searchTimer=null;
$("#dictSearch").addEventListener("input",(e)=>{
  clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>{
    dict.search=e.target.value.trim(); dict.page=0; loadWords();
  }, 300);
});
$("#dictFilter").onchange = (e)=>{
  dict.learned=e.target.value; dict.page=0; loadWords();
};

// Закрывает открытое меню карточки (клик мимо, Esc, повторный клик).
function closeMenus(except){
  document.querySelectorAll(".more-menu:not(.hidden)").forEach(m=>{
    if(m===except) return;
    m.classList.add("hidden");
    const btn=m.parentElement.querySelector(".more-btn");
    if(btn) btn.setAttribute("aria-expanded","false");
  });
}
document.addEventListener("click",(e)=>{ if(!e.target.closest(".more")) closeMenus(); });
document.addEventListener("keydown",(e)=>{ if(e.key==="Escape") closeMenus(); });

/* Делегирование кликов по карточкам */
$("#list").onclick = async (e)=>{
  const btn=e.target.closest("button[data-act]"); if(!btn) return;
  const cardEl=e.target.closest(".word");
  const id=cardEl.dataset.id;
  const act=btn.dataset.act;

  if(act==="more"){
    const menu=btn.parentElement.querySelector(".more-menu");
    const willOpen=menu.classList.contains("hidden");
    closeMenus(menu);
    menu.classList.toggle("hidden", !willOpen);
    btn.setAttribute("aria-expanded", willOpen ? "true" : "false");
    return;
  }
  closeMenus();

  // Необратимые действия подтверждаем. Раньше «Удалить» и «Сбросить»
  // срабатывали с первого клика, без отмены и без возможности вернуть прогресс.
  const wordText=cardEl.querySelector(".en").textContent;
  if(act==="del" && !confirm(`Удалить «${wordText}» вместе с прогрессом?`)) return;
  if(act==="reset" && !confirm(`Сбросить прогресс по слову «${wordText}»?`)) return;

  try{
    if(act==="review"){
      updateCard(cardEl, await api(`/words/${id}/review`,{method:"PATCH"}));
      toast("Повторили ✓");
    }
    else if(act==="regen"){
      updateCard(cardEl, await api(`/words/${id}/regenerate-phrase`,{method:"PATCH"}));
      toast("Новая фраза");
    }
    else if(act==="learned"){
      const isLearned=cardEl.classList.contains("learned");
      updateCard(cardEl, await api(`/words/${id}/learned`,{method:"PATCH",body:{is_learned:!isLearned}}));
    }
    else if(act==="reset"){
      updateCard(cardEl, await api(`/words/${id}/reset`,{method:"PATCH"}));
      toast("Прогресс сброшен");
    }
    else if(act==="del"){
      await api(`/words/${id}`,{method:"DELETE"});
      toast("Удалено");
      // Перезагружаем страницу списка целиком: изменилось общее число слов,
      // а с ним нумерация страниц и состав текущей.
      await Promise.all([loadWords(), refreshStats()]);
      return;
    }
    await refreshStats();
  }catch(err){
    toast(err.message);
  }
};

// Перерисовывает ОДНУ карточку по ответу сервера. Раньше каждое такое действие
// звало refresh(): три запроса и полная пересборка списка до тысячи карточек,
// с потерей позиции прокрутки.
function updateCard(cardEl, word){
  const holder=document.createElement("div");
  holder.innerHTML=wordCardHtml(word);
  cardEl.replaceWith(holder.firstElementChild);
}

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
  const msg=$("#addMsg"); msg.className="msg"; msg.textContent="";
  if(!text||!translation){ msg.className="msg err"; msg.textContent="Введите слово и перевод."; return; }
  try{
    await api("/words",{method:"POST",body:{text,translation}});
    $("#wText").value=""; $("#wTrans").value=""; $("#previewBox").classList.add("hidden");
    await refresh(); toast("Слово добавлено");
  }catch(e){
    msg.className="msg err";
    msg.textContent=e.message;
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
    `<option value="">Все темы</option>` +
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
        ? "Готовых наборов ещё нет — добавьте слово вручную на соседней вкладке."
        : "Попробуйте другой уровень или тему."}</div>`;
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
    if(r.limit_skipped_count) toast("Часть слов не поместилась в дневной лимит — добавим завтра");
    await Promise.all([loadCatalogWords(), refresh()]);  // статусы и словарь без перезагрузки
  }catch(e){
    toast(e.message);
  }finally{
    catalog.sending = false;
    renderCatalog();
  }
};
