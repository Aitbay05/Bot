# Help Counter Bot — Production Audit есебі

Дата: 2026-08-17
Аудит көлемі: барлық код файлдары (`bot.py`, `database.py`, `google_sheet.py`,
`ocr.py`, `utils.py`, `config.py`, `main.py`), инфрақұрылым файлдары
(`Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.gitignore`, `env.example`).

---

## 🔴 Critical

### 1. `env.example` ішінде НАҚТЫ құпия деректер committed болған
- **Файл:** `env.example`
- **Проблема:** `BOT_TOKEN=8840442455:AAHTDrgAz2YerjFkGjIwZeLcUJUsg2lOMbQ` және
  `GOOGLE_SHEET_ID=1LvL3JeEgQcESnO_NuyBuR7RvryND3_Xb7TpnCcCP33U` — нақты
  мәндер, үлгі емес. `env.example` әдетте Git-ке commit жасалады (тек `.env`
  `.gitignore`-де тұр), яғни бұл токен GitHub тарихында қалуы мүмкін.
- **Неге қауіпті:** кез келген адам осы токенмен ботты толық басқара алады
  (хабарлама жіберу, дерек оқу, боттың орнына әрекет ету).
- **Шешім:**
  1. `env.example`-ден нақты мәндерді алып тастап, тек placeholder қалдырдым
     (`your_bot_token_here` т.б.) — түзетілді.
  2. **МІНДЕТТІ:** BotFather-ден `/revoke` арқылы осы токенді қазірдің
     өзінде жарамсыз етіп, жаңа токен алыңыз — код түзетілгенімен, ескі
     токен әлі де жұмыс істейді, себебі ол Git тарихында қалады.
  3. Git тарихынан толық өшіру үшін `git filter-repo` немесе BFG Repo-Cleaner
     қолдану керек (жай ғана жаңа commit жасау жеткіліксіз — файл әлі де
     ескі commit-терде оқылады).
  4. Google Service Account credentials (`credentials.json`) де сол сияқты
     тексерілуі керек — егер бір рет те commit жасалған болса, IAM консолінен
     кілтті rotate/delete жасаңыз.

### 2. `package_count = None` кезінде заказ диспетчерсіз автоматты тіркеледі (логика қатесі)
- **Файл:** `bot.py`, `handle_screenshot()`
- **Бұрынғы код:**
  ```python
  needs_dispatcher_approval = (
      package_count is not None and package_count <= MIN_PACKAGES_FOR_AUTO_ACCEPT
  )
  ```
- **Неге қауіпті:** OCR пакет санын таппаса (`package_count is None`),
  жоғарыдағы шарт `False` болып, заказ **дереу автоматты тіркеледі** —
  диспетчерге ешбір хабарлама кетпейді (`if package_count is not None and
  package_count > MIN...` шарты да орындалмайды). README мен `/help`
  мәтінінде "5-тен аз пакет — диспетчерге барады" деп жазылған, бірақ
  нақты код бойынша "пакет саны танылмаса" — толық бақылаусыз өтеді.
  Бұл қате скриншот жіберу арқылы (мысалы, "Пакеты" секциясы жоқ немесе
  бұрмаланған скриншот) диспетчер тексеруінен айналып өтуге мүмкіндік
  береді.
- **Шешім (түзетілді):**
  ```python
  needs_dispatcher_approval = (
      package_count is None or package_count <= MIN_PACKAGES_FOR_AUTO_ACCEPT
  )
  ```
  Енді пакет саны танылмаса, қауіпсіз дефолт ретінде диспетчерге жіберіледі.

### 3. `dispatcher_decision_callback`-та авторизация тексерілмеген
- **Файл:** `bot.py`
- **Проблема:** "Принять"/"Вернуть" батырмасын басқанда, callback кез
  келген chat-тан келсе де өңделген — `is_dispatcher()` тексерісі мүлдем
  болмаған. Егер диспетчер чаты топ (группа) болса, кез келген қатысушы
  батырманы баса алады. Сонымен қатар, диспетчер `/logout` арқылы шыққаннан
  кейін де, ескі хабарламалардағы батырмалар әлі жұмыс істей береді —
  яғни авторизациядан айырылған адам ескі хабарламамен әлі де заказды
  қабылдай/қайтара алады.
- **Шешім (түзетілді):** `dispatcher_decision_callback` енді бірінші
  кезекте `database.is_dispatcher(chat_id)` тексереді, авторизацияланбаған
  болса `query.answer(..., show_alert=True)` арқылы қате хабарлама беріп,
  әрекетті доғарады. Осы мақсатпен `database.py`-ге `is_dispatcher()`
  функциясы қосылды.

