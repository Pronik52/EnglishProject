/* Экран учёбы. Состав сессии и режим каждой карточки приходят с сервера
   (GET /study/session): отбор по срокам повторов, лестница сложности и
   варианты ответа считаются в app/crud/study.py. Здесь остаётся только
   отрисовка и отправка ответов — так же будет устроен и будущий iOS-клиент. */

import { $, api, toast, esc, highlight, spk, speech } from "./core.js";
import { refresh } from "./app.js";

/* Карточка сессии — {word, mode, options}; study.i указывает на текущую. */
let study = {cards:[], i:0, answered:false, chosen:null, correct:false, ahead:false, dueTotal:0};

// Селектор режима — необязательный override. По умолчанию «Авто»: режим
// назначает сервер по уровню SRS слова, и это главный сценарий.

// До появления авто-режима значением по умолчанию был describe, и он лежит в
// localStorage у каждого, кто открывал приложение раньше. Это ровно тот барьер,
// который мы убираем, поэтому старое умолчание гасим один раз — иначе прежние
// пользователи так и остались бы на самом сложном режиме.
if(localStorage.getItem("studyModeAuto")!=="1"){
  if(localStorage.getItem("studyMode")==="describe") localStorage.removeItem("studyMode");
  localStorage.setItem("studyModeAuto","1");
}
$("#studyMode").value = localStorage.getItem("studyMode") || "auto";
$("#studyMode").onchange = (e)=>{
  localStorage.setItem("studyMode", e.target.value);
  // Переключаем текущую карточку на лету, если ещё не ответили.
  if(!$("#studyView").classList.contains("hidden") && study.i<study.cards.length && !study.answered) renderStudy();
};

// Текущая карточка и её слово.
function card(){ return study.cards[study.i]; }
function word(){ const c=card(); return c ? c.word : null; }

// Заменяет изучаемое слово во фразе на пропуск (••• с подчёркиванием).
function blankPhrase(phrase, word){
  const p=esc(phrase);
  if(!word) return p;
  const re=new RegExp("("+word.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+")","ig");
  return p.replace(re,'<span class="blank">•••</span>');
}

// Загружает сессию с сервера. ahead=true — занятие сверх плана, когда
// на сегодня всё повторено.
async function startStudy(ahead=false){
  let session;
  try{ session=await api("/study/session"+(ahead?"?ahead=true":"")); }
  catch(e){ toast(e.message); return; }

  study={cards:session.cards, i:0, answered:false, chosen:null, correct:false,
         ahead:!!session.ahead, dueTotal:session.due_total};
  $("#appView").classList.add("hidden");
  $("#studyView").classList.remove("hidden");
  goToCard(0);
}

function exitStudy(){
  $("#studyView").classList.add("hidden");
  $("#appView").classList.remove("hidden");
  refresh();
}

function goToCard(index){
  study.i=index; study.answered=false; study.chosen=null; study.correct=false;
  // Состояние режима описания живёт на одну карточку и обнуляется вместе с ней.
  study.verdict=null; study.draft=""; study.hintShown=false; study.sending=false;
  renderStudy();
}

// Режим текущей карточки: обычно тот, что назначил сервер по уровню SRS.
// Селектор в шапке может его перебить — это осознанный выбор пользователя,
// поэтому уважаем его, кроме случая, когда выбранный режим нечем показать.
function currentMode(){
  const c=card();
  if(!c) return "type";
  const sel=$("#studyMode");
  const override=sel ? sel.value : "auto";
  if(override && override!=="auto"){
    // Выбор без вариантов невозможен: их считает сервер, и если он их не
    // прислал (пустой каталог, почти пустой словарь) — собрать здесь не из чего.
    if(override==="choice" && !(c.options && c.options.length)) return c.mode;
    return override;
  }
  return c.mode;
}

// Готова ли картинка к слову. Пока она рисуется, слово тоже считаем годным
// для режима описания — карточка покажет заглушку и дождётся изображения.
function hasScene(w){
  return !!w.image_url || w.image_status==="pending";
}

