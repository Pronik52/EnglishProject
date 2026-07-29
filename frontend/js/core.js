/* Ядро фронтенда: запросы к API, сессия, общие утилиты и озвучка.

   Модуль НИЧЕГО не импортирует и не знает ни про один экран. Это сделано
   намеренно: остальные модули ссылаются друг на друга кольцами (см. app.js),
   и только полностью независимое ядро гарантирует, что к моменту выполнения
   их кода $ и api уже существуют. */

const API = "/api/v1";
const CSRF_COOKIE = "csrf_token";

// Удаляем JWT, оставшийся от прежней localStorage-схемы. Новый access token
// доступен только серверу через HttpOnly cookie.
try { localStorage.removeItem("token"); } catch (_) {}

export const $ = s => document.querySelector(s);
export const toast = (t) => { const el=$("#toast"); el.textContent=t; el.classList.add("show"); setTimeout(()=>el.classList.remove("show"),1800); };

function getCookie(name){
  const prefix = name + "=";
  return document.cookie.split(";").map(v=>v.trim()).find(v=>v.startsWith(prefix))?.slice(prefix.length) || null;
}

function isUnsafeMethod(method){
  return !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
}

export async function api(path, {method="GET", body=null, form=false, auth=false}={}){
  const headers = {};
  if(isUnsafeMethod(method)){
    const csrfToken = getCookie(CSRF_COOKIE);
    if(csrfToken) headers["X-CSRF-Token"] = csrfToken;
  }
  let payload = body;
  if(form){ headers["Content-Type"]="application/x-www-form-urlencoded"; payload=new URLSearchParams(body).toString(); }
  else if(body){ headers["Content-Type"]="application/json"; payload=JSON.stringify(body); }
  const res = await fetch(API+path, {
    method,
    headers,
    body:payload,
    credentials:"same-origin"
  });
  const data = res.status===204 ? null : await res.json().catch(()=>null);
  if(!res.ok){
    // 401 на защищённом запросе = сессия истекла → выходим.
    // На запросах входа/регистрации (auth) 401 = неверные данные, показываем причину.
    if(res.status===401 && !auth){ showLoggedOut(); const e=new Error("Нужно войти заново."); e.status=401; throw e; }
    const m = data?.error?.message || data?.detail || "Что-то пошло не так, попробуйте ещё раз.";
    const e = new Error(typeof m==="string"?m:JSON.stringify(m));
    e.status = res.status;
    throw e;
  }
  return data;
}

// Отделяем UI от server-side logout: при 401 cookie уже просрочена или невалидна,
// поэтому повторный POST /logout не нужен.
export function showLoggedOut(){
  $("#appView").classList.add("hidden");
  $("#studyView").classList.add("hidden");
  $("#onboardView").classList.add("hidden");
  $("#authView").classList.remove("hidden");
  $("#logoutBtn").classList.add("hidden");
  $("#levelBox").classList.add("hidden");
  $("#speakBox").classList.add("hidden");
  $("#userLabel").classList.add("hidden");
}

export async function logout(){
  try{
    await api("/auth/logout", {method:"POST", auth:true});
  }catch(e){
    // Даже при сетевой ошибке пользователь должен вернуться на экран входа.
  }finally{
    showLoggedOut();
  }
}

/* ---------- Общие утилиты ---------- */

// Русское склонение числительного.
export function plural(n,one,few,many){
  const m10=n%10, m100=n%100;
  if(m10===1 && m100!==11) return one;
  if(m10>=2 && m10<=4 && (m100<10||m100>=20)) return few;
  return many;
}
// Метка следующего повтора по due_at (строка UTC с бэка).
export function dueLabel(dueAt){
  if(!dueAt) return "к повтору";
  const t = Date.parse(/[zZ+]/.test(dueAt) ? dueAt : dueAt+"Z"); // трактуем как UTC
  const ms = t - Date.now();
  if(ms<=0) return "к повтору";
  const days=Math.ceil(ms/86400000);
  if(days>=1) return `через ${days} ${plural(days,'день','дня','дней')}`;
  const hours=Math.max(1,Math.ceil(ms/3600000));
  return `через ${hours} ${plural(hours,'час','часа','часов')}`;
}
// Время «просроченности» для сортировки: чем меньше due_at, тем раньше повтор.
export function dueTime(dueAt){ return dueAt ? Date.parse(/[zZ+]/.test(dueAt)?dueAt:dueAt+"Z") : 0; }

export function esc(s){ return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

export function highlight(phrase, word){
  const p=esc(phrase);
  if(!word) return p;
  const re=new RegExp("("+word.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+")","ig");
  return p.replace(re,"<em>$1</em>");
}

/* ---------- Озвучка (Web Speech API, без внешних зависимостей и ключей) ---------- */
export const speech = {
  supported: typeof window!=="undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window,
  voice: null,
  // getVoices() при первом вызове часто пуст — тогда голоса подтянутся позже по voiceschanged.
  loadVoices(){
    if(!this.supported) return;
    const voices = speechSynthesis.getVoices() || [];
    this.voice = voices.find(v=>v.lang==="en-US")
      || voices.find(v=>v.lang && v.lang.toLowerCase().startsWith("en"))
      || this.voice;  // не нашли — оставим прежний/дефолтный, lang всё равно зададим
  },
  speak(text, btn=null, rate=0.9){
    if(!this.supported || !text) return;
    try{
      speechSynthesis.cancel(); // гасим предыдущую озвучку — не накладываем и не копим при быстрых кликах
      const u = new SpeechSynthesisUtterance(text);
      u.lang="en-US";
      if(this.voice) u.voice=this.voice;
      u.rate=rate;
      document.querySelectorAll(".speak-btn.playing").forEach(b=>b.classList.remove("playing"));
      if(btn) btn.classList.add("playing");
      u.onend = u.onerror = ()=>{ if(btn) btn.classList.remove("playing"); };
      speechSynthesis.speak(u);
    }catch(e){ /* озвучка необязательна — молча игнорируем сбой */ }
  }
};
if(speech.supported){
  speech.loadVoices();
  speechSynthesis.onvoiceschanged = ()=>speech.loadVoices();
}
// HTML кнопки-динамика. Пусто, если API не поддерживается — тогда кнопку просто не рисуем.
export function spk(text){
  if(!speech.supported || !text) return "";
  return `<button type="button" class="speak-btn" data-speak="${esc(text)}" title="Озвучить" aria-label="Озвучить">🔊</button>`;
}
// Единый делегат: клик по любой кнопке-динамику озвучивает её текст (stopPropagation — чтобы не задеть клики карточек).
document.addEventListener("click",(e)=>{
  const b=e.target.closest(".speak-btn");
  if(b){ e.stopPropagation(); speech.speak(b.dataset.speak, b); }
});
// Настройка автоозвучки (по умолчанию выкл), сохраняем в localStorage.
if(!speech.supported){ $("#speakBox").classList.add("hidden"); }
else{
  $("#autoSpeak").checked = localStorage.getItem("autoSpeak")==="1";
  $("#autoSpeak").onchange = (e)=>localStorage.setItem("autoSpeak", e.target.checked?"1":"0");
}
