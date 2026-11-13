'use strict';

// подписи вкладок и статусов — в i18n.js (tab.<id>, status.<id>)
const TABS = [
  { id: 'primary',   countKey: 'primary' },
  { id: 'secondary', countKey: 'secondary' },
  { id: 'saved',     countKey: 'saved' },
  { id: 'applied',   countKey: 'applied' },
  { id: 'all',       countKey: 'total' },
  { id: 'hidden',    countKey: 'hidden' },
];

const STATUSES = ['new', 'saved', 'applied', 'interview', 'rejected', 'hidden'];

const SOURCE_LABELS = {
  'work.ua': 'work.ua', 'robota.ua': 'robota.ua', 'djinni.co': 'djinni',
  'dou.ua': 'dou', 'linkedin': 'linkedin',
};

const state = { tab: 'primary', search: '', source: '', sort: loadSort(), period: '', app: null, items: [], polling: null };

function loadSort() {
  try {
    const saved = localStorage.getItem('sort');
    return ['new', 'salary'].includes(saved) ? saved : 'score';
  } catch { return 'score'; }
}

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
  if (!res.ok) {
    const detail = data.detail || data.error;
    // сервер присылает коды вроде «api_key_invalid» — переводим, если знаем
    const known = detail && (I18N[currentLang][`error.${detail}`] || I18N.ru[`error.${detail}`]);
    throw new Error(known ? t(`error.${detail}`) : detail || t('error.http', { status: res.status }));
  }
  return data;
}

function toast(message) {
  document.querySelectorAll('.toast').forEach((node) => node.remove());
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
  if (diff < 3600) return t('time.min', { n: Math.max(1, Math.round(diff / 60)) });
  if (diff < 86400) return t('time.hour', { n: Math.round(diff / 3600) });
  const days = Math.round(diff / 86400);
  if (days < 30) return t('time.day', { n: days });
  return shortDate(iso);
}

function shortDate(iso) {
  return new Date(iso).toLocaleDateString(locale(), { day: 'numeric', month: 'short' });
}

function statusText(item) {
  const label = t(`status.${item.status}`);
  if (!item.applied_at) return label;
  const date = shortDate(item.applied_at);
  return item.status === 'applied' ? `${label} ${date}` : t('status.appliedOn', { status: label, date });
}

function isNew(item) {
  return (Date.now() - new Date(item.first_seen).getTime()) < 36 * 3600 * 1000;
}

// ------------------------------------------------------------------ язык

