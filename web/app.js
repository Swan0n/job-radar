'use strict';

const TABS = [
  { id: 'primary',   label: 'Подходящие',   countKey: 'primary' },
  { id: 'secondary', label: 'Почти',        countKey: 'secondary' },
  { id: 'saved',     label: 'Избранное',    countKey: 'saved' },
  { id: 'applied',   label: 'Отклики',      countKey: 'applied' },
  { id: 'all',       label: 'Все',          countKey: 'total' },
  { id: 'hidden',    label: 'Скрытые',      countKey: 'hidden' },
];

const STATUS_LABELS = {
  new: 'Новая', saved: 'В избранном', applied: 'Откликнулся',
  interview: 'Собеседование', rejected: 'Отказ', hidden: 'Скрыта',
};

const SOURCE_LABELS = {
  'work.ua': 'work.ua', 'robota.ua': 'robota.ua', 'djinni.co': 'djinni',
  'dou.ua': 'dou', 'linkedin': 'linkedin',
};

const state = { tab: 'primary', search: '', source: '', app: null, items: [], polling: null };

// ------------------------------------------------------------------ утилиты

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
};

async function api(path, options) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || `Ошибка ${res.status}`);
  return data;
}

function toast(message) {
  document.querySelectorAll('.toast').forEach((t) => t.remove());
  const node = el('div', 'toast', message);
  document.body.appendChild(node);
  setTimeout(() => node.remove(), 3200);
}

