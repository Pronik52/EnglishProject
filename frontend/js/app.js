/* Точка входа: пересчёт экрана и автовход.

   refresh() лежит здесь, а не в одном из модулей-экранов, потому что собирает
   данные сразу для нескольких: статистика и список слов. Из-за этого app.js и
   модули экранов импортируют друг друга кольцом — для объявлений функций это
   безопасно (они поднимаются), а вызовы происходят уже после загрузки всех
   модулей. */

import { $, api, showLoggedOut } from "./core.js";
import { enterApp } from "./auth.js";
import { loadWords, setRules } from "./dictionary.js";
import { shouldOnboard, showOnboarding } from "./onboarding.js";
import "./study.js";   // модуль сам вешает обработчики экрана учёбы

// Числа дашборда и правила показа. /words/stats отдаёт и то и другое, поэтому
// клиенту не нужно хранить копии серверных констант.
function applyStats(stats){
  $("#stTotal").textContent=stats.total;
  $("#stLearned").textContent=stats.learned;
  $("#stLeft").textContent=stats.remaining;
  $("#stDue").textContent=stats.due ?? 0;
  setRules(stats);
}

/* Полный пересчёт: числа плюс перерисовка словаря. Нужен при входе на экран и
   при возврате из тренировки — то есть когда изменилось сразу многое.
   Для одиночных действий над словом есть refreshStats(). */
export async function refresh(){
  const stats = await api("/words/stats");

  // Пустой словарь = человек здесь впервые. Показываем мастер вместо дашборда
  // с нулями: на нём всё равно нечего смотреть, а главная кнопка не работает.
  if(shouldOnboard(stats)){ showOnboarding($("#levelSel").value); return; }

  // setRules до loadWords: по этим правилам рисуются бейджи и остаток генераций.
  applyStats(stats);
  await loadWords();
}

/* Лёгкое обновление: только числа. Карточку слова её обработчик перерисовывает
   сам по ответу сервера, поэтому тянуть весь список ради одного действия
   не нужно — это стоило трёх запросов и сбрасывало позицию прокрутки. */
export async function refreshStats(){
  try{ applyStats(await api("/words/stats")); }
  catch(e){ /* числа на дашборде не критичны — не мешаем работе */ }
}

/* Автовход: наличие и валидность HttpOnly cookie проверяет /auth/me. */
enterApp().catch(showLoggedOut);
