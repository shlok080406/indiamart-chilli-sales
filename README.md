# IndiaMART Chilli Sales Assistant

A lightweight B2B sales and pricing system for red chilli powder enquiries. Built with Python + Streamlit.

## Features

### Core
- **Product catalogue** — 5 chilli powder varieties with specs (colour, SHU, ASTA)
- **Dynamic pricing model** — Cost-based pricing with margin calculator
- **Quantity-tiered pricing** — Different rates for different order sizes
- **Price history** — Never overwrite prices; full history preserved in SQLite
- **PDF quotation generation** — Professional PDF quotations with ReportLab

### Sales Workflow
- **IndiaMART API sync** — Pull new enquiries directly from IndiaMART (credentials required)
- **Gmail watcher (free auto-import)** — Reads IndiaMART enquiry emails from your inbox and creates leads every 5 minutes, no IndiaMART API needed
- **AI enquiry parser** — Automatically extracts customer, quantity, variety, and location from enquiry text
- **Lead management** — Track New → Follow-up → Quoted → Converted pipeline
- **Auto-send quotations** — Email or WhatsApp delivery after your confirmation
- **Follow-up scheduling** — Automatic date reminders per lead status

### Analytics
- **Sales dashboard** — Pipeline funnel, conversion rate, overdue follow-up alerts
- **Quotation history** — Full log of every sent quotation

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Or using the virtual environment:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure credentials

Create `data/secrets.json` (not tracked by git):

```json
{
  "indiamart_crm_id": "YOUR_INDIAMART_CRM_ID",
  "indiamart_api_key": "YOUR_INDIAMART_API_KEY",
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "your@email.com",
  "smtp_password": "your-app-password",
  "smtp_from_email": "your@email.com",
  "smtp_from_name": "Vijaylaxmi Trading Company",
  "whatsapp_token": "WHATSAPP_ACCESS_TOKEN",
  "whatsapp_phone_id": "PHONE_NUMBER_ID",
  "anthropic_api_key": "sk-ant-..."
}
```

> **Gmail SMTP:** Use an [App Password](https://support.google.com/accounts/answer/185833) (not your login password).
> **WhatsApp:** Requires WhatsApp Business Cloud API with a permanent access token.

Environment variables can be used instead (prefix `EMAIL_`, `WHATSAPP_`, `INDIAMART_`, `ANTHROPIC_`, `GMAIL_`).

## Gmail Watcher (auto-import IndiaMART enquiries)

IndiaMART's Pull API is a paid add-on. The Gmail watcher is the free alternative: it reads enquiry emails from your inbox (IndiaMART emails you on every new lead) and creates leads automatically.

### One-time setup

1. **Enable 2-Step Verification** on the Google account that receives IndiaMART emails:
   https://myaccount.google.com/security

2. **Generate an App Password**:
   https://myaccount.google.com/apppasswords
   - App name: "Chilli Sales Watcher"
   - Copy the 16-character password (e.g. `abcd efgh ijkl mnop`)

3. **Add the credentials to `data/secrets.json`**:
   ```json
   {
     "gmail_user": "you@gmail.com",
     "gmail_app_password": "abcd efgh ijkl mnop"
   }
   ```
   Or set environment variables:
   ```
   $env:GMAIL_USER = "you@gmail.com"
   $env:GMAIL_APP_PASSWORD = "abcd efgh ijkl mnop"
   ```

4. **Confirm IndiaMART sends enquiry emails to this Gmail account**:
   - Log in to seller.indiamart.com
   - Go to **My Profile → Notification Settings**
   - Make sure **email alerts for new enquiries** are enabled and pointing at the Gmail address above

5. **Start the watcher**:
   ```bash
   py run_watcher.py                  # polls every 5 minutes
   py run_watcher.py --interval 60    # polls every minute
   py run_watcher.py --once           # single poll, then exit
   ```
   The first run scans the last 7 days. Subsequent runs only process new mail. Each lead it creates is also passed through the AI parser so variety, quantity, and location are auto-filled.

### Status & logs

- **In the app**: log in as admin → **Enquiries** page → "Gmail Watcher" section shows configured status, last poll, leads imported today.
- **Logs**: `data/gmail_watcher.log`
- **State**: `data/gmail_watcher_state.json` (tracks which emails have been processed)

### Run automatically on Windows startup

1. Press Win+R, type `shell:startup`, press Enter
2. Create a shortcut to `py run_watcher.py` with "Start in" set to the project folder
3. The watcher will start in the background every time you log in

### Troubleshooting

- **"Authentication failed"** → Re-generate the app password; 2-Step Verification must be on.
- **"No mail fetched"** → Log in to Gmail web and confirm IndiaMART emails are arriving in the inbox (not promotions/spam).
- **"Connection error"** → Some corporate networks block IMAP. Try from a different network.
- **"IMAP is disabled"** → Enable IMAP at https://mail.google.com/mail/u/0/#settings/fwdandpop
- **Want it running 24/7 even when your PC is off** → Deploy `run_watcher.py` to a free cloud host (PythonAnywhere scheduled tasks, Render cron, etc.).

### 3. Initialize the database

```bash
python database/pricing_db.py
```

### 4. Run the app

```bash
streamlit run app/dashboard.py
```

The app runs at `http://localhost:8501`.

## Project Structure

```
.
├── app/
│   ├── dashboard.py        # Main Streamlit UI
│   └── enquiry_ingest.py  # Enquiry sync & AI parser page
├── database/
│   ├── pricing_db.py       # SQLite database layer
│   └── schema.md          # Database schema docs
├── services/
│   ├── indiamart_api.py    # IndiaMART API client
│   ├── gmail_watcher.py    # Gmail IMAP enquiry auto-importer
│   ├── enquiry_parser.py   # AI + rule-based enquiry parser
│   ├── pricing.py          # Core pricing calculations
│   ├── pricing_tiers.py    # Quantity-based tiered pricing
│   ├── followup_scheduler.py # Follow-up date calculator
│   ├── email_sender.py     # SMTP email sender
│   ├── whatsapp_sender.py   # WhatsApp Cloud API sender
│   └── quotation_sender.py # Orchestrator for sending
├── run_watcher.py          # Background scheduler for Gmail watcher
├── data/
│   ├── products.json        # Product catalogue
│   ├── leads.json           # Legacy leads (migrating to DB)
│   ├── customers.json       # Customer records
│   ├── pricing_tiers.json   # Quantity-tiered pricing per product
│   ├── business_rules.json  # Business configuration
│   └── chilli_sales.db      # SQLite database
└── tests/                   # Unit tests (run with pytest)
```

## Running Tests

```bash
py -m pytest tests/ -v
```

## Business Rules

- Review market prices every 15 days.
- Export-quality pricing must be manually confirmed.
- Domestic prices assume a 7% oil and salt mixture.
- Do not claim current-batch lab reports unless verified.
- Follow-up intervals are configurable in `data/business_rules.json`.

## Initial Products

Imported from the IndiaMART knowledge-transfer workbook:
1. Teja / Guntur
2. Teja Premium / Guntur
3. Resham Patti / Byadgi Blend
4. Pure Byadgi
5. Kashmiri Byadgi / Kashmiri