function renderStudy(){
  const {cards,i,answered,chosen,correct}=study;
  const body=$("#studyBody");
  if(i>=cards.length){ renderSessionEnd(); return; }
  $("#studyCount").textContent=(i+1)+" / "+cards.length;
  $("#studyProgress").style.width=(i/cards.length*100)+"%";
  const w=word();
  const options=card().options||[];

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

// Конец сессии. Состояния важно не путать: пустая сессия — это не ошибка и не
// «нет слов», а штатный результат интервальных повторов, и говорить о нём надо
// прямо, иначе человек решит, что приложение сломалось.
function renderSessionEnd(){
  const {cards, ahead, dueTotal}=study;
  $("#studyCount").textContent=cards.length+" / "+cards.length;
  $("#studyProgress").style.width="100%";

  let title, note, extra="";
  if(!cards.length && !ahead){
    title="На сегодня всё";
    note="Слова вернутся в практику, когда подойдёт их срок. Возвращаться к слову раньше времени бесполезно — на этом и держится интервальное запоминание.";
    extra=`<button class="btn ghost" data-s="ahead">Позаниматься сверх плана</button>`;
  }else if(!cards.length){
    title="Словарь пройден";
    note="Все слова закреплены. Добавьте новые — из каталога или свои.";
  }else{
    const left=dueTotal-cards.length;
    title="Готово!";
    note = left>0
      ? `Прошли ${cards.length}. На сегодня ждут ещё ${left} — можно продолжить.`
      : "Вы прошли всё, что было запланировано на сегодня.";
    if(left>0) extra=`<button class="btn ghost" data-s="more">Продолжить</button>`;
  }

  $("#studyBody").innerHTML=`<div class="study-done"><div class="big"></div>
    <h2>${esc(title)}</h2><p class="muted">${esc(note)}</p>
    <div class="study-actions">
      <button class="btn" data-s="exit">Вернуться к словам</button>
      ${extra}
    </div></div>`;
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
        if(word() === w) renderStudy();
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
    if(word()===w) renderStudy();
    if(r.image_status==="pending") pollSceneImage(w);
  }catch(err){
    // Картинки выключены или у слова нет фразы — режим описания тут не
    // применим. Честно говорим об этом и предлагаем другой режим.
    w.image_status = "failed";
    if(word()===w) renderSceneUnavailable(w, err.message);
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

  const w=word();
  study.draft=text; study.sending=true;
  renderDescribeCard(w);                 // показываем «Проверяем…»
  try{
    const r=await api(`/words/${w.id}/describe`,{method:"POST",body:{text}});
    study.verdict=r.verdict;
    study.answered=true;
    study.correct=r.verdict.correct;
    // Перевод фразы, уже загруженный ранее, не теряем.
    if(r.word.phrase_ru==null) r.word.phrase_ru=w.phrase_ru;
    card().word=r.word;
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
    if(word()===w && study.answered) renderStudy();
  }catch(e){ w.phrase_ru = ""; }
}

// Общая обработка ответа (и для выбора, и для ввода).
async function submitAnswer(chosenText){
  if(study.answered) return;
  const w=word();
  const correct = chosenText.toLowerCase()===w.text.toLowerCase();
  study.answered=true; study.chosen=chosenText; study.correct=correct;
  renderStudy(); // сразу показываем результат
  if(speech.supported && $("#autoSpeak").checked) speech.speak(w.phrase); // автоозвучка на показе ответа
  try{
    const updated=await api(`/words/${w.id}/answer`,{method:"PATCH",body:{correct}});
    // сервер вернёт слово с сохранённым phrase_ru — подхватываем, не теряя загруженный перевод
    if(updated.phrase_ru==null) updated.phrase_ru=w.phrase_ru;
    card().word=updated;
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
  if(act.dataset.s==="exit"){ exitStudy(); return; }                   // конец сессии
  if(act.dataset.s==="ahead"){ startStudy(true); return; }             // сверх плана
  if(act.dataset.s==="more"){ startStudy(); return; }                  // добрать оставшиеся
  if(act.dataset.s==="next" || act.dataset.s==="skip") goToCard(study.i+1);
};
// Enter в поле ввода = проверить. В описании Enter переносит строку,
// поэтому там отправка по Ctrl/Cmd+Enter.
$("#studyBody").addEventListener("keydown",(e)=>{
  if(e.key==="Enter" && e.target.id==="typeAns"){ e.preventDefault(); const v=e.target.value.trim(); if(v) submitAnswer(v); }
  if(e.key==="Enter" && (e.ctrlKey||e.metaKey) && e.target.id==="describeAns"){ e.preventDefault(); submitDescription(); }
});
// Обёртка обязательна: onclick передал бы объект события первым аргументом,
// и сессия всегда открывалась бы в режиме «сверх плана».
$("#studyBtn").onclick=()=>startStudy();
$("#studyExit").onclick=exitStudy;

export { startStudy };
