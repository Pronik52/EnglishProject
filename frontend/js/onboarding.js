/* Первый запуск: уровень → тема → готовый набор слов → сразу практика.

   Мастер существует ради одной цели: человек не должен видеть пустой дашборд
   с нулями и кнопкой, которая ничего не делает. Поэтому он заканчивается не
   возвратом на главный экран, а первой карточкой — дашборд пользователь
   увидит после сессии, когда на нём уже есть что показывать. */

import { $, api, toast, esc } from "./core.js";
import { startStudy } from "./study.js";
import { refresh } from "./app.js";

// Сколько слов кладём в стартовый набор. Ровно на одну сессию: набор должен
// заканчиваться, а не висеть неподъёмным списком.
const STARTER_SIZE = 10;

// Флаг «мастер не нужен» живёт в localStorage, а не в базе. Признак «словарь
// пуст» и так достаточен и работает одинаково для веба и будущего iOS, а
// отдельная колонка ради кнопки «пропустить» не окупает миграцию.
const SKIP_KEY = "onboardSkipped";

let ob = {step:1, level:"A1", category:"", words:[], busy:false, error:""};

export function isOnboardingVisible(){
  return !$("#onboardView").classList.contains("hidden");
}

// Показывать ли мастер: словарь пуст и человек его ещё не пропускал.
export function shouldOnboard(stats){
  return stats.total===0 && localStorage.getItem(SKIP_KEY)!=="1";
}

export function showOnboarding(level){
  ob = {step:1, level:level||"A1", category:"", words:[], busy:false, error:""};
  $("#appView").classList.add("hidden");
  $("#studyView").classList.add("hidden");
  $("#onboardView").classList.remove("hidden");
  renderOnboarding();
}

function hideOnboarding(){
  $("#onboardView").classList.add("hidden");
  $("#appView").classList.remove("hidden");
}

// Пропуск мастера: человек хочет собрать словарь сам. Больше не показываем.
function skipOnboarding(){
  localStorage.setItem(SKIP_KEY, "1");
  hideOnboarding();
  toast("Добавьте первое слово ниже");
}

function renderOnboarding(){
  if(ob.step===1) return renderLevelStep();
  if(ob.step===2) return renderCategoryStep();
  return renderStarterStep();
}

function stepDots(){
  return `<div class="ob-steps" aria-label="Шаг ${ob.step} из 3">${
    [1,2,3].map(n=>`<i class="${n===ob.step?'on':(n<ob.step?'done':'')}"></i>`).join("")
  }</div>`;
}

/* ---------- Шаг 1: уровень ---------- */
// Здесь же единственное место, где объясняется сама механика. Она нестандартная,
// и без одной поясняющей фразы человек не понимает, чем это отличается от
// обычных карточек со словами.
async function renderLevelStep(){
  $("#onboardBody").innerHTML=`
    ${stepDots()}
    <p class="eyebrow">Шаг 1 из 3</p>
    <h1>С какого уровня начнём?</h1>
    <p class="ob-lead">
      Здесь слово живёт внутри сцены: вы смотрите на картинку, вспоминаете слово,
      а позже описываете происходящее своими словами. Уровень определяет
      сложность фраз — его можно поменять в любой момент.
    </p>
    <div class="ob-grid" id="obLevels"><div class="muted">Загружаем уровни…</div></div>
    <div class="ob-actions">
      <button class="btn ghost sm" data-o="skip">Пропустить, добавлю слова сам</button>
    </div>`;

  let levels;
  try{ levels = await api("/catalog/levels"); }
  catch(e){ $("#obLevels").innerHTML=`<div class="msg err">${esc(e.message)}</div>`; return; }

  $("#obLevels").innerHTML = levels.map(l=>`
    <button class="ob-card ${l.code===ob.level?'on':''}" data-level="${esc(l.code)}">
      <b>${esc(l.code)}</b><span>${esc(l.title.replace(l.code+" · ",""))}</span>
    </button>`).join("");
}

