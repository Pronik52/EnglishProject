/* Тариф и монетизация: пилюля в шапке, окно покупки Premium, форма карты. */

import { $, api, toast } from "./core.js";
import { refresh } from "./app.js";

// Текущий тариф. Пишет его refresh() через setBilling — остальные модули
// только читают: импортированная переменная остаётся живой на чтение.
export let billing=null;
export function setBilling(value){ billing = value; }

// Рисует пилюлю тарифа по текущему billing (без сетевого запроса).
export function renderPill(){
  if(!billing) return;
  const pill=$("#planPill");
  pill.classList.remove("hidden");
  if(billing.is_premium){
    pill.textContent="Premium";
    pill.classList.add("premium");
  }else{
    pill.textContent=`Free · ${billing.used_today}/${billing.daily_limit} сегодня`;
    pill.classList.remove("premium");
  }
}

const PREMIUM_FEATURES=[
  ["Безлимит слов в день", true],
  ["Подбор слов от ИИ по уровню (A1–C1)", false],
  ["Генерация картинок к словам «на лету»", false],
  ["Озвучка фраз и проверка произношения", false],
  ["Умное повторение и статистика прогресса", false],
  ["Импорт словарей и экспорт в Anki", false],
];

// Тарифные планы (срок в месяцах должен совпадать с допустимыми на бэке: 1/3/12).
const PLANS=[
  {months:1,  price:299,  old:null, per:"299 ₽ / мес",  term:"1 месяц"},
  {months:3,  price:799,  old:897,  per:"266 ₽ / мес",  term:"3 месяца",  badge:"−11%"},
  {months:12, price:2490, old:3588, per:"208 ₽ / мес",  term:"12 месяцев", badge:"−30%", best:true},
];
const fmtRub=n=>n.toLocaleString("ru-RU")+" ₽";

// Состояние окна покупки: шаг ("plans" → выбор плана, "card" → форма оплаты).
let premiumStep="plans", selectedPlan=null;

export function openPremium(){ premiumStep="plans"; selectedPlan=null; renderPremium(); $("#premiumModal").classList.add("show"); }
function closePremium(){ $("#premiumModal").classList.remove("show"); }

// Роутер окна: активному Premium — статус, иначе выбор плана либо форма карты.
function renderPremium(){
  if(billing && billing.is_premium){ renderPremiumStatus(); return; }
  if(premiumStep==="card" && selectedPlan){ renderCardForm(); return; }
  renderPlans();
}

function featsList(){
  return PREMIUM_FEATURES.map(([name,ready])=>
    `<li><span aria-hidden="true">${ready?'✓':'—'}</span> ${name}${ready?'':'<span class="soon">скоро</span>'}</li>`).join("");
}

function renderPlans(){
  const plans=PLANS.map(p=>`
    <button class="plan ${p.best?'best':''}" data-plan="${p.months}">
      ${p.badge?`<span class="p-badge">${p.badge}</span>`:''}
      <div>
        <div class="p-term">${p.term}</div>
        <div class="p-per">${p.per}</div>
      </div>
      <div class="p-price">${p.old?`<span class="p-old">${fmtRub(p.old)}</span>`:''}${fmtRub(p.price)}</div>
    </button>`).join("");
  $("#premiumBody").innerHTML=`
    <h2>PhraseLearn Premium</h2>
    <div class="price">Выберите срок подписки</div>
    <div class="plans">${plans}</div>
    <ul>${featsList()}</ul>
    <div class="note">Демо-режим: оплата фиктивная, деньги не списываются.</div>
    <div class="note"><button class="btn ghost sm" data-b="close">Закрыть</button></div>`;
}

