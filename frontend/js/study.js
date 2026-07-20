/* Режим учёбы: описание картинки (главный), викторина с выбором и ввод слова. */

import { $, api, toast, esc, highlight, spk, speech, dueTime } from "./core.js";
import { refresh } from "./app.js";

/* ---------- Режим учёбы: викторина с выбором из 4 слов ---------- */
let study = {cards:[], i:0, options:[], answered:false, chosen:null, correct:false};

// Режим тренировки: описание картинки (по умолчанию), выбор варианта или ввод.
$("#studyMode").value = localStorage.getItem("studyMode") || "describe";
$("#studyMode").onchange = (e)=>{
  localStorage.setItem("studyMode", e.target.value);
  // Переключаем текущую карточку на лету, если ещё не ответили.
  if(!$("#studyView").classList.contains("hidden") && study.i<study.cards.length && !study.answered) renderStudy();
};

// Запасные слова-отвлекатели, если в словаре пока мало слов.
const FALLBACK_WORDS=["time","people","water","music","light","money","house","garden",
  "market","letter","summer","travel","coffee","window","picture","school","animal","river"];

function shuffle(a){ for(let k=a.length-1;k>0;k--){ const j=Math.floor(Math.random()*(k+1)); [a[k],a[j]]=[a[j],a[k]]; } return a; }

// Заменяет изучаемое слово во фразе на пропуск (••• с подчёркиванием).
function blankPhrase(phrase, word){
  const p=esc(phrase);
  if(!word) return p;
  const re=new RegExp("("+word.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+")","ig");
  return p.replace(re,'<span class="blank">•••</span>');
}

// Собирает 4 варианта: правильное слово + 3 отвлекателя из других слов словаря.
function buildOptions(cards, i){
  const correct=cards[i].text;
  const seen=new Set([correct.toLowerCase()]);
  const pool=[];
  for(const c of cards){ const t=c.text; if(!seen.has(t.toLowerCase())){ pool.push(t); seen.add(t.toLowerCase()); } }
  shuffle(pool);
  const extra=shuffle(FALLBACK_WORDS.filter(f=>!seen.has(f)));
  const distractors=[...pool, ...extra].slice(0,3);
  return shuffle([correct, ...distractors]);
}

async function startStudy(){
  let words;
  try{ words=(await api("/words?limit=1000")).items; }
  catch(e){ toast(e.message); return; }
  if(!words.length){ toast("Сначала добавьте слова ☝️"); return; }
  // SRS-порядок: выученные в конец, остальные — по «просроченности» (раньше due_at → раньше).
  words.sort((a,b)=>{
    if(a.is_learned!==b.is_learned) return a.is_learned?1:-1;
    return dueTime(a.due_at) - dueTime(b.due_at);
  });
  study={cards:words, i:0, options:[], answered:false, chosen:null, correct:false};
  $("#appView").classList.add("hidden");
  $("#studyView").classList.remove("hidden");
  goToCard(0);
}

function exitStudy(){
  $("#studyView").classList.add("hidden");
  $("#appView").classList.remove("hidden");
  refresh();
}
// Экран «Готово!» зовёт выход инлайновым onclick из шаблона ниже, а функции
// модуля в window не попадают — публикуем её адресно.
window.exitStudy = exitStudy;

function goToCard(index){
  study.i=index; study.answered=false; study.chosen=null; study.correct=false;
  // Состояние режима описания живёт на одну карточку и обнуляется вместе с ней.
  study.verdict=null; study.draft=""; study.hintShown=false; study.sending=false;
  if(index<study.cards.length) study.options=buildOptions(study.cards, index);
  renderStudy();
}

// Текущий режим тренировки: describe (главный) | choice | type.
function currentMode(){
  const sel=$("#studyMode");
  return sel ? sel.value : "describe";
}

// Готова ли картинка к слову. Пока она рисуется, слово тоже считаем годным
// для режима описания — карточка покажет заглушку и дождётся изображения.
function hasScene(w){
  return !!w.image_url || w.image_status==="pending";
}

