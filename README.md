# Help Counter Bot

Қызметкерлердің бір-біріне көрсеткен көмегін автоматты түрде есептейтін
Telegram бот. Қызметкер заказ скриншотын аты-жөнімен бірге жібереді, бот
OCR арқылы заказ нөмірін таниды және мәліметті **Excel файлына немесе
Google Sheets кестесіне** жазады.

## Мазмұны

- [Мүмкіндіктер](#мүмкіндіктер)
- [Технологиялар](#технологиялар)
- [Жоба құрылымы](#жоба-құрылымы)
- [1. Telegram bot жасау](#1-telegram-bot-жасау)
- [2. Жобаны орнату](#2-жобаны-орнату)
- [3. .env файлын толтыру](#3-env-файлын-толтыру)
- [4. Локальді іске қосу](#4-локальді-іске-қосу)
- [5. Docker арқылы іске қосу](#5-docker-арқылы-іске-қосу)
- [6. VPS-те 24/7 жұмыс істету](#6-vps-те-247-жұмыс-істету)
- [7. Қолдану нұсқаулығы](#7-қолдану-нұсқаулығы)
- [8. Excel файл құрылымы](#8-excel-файл-құрылымы)
- [9. Ақаулықтарды жою](#9-ақаулықтарды-жою)

## Мүмкіндіктер

- 📸 Скриншоттан заказ нөмірін автоматты тану (OCR)
- 📊 Деректерді жергілікті **Excel (.xlsx)** файлына немесе
  **Google Sheets** кестесіне жазу
- 🔁 Қайталанған заказдарды автоматты анықтау (SQLite)
- 🏆 `/stats` және `/top5` арқылы рейтинг көрсету
- 🐳 Docker арқылы серверде 24/7 жұмыс істеу

## Технологиялар

- Python 3.12+
- python-telegram-bot 21.x (async)
- openpyxl (Excel файлмен жұмыс)
- Tesseract OCR (немесе EasyOCR)
- SQLite (aiosqlite)
- Docker / Docker Compose

## Жоба құрылымы

```
help-counter-bot/
├── main.py             # Кіру нүктесі
├── bot.py              # Telegram handlerлер
├── excel_sheet.py      # Excel (.xlsx) файлмен жұмыс логикасы
├── ocr.py               # Скриншоттан заказ нөмірін тану
├── database.py          # SQLite (дубликат тексеру)
├── config.py             # Орта айнымалылары мен логтау
├── utils.py               # Көмекші функциялар
├── requirements.txt
├── help_counter.xlsx    # Деректер сақталатын Excel файл (автоматты жасалады)
├── orders.db             # Дубликат тексеру дерекқоры (автоматты жасалады)
├── .env                  # Құпия баптаулар (өзіңіз жасайсыз)
├── Dockerfile
├── docker-compose.yml
├── README.md
├── images/
└── logs/
```

## 1. Telegram bot жасау

1. Telegram-да [@BotFather](https://t.me/BotFather) ашыңыз.
2. `/newbot` командасын жіберіңіз.
3. Бот атын және username-ін енгізіңіз (username `bot` деп аяқталуы керек).
4. BotFather сізге **токен** береді, мысалы:
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
5. Бұл токенді сақтап қойыңыз — ол `.env` файлындағы `BOT_TOKEN`
   мәні болады.

## 2. Жобаны орнату

```bash
git clone <репозиторий-сілтемесі>
cd help-counter-bot

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

> **Ескерту (Tesseract):** `pytesseract` — тек Python "wrapper" (аударушы),
> ол Tesseract-OCR бағдарламасының өзін қамтымайды. Оны жүйеге бөлек
> орнату керек.
>
> **Linux (Ubuntu/Debian):**
> ```bash
> sudo apt-get install tesseract-ocr tesseract-ocr-rus
> ```
>
> **Windows:**
> 1. [UB Mannheim Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki)
>    сайтынан `.exe` файлды жүктеп алыңыз (мысалы,
>    `tesseract-ocr-w64-setup-5.x.x.exe`).
> 2. Орнату кезінде **"Additional language data" → Russian** тілін
>    міндетті түрде белгілеп қойыңыз (әйтпесе кирилицаны танымайды).
> 3. Әдепкі бойынша ол мына жерге орнатылады:
>    `C:\Program Files\Tesseract-OCR\tesseract.exe`
> 4. Егер бот бәрібір "Заказ нөмірі анықталмады" деп жауап берсе,
>    `.env` файлына осы жолды қосыңыз:
>    ```env
>    TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
>    ```
>    (орнату кезінде жолды өзгертсеңіз, соған сай көрсетіңіз)
>
> **macOS:**
> ```bash
> brew install tesseract tesseract-lang
> ```
>
> EasyOCR қолдансаңыз (`OCR_ENGINE=easyocr`), бөлек орнатудың қажеті жоқ,
> бірақ бірінші іске қосуда модель файлдары жүктеледі әрі жады көбірек
> қажет етеді.

## 3. .env файлын толтыру

`.env.example` файлын көшіріп, өз мәндеріңізді енгізіңіз:

```bash
cp .env.example .env
```

```env
BOT_TOKEN=123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EXCEL_FILE_PATH=help_counter.xlsx
EXCEL_SHEET_NAME=Sheet1
OCR_ENGINE=tesseract
OCR_LANGUAGES=rus+eng
DATABASE_PATH=orders.db
LOG_LEVEL=INFO
```

`EXCEL_FILE_PATH` — деректер сақталатын Excel файлдың жолы. Файл жоқ
болса, бот оны бірінші іске қосылғанда өзі тақырыптарымен бірге жасайды.

Егер `GOOGLE_SHEETS_ENABLED=true` болса, бот жазбаларды Google Sheets
ке жазады. Сол үшін `.env` файлына `GOOGLE_SHEET_ID` және
`GOOGLE_SERVICE_ACCOUNT_FILE` көрсетіңіз.

## 4. Локальді іске қосу

```bash
python main.py
```

Терминалда мынадай жол шықса, бот сәтті іске қосылған:

```
Bot іске қосылды. Polling режимінде жұмыс істеп жатыр...
```

Жоба папкасында `help_counter.xlsx` файлы автоматты пайда болады —
оны әдеттегі Excel/LibreOffice/Google Sheets-ке импорттап та аша
аласыз.

## 5. Docker арқылы іске қосу

```bash
docker compose up --build -d
```

Бұл команда:

- образды құрастырады (Tesseract-пен бірге);
- `.env` файлын контейнерге қосады;
- `help_counter.xlsx` және `orders.db` файлдарын хост машинамен
  бөліседі (volume), сондықтан контейнер қайта жасалса да деректер
  жоғалмайды;
- `restart: always` арқасында сервер қайта жүктелсе де бот өзі қайта
  іске қосылады.

Алғаш іске қосу алдында бос файлдарды өзіңіз жасап қойыңыз (Docker
volume бос директорияны файл деп қате түсінбеуі үшін):

```bash
touch help_counter.xlsx orders.db
docker compose up --build -d
```

Логтарды көру:

```bash
docker compose logs -f
```

Тоқтату:

```bash
docker compose down
```

## 6. VPS-те 24/7 жұмыс істету

### Нұсқа A — Docker Compose (ұсынылады)

Oracle Cloud Free немесе кез келген Ubuntu VPS-те:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin

git clone <репозиторий-сілтемесі>
cd help-counter-bot
cp .env.example .env   # мәндерді толтырыңыз
touch help_counter.xlsx orders.db

docker compose up --build -d
```

`restart: always` баптауының арқасында сервер қайта жүктелген кезде де
(немесе бот құлап қалса да) контейнер автоматты түрде қайта іске қосылады.

### Нұсқа B — systemd (Docker-сіз)

```ini
# /etc/systemd/system/help-counter-bot.service
[Unit]
Description=Help Counter Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/help-counter-bot
ExecStart=/home/ubuntu/help-counter-bot/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Іске қосу:

```bash
sudo systemctl daemon-reload
sudo systemctl enable help-counter-bot
sudo systemctl start help-counter-bot
sudo systemctl status help-counter-bot
```

Ноутбук өшірулі тұрса да, бот VPS-те үздіксіз жұмыс істей береді.

### Excel файлды серверден қалай алуға болады

`help_counter.xlsx` серверде жатады, оны кез келген уақытта жүктеп
алуға болады:

```bash
scp user@server-ip:/path/to/help-counter-bot/help_counter.xlsx ./
```

Немесе бот кодына `/export` командасын қосып, Telegram арқылы файлды
тікелей жіберуге де болады (қажет болса, сұраңыз — қосып беремін).

## 7. Қолдану нұсқаулығы

| Команда | Сипаттамасы |
|---|---|
| `/start` | Бот туралы қысқаша ақпарат |
| `/help` | Қолдану нұсқаулығы |
| `/stats` | Барлық қызметкерлердің толық рейтингі |
| `/top5` | Ең көп көмек көрсеткен 5 қызметкер |

**Көмекті тіркеу үшін:**

1. Заказдың скриншотын түсіріңіз.
2. Ботқа скриншотты, астына (caption) көмек көрсеткен қызметкердің
   аты-жөнін жазып жіберіңіз (мысалы: `Айтбай Рахымжан`).
3. Бот заказ нөмірін автоматты танып, Excel файлға жазады және растау
   хабарламасын жібереді:

```
✅ Көмек тіркелді

👤 Айтбай Рахымжан
📦 Заказ №254891
📊 Жалпы көмек саны: 12
```

Егер заказ бұрын тіркелген болса — бот "Бұл заказ бұрын тіркелген."
деп жауап береді және Excel файл өзгермейді.

## 8. Excel файл құрылымы

`help_counter.xlsx` файлындағы бірінші парақ:

| Аты-жөні | Көмек саны | Заказтар | Соңғы заказ | Соңғы жаңарту |
|---|---|---|---|---|
| Айтбай Рахымжан | 12 | 254123, 254456, ... | 254891 | 02.08.2026 14:05 |

- **Аты-жөні** — қызметкердің толық аты (caption арқылы келеді)
- **Көмек саны** — тіркелген заказдардың жалпы саны
- **Заказтар** — барлық заказ нөмірлері үтірмен бөлінген түрде
- **Соңғы заказ** — ең соңғы тіркелген заказ нөмірі
- **Соңғы жаңарту** — жазба соңғы рет қашан жаңартылғаны

Файлды әдеттегі Excel, LibreOffice Calc немесе Google Sheets-ке
жүктеп ашуға болады — ол қарапайым `.xlsx` форматында сақталады.

## 9. Ақаулықтарды жою

| Мәселе | Шешімі |
|---|---|
| `.env файлында ... толтырылмаған` қатесі | `.env` файлын толтырыңыз, `BOT_TOKEN` міндетті |
| `Excel файлынан деректерді алу кезінде қате` | `EXCEL_FILE_PATH` жолы дұрыс па, файлға жазу құқығы бар ма — тексеріңіз |
| `Заказ нөмірі анықталмады` жиі шығады | Скриншот сапасын тексеріңіз; `OCR_ENGINE=easyocr` көріп көріңіз |
| Windows-та `TesseractNotFoundError` немесе OCR ешбір мәтін таппайды | `logs\bot.log` ішінен нақты қатені қараңыз; Tesseract орнатылмаған болса — жоғарыдағы "Windows" бөлімін оқыңыз, `.env`-ге `TESSERACT_CMD` қосыңыз |
| Tesseract табылмады қатесі | `sudo apt-get install tesseract-ocr tesseract-ocr-rus` орнатыңыз (Docker қолдансаңыз бұл автоматты) |
| Docker-де Excel файл өзгермейді | `docker-compose.yml` ішіндегі volume жолдары дұрыс екенін тексеріңіз |
| Бот polling кезінде тоқтап қалады | `docker compose logs -f` немесе `logs/bot.log` арқылы қатені қараңыз |

---

Сұрақтарыңыз болса, `logs/bot.log` файлындағы толық логты тексеріңіз —
барлық қателер уақыты мен себебімен бірге жазылады.
