'use strict';
const tg = window.Telegram?.WebApp;
const $ = id => document.getElementById(id);
let data, selected, busy = false;
// English until an explicit server-persisted choice is loaded; never infer from Telegram locale.
let ru = false;
const t = (english, russian) => ru ? russian : english;
const number = value => new Intl.NumberFormat(ru ? 'ru' : 'en', {maximumFractionDigits: 0}).format(value);
tg?.ready(); tg?.expand();
function labels() {
  document.documentElement.lang = ru ? 'ru' : 'en';
  for (const [id, en, russian] of [['heading','Your day in food','Твой день в еде'], ['date-label','Day','День'], ['unit','kcal','ккал'], ['protein-label','Protein, g','Белки, г'], ['carbs-label','Carbs, g','Углеводы, г'], ['fat-label','Fat, g','Жиры, г'], ['history-title','Daily calories','Калории по дням'], ['meals-title','Meals','Что было за день'], ['footnote','Estimates, not a calorie target. Days without entries do not mean you ate nothing.','Это оценка, не целевая норма. День без записей не означает, что ты ничего не ел.']]) $(id).textContent = t(en,russian);
  for (const option of $('range').options) option.textContent = option.value + t(' days',' дней');
  $('previous').setAttribute('aria-label',t('Previous day','Предыдущий день'));
  $('next').setAttribute('aria-label',t('Next day','Следующий день'));
  $('range').setAttribute('aria-label',t('History period','Период истории'));
  $('chart').setAttribute('aria-label',t('Daily calories chart','График калорий по дням'));
}
function render() {
  const day = data.days.find(d => d.date === selected) || data.days.at(-1);
  selected = day.date; $('date').value = selected;
  $('previous').disabled = selected === data.days[0].date;
  $('next').disabled = selected === data.today;
  $('day-title').textContent = selected === data.today ? t('Today','Сегодня') : new Date(selected+'T12:00:00').toLocaleDateString(ru?'ru':'en',{day:'numeric',month:'long'});
  $('calories').textContent = number(day.calories_kcal);
  $('count').textContent = day.count ? t('Entries: ','Записей: ')+day.count : t('No meals logged yet','Пока нет записей');
  ['protein','carbs','fat'].forEach(k => $(k).textContent = number(day[k+'_g']));
  const missing = day.fiber_missing ?? day.count;
  $('fiber-label').textContent = t('Dietary fiber','Клетчатка');
  $('fiber').textContent = (missing && missing === day.count) ? '—' : (missing ? '≥ ' : '') + new Intl.NumberFormat(ru?'ru':'en',{maximumFractionDigits:1}).format(day.fiber_g ?? 0) + t(' g',' г');
  $('fiber-note').textContent = missing ? t('No fiber data for entries: ','Нет данных о клетчатке для записей: ')+missing+t('. Re-estimate them through a reply in the bot.','. Их можно пересчитать ответом в боте.') : t('Total for logged meals.','Сумма по записанным блюдам.');
  $('meals').replaceChildren();
  if (!day.count) $('meals').textContent = t('Send a meal to the bot. It will appear here.','Отправь боту еду — она появится здесь.');
  for (const meal of day.meals) {
    const row = document.createElement('div'); row.className='meal';
    const title = document.createElement('div'); title.className='meal-title'; title.textContent=meal.dish;
    const detail = document.createElement('small'); detail.textContent=meal.time+' · '+t('P / C / F: ','Б / У / Ж: ')+[meal.protein_g,meal.carbs_g,meal.fat_g].map(number).join(' / ')+t(' g',' г');
    detail.textContent += ' · '+t('Fiber: ','Клетчатка: ')+(meal.fiber_g == null ? '—' : new Intl.NumberFormat(ru?'ru':'en',{maximumFractionDigits:1}).format(meal.fiber_g)+t(' g',' г'));
    title.append(detail); const energy=document.createElement('strong'); energy.textContent=number(meal.calories_kcal)+t(' kcal',' ккал'); row.append(title,energy); $('meals').append(row);
  }
  $('chart').replaceChildren(); const max=Math.max(1,...data.days.map(d=>d.calories_kcal));
  for (const d of data.days) {
    const b=document.createElement('button'); b.className='bar'; b.setAttribute('aria-pressed',String(d.date===selected)); b.setAttribute('aria-label',d.date+': '+(d.count ? number(d.calories_kcal)+t(' kcal',' ккал') : t('no entries','нет записей')));
    const value=document.createElement('span'); value.className='bar-value'; value.textContent=d.count?number(d.calories_kcal):'—';
    // SVG avoids inline CSS so the page keeps a restrictive style policy.
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'); svg.setAttribute('width','20'); svg.setAttribute('height',String(d.count?Math.max(3,100*d.calories_kcal/max):2));
    const rect=document.createElementNS(svg.namespaceURI,'rect'); rect.setAttribute('width','20'); rect.setAttribute('height','100%'); rect.setAttribute('rx','5'); rect.setAttribute('fill',d.count?'#80b69a':'#94a09a'); svg.append(rect);
    const date=document.createElement('span'); date.textContent=d.date.slice(8)+'.'+d.date.slice(5,7); b.append(value,svg,date); b.onclick=()=>{selected=d.date;render();}; $('chart').append(b);
  }
  const active=data.days.filter(d=>d.count);
  $('average').textContent=t('Average on logged days: ','Среднее по дням с записями: ')+(active.length?number(active.reduce((s,d)=>s+d.calories_kcal,0)/active.length):'—')+t(' kcal · ',' ккал · ')+data.timezone;
}
async function load() {
  if (busy) return; busy=true;
  labels(); $('status').hidden=false; $('status').textContent=t('Updating…','Обновляю…');
  try {
    if (!tg?.initData) throw new Error('auth');
    const response=await fetch('/api/stats?days='+$('range').value,{headers:{'X-Telegram-Init-Data':tg.initData},cache:'no-store',signal:AbortSignal.timeout(15000)});
    if (response.status===401) throw new Error('auth');
    if (!response.ok) throw new Error('network');
    data=await response.json(); ru=['russian','ru'].includes(data.language.toLowerCase()); labels();
    $('date').min=data.days[0].date; $('date').max=data.today; selected=selected||data.today;
    render(); $('dashboard').hidden=false; $('status').hidden=true;
  } catch(error) {
    if(error.message==='auth') $('dashboard').hidden=true;
    $('status').textContent=error.message==='auth'?t('Open this page using the Calories button in the bot. If your session expired, close and reopen it.','Открой эту страницу кнопкой «Калории» в боте. Если сессия истекла — закрой и открой её снова.'):t('Could not refresh. Close and reopen the app to retry. Any displayed data may be outdated.','Не удалось обновить. Закрой и открой приложение ещё раз. Данные на экране могут быть устаревшими.');
  } finally {busy=false;}
}
$('range').onchange=load;
$('date').onchange=()=>{selected=$('date').value;render();};
for(const [id,delta] of [['previous',-1],['next',1]]) $(id).onclick=()=>{const index=data.days.findIndex(d=>d.date===selected); selected=data.days[index+delta]?.date||selected;render();};
tg?.onEvent('activated',load); tg?.onEvent('themeChanged',labels);
document.addEventListener('visibilitychange',()=>{if(!document.hidden) load();});
load().then(()=>$('chart').scrollLeft=$('chart').scrollWidth);