function renderStudy(){
  const {cards,i,answered,chosen,correct,options}=study;
  const body=$("#studyBody");
  if(i>=cards.length){
    $("#studyCount").textContent=cards.length+" / "+cards.length;
    $("#studyProgress").style.width="100%";
    body.innerHTML=`<div class="study-done"><div class="big">🎉</div>
      <h2>Готово!</h2><p class="muted">Вы прошли все фразы.</p>
      <button class="btn" onclick="exitStudy()">Вернуться к словам</button></div>`;
    return;
  }
  $("#studyCount").textContent=(i+1)+" / "+cards.length;
  $("#studyProgress").style.width=(i/cards.length*100)+"%";
  const w=cards[i];

  // Главный режим — описание картинки. Карточка сама разбирается со случаем
  // «картинки ещё нет»: молча откатываться на викторину нельзя — пользователь
  // выбрал режим и должен понимать, что происходит.
  if(currentMode()==="describe"){ renderDescribeCard(w); return; }

  const typeMode = currentMode()==="type";
  const phraseHtml=answered?highlight(w.phrase||'—',w.text):blankPhrase(w.phrase||'—',w.text);

  // Область ответа: поле ввода (режим «Ввод») либо варианты для выбора.
  let answerArea;
  if(typeMode){
    answerArea = answered
      ? `<div class="type-answer ${correct?'ok':'no'}">Ваш ответ: <b>${esc(chosen||'—')}</b>${correct?'':` · верно: <b>${esc(w.text)}</b>`}</div>`
      : `<div class="study-type">
           <input id="typeAns" type="text" placeholder="введите пропущенное слово" autocomplete="off" autocapitalize="off" spellcheck="false">
           <button class="btn" data-s="check">Проверить</button>
         </div>`;
  }else{
    const optsHtml=options.map(o=>{
      let cls="opt";
      if(answered){
        if(o.toLowerCase()===w.text.toLowerCase()) cls+=" correct";
        else if(o===chosen) cls+=" wrong";
      }
      return `<button class="${cls}" data-opt="${esc(o)}" ${answered?'disabled':''}>${esc(o)}</button>`;
    }).join("");
    answerArea = `<div class="study-options">${optsHtml}</div>`;
  }

  // До ответа — подсказка «перевод слова»; после ответа — перевод ВСЕЙ фразы.
  // phrase_ru: непусто — показываем; "" — недоступен, откатываемся на перевод слова; null — ещё грузится.
  let meaning;
  if(!answered){
    meaning = `<div class="muted">Перевод слова: ${esc(w.translation)}</div>`;
  }else{
    const ruText = w.phrase_ru ? esc(w.phrase_ru) : (w.phrase_ru==="" ? esc(w.translation) : "…");
    meaning = `<div class="phrase-ru"><b>Перевод фразы:</b> ${ruText}</div>`;
  }

  const feedback=answered
    ? `<div class="study-feedback ${correct?'ok':'no'}">${correct?'Верно! +1 запоминание':'Неверно, −1 запоминание'}</div>`
    : '';
  const actions=answered
    ? `<button class="btn" data-s="next">Дальше →</button>`
    : `<button class="btn ghost" data-s="skip">Пропустить →</button>`;
  body.innerHTML=`
    <div class="hint">${answered?'слово во фразе':'какое слово пропущено?'}</div>
    ${sceneHtml(w)}
    <div class="big-phrase">${phraseHtml} ${answered && w.phrase?spk(w.phrase):''}</div>
    ${meaning}
    ${answerArea}
    ${feedback}
    <div class="study-actions">${actions}</div>`;

  if(typeMode && !answered){ const inp=$("#typeAns"); if(inp) inp.focus(); }
  // Перевод фразы ещё не загружен (старые слова) — тянем лениво и перерисовываем.
  if(answered && w.phrase_ru==null) loadPhraseRu(w);
  // Картинка ещё рисуется на сервере — ждём её и обновляем карточку.
  if(w.image_status==="pending") pollSceneImage(w);
}

// Блок картинки-сцены. Показываем ДО ответа: изображение — это подсказка,
// через которую вспоминается фраза, в этом и смысл ассоциативного запоминания.
// Если картинки нет (не сгенерировалась или выключена) — не занимаем место.
function sceneHtml(w){
  if(w.image_url) return `<div class="scene"><img src="${esc(w.image_url)}" alt=""></div>`;
  if(w.image_status==="pending") return `<div class="scene loading">рисуем картинку…</div>`;
  return "";
}

// Опрос готовности картинки. Сервер рисует её в фоне, поэтому спрашиваем
// раз в 2 секунды, но не дольше минуты — чтобы не долбить сервер вечно,
// если провайдер завис.
async function pollSceneImage(w){
  if(w._scenePolling) return;      // уже опрашиваем эту карточку
  w._scenePolling = true;
  for(let attempt=0; attempt<30; attempt++){
    await new Promise(r=>setTimeout(r, 2000));
    try{
      const r = await api(`/words/${w.id}/image`);
      if(r.image_status !== "pending"){
        w.image_url = r.image_url;
        w.image_status = r.image_status;
        // Перерисовываем, только если пользователь всё ещё на этой карточке.
        if(study.cards[study.i] === w) renderStudy();
        break;
      }
    }catch(e){ break; }            // слово удалили или сеть отвалилась
  }
  w._scenePolling = false;
}

