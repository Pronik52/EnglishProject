/* Экран входа и регистрации, кнопка выхода, смена уровня в шапке. */

import { $, api, toast, setToken, logout, speech } from "./core.js";
import { schedulePreview } from "./dictionary.js";
import { refresh } from "./app.js";

let authMode = "login";

/* ---------- Авторизация ---------- */
// Селектор сужен до [data-mode]: класс .tab носят ещё и вкладки «вручную /
// каталог», и без уточнения этот обработчик и обработчик каталога перетирали
// бы друг друга на всех вкладках сразу.
document.querySelectorAll(".tab[data-mode]").forEach(t=>t.onclick=()=>{
  authMode=t.dataset.mode;
  document.querySelectorAll(".tab[data-mode]").forEach(x=>{
    const active=x===t;
    x.classList.toggle("active",active);
    x.setAttribute("aria-selected", active ? "true" : "false");
  });
  $("#authBtn").textContent = authMode==="login" ? "Войти" : "Зарегистрироваться";
  $("#pwHint").style.display = authMode==="register" ? "block" : "none";
  $("#password").autocomplete = authMode==="login" ? "current-password":"new-password";
  $("#authMsg").textContent="";
});
$("#pwHint").style.display="none";

$("#authBtn").onclick = async ()=>{
  const email=$("#email").value.trim(), password=$("#password").value;
  const msg=$("#authMsg"); msg.className="msg"; msg.textContent="";
  if(!email||!password){ msg.className="msg err"; msg.textContent="Заполните email и пароль."; return; }
  try{
    if(authMode==="register"){
      await api("/auth/register",{method:"POST",body:{email,password},auth:true});
      msg.className="msg ok"; msg.textContent="Готово! Входим…";
    }
    const tok = await api("/auth/login",{method:"POST",form:true,body:{username:email,password},auth:true});
    setToken(tok.access_token); localStorage.setItem("token",tok.access_token);
    enterApp();
  }catch(e){ msg.className="msg err"; msg.textContent=e.message; }
};
["#email", "#password"].forEach(selector=>$(selector).addEventListener("keydown",e=>{
  if(e.key==="Enter") $("#authBtn").click();
}));

$("#logoutBtn").onclick=logout;

/* Смена уровня: новые фразы (при добавлении/регенерации/предпросмотре) станут
   проще или сложнее. Уже сохранённые фразы не меняются. */
$("#levelSel").onchange = async ()=>{
  try{
    await api("/auth/level",{method:"PATCH",body:{level:$("#levelSel").value}});
    toast("Уровень: "+$("#levelSel").value);
    if($("#wText").value.trim()) schedulePreview();
  }catch(e){ toast(e.message); }
};

/* ---------- Основной экран ---------- */
export async function enterApp(){
  $("#authView").classList.add("hidden");
  $("#appView").classList.remove("hidden");
  $("#logoutBtn").classList.remove("hidden");
  try{
    const me=await api("/auth/me");
    $("#levelSel").value=me.level;
    $("#userLabel").textContent=me.email;
    $("#userLabel").classList.remove("hidden");
  }catch(e){}
  $("#levelBox").classList.remove("hidden");
  if(speech.supported) $("#speakBox").classList.remove("hidden"); // тумблер автоозвучки — только если API есть
  await refresh();
}
