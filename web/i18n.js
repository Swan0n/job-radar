'use strict';

// Тексты интерфейса на трёх языках. Строка может содержать подстановки {name};
// если текст зависит от числа, значение — функция, которая сама выбирает форму.

const LANGS = { ru: 'RU', uk: 'UA', en: 'EN' };
const LOCALES = { ru: 'ru-RU', uk: 'uk-UA', en: 'en-GB' };

// формы по Intl.PluralRules: one / few / many / other
function plural(lang, n, forms) {
  const kind = new Intl.PluralRules(LOCALES[lang]).select(n);
  return (forms[kind] ?? forms.other).replace('{n}', n);
}

const I18N = {
  ru: {
    'page.title': 'Job Radar — вакансии под твоё резюме',
    'tab.primary': 'Подходящие', 'tab.secondary': 'Почти', 'tab.saved': 'Избранное',
    'tab.applied': 'Отклики', 'tab.all': 'Все', 'tab.hidden': 'Скрытые',
    'status.new': 'Новая', 'status.saved': 'В избранном', 'status.applied': 'Откликнулся',
    'status.interview': 'Собеседование', 'status.rejected': 'Отказ', 'status.hidden': 'Скрыта',
    'status.toast': 'Статус: {status}',
    'status.appliedOn': '{status} · отклик {date}',

    'header.settings': 'Настройки', 'header.scan': 'Обновить сейчас', 'header.scanning': 'Идёт обновление…',
    'header.lang': 'Язык интерфейса',
    'toolbar.search': 'Поиск по названию, компании и описанию…',
    'toolbar.allSources': 'Все источники',
    'period.all': 'За всё время', 'period.1': 'За сегодня', 'period.3': 'За 3 дня', 'period.7': 'За 7 дней',
    'sort.score': 'По совпадению', 'sort.new': 'Сначала новые', 'sort.salary': 'По зарплате',

    'time.min': '{n} мин назад', 'time.hour': '{n} ч назад', 'time.day': '{n} дн назад',
    'sub.filtered': 'отсеяно фильтром: {n}',
    'sub.filteredTitle': 'Вакансии, которые предфильтр не пустил к оценке: стоп-слова, нет профильных слов в названии, не тот грейд. Токены на них не тратятся.',
    'sub.updated': 'обновлено {when}', 'sub.next': 'следующее {when}', 'sub.manual': 'обновление вручную',

    'notice.noKey': 'Нет ключа Claude API',
    'notice.noKeyText': 'Впиши ANTHROPIC_API_KEY в файл .env в папке проекта и перезапусти сервис.',
    'notice.noResume': 'Резюме не загружено',
    'notice.resumeFile': 'Файл {file} лежит в папке resume/ — осталось его разобрать.',
    'notice.resumePut': 'Положи PDF или DOCX в папку resume/ рядом с проектом.',
    'notice.parseResume': 'Разобрать резюме',
    'notice.runFailed': 'Прошлый прогон не удался',
    'notice.badKey': 'Ключ Claude API недействителен',
    'notice.badKeyText': 'Anthropic отклонил ключ из файла .env (ошибка 401), прогон остановлен. Создай новый ключ в Console (Settings → API keys), вставь его целиком в .env как ANTHROPIC_API_KEY=<ключ> и нажми «Проверить снова» — перезапускать сервер не нужно.',
    'notice.badKeyRetry': 'Проверить снова',
    'error.api_key_invalid': 'Ключ Claude API недействителен — проверь ANTHROPIC_API_KEY в файле .env.',
    'notice.unscored': (p) => plural('ru', p.n, {
      one: 'Ещё {n} вакансия ждёт оценки', few: 'Ещё {n} вакансии ждут оценки', other: 'Ещё {n} вакансий ждут оценки' }),
    'notice.unscoredText': 'За один прогон оценивается не больше {limit} вакансий, чтобы не жечь токены. Нажми «Разобрать» или увеличь лимит в настройках.',
    'notice.unscoredBtn': 'Разобрать',
    'notice.sourcesFailed': 'Часть запросов не удалась',

    'progress.idle': 'ожидание',
    'progress.browser': 'запуск браузера для сайтов за Cloudflare',
    'progress.collect': 'сбор: {source}, «{query}», страница {page}',
    'progress.save': (p) => plural('ru', p.n, {
      one: 'сохранение: {n} вакансия', few: 'сохранение: {n} вакансии', other: 'сохранение: {n} вакансий' }),
    'progress.details': (p) => plural('ru', p.n, {
      one: 'загрузка описаний: {n} вакансия', few: 'загрузка описаний: {n} вакансии', other: 'загрузка описаний: {n} вакансий' }),
    'progress.score': 'оценка: {done} из {total}',
    'progress.done': 'готово: оценено {scored}, подходящих {good}',
    'progress.error': 'ошибка: {message}',
    'progress.error_key': 'ключ Claude API недействителен',
    'progress.counters': 'найдено {found}, оценено {scored}',

    'card.new': 'новое',
    'card.engTitle': 'Требуемый английский: {level}', 'card.engFits': 'у тебя {mine} — хватает',
    'card.engAbove': 'у тебя {mine} — требуют выше', 'card.engNone': 'EN не нужен',
    'card.engNoneTitle': 'Работодатель указал, что английский не требуется',
    'card.skills': 'Навыки и стек', 'card.experience': 'Опыт и грейд', 'card.conditions': 'Условия',
    'card.letter': 'Кавер-леттер', 'card.letterReady': 'Письмо готово', 'card.open': 'Открыть вакансию',

    'empty.title': 'Пока пусто',
    'empty.noResume': 'Сначала загрузи резюме — по нему считается совпадение.',
    'empty.noRun': 'Первый сбор ещё не запускался. Он займёт 10–20 минут и соберёт вакансии за 30 дней.',
    'empty.firstRun': 'Запустить первый сбор',
    'empty.period1': 'На вкладке «{tab}» нет вакансий, найденных сегодня. Выбери «За всё время», чтобы увидеть остальные.',
    'empty.periodN': 'На вкладке «{tab}» нет вакансий за последние {days} дн. Выбери «За всё время», чтобы увидеть остальные.',
    'empty.tab': 'На вкладке «{tab}» ничего нет. Попробуй снизить порог в настройках или добавить поисковые запросы.',

    'scan.first': 'Первый сбор запущен — это надолго', 'scan.started': 'Обновление запущено',
    'resume.parsing': 'Разбираю резюме…', 'resume.parsed': 'Резюме разобрано: {headline}',
    'error.http': 'Ошибка {status}',

    'letter.writing': 'Пишу письмо под эту вакансию…', 'letter.rewriting': 'Переписываю…',
    'letter.copy': 'Скопировать', 'letter.again': 'Написать заново', 'letter.failed': 'Не получилось: {message}',
    'letter.copied': 'Письмо скопировано', 'letter.copyFailed': 'Не вышло скопировать — выдели текст вручную',

    'set.title': 'Настройки', 'set.save': 'Сохранить', 'set.saved': 'Настройки сохранены', 'set.reloadResume': 'Перечитать резюме',
    'set.whatSection': 'Что искать',
    'set.queries': 'Поисковые запросы, по одному в строке',
    'set.queriesHint': 'Их вводят в поиск на джоб-бордах. Если оставить пусто, возьму роли из резюме.',
    'set.exclude': 'Стоп-слова в названии, через запятую', 'set.excludePh': '1С, продажи, стажер',
    'set.excludeHint': 'Вакансии с этими словами в названии даже не оцениваются.',
    'set.conditionsSection': 'Условия работы',
    'fmt.remote': 'Удалённо', 'fmt.hybrid': 'Гибрид', 'fmt.office': 'Офис',
    'set.format': 'Формат работы', 'set.formatHint': 'Не подходящий формат сильно снижает процент, но вакансию не прячет.',
    'set.cities': 'Города, через запятую', 'set.citiesHint': 'Для удалённых вакансий город не учитывается.',
    'set.salary': 'Зарплатный ориентир', 'set.salaryHint': 'Мягкий фильтр: вакансии ниже опускаются в списке, но остаются видимыми.',
    'set.selectionSection': 'Отбор',
    'set.threshold': 'Порог «подходит»',
    'set.thresholdHint': 'Вакансии выше порога попадают на первую вкладку, от 50% до порога — на вторую.',
    'set.domain': 'Домен', 'set.weights': 'Веса измерений', 'set.weightsHint': 'Приводятся к сумме 100 автоматически.',
    'set.sourcesSection': 'Источники', 'set.where': 'Где искать',
    'set.whereHint': 'work.ua и robota.ua требуют браузера и работают медленнее. LinkedIn — неофициальный публичный поиск, может отвалиться.',
    'set.pages': 'Страниц на запрос', 'set.pagesHint': 'Больше страниц — глубже охват и дольше прогон.',
    'set.perRun': 'Вакансий на оценку за прогон',
    'set.perRunHint': 'Сколько вакансий за одно обновление загружать и оценивать моделью. Больше — меньше нажатий «Обновить», но дольше прогон и больше токенов (100 вакансий — примерно 0,25–0,50 $ на Sonnet).',
    'set.perRunPending': ' Сейчас ждут оценки: {n}.',
    'set.updateSection': 'Обновление и модели',
    'set.auto': 'Обновлять автоматически каждый день', 'set.autoField': 'Режим обновления',
    'set.autoHint': 'Выключено — вакансии собираются и оцениваются только по кнопке «Обновить сейчас», и токены без спроса не тратятся.',
    'set.time': 'Время ежедневного обновления (Киев)',
    'set.timeHint': 'Если Mac в это время спал, обновление догонится при следующем запуске.',
    'set.notify': 'Уведомление macOS, когда обновление нашло новые вакансии', 'set.notifyField': 'Уведомления',
    'set.modelScoring': 'Оценка вакансий', 'set.modelLetters': 'Кавер-леттеры', 'set.models': 'Модели Claude',
    'set.modelsHint': 'Оценка — самая массовая операция. Sonnet заметно дешевле Opus, качество разбора чуть ниже.',
  },

  uk: {
    'page.title': 'Job Radar — вакансії під твоє резюме',
    'tab.primary': 'Підходять', 'tab.secondary': 'Майже', 'tab.saved': 'Обране',
    'tab.applied': 'Відгуки', 'tab.all': 'Усі', 'tab.hidden': 'Приховані',
    'status.new': 'Нова', 'status.saved': 'В обраному', 'status.applied': 'Відгукнувся',
    'status.interview': 'Співбесіда', 'status.rejected': 'Відмова', 'status.hidden': 'Прихована',
    'status.toast': 'Статус: {status}',
    'status.appliedOn': '{status} · відгук {date}',

    'header.settings': 'Налаштування', 'header.scan': 'Оновити зараз', 'header.scanning': 'Оновлення триває…',
    'header.lang': 'Мова інтерфейсу',
    'toolbar.search': 'Пошук за назвою, компанією та описом…',
    'toolbar.allSources': 'Усі джерела',
    'period.all': 'За весь час', 'period.1': 'За сьогодні', 'period.3': 'За 3 дні', 'period.7': 'За 7 днів',
    'sort.score': 'За збігом', 'sort.new': 'Спочатку нові', 'sort.salary': 'За зарплатою',

    'time.min': '{n} хв тому', 'time.hour': '{n} год тому', 'time.day': '{n} дн тому',
    'sub.filtered': 'відсіяно фільтром: {n}',
    'sub.filteredTitle': 'Вакансії, які фільтр не пустив до оцінки: стоп-слова, немає профільних слів у назві, не той грейд. Токени на них не витрачаються.',
    'sub.updated': 'оновлено {when}', 'sub.next': 'наступне {when}', 'sub.manual': 'оновлення вручну',

    'notice.noKey': 'Немає ключа Claude API',
    'notice.noKeyText': 'Впиши ANTHROPIC_API_KEY у файл .env у папці проєкту й перезапусти сервіс.',
    'notice.noResume': 'Резюме не завантажене',
    'notice.resumeFile': 'Файл {file} лежить у папці resume/ — лишилося його розібрати.',
    'notice.resumePut': 'Поклади PDF або DOCX у папку resume/ поруч із проєктом.',
    'notice.parseResume': 'Розібрати резюме',
    'notice.runFailed': 'Минулий прогін не вдався',
    'notice.badKey': 'Ключ Claude API недійсний',
    'notice.badKeyText': 'Anthropic відхилив ключ із файлу .env (помилка 401), прогін зупинено. Створи новий ключ у Console (Settings → API keys), встав його повністю в .env як ANTHROPIC_API_KEY=<ключ> і натисни «Перевірити знову» — перезапускати сервер не потрібно.',
    'notice.badKeyRetry': 'Перевірити знову',
    'error.api_key_invalid': 'Ключ Claude API недійсний — перевір ANTHROPIC_API_KEY у файлі .env.',
    'notice.unscored': (p) => plural('uk', p.n, {
      one: 'Ще {n} вакансія чекає оцінки', few: 'Ще {n} вакансії чекають оцінки', other: 'Ще {n} вакансій чекають оцінки' }),
    'notice.unscoredText': 'За один прогін оцінюється не більше {limit} вакансій, щоб не палити токени. Натисни «Розібрати» або збільш ліміт у налаштуваннях.',
    'notice.unscoredBtn': 'Розібрати',
    'notice.sourcesFailed': 'Частина запитів не вдалася',

    'progress.idle': 'очікування',
    'progress.browser': 'запуск браузера для сайтів за Cloudflare',
    'progress.collect': 'збір: {source}, «{query}», сторінка {page}',
    'progress.save': (p) => plural('uk', p.n, {
      one: 'збереження: {n} вакансія', few: 'збереження: {n} вакансії', other: 'збереження: {n} вакансій' }),
    'progress.details': (p) => plural('uk', p.n, {
      one: 'завантаження описів: {n} вакансія', few: 'завантаження описів: {n} вакансії', other: 'завантаження описів: {n} вакансій' }),
    'progress.score': 'оцінка: {done} з {total}',
    'progress.done': 'готово: оцінено {scored}, підходять {good}',
    'progress.error': 'помилка: {message}',
    'progress.error_key': 'ключ Claude API недійсний',
    'progress.counters': 'знайдено {found}, оцінено {scored}',

    'card.new': 'нове',
    'card.engTitle': 'Потрібна англійська: {level}', 'card.engFits': 'у тебе {mine} — достатньо',
    'card.engAbove': 'у тебе {mine} — вимагають вище', 'card.engNone': 'EN не потрібна',
    'card.engNoneTitle': 'Роботодавець вказав, що англійська не потрібна',
    'card.skills': 'Навички та стек', 'card.experience': 'Досвід і грейд', 'card.conditions': 'Умови',
    'card.letter': 'Супровідний лист', 'card.letterReady': 'Лист готовий', 'card.open': 'Відкрити вакансію',

    'empty.title': 'Поки порожньо',
    'empty.noResume': 'Спершу завантаж резюме — за ним рахується збіг.',
    'empty.noRun': 'Перший збір ще не запускався. Він займе 10–20 хвилин і збере вакансії за 30 днів.',
    'empty.firstRun': 'Запустити перший збір',
    'empty.period1': 'На вкладці «{tab}» немає вакансій, знайдених сьогодні. Обери «За весь час», щоб побачити решту.',
    'empty.periodN': 'На вкладці «{tab}» немає вакансій за останні {days} дн. Обери «За весь час», щоб побачити решту.',
    'empty.tab': 'На вкладці «{tab}» нічого немає. Спробуй знизити поріг у налаштуваннях або додати пошукові запити.',

    'scan.first': 'Перший збір запущено — це надовго', 'scan.started': 'Оновлення запущено',
    'resume.parsing': 'Розбираю резюме…', 'resume.parsed': 'Резюме розібране: {headline}',
    'error.http': 'Помилка {status}',

    'letter.writing': 'Пишу лист під цю вакансію…', 'letter.rewriting': 'Переписую…',
    'letter.copy': 'Скопіювати', 'letter.again': 'Написати заново', 'letter.failed': 'Не вийшло: {message}',
    'letter.copied': 'Лист скопійовано', 'letter.copyFailed': 'Не вдалося скопіювати — виділи текст вручну',

    'set.title': 'Налаштування', 'set.save': 'Зберегти', 'set.saved': 'Налаштування збережено', 'set.reloadResume': 'Перечитати резюме',
    'set.whatSection': 'Що шукати',
    'set.queries': 'Пошукові запити, по одному в рядку',
    'set.queriesHint': 'Їх вводять у пошук на джоб-бордах. Якщо лишити порожнім, візьму ролі з резюме.',
    'set.exclude': 'Стоп-слова в назві, через кому', 'set.excludePh': '1С, продажі, стажер',
    'set.excludeHint': 'Вакансії з цими словами в назві навіть не оцінюються.',
    'set.conditionsSection': 'Умови роботи',
    'fmt.remote': 'Віддалено', 'fmt.hybrid': 'Гібрид', 'fmt.office': 'Офіс',
    'set.format': 'Формат роботи', 'set.formatHint': 'Невідповідний формат сильно знижує відсоток, але вакансію не ховає.',
    'set.cities': 'Міста, через кому', 'set.citiesHint': 'Для віддалених вакансій місто не враховується.',
    'set.salary': 'Зарплатний орієнтир', 'set.salaryHint': "М'який фільтр: нижчі вакансії опускаються в списку, але лишаються видимими.",
    'set.selectionSection': 'Відбір',
    'set.threshold': 'Поріг «підходить»',
    'set.thresholdHint': 'Вакансії вище порогу потрапляють на першу вкладку, від 50% до порогу — на другу.',
    'set.domain': 'Домен', 'set.weights': 'Ваги вимірів', 'set.weightsHint': 'Автоматично зводяться до суми 100.',
    'set.sourcesSection': 'Джерела', 'set.where': 'Де шукати',
    'set.whereHint': 'work.ua і robota.ua потребують браузера й працюють повільніше. LinkedIn — неофіційний публічний пошук, може відвалитися.',
    'set.pages': 'Сторінок на запит', 'set.pagesHint': 'Більше сторінок — глибше охоплення й довший прогін.',
    'set.perRun': 'Вакансій на оцінку за прогін',
    'set.perRunHint': 'Скільки вакансій за одне оновлення завантажувати й оцінювати моделлю. Більше — менше натискань «Оновити», але довший прогін і більше токенів (100 вакансій — приблизно 0,25–0,50 $ на Sonnet).',
    'set.perRunPending': ' Зараз чекають оцінки: {n}.',
    'set.updateSection': 'Оновлення та моделі',
    'set.auto': 'Оновлювати автоматично щодня', 'set.autoField': 'Режим оновлення',
    'set.autoHint': 'Вимкнено — вакансії збираються й оцінюються лише кнопкою «Оновити зараз», і токени без потреби не витрачаються.',
    'set.time': 'Час щоденного оновлення (Київ)',
    'set.timeHint': 'Якщо Mac у цей час спав, оновлення наздожене при наступному запуску.',
    'set.notify': 'Сповіщення macOS, коли оновлення знайшло нові вакансії', 'set.notifyField': 'Сповіщення',
    'set.modelScoring': 'Оцінка вакансій', 'set.modelLetters': 'Супровідні листи', 'set.models': 'Моделі Claude',
    'set.modelsHint': 'Оцінка — наймасовіша операція. Sonnet помітно дешевший за Opus, якість розбору трохи нижча.',
  },

  en: {
    'page.title': 'Job Radar — jobs that fit your resume',
    'tab.primary': 'Good fit', 'tab.secondary': 'Almost', 'tab.saved': 'Saved',
    'tab.applied': 'Applied', 'tab.all': 'All', 'tab.hidden': 'Hidden',
    'status.new': 'New', 'status.saved': 'Saved', 'status.applied': 'Applied',
    'status.interview': 'Interview', 'status.rejected': 'Rejected', 'status.hidden': 'Hidden',
    'status.toast': 'Status: {status}',
    'status.appliedOn': '{status} · applied {date}',

    'header.settings': 'Settings', 'header.scan': 'Update now', 'header.scanning': 'Updating…',
    'header.lang': 'Interface language',
    'toolbar.search': 'Search title, company and description…',
    'toolbar.allSources': 'All sources',
    'period.all': 'All time', 'period.1': 'Today', 'period.3': 'Last 3 days', 'period.7': 'Last 7 days',
    'sort.score': 'Best match', 'sort.new': 'Newest first', 'sort.salary': 'Highest salary',

    'time.min': '{n} min ago', 'time.hour': '{n} h ago', 'time.day': '{n} d ago',
    'sub.filtered': 'filtered out: {n}',
    'sub.filteredTitle': 'Jobs the pre-filter kept from scoring: stop words, no relevant words in the title, wrong level. No tokens are spent on them.',
    'sub.updated': 'updated {when}', 'sub.next': 'next {when}', 'sub.manual': 'manual updates',

    'notice.noKey': 'No Claude API key',
    'notice.noKeyText': 'Put ANTHROPIC_API_KEY into the .env file in the project folder and restart the service.',
    'notice.noResume': 'Resume not loaded',
    'notice.resumeFile': '{file} is in the resume/ folder — it just needs to be parsed.',
    'notice.resumePut': 'Put a PDF or DOCX into the resume/ folder next to the project.',
    'notice.parseResume': 'Parse resume',
    'notice.runFailed': 'Last run failed',
    'notice.badKey': 'Claude API key is invalid',
    'notice.badKeyText': 'Anthropic rejected the key from the .env file (error 401), so the run was stopped. Create a new key in the Console (Settings → API keys), paste it whole into .env as ANTHROPIC_API_KEY=<key> and press “Check again” — no server restart needed.',
    'notice.badKeyRetry': 'Check again',
    'error.api_key_invalid': 'Claude API key is invalid — check ANTHROPIC_API_KEY in the .env file.',
    'notice.unscored': (p) => plural('en', p.n, {
      one: '{n} more job is waiting to be scored', other: '{n} more jobs are waiting to be scored' }),
    'notice.unscoredText': 'Each run scores at most {limit} jobs to save tokens. Press “Score” or raise the limit in settings.',
    'notice.unscoredBtn': 'Score',
    'notice.sourcesFailed': 'Some requests failed',

    'progress.idle': 'idle',
    'progress.browser': 'starting the browser for Cloudflare-protected sites',
    'progress.collect': 'collecting: {source}, “{query}”, page {page}',
    'progress.save': (p) => plural('en', p.n, { one: 'saving: {n} job', other: 'saving: {n} jobs' }),
    'progress.details': (p) => plural('en', p.n, {
      one: 'loading descriptions: {n} job', other: 'loading descriptions: {n} jobs' }),
    'progress.score': 'scoring: {done} of {total}',
    'progress.done': 'done: scored {scored}, good fit {good}',
    'progress.error': 'error: {message}',
    'progress.error_key': 'Claude API key is invalid',
    'progress.counters': 'found {found}, scored {scored}',

    'card.new': 'new',
    'card.engTitle': 'Required English: {level}', 'card.engFits': 'yours is {mine} — enough',
    'card.engAbove': 'yours is {mine} — they want more', 'card.engNone': 'No English',
    'card.engNoneTitle': 'The employer says English is not required',
    'card.skills': 'Skills & stack', 'card.experience': 'Experience & level', 'card.conditions': 'Conditions',
    'card.letter': 'Cover letter', 'card.letterReady': 'Letter ready', 'card.open': 'Open job',

    'empty.title': 'Nothing here yet',
    'empty.noResume': 'Load your resume first — matching is based on it.',
    'empty.noRun': 'The first collection has not run yet. It takes 10–20 minutes and gathers jobs from the last 30 days.',
    'empty.firstRun': 'Start first collection',
    'empty.period1': 'No jobs found today on the “{tab}” tab. Choose “All time” to see the rest.',
    'empty.periodN': 'No jobs from the last {days} days on the “{tab}” tab. Choose “All time” to see the rest.',
    'empty.tab': 'Nothing on the “{tab}” tab. Try lowering the threshold in settings or adding search queries.',

    'scan.first': 'First collection started — this will take a while', 'scan.started': 'Update started',
    'resume.parsing': 'Parsing resume…', 'resume.parsed': 'Resume parsed: {headline}',
    'error.http': 'Error {status}',

    'letter.writing': 'Writing a letter for this job…', 'letter.rewriting': 'Rewriting…',
    'letter.copy': 'Copy', 'letter.again': 'Rewrite', 'letter.failed': 'Failed: {message}',
    'letter.copied': 'Letter copied', 'letter.copyFailed': 'Could not copy — select the text manually',

    'set.title': 'Settings', 'set.save': 'Save', 'set.saved': 'Settings saved', 'set.reloadResume': 'Re-read resume',
    'set.whatSection': 'What to search',
    'set.queries': 'Search queries, one per line',
    'set.queriesHint': 'They are typed into job board search. Leave empty to use roles from the resume.',
    'set.exclude': 'Stop words in the title, comma-separated', 'set.excludePh': '1C, sales, intern',
    'set.excludeHint': 'Jobs with these words in the title are not even scored.',
    'set.conditionsSection': 'Working conditions',
    'fmt.remote': 'Remote', 'fmt.hybrid': 'Hybrid', 'fmt.office': 'Office',
    'set.format': 'Work format', 'set.formatHint': 'A non-matching format lowers the score a lot but does not hide the job.',
    'set.cities': 'Cities, comma-separated', 'set.citiesHint': 'City is ignored for remote jobs.',
    'set.salary': 'Salary target', 'set.salaryHint': 'Soft filter: lower-paid jobs drop down the list but stay visible.',
    'set.selectionSection': 'Selection',
    'set.threshold': '“Good fit” threshold',
    'set.thresholdHint': 'Jobs above the threshold go to the first tab, from 50% up to the threshold — to the second.',
    'set.domain': 'Domain', 'set.weights': 'Dimension weights', 'set.weightsHint': 'Normalized to a total of 100 automatically.',
    'set.sourcesSection': 'Sources', 'set.where': 'Where to search',
    'set.whereHint': 'work.ua and robota.ua need a browser and are slower. LinkedIn is an unofficial public search and may break.',
    'set.pages': 'Pages per query', 'set.pagesHint': 'More pages — wider coverage and a longer run.',
    'set.perRun': 'Jobs to score per run',
    'set.perRunHint': 'How many jobs one update loads and scores with the model. More means fewer “Update” clicks, but a longer run and more tokens (100 jobs ≈ $0.25–0.50 on Sonnet).',
    'set.perRunPending': ' Waiting to be scored now: {n}.',
    'set.updateSection': 'Updates & models',
    'set.auto': 'Update automatically every day', 'set.autoField': 'Update mode',
    'set.autoHint': 'Off — jobs are collected and scored only with the “Update now” button, so no tokens are spent unasked.',
    'set.time': 'Daily update time (Kyiv)',
    'set.timeHint': 'If the Mac was asleep at that time, the update catches up on the next start.',
    'set.notify': 'macOS notification when an update finds new jobs', 'set.notifyField': 'Notifications',
    'set.modelScoring': 'Job scoring', 'set.modelLetters': 'Cover letters', 'set.models': 'Claude models',
    'set.modelsHint': 'Scoring is the bulk operation. Sonnet is noticeably cheaper than Opus, with slightly lower quality.',
  },
};

let currentLang = (() => {
  try {
    const saved = localStorage.getItem('lang');
    if (saved && I18N[saved]) return saved;
  } catch { /* приватный режим */ }
  return 'ru';
})();

function t(key, params = {}) {
  const value = I18N[currentLang][key] ?? I18N.ru[key] ?? key;
  const text = typeof value === 'function' ? value(params) : value;
  return text.replace(/\{(\w+)\}/g, (m, name) => (name in params ? params[name] : m));
}

function locale() {
  return LOCALES[currentLang];
}