function scoreClass(score) {
  if (score >= 85) return 'high';
  if (score >= 70) return 'good';
  if (score >= 50) return 'mid';
  return 'low';
}

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(diff)) return '';
  if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))} мин назад`;
  if (diff < 86400) return `${Math.round(diff / 3600)} ч назад`;
  const days = Math.round(diff / 86400);
  if (days < 30) return `${days} дн назад`;
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function isNew(item) {
  return (Date.now() - new Date(item.first_seen).getTime()) < 36 * 3600 * 1000;
}

// ------------------------------------------------------------------ шапка

function renderTabs() {
  const counts = state.app?.counts || {};
  const nav = $('#tabs');
  nav.replaceChildren();
  for (const tab of TABS) {
    const btn = el('button', `tab${state.tab === tab.id ? ' active' : ''}`);
    btn.append(tab.label);
    const n = counts[tab.countKey];
    if (n != null) btn.append(el('span', 'n', String(n)));
    btn.onclick = () => { state.tab = tab.id; renderTabs(); loadList(); };
    nav.append(btn);
  }
}

function renderSubtitle() {
  const app = state.app;
  if (!app) return;
  const parts = [];
  if (app.last_run?.finished_at) parts.push(`обновлено ${timeAgo(app.last_run.finished_at)}`);
  if (app.next_run) {
    const next = new Date(app.next_run);
    parts.push(`следующее ${next.toLocaleString('ru-RU', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })}`);
  } else {
    parts.push('обновление вручную');
  }
  $('#subtitle').textContent = parts.join(' · ');
}

function renderNotices() {
  const box = $('#notices');
  box.replaceChildren();
  const app = state.app;
  if (!app) return;

  const add = (kind, title, text, actionLabel, action) => {
    const node = el('div', `notice ${kind}`);
    const grow = el('div', 'grow');
    grow.append(el('b', null, title), el('span', null, text));
    node.append(grow);
    if (actionLabel) {
      const btn = el('button', 'btn sm', actionLabel);
      btn.onclick = action;
      node.append(btn);
    }
    box.append(node);
  };

  if (!app.has_api_key) {
    add('err', 'Нет ключа Claude API',
        'Впиши ANTHROPIC_API_KEY в файл .env в папке проекта и перезапусти сервис.');
  }
  if (!app.profile) {
    const hasFile = app.resume_file_present;
    add('warn', 'Резюме не загружено',
        hasFile ? `Файл ${hasFile} лежит в папке resume/ — осталось его разобрать.`
                : 'Положи PDF или DOCX в папку resume/ рядом с проектом.',
        hasFile ? 'Разобрать резюме' : null,
        hasFile ? reloadResume : null);
  }
  if (app.last_run && app.last_run.ok === 0 && app.last_run.error) {
    add('err', 'Прошлый прогон не удался', app.last_run.error);
  }
  if (app.unscored > 0 && !app.progress?.running) {
    add('info', `Ещё ${app.unscored} вакансий ждут оценки`,
        'За один прогон оценивается ограниченная пачка, чтобы не жечь токены. Нажми «Обновить сейчас», чтобы разобрать остаток.',
        'Разобрать', () => startScan(false));
  }
  const errs = app.progress?.errors || [];
  if (errs.length && !app.progress.running) {
    add('info', 'Часть источников не ответила', errs.join('; '));
  }
}

function renderProgress() {
  const p = state.app?.progress;
  const box = $('#progress');
  const scanBtn = $('#btn-scan');
  if (p?.running) {
    box.hidden = false;
    $('#progress-text').textContent =
      `${p.stage}${p.detail ? ': ' + p.detail : ''} · найдено ${p.found}, оценено ${p.scored}`;
    scanBtn.disabled = true;
    scanBtn.textContent = 'Идёт обновление…';
    if (!state.polling) state.polling = setInterval(refreshState, 2000);
  } else {
    box.hidden = true;
    scanBtn.disabled = false;
    scanBtn.textContent = 'Обновить сейчас';
    if (state.polling) { clearInterval(state.polling); state.polling = null; }
  }
}

// ------------------------------------------------------------------ карточки

function barRow(label, value) {
  const row = el('div', 'bar-row');
  const lbl = el('div', 'lbl');
  lbl.append(el('span', null, label), el('b', null, `${Math.round(value)}%`));
  const bar = el('div', 'bar');
  const fill = el('i');
  fill.style.width = `${Math.max(2, Math.min(100, value))}%`;
  if (value < 50) fill.style.background = 'var(--amber)';
  if (value >= 80) fill.style.background = 'var(--green)';
  bar.append(fill);
  row.append(lbl, bar);
  return row;
}

function renderCard(item) {
  const card = el('div', 'card');
  const head = el('div', 'card-head');

  const score = el('div', `score ${scoreClass(item.score)}`, Math.round(item.score));
  const main = el('div');
  main.style.flex = '1';
  main.style.minWidth = '0';

  const title = el('div', 'card-title');
  const link = el('a', null, item.title);
  link.href = item.url; link.target = '_blank'; link.rel = 'noopener';
  title.append(link);
  if (isNew(item)) title.append(' ', el('span', 'badge-new', 'новое'));

  const meta = el('div', 'meta');
  if (item.company) meta.append(el('span', 'company', item.company));
  if (item.location) meta.append(el('span', null, item.location));
  if (item.salary_raw) meta.append(el('span', 'salary', item.salary_raw));
  meta.append(el('span', 'src', SOURCE_LABELS[item.source] || item.source));
  const when = item.posted_at || item.first_seen;
  if (when) meta.append(el('span', null, timeAgo(when)));
  if (item.status && item.status !== 'new') {
    meta.append(el('span', 'chip', STATUS_LABELS[item.status]));
  }

  main.append(title, meta);
  if (item.summary) main.append(el('p', 'summary', item.summary));

  head.append(score, main);
  card.append(head);

  const b = item.breakdown || {};
  if (Object.keys(b).length) {
    const bars = el('div', 'bars');
    bars.append(
      barRow('Навыки и стек', b.skills ?? 0),
      barRow('Опыт и грейд', b.experience ?? 0),
      barRow('Условия', b.conditions ?? 0),
    );
    card.append(bars);
  }

  const chips = el('div', 'chips');
  (item.matched || []).slice(0, 6).forEach((t) => chips.append(el('span', 'chip ok', '✓ ' + t)));
  (item.missing || []).slice(0, 4).forEach((t) => chips.append(el('span', 'chip miss', '− ' + t)));
  (item.red_flags || []).slice(0, 3).forEach((t) => chips.append(el('span', 'chip flag', '⚑ ' + t)));
  if (chips.children.length) card.append(chips);

  // --- действия ---
  const actions = el('div', 'card-actions');
  const letterBtn = el('button', 'btn primary sm',
    item.has_letter ? 'Письмо готово' : 'Кавер-леттер');
  letterBtn.onclick = () => openLetter(item, letterBtn);
  actions.append(letterBtn);

  const openBtn = el('button', 'btn sm', 'Открыть вакансию');
  openBtn.onclick = () => window.open(item.url, '_blank', 'noopener');
  actions.append(openBtn);

  const statusSel = el('select');
  statusSel.className = 'btn sm';
  for (const [value, label] of Object.entries(STATUS_LABELS)) {
    const opt = el('option', null, label);
    opt.value = value;
    if (value === (item.status || 'new')) opt.selected = true;
    statusSel.append(opt);
  }
  statusSel.onchange = async () => {
    try {
      const res = await api(`/api/vacancies/${item.id}/status`, {
        method: 'POST', body: JSON.stringify({ status: statusSel.value }),
      });
      state.app.counts = res.counts;
      renderTabs();
      toast(`Статус: ${STATUS_LABELS[statusSel.value]}`);
      if (statusSel.value === 'hidden' && state.tab !== 'hidden') card.remove();
    } catch (e) { toast(e.message); }
  };
  const spacer = el('div', 'spacer');
  actions.append(spacer, statusSel);
  card.append(actions);

  return card;
}

function renderList() {
  const list = $('#list');
  list.replaceChildren();

  if (!state.items.length) {
    const empty = el('div', 'empty');
    const tab = TABS.find((t) => t.id === state.tab);
    empty.append(el('h3', null, 'Пока пусто'));
    if (!state.app?.profile) {
      empty.append(el('p', null, 'Сначала загрузи резюме — по нему считается совпадение.'));
    } else if (!state.app?.last_run) {
      empty.append(el('p', null, 'Первый сбор ещё не запускался. Он займёт 10–20 минут и соберёт вакансии за 30 дней.'));
      const btn = el('button', 'btn primary', 'Запустить первый сбор');
      btn.onclick = () => startScan(true);
      empty.append(btn);
    } else {
      empty.append(el('p', null, `На вкладке «${tab.label}» ничего нет. Попробуй снизить порог в настройках или добавить поисковые запросы.`));
    }
    list.append(empty);
    return;
  }

  const frag = document.createDocumentFragment();
  state.items.forEach((item) => frag.append(renderCard(item)));
  list.append(frag);
}

// ------------------------------------------------------------------ данные

async function refreshState() {
  try {
    state.app = await api('/api/state');
    renderTabs(); renderSubtitle(); renderNotices(); renderProgress();
    fillSourceFilter();
  } catch (e) { console.error(e); }
}

function fillSourceFilter() {
  const sel = $('#source-filter');
  if (sel.options.length > 1) return;
  (state.app?.all_sources || []).forEach((s) => {
    const opt = el('option', null, SOURCE_LABELS[s] || s);
    opt.value = s;
    sel.append(opt);
  });
}

async function loadList() {
  const params = new URLSearchParams({ tab: state.tab });
  if (state.search) params.set('search', state.search);
  if (state.source) params.set('source', state.source);
  try {
    const data = await api(`/api/vacancies?${params}`);
    state.items = data.items;
    renderList();
  } catch (e) { toast(e.message); }
}

async function startScan(firstRun) {
  try {
    await api(`/api/scan?first_run=${firstRun ? 'true' : 'false'}`, { method: 'POST' });
    toast(firstRun ? 'Первый сбор запущен — это надолго' : 'Обновление запущено');
    setTimeout(refreshState, 600);
  } catch (e) { toast(e.message); }
}

async function reloadResume() {
  toast('Разбираю резюме…');
  try {
    const res = await api('/api/resume/reload', { method: 'POST' });
    toast(`Резюме разобрано: ${res.profile.headline}`);
    await refreshState();
    renderList();
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ модалки

function modal({ title, body, footer }) {
  const overlay = el('div', 'overlay');
  const box = el('div', 'modal');
  const head = document.createElement('header');
  head.append(el('h2', null, title));
  const close = el('button', 'btn ghost sm', '✕');
  close.onclick = () => overlay.remove();
  head.append(close);

  const bodyBox = el('div', 'body');
  bodyBox.append(body);
  box.append(head, bodyBox);

  if (footer) {
    const foot = document.createElement('footer');
    foot.append(...footer);
    box.append(foot);
  }
  overlay.append(box);
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  document.addEventListener('keydown', function onEsc(e) {
    if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onEsc); }
  });
  document.body.append(overlay);
  return overlay;
}

async function openLetter(item, button) {
  const body = el('div');
  const letter = el('div', 'letter', 'Пишу письмо под эту вакансию…');
  body.append(letter);

  const copyBtn = el('button', 'btn primary', 'Скопировать');
  const againBtn = el('button', 'btn', 'Написать заново');
  const overlay = modal({
    title: item.title,
    body,
    footer: [againBtn, copyBtn],
  });

  const load = async (regenerate) => {
    letter.textContent = regenerate ? 'Переписываю…' : 'Пишу письмо под эту вакансию…';
    try {
      const res = await api(`/api/vacancies/${item.id}/cover`, {
        method: 'POST', body: JSON.stringify({ regenerate }),
      });
      letter.textContent = res.text;
      item.has_letter = true;
      if (button) button.textContent = 'Письмо готово';
    } catch (e) {
      letter.textContent = `Не получилось: ${e.message}`;
    }
  };

  copyBtn.onclick = async () => {
    try {
      await navigator.clipboard.writeText(letter.textContent);
      toast('Письмо скопировано');
    } catch { toast('Не вышло скопировать — выдели текст вручную'); }
  };
  againBtn.onclick = () => load(true);

  await load(false);
  return overlay;
}

// ------------------------------------------------------------------ настройки

function field(label, control, hint) {
  const wrap = el('div', 'field');
  wrap.append(el('label', null, label), control);
  if (hint) wrap.append(el('div', 'hint', hint));
  return wrap;
}

function textInput(value, placeholder) {
  const input = el('input');
  input.type = 'text'; input.value = value ?? ''; input.placeholder = placeholder || '';
  return input;
}

function openSettings() {
  const s = JSON.parse(JSON.stringify(state.app.settings));
  const body = el('div');

  const add = (node) => body.append(node);
  const sectionTitle = (t) => add(el('div', 'section-title', t));

  // --- поиск ---
  sectionTitle('Что искать');
  const queries = el('textarea');
  queries.value = (s.queries || []).join('\n');
  queries.placeholder = 'Python Developer\nBackend Engineer';
  add(field('Поисковые запросы, по одному в строке', queries,
    'Их вводят в поиск на джоб-бордах. Если оставить пусто, возьму роли из резюме.'));

  const exclude = textInput((s.exclude_keywords || []).join(', '), '1С, продажи, стажер');
  add(field('Стоп-слова в названии, через запятую', exclude,
    'Вакансии с этими словами в названии даже не оцениваются.'));

  // --- условия ---
  sectionTitle('Условия работы');
  const formats = el('div', 'checks');
  const fmtMap = { remote: 'Удалённо', hybrid: 'Гибрид', office: 'Офис' };
  for (const [value, label] of Object.entries(fmtMap)) {
    const lab = el('label', 'check');
    const cb = el('input'); cb.type = 'checkbox'; cb.value = value;
    cb.checked = (s.work_formats || []).includes(value);
    lab.append(cb, el('span', null, label));
    formats.append(lab);
  }
  add(field('Формат работы', formats, 'Не подходящий формат сильно снижает процент, но вакансию не прячет.'));

  const cities = textInput((s.cities || []).join(', '), 'Київ, Львів');
  add(field('Города, через запятую', cities, 'Для удалённых вакансий город не учитывается.'));

  const money = el('div', 'row2');
  const salary = el('input'); salary.type = 'number'; salary.value = s.min_salary || 0; salary.min = 0;
  const currency = el('select');
  ['USD', 'UAH'].forEach((c) => {
    const opt = el('option', null, c); opt.value = c;
    if (c === s.salary_currency) opt.selected = true;
    currency.append(opt);
  });
  money.append(salary, currency);
  add(field('Зарплатный ориентир', money,
    'Мягкий фильтр: вакансии ниже опускаются в списке, но остаются видимыми.'));

  // --- отбор ---
  sectionTitle('Отбор');
  const sliderWrap = el('div', 'slider-row');
  const slider = el('input');
  slider.type = 'range'; slider.min = 40; slider.max = 95; slider.step = 5; slider.value = s.threshold;
  const out = el('output', null, `${s.threshold}%`);
  slider.oninput = () => { out.textContent = `${slider.value}%`; };
  sliderWrap.append(slider, out);
  add(field('Порог «подходит»', sliderWrap,
    'Вакансии выше порога попадают на первую вкладку, от 50% до порога — на вторую.'));

  const weightsBox = el('div', 'row2');
  const weightInputs = {};
  const weightLabels = { skills: 'Навыки и стек', experience: 'Опыт и грейд',
                         conditions: 'Условия', domain: 'Домен' };
  for (const [key, label] of Object.entries(weightLabels)) {
    const input = el('input');
    input.type = 'number'; input.min = 0; input.max = 100;
    input.value = (s.weights || {})[key] ?? 0;
    weightInputs[key] = input;
    const wrap = el('div', 'field');
    wrap.style.margin = '0';
    wrap.append(el('label', null, label), input);
    weightsBox.append(wrap);
  }
  add(field('Веса измерений', weightsBox, 'Приводятся к сумме 100 автоматически.'));

  // --- источники ---
  sectionTitle('Источники');
  const sources = el('div', 'checks');
  const srcInputs = {};
  (state.app.all_sources || []).forEach((name) => {
    const lab = el('label', 'check');
    const cb = el('input'); cb.type = 'checkbox';
    cb.checked = (s.sources_enabled || {})[name] !== false;
    srcInputs[name] = cb;
    lab.append(cb, el('span', null, SOURCE_LABELS[name] || name));
    sources.append(lab);
  });
  add(field('Где искать', sources,
    'work.ua и robota.ua требуют браузера и работают медленнее. LinkedIn — неофициальный публичный поиск, может отвалиться.'));

  const pages = el('input');
  pages.type = 'number'; pages.min = 1; pages.max = 10; pages.value = s.max_pages_per_query;
  add(field('Страниц на запрос', pages, 'Больше страниц — глубже охват и дольше прогон.'));

  // --- расписание ---
  sectionTitle('Обновление и модели');
  const auto = el('label', 'check');
  const autoCb = el('input'); autoCb.type = 'checkbox'; autoCb.checked = !!s.auto_schedule;
  auto.append(autoCb, el('span', null, 'Обновлять автоматически каждый день'));
  add(field('Режим обновления', auto,
    'Выключено — вакансии собираются и оцениваются только по кнопке «Обновить сейчас», и токены без спроса не тратятся.'));

  const timeInput = el('input');
  timeInput.type = 'text'; timeInput.value = s.schedule_time; timeInput.placeholder = '09:00';
  const timeField = field('Время ежедневного обновления (Киев)', timeInput,
    'Если Mac в это время спал, обновление догонится при следующем запуске.');
  timeField.hidden = !autoCb.checked;
  autoCb.onchange = () => { timeField.hidden = !autoCb.checked; };
  add(timeField);

  const notify = el('label', 'check');
  const notifyCb = el('input'); notifyCb.type = 'checkbox'; notifyCb.checked = !!s.notify_macos;
  notify.append(notifyCb, el('span', null, 'Уведомление macOS, когда обновление нашло новые вакансии'));
  add(field('Уведомления', notify));

  const models = el('div', 'row2');
  const modelOpts = ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'];
  const mkModel = (current) => {
    const sel = el('select');
    modelOpts.forEach((m) => {
      const opt = el('option', null, m); opt.value = m;
      if (m === current) opt.selected = true;
      sel.append(opt);
    });
    return sel;
  };
  const scoringModel = mkModel(s.scoring_model);
  const letterModel = mkModel(s.letter_model);
  const m1 = el('div', 'field'); m1.style.margin = '0';
  m1.append(el('label', null, 'Оценка вакансий'), scoringModel);
  const m2 = el('div', 'field'); m2.style.margin = '0';
  m2.append(el('label', null, 'Кавер-леттеры'), letterModel);
  models.append(m1, m2);
  add(field('Модели Claude', models,
    'Оценка — самая массовая операция. Sonnet заметно дешевле Opus, качество разбора чуть ниже.'));

  // --- сохранение ---
  const saveBtn = el('button', 'btn primary', 'Сохранить');
  const resumeBtn = el('button', 'btn', 'Перечитать резюме');
  const overlay = modal({ title: 'Настройки', body, footer: [resumeBtn, saveBtn] });

  resumeBtn.onclick = async () => { await reloadResume(); overlay.remove(); };

  saveBtn.onclick = async () => {
    const payload = {
      queries: queries.value.split('\n').map((x) => x.trim()).filter(Boolean),
      exclude_keywords: exclude.value.split(',').map((x) => x.trim()).filter(Boolean),
      work_formats: [...formats.querySelectorAll('input:checked')].map((i) => i.value),
      cities: cities.value.split(',').map((x) => x.trim()).filter(Boolean),
      min_salary: Number(salary.value) || 0,
      salary_currency: currency.value,
      threshold: Number(slider.value),
      weights: Object.fromEntries(Object.entries(weightInputs).map(([k, i]) => [k, Number(i.value) || 0])),
      sources_enabled: Object.fromEntries(Object.entries(srcInputs).map(([k, i]) => [k, i.checked])),
      max_pages_per_query: Number(pages.value) || 3,
      auto_schedule: autoCb.checked,
      schedule_time: timeInput.value.trim() || '09:00',
      notify_macos: notifyCb.checked,
      scoring_model: scoringModel.value,
      letter_model: letterModel.value,
    };
    try {
      const res = await api('/api/settings', { method: 'POST', body: JSON.stringify(payload) });
      state.app.settings = res.settings;
      state.app.counts = res.counts;
      state.app.next_run = res.next_run;
      renderTabs(); renderSubtitle();
      overlay.remove();
      toast('Настройки сохранены');
      loadList();
    } catch (e) { toast(e.message); }
  };
}

// ------------------------------------------------------------------ старт

let searchTimer = null;
$('#search').oninput = (e) => {
  state.search = e.target.value.trim();
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadList, 280);
};
$('#source-filter').onchange = (e) => { state.source = e.target.value; loadList(); };
$('#btn-scan').onclick = () => startScan(!state.app?.last_run);
$('#btn-settings').onclick = () => { if (state.app) openSettings(); };

(async function init() {
  await refreshState();
  await loadList();
})();