function applyStaticTexts() {
  document.documentElement.lang = currentLang;
  document.title = t('page.title');
  document.querySelectorAll('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((node) => { node.placeholder = t(node.dataset.i18nPlaceholder); });
  document.querySelectorAll('[data-i18n-title]').forEach((node) => { node.title = t(node.dataset.i18nTitle); });
}

function fillLangSelect() {
  const sel = $('#lang');
  sel.replaceChildren();
  for (const [code, label] of Object.entries(LANGS)) {
    const opt = el('option', null, label);
    opt.value = code;
    sel.append(opt);
  }
  sel.value = currentLang;
}

function setLang(lang) {
  if (!I18N[lang]) return;
  currentLang = lang;
  try { localStorage.setItem('lang', lang); } catch { /* приватный режим */ }
  $('#lang').value = lang;
  applyStaticTexts();
  renderTabs(); renderSubtitle(); renderNotices(); renderProgress();
  if (state.listLoaded) renderList();
}

// ------------------------------------------------------------------ шапка

function renderTabs() {
  const counts = state.app?.counts || {};
  const nav = $('#tabs');
  nav.replaceChildren();
  for (const tab of TABS) {
    const btn = el('button', `tab${state.tab === tab.id ? ' active' : ''}`);
    btn.append(t(`tab.${tab.id}`));
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
  if (app.last_run?.finished_at) parts.push(t('sub.updated', { when: timeAgo(app.last_run.finished_at) }));
  if (app.next_run) {
    const next = new Date(app.next_run);
    parts.push(t('sub.next', { when: next.toLocaleString(locale(), { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' }) }));
  } else {
    parts.push(t('sub.manual'));
  }
  if (app.filtered > 0) parts.push(t('sub.filtered', { n: app.filtered }));
  $('#subtitle').textContent = parts.join(' · ');
  $('#subtitle').title = app.filtered > 0 ? t('sub.filteredTitle') : '';
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
    add('err', t('notice.noKey'), t('notice.noKeyText'));
  }
  if (!app.profile) {
    const hasFile = app.resume_file_present;
    add('warn', t('notice.noResume'),
        hasFile ? t('notice.resumeFile', { file: hasFile }) : t('notice.resumePut'),
        hasFile ? t('notice.parseResume') : null,
        hasFile ? reloadResume : null);
  }
  if (app.last_run && app.last_run.ok === 0 && app.last_run.error === 'api_key_invalid') {
    add('err', t('notice.badKey'), t('notice.badKeyText'),
        t('notice.badKeyRetry'), () => startScan(false));
  } else if (app.last_run && app.last_run.ok === 0 && app.last_run.error) {
    add('err', t('notice.runFailed'), app.last_run.error);
  }
  // с недействительным ключом «Разобрать» ничего не даст — хватает плашки про ключ
  const badKey = app.last_run?.ok === 0 && app.last_run?.error === 'api_key_invalid';
  if (app.unscored > 0 && !app.progress?.running && !badKey) {
    add('info', t('notice.unscored', { n: app.unscored }),
        t('notice.unscoredText', { limit: app.settings?.max_details_per_run ?? 120 }),
        t('notice.unscoredBtn'), () => startScan(false));
  }
  const errs = app.progress?.errors || [];
  if (errs.length && !app.progress.running) {
    add('info', t('notice.sourcesFailed'), errs.join('; '));
  }
}

function renderProgress() {
  const p = state.app?.progress;
  const box = $('#progress');
  const scanBtn = $('#btn-scan');
  if (p?.running) {
    box.hidden = false;
    $('#progress-text').textContent =
      `${t(`progress.${p.stage}`, p.params || {})} · ${t('progress.counters', p)}`;
    scanBtn.disabled = true;
    scanBtn.textContent = t('header.scanning');
    if (!state.polling) state.polling = setInterval(refreshState, 2000);
  } else {
    box.hidden = true;
    scanBtn.disabled = false;
    scanBtn.textContent = t('header.scan');
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

const CEFR = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

// Свой уровень берём из разобранного резюме: languages вроде «English B2» / «Англійська — C1».
function myEnglish() {
  for (const lang of state.app?.profile?.languages || []) {
    if (!/english|англ/i.test(lang)) continue;
    const m = lang.toUpperCase().replace(/А/g, 'A').replace(/В/g, 'B').replace(/С/g, 'C').match(/\b([ABC][12])\b/);
    if (m) return m[1];
    if (/native|рідн|родн/i.test(lang)) return 'C2';
    if (/fluent|advanced|вільн|свободн/i.test(lang)) return 'C1';
    if (/upper/i.test(lang)) return 'B2';
    if (/intermediate/i.test(lang)) return 'B1';
  }
  return null;
}

function englishBadge(level) {
  if (!level) return null;
  if (level === 'none') {
    const b = el('span', 'badge-eng ok', t('card.engNone'));
    b.title = t('card.engNoneTitle');
    return b;
  }
  const mine = myEnglish();
  const fits = mine ? CEFR.indexOf(mine) >= CEFR.indexOf(level) : null;
  const b = el('span', `badge-eng${fits === true ? ' ok' : fits === false ? ' hi' : ''}`, `EN ${level}`);
  b.title = t('card.engTitle', { level })
    + (mine ? ' · ' + t(fits ? 'card.engFits' : 'card.engAbove', { mine }) : '');
  return b;
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
  if (item.salary_raw) title.append(' ', el('span', 'badge-salary', item.salary_raw));
  const eng = englishBadge(item.english);
  if (eng) title.append(' ', eng);
  if (isNew(item)) title.append(' ', el('span', 'badge-new', t('card.new')));

  const meta = el('div', 'meta');
  if (item.company) meta.append(el('span', 'company', item.company));
  if (item.location) meta.append(el('span', null, item.location));
  meta.append(el('span', 'src', SOURCE_LABELS[item.source] || item.source));
  const when = item.posted_at || item.first_seen;
  if (when) meta.append(el('span', null, timeAgo(when)));
  const statusChip = el('span', 'chip');
  const renderStatusChip = () => {
    statusChip.textContent = statusText(item);
    if (item.status && item.status !== 'new') meta.append(statusChip);
    else statusChip.remove();
  };
  renderStatusChip();

  main.append(title, meta);
  if (item.summary) main.append(el('p', 'summary', item.summary));

  head.append(score, main);
  card.append(head);

  const b = item.breakdown || {};
  if (Object.keys(b).length) {
    const bars = el('div', 'bars');
    bars.append(
      barRow(t('card.skills'), b.skills ?? 0),
      barRow(t('card.experience'), b.experience ?? 0),
      barRow(t('card.conditions'), b.conditions ?? 0),
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
    item.has_letter ? t('card.letterReady') : t('card.letter'));
  letterBtn.onclick = () => openLetter(item, letterBtn);
  actions.append(letterBtn);

  const openBtn = el('button', 'btn sm', t('card.open'));
  openBtn.onclick = () => window.open(item.url, '_blank', 'noopener');
  actions.append(openBtn);

  const statusSel = el('select');
  statusSel.className = 'btn sm';
  for (const value of STATUSES) {
    const opt = el('option', null, t(`status.${value}`));
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
      item.status = statusSel.value;
      item.applied_at = res.applied_at ?? null;
      renderStatusChip();
      renderTabs();
      toast(t('status.toast', { status: t(`status.${statusSel.value}`) }));
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
    const tab = t(`tab.${state.tab}`);
    empty.append(el('h3', null, t('empty.title')));
    if (!state.app?.profile) {
      empty.append(el('p', null, t('empty.noResume')));
    } else if (!state.app?.last_run) {
      empty.append(el('p', null, t('empty.noRun')));
      const btn = el('button', 'btn primary', t('empty.firstRun'));
      btn.onclick = () => startScan(true);
      empty.append(btn);
    } else if (state.period) {
      empty.append(el('p', null, state.period === '1'
        ? t('empty.period1', { tab })
        : t('empty.periodN', { tab, days: state.period })));
    } else {
      empty.append(el('p', null, t('empty.tab', { tab })));
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
    const first = !state.app;
    state.app = await api('/api/state');
    // язык хранится в настройках на сервере; localStorage нужен только для первой отрисовки
    const serverLang = state.app.settings?.ui_lang;
    if (first && serverLang && serverLang !== currentLang) setLang(serverLang);
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
  if (state.sort !== 'score') params.set('sort', state.sort);
  if (state.period) {
    // считаем календарными днями: «за 3 дня» — сегодня и два предыдущих дня
    const since = new Date();
    since.setHours(0, 0, 0, 0);
    since.setDate(since.getDate() - (Number(state.period) - 1));
    params.set('since', since.toISOString());
  }
  try {
    const data = await api(`/api/vacancies?${params}`);
    state.items = data.items;
    state.listLoaded = true;
    renderList();
  } catch (e) { toast(e.message); }
}

async function startScan(firstRun) {
  try {
    await api(`/api/scan?first_run=${firstRun ? 'true' : 'false'}`, { method: 'POST' });
    toast(firstRun ? t('scan.first') : t('scan.started'));
    setTimeout(refreshState, 600);
  } catch (e) { toast(e.message); }
}

async function reloadResume() {
  toast(t('resume.parsing'));
  try {
    const res = await api('/api/resume/reload', { method: 'POST' });
    toast(t('resume.parsed', { headline: res.profile.headline }));
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
  const letter = el('div', 'letter', t('letter.writing'));
  body.append(letter);

  const copyBtn = el('button', 'btn primary', t('letter.copy'));
  const againBtn = el('button', 'btn', t('letter.again'));
  const overlay = modal({
    title: item.title,
    body,
    footer: [againBtn, copyBtn],
  });

  const load = async (regenerate) => {
    letter.textContent = regenerate ? t('letter.rewriting') : t('letter.writing');
    try {
      const res = await api(`/api/vacancies/${item.id}/cover`, {
        method: 'POST', body: JSON.stringify({ regenerate }),
      });
      letter.textContent = res.text;
      item.has_letter = true;
      if (button) button.textContent = t('card.letterReady');
    } catch (e) {
      letter.textContent = t('letter.failed', { message: e.message });
    }
  };

  copyBtn.onclick = async () => {
    try {
      await navigator.clipboard.writeText(letter.textContent);
      toast(t('letter.copied'));
    } catch { toast(t('letter.copyFailed')); }
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
  sectionTitle(t('set.whatSection'));
  const queries = el('textarea');
  queries.value = (s.queries || []).join('\n');
  queries.placeholder = 'Python Developer\nBackend Engineer';
  add(field(t('set.queries'), queries, t('set.queriesHint')));

  const exclude = textInput((s.exclude_keywords || []).join(', '), t('set.excludePh'));
  add(field(t('set.exclude'), exclude, t('set.excludeHint')));

  // --- условия ---
  sectionTitle(t('set.conditionsSection'));
  const formats = el('div', 'checks');
  for (const value of ['remote', 'hybrid', 'office']) {
    const label = t(`fmt.${value}`);
    const lab = el('label', 'check');
    const cb = el('input'); cb.type = 'checkbox'; cb.value = value;
    cb.checked = (s.work_formats || []).includes(value);
    lab.append(cb, el('span', null, label));
    formats.append(lab);
  }
  add(field(t('set.format'), formats, t('set.formatHint')));

  const cities = textInput((s.cities || []).join(', '), 'Київ, Львів');
  add(field(t('set.cities'), cities, t('set.citiesHint')));

  const money = el('div', 'row2');
  const salary = el('input'); salary.type = 'number'; salary.value = s.min_salary || 0; salary.min = 0;
  const currency = el('select');
  ['USD', 'UAH'].forEach((c) => {
    const opt = el('option', null, c); opt.value = c;
    if (c === s.salary_currency) opt.selected = true;
    currency.append(opt);
  });
  money.append(salary, currency);
  add(field(t('set.salary'), money, t('set.salaryHint')));

  // --- отбор ---
  sectionTitle(t('set.selectionSection'));
  const sliderWrap = el('div', 'slider-row');
  const slider = el('input');
  slider.type = 'range'; slider.min = 40; slider.max = 95; slider.step = 5; slider.value = s.threshold;
  const out = el('output', null, `${s.threshold}%`);
  slider.oninput = () => { out.textContent = `${slider.value}%`; };
  sliderWrap.append(slider, out);
  add(field(t('set.threshold'), sliderWrap, t('set.thresholdHint')));

  const weightsBox = el('div', 'row2');
  const weightInputs = {};
  const weightLabels = { skills: t('card.skills'), experience: t('card.experience'),
                         conditions: t('card.conditions'), domain: t('set.domain') };
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
  add(field(t('set.weights'), weightsBox, t('set.weightsHint')));

  // --- источники ---
  sectionTitle(t('set.sourcesSection'));
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
  add(field(t('set.where'), sources, t('set.whereHint')));

  const pages = el('input');
  pages.type = 'number'; pages.min = 1; pages.max = 10; pages.value = s.max_pages_per_query;
  add(field(t('set.pages'), pages, t('set.pagesHint')));

  const perRun = el('input');
  perRun.type = 'number'; perRun.min = 10; perRun.max = 1000; perRun.step = 10;
  perRun.value = s.max_details_per_run;
  add(field(t('set.perRun'), perRun,
    t('set.perRunHint') + (state.app.unscored ? t('set.perRunPending', { n: state.app.unscored }) : '')));

  // --- расписание ---
  sectionTitle(t('set.updateSection'));
  const auto = el('label', 'check');
  const autoCb = el('input'); autoCb.type = 'checkbox'; autoCb.checked = !!s.auto_schedule;
  auto.append(autoCb, el('span', null, t('set.auto')));
  add(field(t('set.autoField'), auto, t('set.autoHint')));

  const timeInput = el('input');
  timeInput.type = 'text'; timeInput.value = s.schedule_time; timeInput.placeholder = '09:00';
  const timeField = field(t('set.time'), timeInput, t('set.timeHint'));
  timeField.hidden = !autoCb.checked;
  autoCb.onchange = () => { timeField.hidden = !autoCb.checked; };
  add(timeField);

  const notify = el('label', 'check');
  const notifyCb = el('input'); notifyCb.type = 'checkbox'; notifyCb.checked = !!s.notify_macos;
  notify.append(notifyCb, el('span', null, t('set.notify')));
  add(field(t('set.notifyField'), notify));

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
  m1.append(el('label', null, t('set.modelScoring')), scoringModel);
  const m2 = el('div', 'field'); m2.style.margin = '0';
  m2.append(el('label', null, t('set.modelLetters')), letterModel);
  models.append(m1, m2);
  add(field(t('set.models'), models, t('set.modelsHint')));

  // --- сохранение ---
  const saveBtn = el('button', 'btn primary', t('set.save'));
  const resumeBtn = el('button', 'btn', t('set.reloadResume'));
  const overlay = modal({ title: t('set.title'), body, footer: [resumeBtn, saveBtn] });

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
      max_details_per_run: Math.min(1000, Math.max(10, Number(perRun.value) || 120)),
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
      state.app.unscored = res.unscored;
      state.app.filtered = res.filtered;
      renderTabs(); renderSubtitle(); renderNotices();
      overlay.remove();
      toast(t('set.saved'));
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
$('#period').onchange = (e) => { state.period = e.target.value; loadList(); };
$('#sort').value = state.sort;
$('#sort').onchange = (e) => {
  state.sort = e.target.value;
  try { localStorage.setItem('sort', state.sort); } catch { /* приватный режим */ }
  loadList();
};
$('#btn-scan').onclick = () => startScan(!state.app?.last_run);
$('#btn-settings').onclick = () => { if (state.app) openSettings(); };
$('#lang').onchange = async (e) => {
  setLang(e.target.value);
  try {
    const res = await api('/api/settings', { method: 'POST', body: JSON.stringify({ ui_lang: currentLang }) });
    state.app.settings = res.settings;
  } catch (err) { toast(err.message); }
};

fillLangSelect();
applyStaticTexts();

(async function init() {
  await refreshState();
  await loadList();
})();
