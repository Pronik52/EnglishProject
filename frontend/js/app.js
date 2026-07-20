/* Точка входа: общий пересчёт экрана и автовход.

   refresh() лежит здесь, а не в одном из модулей-экранов, потому что собирает
   данные сразу для нескольких: статистика, тариф и список слов. Из-за этого
   app.js и модули экранов импортируют друг друга кольцом — для объявлений
   функций это безопасно (они поднимаются), а вызовы происходят уже после
   загрузки всех модулей. */

import { $, api, token, logout } from "./core.js";
import { enterApp } from "./auth.js";
import { renderPill, setBilling } from "./billing.js";
import { renderList } from "./dictionary.js";
import "./study.js";   // модуль сам вешает обработчики экрана учёбы

export async function refresh(){
  const [stats, words, bill] = await Promise.all([
    api("/words/stats"),
    api("/words?limit=1000"),
    api("/billing/status").catch(()=>null)
  ]);
  $("#stTotal").textContent=stats.total;
  $("#stLearned").textContent=stats.learned;
  $("#stLeft").textContent=stats.remaining;
  $("#stDue").textContent=stats.due ?? 0;
  // billing нужен до renderList: по нему считаем остаток генераций на кнопке.
  if(bill){ setBilling(bill); renderPill(); }
  renderList(words.items);
}

/* Автовход, если есть токен */
if(token){ enterApp().catch(logout); }