### 4. Race condition: екі диспетчер бір заказды қатар "Принять" басса — қос жазба
- **Файл:** `bot.py`, `database.py`
- **Проблема:** Бұрын `update_pending_order_status()` шартсыз
  `UPDATE ... WHERE order_number = ?` жасайтын, яғни "статус әлі
  pending ба" екенін тексерместен жаза беретін. Егер екі диспетчер
  (немесе бір диспетчердің екі құрылғысы) бір батырманы бір мезгілде
  бассы, `google_sheet.add_help_record()` **екі рет** шақырылып,
  Google Таблицада саны қате өсіп кетуі мүмкін еді.
- **Шешім (түзетілді):** `update_pending_order_status()` енді
  `UPDATE ... WHERE order_number = ? AND status = 'pending'` жасайды
  және `rowcount > 0` арқылы шынымен өзгеріс болды ма, соны қайтарады.
  `bot.py` осы нәтижені тексеріп, екінші рет басылған әрекетті
  "заказ басқа диспетчермен өңделген" деп қайтарады, Sheets-ке қайта
  жазбайды.

---

## 🟠 High

### 5. `order_exists()` / `save_order()` арасында race condition (аз ықтималды, бірақ мүмкін)
- **Файл:** `database.py`, `bot.py`
- **Проблема:** Екі пайдаланушы бір заказ нөмірін бір мезгілде жіберсе,
  екеуі де `order_exists()`-тен "жоқ" деген жауап алуы мүмкін, содан кейін
  екеуі де `save_order()`-ды шақырады. `order_number` — PRIMARY KEY
  болғандықтан, екіншісі `IntegrityError` алады, бірақ бұрын бұл жалпы
  `except Exception` ішіне түсіп, пайдаланушыға түсініксіз "сервер қатесі"
  деп көрсетілетін.
- **Шешім (түзетілді):** `save_order()`/`save_pending_order()`
  `aiosqlite.IntegrityError`-ды арнайы аулап, `DuplicateOrderError`
  ретінде көтереді; `bot.py` мұны "заказ бұрын тіркелген/өңделуде" деп
  дұрыс түсіндіреді.

### 6. `/admin` командасына brute-force шабуылдан қорғаныс жоқ
- **Файл:** `bot.py`
- **Проблема:** `ADMIN_LOGIN`/`ADMIN_PASSWORD` шектеусіз рет тексеріле
  береді. Пароль қарапайым (`env.example`-де `Arbuz` деп тұрған) болса,
  автоматтандырылған бот арқылы бірнеше минутта brute-force жасауға
  болады.
- **Шешім (түзетілді):** Chat_id бойынша in-memory rate limiter қосылды —
  15 минут ішінде 5 сәтсіз әрекеттен кейін чат уақытша бұғатталады.
  Бұл толық шешім емес (процесс қайта қосылса, есептегіш нөлденеді),
  бірақ автоматтандырылған перебор жылдамдығын күрт төмендетеді.
  **Ұсыныс:** `ADMIN_PASSWORD`-ты күшті, кездейсоқ жолмен ауыстырыңыз
  (`env.example` жаңартылды — "change_me" placeholder).

### 7. `requirements.txt` ішінде ауыр тәуелділіктер әдепкі бойынша орнатылады
- **Файл:** `requirements.txt`, `Dockerfile`
- **Проблема:** `torch`, `torchvision`, `easyocr` (~2GB) әдепкі
  `OCR_ENGINE=tesseract` болса да әрдайым орнатылады — build уақыты мен
  image өлшемі айтарлықтай өседі.
- **Шешім (түзетілді):** `easyocr`/`torch` бөлек `requirements-easyocr.txt`
  файлына шығарылды, тек `OCR_ENGINE=easyocr` қолданғысы келгендер ғана
  орнатады. `Dockerfile`-да сәйкес комментарий қосылды.

### 8. Google Sheets API-дегі уақытша ақаулар (429/5xx) қайталанбайды
- **Файл:** `google_sheet.py`
- **Проблема:** Rate limit (429) немесе уақытша сервер қатесі (5xx)
  болса, бірден exception көтеріліп, қолданушыға "Ошибка сервера"
  көрсетіледі — сұранысты қолмен қайталау керек.
- **Шешім (түзетілді):** `_with_retry()` көмекші функциясы қосылды —
  429/5xx қателерде 3 реттке дейін exponential backoff-пен қайталайды.