/* ===== Главный режим: описание картинки =====
   Пользователь видит сцену и русский перевод целевого слова, а английское
   слово должен вспомнить сам и употребить в описании. Так работает и
   припоминание, и продуктивное использование сразу. Английское слово доступно
   по кнопке-подсказке — чтобы новичок не застревал. */
function renderDescribeCard(w){
  const v=study.verdict;
  const body=$("#studyBody");

  // Картинки ещё нет — описывать нечего. Не подсовываем викторину молча:
  // объясняем, что готовим сцену, и запускаем её генерацию.
  if(!v && !hasScene(w)){
    // Попытка уже была и не удалась — не крутим заглушку вечно.
    if(w._sceneRequested && w.image_status==="failed"){
      renderSceneUnavailable(w, "Не удалось нарисовать картинку для этого слова.");
      return;
    }
    body.innerHTML=`
      <div class="hint">готовим картинку</div>
      <div class="scene loading">рисуем картинку…</div>
      <div class="describe-task">
        Это слово добавлено до появления картинок — рисуем сцену к его фразе.
        Обычно это занимает полминуты.
      </div>
      <div class="big-phrase">${highlight(w.phrase||'—', w.text)}</div>
      <div class="study-actions">
        <button class="btn ghost" data-s="skip">Пропустить →</button>
      </div>`;
    ensureScene(w);
    return;
  }

  if(!v){
    const hintShown=study.hintShown;
    body.innerHTML=`
      <div class="hint">опишите картинку своими словами</div>
      ${sceneHtml(w)}
      <div class="describe-task">
        Используйте слово: <b>${esc(w.translation)}</b>
        ${hintShown
          ? `<span class="describe-reveal">${esc(w.text)} ${spk(w.text)}</span>`
          : `<button class="btn ghost sm" data-s="hint">подсказка</button>`}
      </div>
      <textarea id="describeAns" class="describe-input" rows="3"
        placeholder="Например: An old man is looking at the sea…"
        autocomplete="off" autocapitalize="off" spellcheck="false"></textarea>
      <div class="study-actions">
        <button class="btn" data-s="send" ${study.sending?'disabled':''}>
          ${study.sending?'Проверяем…':'Проверить'}
        </button>
        <button class="btn ghost" data-s="skip">Пропустить →</button>
      </div>`;
    const inp=$("#describeAns");
    if(inp){ inp.value=study.draft||""; if(!study.sending) inp.focus(); }
    if(w.image_status==="pending") pollSceneImage(w);
    return;
  }

  // Разбор ответа. Оценка мягкая: 2 и выше — повтор засчитан.
  const stars="★".repeat(v.grade)+"☆".repeat(3-v.grade);
  const grammar=(v.grammar_ru&&v.grammar_ru.length)
    ? `<div class="describe-grammar"><b>Обратите внимание:</b><ul>${
        v.grammar_ru.map(g=>`<li>${esc(g)}</li>`).join("")}</ul></div>`
    : "";
  const better=v.better_en
    ? `<div class="describe-better"><b>Можно сказать так:</b> ${esc(v.better_en)} ${spk(v.better_en)}</div>`
    : "";
  const ruText = w.phrase_ru ? esc(w.phrase_ru) : (w.phrase_ru==="" ? esc(w.translation) : "…");

  body.innerHTML=`
    <div class="hint">${v.correct?'повтор засчитан':'слово не засчитано'}</div>
    ${sceneHtml(w)}
    <div class="describe-verdict ${v.correct?'ok':'no'}">
      <span class="stars">${stars}</span> ${esc(v.feedback_ru||'')}
    </div>
    <div class="describe-your">Ваш ответ: <i>${esc(study.draft||'')}</i></div>
    ${grammar}
    ${better}
    <div class="big-phrase">${highlight(w.phrase||'—', w.text)} ${w.phrase?spk(w.phrase):''}</div>
    <div class="phrase-ru"><b>Перевод фразы:</b> ${ruText}</div>
    <div class="study-actions"><button class="btn" data-s="next">Дальше →</button></div>`;

  if(w.phrase_ru==null) loadPhraseRu(w);
}

// Просит сервер подготовить сцену для слова, у которого её ещё нет.
// Вызывается один раз на слово: повторные заходы на ту же карточку не должны
// плодить запросы.
async function ensureScene(w){
  if(w._sceneRequested) return;
  w._sceneRequested = true;
  try{
    const r = await api(`/words/${w.id}/scene`,{method:"POST"});
    w.image_url = r.image_url;
    w.image_status = r.image_status;
    if(study.cards[study.i]===w) renderStudy();
    if(r.image_status==="pending") pollSceneImage(w);
  }catch(err){
    // Картинки выключены или у слова нет фразы — режим описания тут не
    // применим. Честно говорим об этом и предлагаем другой режим.
    w.image_status = "failed";
    if(study.cards[study.i]===w) renderSceneUnavailable(w, err.message);
  }
}

