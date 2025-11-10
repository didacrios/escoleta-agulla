# 🍽️ Menú Escolar Agulla - Bot de Telegram

Projecte per automatitzar l'enviament diari del menú escolar per Telegram.

## 📋 Característiques

- ✅ Parser de PDFs del menú escolar
- ✅ Mode interactiu per revisar i corregir dades
- ✅ Bot de Telegram per enviar el menú diari
- ✅ Automatització amb GitHub Actions (cada matí de dilluns a divendres)
- ✅ Detecció automàtica de dates i mesos

## 🚀 Configuració inicial

### 1. Instal·lar dependències

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Crear el bot de Telegram

1. Obre Telegram i cerca **@BotFather**
2. Envia `/newbot` i segueix les instruccions
3. Guarda el **token** que et dona
4. Envia un missatge al teu bot per iniciar la conversa
5. Obté el teu **Chat ID** executant:
   ```bash
   python3 src/get_chat_id.py --token "EL_TEU_TOKEN"
   ```

### 3. Configurar variables d'entorn

Crea un fitxer `.env` a l'arrel del projecte:

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789

# Timezone
TIMEZONE=Europe/Madrid
```

### 4. Configurar GitHub Secrets

Per activar l'automatització, afegeix els secrets al teu repositori de GitHub:

1. Ves a **Settings** → **Secrets and variables** → **Actions**
2. Clica **New repository secret**
3. Afegeix aquests 2 secrets:
   - `TELEGRAM_BOT_TOKEN`: El token del teu bot
   - `TELEGRAM_CHAT_ID`: El teu chat ID

## 📖 Ús

### Processar un PDF del menú

```bash
# Mode automàtic (amb detecció de majúscules)
./parse_menu.sh menu/pdfs/novembre_2025.pdf

# Mode interactiu (per revisar i corregir)
./parse_menu.sh menu/pdfs/novembre_2025.pdf --interactive
```

Això generarà automàticament el fitxer JSON a `menu/data/`.

### Enviar el menú per Telegram

```bash
# Enviar el menú d'avui
python3 src/telegram_bot.py -f menu/data/novembre_2025.json

# Enviar el menú d'una data específica
python3 src/telegram_bot.py -f menu/data/novembre_2025.json -d 2025-11-15
```

### Automatització

El workflow de GitHub Actions s'executarà automàticament:
- **Cada matí de dilluns a divendres a les 8:00 AM** (hora de Madrid)
- També es pot executar manualment des de la pestanya **Actions** de GitHub

## 📁 Estructura del projecte

```
escoleta-agulla/
├── .github/
│   └── workflows/
│       └── daily-menu.yml       # Automatització GitHub Actions
├── menu/
│   ├── pdfs/                    # PDFs mensuals originals
│   │   └── novembre_2025.pdf
│   └── data/                    # JSONs processats
│       └── novembre_2025.json
├── src/
│   ├── pdf_menu_parser.py       # Parser del PDF
│   ├── telegram_bot.py          # Bot de Telegram
│   └── get_chat_id.py           # Utilitat per obtenir Chat ID
├── .env                         # Variables d'entorn (NO pujar a git)
├── .gitignore
├── requirements.txt
├── parse_menu.sh                # Script wrapper
└── README.md
```

## 🔄 Workflow mensual

Cada mes:

1. Descarrega el nou PDF del menú
2. Col·loca'l a `menu/pdfs/` amb el nom `[mes]_[any].pdf` (ex: `desembre_2025.pdf`)
3. Executa el parser:
   ```bash
   ./parse_menu.sh menu/pdfs/desembre_2025.pdf --interactive
   ```
4. Revisa i corregeix les dades si cal
5. Puja els canvis a GitHub:
   ```bash
   git add menu/
   git commit -m "Afegir menú de desembre 2025"
   git push
   ```
6. L'automatització detectarà automàticament el nou fitxer JSON

## 🛠️ Tecnologies utilitzades

- **Python 3.12**
- **pdfplumber** - Extracció de dades dels PDFs
- **python-telegram-bot** - API de Telegram
- **GitHub Actions** - Automatització
- **click** - CLI
- **python-dotenv** - Gestió de variables d'entorn

## 📝 Notes

- Els PDFs han de tenir una estructura de taula clara
- El parser utilitza majúscules per detectar l'inici de cada plat
- Les dates es generen automàticament en format ISO (YYYY-MM-DD)
- El bot només envia missatges en dies laborables (dilluns a divendres)

## 🐛 Solució de problemes

### El parser no detecta bé els plats

Usa el mode interactiu per revisar i corregir:
```bash
./parse_menu.sh menu/pdfs/[fitxer].pdf --interactive
```

### El bot no envia missatges

1. Comprova que el `.env` existeix i té els valors correctes
2. Verifica que has enviat un missatge al bot primer
3. Comprova els secrets de GitHub (si uses GitHub Actions)

### El workflow de GitHub Actions falla

1. Verifica que el fitxer JSON del mes actual existeix a `menu/data/`
2. Comprova els logs del workflow a la pestanya **Actions**
3. Assegura't que els secrets estan configurats correctament

## 💡 Inspiració

Aquest projecte està inspirat en [menu-stnico](https://github.com/joaoqalves/menu-stnico) de [@joaoqalves](https://github.com/joaoqalves), un parser del menú del Centre Escolar Sant Nicolau de Sabadell.

Gràcies per compartir el teu treball i inspirar aquest projecte! 🙏

## 📄 Llicència

GNU GPL v3 - Projecte de codi lliure (copyleft).

Això significa que pots usar, modificar i distribuir aquest codi lliurement, però qualsevol versió modificada també ha de ser programari lliure sota la mateixa llicència.