### 9. Пайдаланылмаған `images/` каталогы, ескірген Excel-негізді дизайн іздері
- **Файл:** README/жоба құрылымы
- **Проблема:** README-де `images/` каталогы "скриншоттар сақталады" деп
  сипатталған, бірақ нақты кодта скриншоттар `tempfile.TemporaryDirectory()`
  ішінде өңделіп, дереу өшіріледі — `images/` мүлдем қолданылмайды
  (dead directory). Бұл шатастырады: пайдаланушы "суреттер сақталады
  ма" деп ойлауы мүмкін.
- **Шешім:** `Dockerfile`-дан `images` каталогын жасау алынып тасталды.
  README-де осы каталогтың мақсаты жоқтығын түсіндіру ұсынылады (немесе
  егер болашақта скриншот-архив қажет болса, нақты `save_debug_images`
  функциясы қосылуы керек).

---

## 🟡 Medium

### 10. SQLite — жоғары concurrency жағдайында "database is locked" қаупі
- **Файл:** `database.py`
- **Түсіндірме:** Әр функция жаңа қосылым ашады (`aiosqlite.connect`),
  бұл көп жазба бір мезгілде түссе SQLite-тың WAL емес әдепкі режимінде
  "database is locked" қатесіне әкелуі мүмкін.
- **Шешім (түзетілді):** `init_db()` ішінде `PRAGMA journal_mode=WAL;`
  қосылды — бір оқу, бір жазу параллель жүре алады. Жоба көлемі (бір
  команда/шағын кәсіпорын) үшін бұл жеткілікті; егер жүктеме күрт өссе
  (жүздеген қатар сұраныс), PostgreSQL-ге көшу қарастырылуы керек —
  бірақ қазіргі көлемде бұл артық күрделендіру болар еді.

### 11. OCR нәтижесі валидациясыз тікелей сенімге алынады
- **Файл:** `ocr.py`, `utils.py`
- **Түсіндірме:** Заказ нөмірі regex арқылы табылады, бірақ OCR
  қателерін (мыс., "0" мен "O", "1" мен "l" шатасуы) тексеретін
  checksum/confirmation механизмі жоқ. Толық шешім OCR "confidence
  score" қолдануды талап етеді (tesseract бұл мүмкіндікті
  `image_to_data`-мен береді), бұл — үлкен өзгеріс, сондықтан бұл
  жерде тек белгіленеді ("тексеруді қажет етеді").
- **Ұсыныс:** Болашақта, OCR сенімділігі төмен болса (мыс. tesseract
  confidence < 60), заказды автоматты тіркемей, диспетчерге "OCR
  сенімсіз, қолмен тексеріңіз" деген белгімен жіберу.

### 12. `.env` файлы Docker volume ретінде де қосылмайды (тек `env_file`)
- **Файл:** `docker-compose.yml`
- **Түсіндірме:** Бұл дұрыс — `.env` конфигурацияны тек айнымалылар
  ретінде береді, image-ге COPY жасалмайды. Бірақ `.dockerignore`
  болмағандықтан, `docker build` кезінде `.env`/`credentials.json`
  кездейсоқ image ішіне түсіп кетуі мүмкін еді (себебі Dockerfile-да
  `COPY . .` бар).
- **Шешім (түзетілді):** `.dockerignore` қосылды — `.env`,
  `credentials.json`, `*.db`, `*.log`, `.git/` image ішіне түспейді.

### 13. Тест жоқ болды
- **Файл:** жоба құрылымы
- **Шешім (түзетілді):** `tests/test_utils.py` қосылды — `utils.py`
  ішіндегі ең маңызды бизнес-логиканы (заказ нөмірін/пакет санын табу,
  ФИО тазалау) 16 тест-кейспен қамтиды. Барлығы өтті (`pytest` арқылы
  тексерілді). Толық integration/e2e тесттер (Telegram API, Google
  Sheets mock) — келесі кезеңге ұсынылады, себебі олар қосымша
  инфрақұрылым (mock сервер) талап етеді.

---

## 🟢 Low

- **`bot.py`:** `_notify_dispatchers_auto_warning` шарты артық болатын
  (`package_count is not None and package_count > MIN...`), себебі бұл
  функция тек auto-accept тармағында шақырылады, ал сол тармаққа тек
  `package_count > MIN` болғанда ғана түседі (None жағдайы енді
  dispatcher-ге барады). Қарапайымдандырылды.
- **`config.py`:** `TESSERACT_CMD` бос жол болғанда да `_configure_tesseract()`
  әрқашан шақырылады — зияны жоқ, бірақ артық шарт тексеруге болады
  (өзгертілмеді, себебі маңызды емес).
- **README:** нақты токен мысалы (`123456789:AAExxx...`) — бұл — жалған
  үлгі формат, қауіп жоқ, бірақ нақты `env.example`-мен шатастырмау
  үшін ескерту қосу ұсынылады.