// Тупик режима описания: картинку получить не удалось.
function renderSceneUnavailable(w, reason){
  $("#studyBody").innerHTML=`
    <div class="hint">картинки нет</div>
    <div class="describe-task">${esc(reason||"Не удалось подготовить картинку.")}</div>
    <div class="big-phrase">${highlight(w.phrase||'—', w.text)}</div>
    <div class="describe-task muted">
      Для этого слова доступны режимы «Выбор» и «Ввод» — переключите справа вверху.
    </div>
    <div class="study-actions">
      <button class="btn ghost" data-s="skip">Пропустить →</button>
    </div>`;
}

// Отправка описания на проверку.
async function submitDescription(){
  if(study.sending || study.verdict) return;
  const inp=$("#describeAns");
  const text=(inp?inp.value:"").trim();
  if(!text){ toast("Опишите, что происходит на картинке"); return; }

  const w=study.cards[study.i];
  study.draft=text; study.sending=true;
  renderDescribeCard(w);                 // показываем «Проверяем…»
  try{
    const r=await api(`/words/${w.id}/describe`,{method:"POST",body:{text}});
    study.verdict=r.verdict;
    study.answered=true;
    study.correct=r.verdict.correct;
    // Перевод фразы, уже загруженный ранее, не теряем.
    if(r.word.phrase_ru==null) r.word.phrase_ru=w.phrase_ru;
    study.cards[study.i]=r.word;
    if(r.describes_left===0) toast("Дневной лимит проверок исчерпан");
  }catch(err){
    toast(err.message);
  }finally{
    study.sending=false;
    renderStudy();
  }
}

// Ленивая подгрузка русского перевода фразы для текущей карточки.
async function loadPhraseRu(w){
  try{
    const r=await api(`/words/${w.id}/phrase-translation`);
    w.phrase_ru = r.phrase_ru || ""; // "" — перевод недоступен, но повторно не тянем
    if(study.cards[study.i]===w && study.answered) renderStudy();
  }catch(e){ w.phrase_ru = ""; }
}

// Общая обработка ответа (и для выбора, и для ввода).
async function submitAnswer(chosenText){
  if(study.answered) return;
  const w=study.cards[study.i];
  const correct = chosenText.toLowerCase()===w.text.toLowerCase();
  study.answered=true; study.chosen=chosenText; study.correct=correct;
  renderStudy(); // сразу показываем результат
  if(speech.supported && $("#autoSpeak").checked) speech.speak(w.phrase); // автоозвучка на показе ответа
  try{
    const updated=await api(`/words/${w.id}/answer`,{method:"PATCH",body:{correct}});
    // сервер вернёт слово с сохранённым phrase_ru — подхватываем, не теряя загруженный перевод
    if(updated.phrase_ru==null) updated.phrase_ru=w.phrase_ru;
    study.cards[study.i]=updated;
    renderStudy();
  }catch(err){ toast(err.message); }
}

$("#studyBody").onclick = (e)=>{
  const opt=e.target.closest("button.opt");
  if(opt){ if(!study.answered) submitAnswer(opt.dataset.opt); return; } // выбор варианта
  const check=e.target.closest('button[data-s="check"]');
  if(check){ const v=($("#typeAns").value||"").trim(); if(v) submitAnswer(v); return; } // проверка ввода
  const act=e.target.closest("button[data-s]");
  if(!act) return;
  if(act.dataset.s==="send"){ submitDescription(); return; }          // проверка описания
  if(act.dataset.s==="hint"){                                          // показать слово
    const inp=$("#describeAns"); if(inp) study.draft=inp.value;
    study.hintShown=true; renderStudy(); return;
  }
  if(act.dataset.s==="next" || act.dataset.s==="skip") goToCard(study.i+1);
};
// Enter в поле ввода = проверить. В описании Enter переносит строку,
// поэтому там отправка по Ctrl/Cmd+Enter.
$("#studyBody").addEventListener("keydown",(e)=>{
  if(e.key==="Enter" && e.target.id==="typeAns"){ e.preventDefault(); const v=e.target.value.trim(); if(v) submitAnswer(v); }
  if(e.key==="Enter" && (e.ctrlKey||e.metaKey) && e.target.id==="describeAns"){ e.preventDefault(); submitDescription(); }
});
$("#studyBtn").onclick=startStudy;
$("#studyExit").onclick=exitStudy;
