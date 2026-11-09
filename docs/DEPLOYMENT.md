# Deployment Guide: putting the system into real use

There are two ways to run the system for real users. Pick one:

| Option | Who can use it | Cost | Best for |
|---|---|---|---|
| **A. Department computer / LAN** | Anyone on the same Wi-Fi or office network | Free | One department office, no internet needed |
| **B. Online (PythonAnywhere)** | Anyone with internet, from anywhere | Free tier available | Students checking results from home |

Before either option, do the **common steps**.

---

## Common steps (do these once)

1. **Get the code** onto the machine: clone it from GitHub, or copy the folder.
2. **Install:**
   ```bash
   python -m venv venv
   venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Create `.env`:** copy `.env.example` to `.env`, then:
   - generate a secret key and paste it into `SECRET_KEY`:
     ```bash
     python -c "import secrets; print(secrets.token_urlsafe(50))"
     ```
   - set `DEBUG=False`;
   - list the addresses users will type in `ALLOWED_HOSTS`.
4. **Create the database and collect the stylesheets:**
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```
5. **Start the server** (see Option A or B), then open the site in a browser. The **first-time setup page** appears automatically:
   - enter the real institution, faculty and department;
   - enter the current session;
   - create your administrator account.

   This page appears only once.

**Do NOT run `seed_demo` on a real installation.** It is disabled when `DEBUG=False`.

---

## Option A: on a department computer (local network)

1. Find the computer's IP address: run `ipconfig` and look for the IPv4 address, e.g. `192.168.1.10`.
2. Put that IP in `ALLOWED_HOSTS` in `.env`.
3. Start the production server:
   ```bash
   venv\Scripts\activate
   python serve.py
   ```
4. On any other computer or phone on the same network, open `http://192.168.1.10:8000`.
5. **Allow it through Windows Firewall** the first time Windows asks: tick *Private networks*.
6. **Start automatically on boot:** create a Windows Task Scheduler task that runs at log on:
   - Program: `C:\path\to\student-records-system\venv\Scripts\python.exe`
   - Arguments: `serve.py`
   - Start in: `C:\path\to\student-records-system`

---

## Option B: online with PythonAnywhere (free)

1. Create an account at https://www.pythonanywhere.com. Your site will be `https://<username>.pythonanywhere.com`.
2. Open a **Bash console** and run:
   ```bash
   git clone https://github.com/<you>/student-records-system.git
   cd student-records-system
   python3.11 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env && nano .env
   ```
3. In `.env`, set:
   ```
   SECRET_KEY=<generated key>
   DEBUG=False
   ALLOWED_HOSTS=<username>.pythonanywhere.com
   CSRF_TRUSTED_ORIGINS=https://<username>.pythonanywhere.com
   USE_HTTPS=True
   ```
4. Create the database and collect static files:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```
5. On the **Web** tab:
   - **Add a new web app**, choose *Manual configuration*, then *Python 3.11*.
   - **Virtualenv:** `/home/<username>/student-records-system/venv`
   - **WSGI configuration file:** replace its contents with:
     ```python
     import os, sys
     path = "/home/<username>/student-records-system"
     if path not in sys.path:
         sys.path.insert(0, path)
     os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
     from django.core.wsgi import get_wsgi_application
     application = get_wsgi_application()
     ```
   - **Static files:** URL `/static/`, directory `/home/<username>/student-records-system/staticfiles`
   - Turn on **Force HTTPS**, then click **Reload**.
6. Visit your site and complete the first-time setup.

**Updating later:**
```bash
git pull
python manage.py migrate
python manage.py collectstatic --noinput
```
Then click **Reload** on the Web tab.

---

## Email for "Forgot password" (optional)

Without email settings, users who forget their password ask the records office, which uses the **Reset password** button.

To send reset links by email with Gmail:

1. Turn on 2-Step Verification on the Gmail account.
2. Create an **App Password** at https://myaccount.google.com/apppasswords.
3. Fill in the `EMAIL_*` lines in `.env`, then restart the server.

Only users with an email address on their account can reset their own password.

---

## Backups (very important)

Choose one, or both:

- **From the browser:** go to *Institution Settings*, then **Download backup now**. This downloads a `.json` file with every record. Keep copies on a flash drive or cloud storage.
- **Automatically:** schedule this daily with Windows Task Scheduler or a PythonAnywhere *Scheduled task*:
  ```bash
  python manage.py backup --keep 30
  ```
  It writes `backups/sars-YYYYMMDD-HHMM.json` plus a zip of uploaded photos, and keeps the newest 30.

**To restore** on a fresh installation:

1. Run `python manage.py migrate`.
2. Run `python manage.py loaddata backups/sars-YYYYMMDD-HHMM.json`.
3. Unzip the media backup into the `media/` folder.

---

## Going live: checklist

- [ ] `DEBUG=False` and a unique `SECRET_KEY` in `.env`
- [ ] First-time setup done with the **real** institution and department names
- [ ] Logo uploaded and registrar name set (*Institution Settings*)
- [ ] Grading scale and degree classes in `config/settings.py` match your institution's handbook
- [ ] Lecturer accounts created; temporary passwords given privately
- [ ] Courses imported and lecturers assigned
- [ ] Students imported; login slips printed and handed out
- [ ] Backup tested (download one, then restore it on a test copy)
- [ ] (Online) HTTPS on, with `USE_HTTPS=True`

## Data protection

The system holds personal data (names, dates of birth, addresses, results). In Nigeria this falls under the **Nigeria Data Protection Act 2023**.

- Give accounts only to people who need them, and disable accounts for staff who leave.
- Keep backups somewhere secure, because they contain everyone's data.
- Student photos are served only to logged-in users who are allowed to see that student. They are never public.
- Every change is recorded in the audit log, which the administrator should review regularly.