function renderCardForm(){
  const p=selectedPlan;
  $("#premiumBody").innerHTML=`
    <button class="back" data-b="back">← Выбрать другой план</button>
    <h2>Оплата Premium</h2>
    <div class="price">${p.term} · <b>${fmtRub(p.price)}</b></div>
    <div class="cardform">
      <div>
        <label>Номер карты</label>
        <input id="ccNum" inputmode="numeric" autocomplete="off" maxlength="19" placeholder="0000 0000 0000 0000">
      </div>
      <div class="row">
        <div><label>Срок действия</label><input id="ccExp" inputmode="numeric" maxlength="5" placeholder="ММ/ГГ"></div>
        <div><label>CVC</label><input id="ccCvc" inputmode="numeric" maxlength="3" placeholder="123"></div>
      </div>
      <div>
        <label>Имя на карте</label>
        <input id="ccName" autocomplete="off" placeholder="IVAN IVANOV">
      </div>
    </div>
    <div class="card-err" id="ccErr"></div>
    <button class="btn" style="width:100%" data-b="pay">Оплатить ${fmtRub(p.price)}</button>
    <div class="note">🔒 Демо-режим: данные карты никуда не отправляются и не сохраняются.</div>`;
  // Лёгкое форматирование ввода — только визуально, оплата всё равно фиктивная.
  const num=$("#ccNum"); num.oninput=()=>{ const v=num.value.replace(/\D/g,"").slice(0,16); num.value=v.replace(/(.{4})/g,"$1 ").trim(); };
  const exp=$("#ccExp"); exp.oninput=()=>{ const v=exp.value.replace(/\D/g,"").slice(0,4); exp.value=v.length>2?v.slice(0,2)+"/"+v.slice(2):v; };
  const cvc=$("#ccCvc"); cvc.oninput=()=>{ cvc.value=cvc.value.replace(/\D/g,"").slice(0,3); };
}

function renderPremiumStatus(){
  const until=billing.premium_until
    ? new Date(billing.premium_until).toLocaleDateString("ru-RU",{day:"numeric",month:"long",year:"numeric"})
    : null;
  $("#premiumBody").innerHTML=`
    <h2>Premium активен</h2>
    <div class="price">${until?`Действует до ${until}`:"Подписка активна"}</div>
    <ul>${featsList()}</ul>
    <button class="btn ghost" style="width:100%" data-b="deactivate">Вернуться на Free</button>
    <div class="note">Отмена пока вручную. В будущем Premium будет отключаться автоматически по истечении срока.</div>
    <div class="note"><button class="btn ghost sm" data-b="close">Закрыть</button></div>`;
}

// Фиктивная проверка карты — чтобы форма ощущалась настоящей. Возвращает текст ошибки или null.
function validateCard(){
  const num=$("#ccNum").value.replace(/\s/g,"");
  const exp=$("#ccExp").value, cvc=$("#ccCvc").value, name=$("#ccName").value.trim();
  if(num.length<16) return "Введите номер карты (16 цифр)";
  if(!/^\d{2}\/\d{2}$/.test(exp)) return "Срок в формате ММ/ГГ";
  const mm=+exp.slice(0,2); if(mm<1||mm>12) return "Неверный месяц в сроке";
  if(cvc.length<3) return "CVC — 3 цифры";
  if(!name) return "Введите имя на карте";
  return null;
}

$("#planPill").onclick=openPremium;
$("#premiumModal").onclick = async (e)=>{
  if(e.target.id==="premiumModal"){ closePremium(); return; } // клик по фону
  // Выбор плана → переход к форме оплаты.
  const planBtn=e.target.closest("button[data-plan]");
  if(planBtn){ selectedPlan=PLANS.find(p=>p.months==planBtn.dataset.plan); premiumStep="card"; renderPremium(); return; }
  const btn=e.target.closest("button[data-b]"); if(!btn) return;
  const b=btn.dataset.b;
  if(b==="close"){ closePremium(); return; }
  if(b==="back"){ premiumStep="plans"; selectedPlan=null; renderPremium(); return; }
  try{
    if(b==="pay"){
      const err=validateCard();
      if(err){ $("#ccErr").textContent=err; return; }
      await api("/billing/activate",{method:"POST",body:{
        plan:selectedPlan.months,
        card_number:$("#ccNum").value, card_exp:$("#ccExp").value,
        card_cvc:$("#ccCvc").value, card_holder:$("#ccName").value
      }});
      toast("Premium активирован");
      closePremium();
      await refresh(); // обновляем тариф и снимаем блокировки на фразах
    } else if(b==="deactivate"){
      await api("/billing/deactivate",{method:"POST"});
      toast("Тариф Free");
      await refresh(); // сбрасывает лимиты: кнопки «другая фраза» снова доступны
      renderPremium();
    }
  }catch(err){
    const errBox=$("#ccErr");
    if(b==="pay" && errBox) errBox.textContent=err.message; else toast(err.message);
  }
};