- **`employee_name`** ұзындығына шектеу болмаған — 200 таңбадан үлкен
  caption келсе, деректер қорына шексіз ұзын жол жазылуы мүмкін еді.
  `bot.py`-де тексеру қосылды.

---

## Тексерілді, бірақ проблема табылмады

- **SQL injection:** барлық сұраныстар parameterized (`?` placeholder),
  инъекция мүмкін емес.
- **Command/path injection:** shell-ге тікелей команда жіберілмейді,
  файл жолдары `tempfile` арқылы қауіпсіз генерацияланады.
- **Логтарда құпия деректер:** `ADMIN_PASSWORD`, `BOT_TOKEN` логқа
  жазылмайды (тексерілді — тек chat_id, order_number, employee_name
  логталады).
- **Webhook/polling конфликті:** `docker-compose.yml`-да `restart: always`
  бар, ал бір ғана контейнер іске қосылады, сондықтан "Conflict:
  terminated by other getUpdates request" қаупі — тек екі инстанс
  қатар қолмен іске қосылса ғана туындайды. Docker Compose бұл жағдайда
  дұрыс жұмыс істейді (бір контейнер = бір инстанс).

---

## Түзетілген файлдар тізімі

| Файл | Өзгеріс түрі |
|---|---|
| `database.py` | Race condition қорғанысы (`DuplicateOrderError`, атомарлы status update), `is_dispatcher()`, WAL режимі, индекс |
| `bot.py` | `package_count=None` логика қатесі түзетілді, авторизация callback-те, brute-force limiter, DuplicateOrderError өңдеу |
| `google_sheet.py` | Retry/backoff (429/5xx) |
| `env.example` | Нақты токен/ID алынып тасталды, placeholder-мен ауыстырылды |
| `Dockerfile` | `requirements-easyocr.txt` бөлек, `images/` каталогы алынып тасталды |
| `requirements.txt` / `requirements-easyocr.txt` (жаңа) | Ауыр тәуелділіктер бөлінді |
| `.dockerignore` (жаңа) | Құпия деректердің image-ге түсуін болдырмау |
| `tests/test_utils.py` (жаңа) | 16 unit тест, барлығы өтті |

---

## FINAL PRODUCTION CHECKLIST

```text
[x] Critical bugs fixed (package_count None логикасы, авторизация, secrets)
[x] Security issues fixed (callback авторизация, brute-force limiter, .dockerignore)
[x] Database safe (WAL, атомарлы update, DuplicateOrderError)
[x] Duplicate records prevented (race condition қорғанысы екі деңгейде)
[x] API failures handled (Google Sheets retry/backoff)
[ ] Telegram errors handled — негізі бар, бірақ webhook-версия/health-check қосылмаған (қажет болса келесі кезең)
[ ] OCR validated — тек regex деңгейінде; confidence-based валидация ұсыныс түрінде қалды
[x] Logging implemented (өзгеріссіз, дұрыс болатын)
[x] Configuration secured (env.example тазаланды, .dockerignore)
[x] Tests added (utils.py үшін 16 тест)
[ ] README updated — секьюрити ескертулерін қосу ұсынылады (әлі толық жаңартылған жоқ)
[ ] Deployment checked — Docker/Compose дұрыс, бірақ health-check/monitoring жоқ
[ ] Backup strategy — SQLite/Sheets үшін нақты backup скрипт ұсынылмаған
[ ] Monitoring — critical error үшін admin-ге alert механизмі жоқ
[x] Production readiness — негізгі критикалық/жоғары мәселелер түзетілді
```

## Әлі қалған мәселелер (келесі кезеңге)

1. **Backup стратегиясы жоқ** — `orders.db` мен Google Sheets үшін
   автоматты backup (мыс. күнделікті `orders.db` көшірмесін алу немесе
   Google Sheets-тің Version History-іне сену) құжатталуы керек.
2. **Monitoring/alerting жоқ** — критикалық қате (мыс. Google Sheets
   толық қолжетімсіз болса) кезінде админге Telegram арқылы дереу
   хабарлау механизмі жоқ.
3. **OCR confidence негізіндегі валидация** — қазір кез келген regex
   сәйкестігі шындыққа сай деп қабылданады.
4. **README толық жаңартылмады** — секьюрити бөлімі (токен rotation,
   .env қорғау) қосылуы керек.
5. **Architecture layering** (services/repositories бөлу) жасалмады —
   ағымдағы жоба көлемі (7 файл) үшін бұл артық күрделендіру болар еді;
   егер жоба өссе (10+ handler, бірнеше external API), сол кезде
   қарастырылуы орынды.