/* ---------- Шаг 2: тема ---------- */
async function renderCategoryStep(){
  $("#onboardBody").innerHTML=`
    ${stepDots()}
    <p class="eyebrow">Шаг 2 из 3</p>
    <h1>О чём хотите говорить?</h1>
    <p class="ob-lead">Подберём первые слова по теме. Остальные темы никуда не денутся.</p>
    <div class="ob-chips" id="obCats"><div class="muted">Загружаем темы…</div></div>
    <div class="ob-actions">
      <button class="btn ghost" data-o="back">← Назад</button>
      <button class="btn" data-o="toStarter">Дальше →</button>
    </div>`;

  let cats;
  try{ cats = await api(`/catalog/categories?level=${encodeURIComponent(ob.level)}`); }
  catch(e){ $("#obCats").innerHTML=`<div class="msg err">${esc(e.message)}</div>`; return; }

  const available = cats.filter(c=>c.words_count>0);
  if(!available.length){
    // Каталог для этого уровня пуст — тему выбирать не из чего, но мастер
    // должен уметь закончиться и в этом случае.
    ob.category="";
    $("#obCats").innerHTML=`<div class="muted">Для уровня ${esc(ob.level)} тем пока нет — соберём набор из общего списка.</div>`;
    return;
  }

  $("#obCats").innerHTML = `
    <button class="ob-chip ${ob.category===""?'on':''}" data-cat="">Любая тема</button>` +
    available.map(c=>`
      <button class="ob-chip ${ob.category===c.slug?'on':''}" data-cat="${esc(c.slug)}">
        ${esc(c.title)} <i>${c.words_count}</i>
      </button>`).join("");
}

/* ---------- Шаг 3: готовый набор ---------- */
async function renderStarterStep(){
  $("#onboardBody").innerHTML=`
    ${stepDots()}
    <p class="eyebrow">Шаг 3 из 3</p>
    <h1>Ваш первый набор</h1>
    <p class="ob-lead">Начнём с этих слов. К каждому подготовим фразу и сцену.</p>
    <div class="ob-words" id="obWords"><div class="muted">Подбираем слова…</div></div>
    <div class="ob-actions" id="obStartBar"></div>`;

  const params = new URLSearchParams({
    level: ob.level, limit: String(STARTER_SIZE), hide_added: "true"
  });
  if(ob.category) params.set("category", ob.category);

  let page;
  try{ page = await api("/catalog/words?"+params.toString()); }
  catch(e){ $("#obWords").innerHTML=`<div class="msg err">${esc(e.message)}</div>`; return; }

  ob.words = page.items || [];

  if(!ob.words.length){
    // Каталог не наполнен. Команду сидирования пользователю показывать нельзя —
    // это забота администратора, а не человека, который пришёл учить язык.
    $("#obWords").innerHTML=`<div class="muted">
      Готовых слов для этой темы пока нет. Ничего страшного — добавьте своё слово,
      фразу и картинку к нему приложение соберёт само.
    </div>`;
    $("#obStartBar").innerHTML=`
      <button class="btn ghost" data-o="back">← Назад</button>
      <button class="btn" data-o="skip">Добавить своё слово</button>`;
    return;
  }

  $("#obWords").innerHTML = ob.words.map(w=>`
    <div class="ob-word">
      <b>${esc(w.text)}</b>
      <span>${esc(w.translation)}</span>
      ${w.transcription?`<i>${esc(w.transcription)}</i>`:""}
    </div>`).join("");

  $("#obStartBar").innerHTML=`
    <button class="btn ghost" data-o="back">← Назад</button>
    <button class="btn" data-o="start" ${ob.busy?'disabled':''}>
      ${ob.busy?'Готовим…':'Начать практику →'}
    </button>`;
}

// Добавляет набор в словарь и сразу открывает первую карточку.
async function startWithStarter(){
  if(ob.busy || !ob.words.length) return;
  ob.busy=true; renderStarterStep();
  try{
    const result = await api("/catalog/words/add", {
      method:"POST", body:{word_ids: ob.words.map(w=>w.id)}
    });
    if(!result.added_count){
      toast("Не удалось добавить слова, попробуйте ещё раз");
      ob.busy=false; renderStarterStep();
      return;
    }
    // Мастер больше не нужен: словарь непустой.
    $("#onboardView").classList.add("hidden");
    await refresh();
    await startStudy();
  }catch(e){
    toast(e.message);
    ob.busy=false; renderStarterStep();
  }
}

// Уровень сохраняем в профиле сразу: от него зависят фразы, которые генератор
// подберёт к словам набора, а слова добавляются уже на третьем шаге.
async function saveLevel(level){
  ob.level=level;
  $("#levelSel").value=level;
  try{ await api("/auth/level",{method:"PATCH",body:{level}}); }
  catch(e){ toast(e.message); }
}

$("#onboardBody").onclick = (e)=>{
  const lvl=e.target.closest("button[data-level]");
  if(lvl){ saveLevel(lvl.dataset.level); ob.step=2; renderOnboarding(); return; }

  const cat=e.target.closest("button[data-cat]");
  if(cat){ ob.category=cat.dataset.cat; ob.step=3; renderOnboarding(); return; }

  const act=e.target.closest("button[data-o]");
  if(!act) return;
  const a=act.dataset.o;
  if(a==="skip"){ skipOnboarding(); return; }
  if(a==="back"){ ob.step=Math.max(1, ob.step-1); renderOnboarding(); return; }
  if(a==="toStarter"){ ob.step=3; renderOnboarding(); return; }
  if(a==="start"){ startWithStarter(); return; }
};
