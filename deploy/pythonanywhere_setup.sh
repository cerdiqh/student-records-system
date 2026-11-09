#!/bin/bash
# One-step setup on PythonAnywhere. In a PythonAnywhere *Bash console* run:
#
#   curl -sL https://raw.githubusercontent.com/cerdiqh/student-records-system/main/deploy/pythonanywhere_setup.sh | bash
#
# Before running it, create the web app on the Web tab:
#   Add a new web app -> Next -> Manual configuration -> Python 3.11 -> Next
# Safe to run again later to update the site to the newest code on GitHub.
set -e

REPO="https://github.com/cerdiqh/student-records-system.git"
APP_DIR="$HOME/student-records-system"
HOST="${USER}.pythonanywhere.com"
WSGI_FILE="/var/www/${USER}_pythonanywhere_com_wsgi.py"
PY=python3.11

echo "==> 1/6  Getting the code from GitHub"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
else
    git clone "$REPO" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> 2/6  Creating the Python environment (takes a few minutes the first time)"
if ! command -v "$PY" >/dev/null; then
    echo "!! $PY is not available on this account. Tell Claude which Python versions the Web tab offers."
    exit 1
fi
[ -d venv ] || "$PY" -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "==> 3/6  Settings (.env)"
if [ ! -f .env ]; then
    echo "Enter the Gmail account the system sends emails from."
    read -r -p "  Gmail address: " GMAIL </dev/tty
    read -r -s -p "  Gmail App Password (16 letters; typing is hidden): " GPASS </dev/tty
    echo
    GPASS="${GPASS// /}"
    SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
    cat > .env <<EOF
SECRET_KEY=$SECRET
DEBUG=False
ALLOWED_HOSTS=$HOST
CSRF_TRUSTED_ORIGINS=https://$HOST
USE_HTTPS=True
SECURE_SSL_REDIRECT=False
DB_ENGINE=sqlite
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=$GMAIL
EMAIL_HOST_PASSWORD=$GPASS
DEFAULT_FROM_EMAIL=Student Academic Records <$GMAIL>
EOF
    chmod 600 .env
    echo "  .env created (only you can read it)."
else
    echo "  .env already exists - keeping it."
fi

echo "==> 4/6  Database and stylesheets"
python manage.py migrate --noinput
python manage.py collectstatic --noinput -v 0

echo "==> 5/6  Testing email"
python manage.py shell -c "
from django.conf import settings
from django.core.mail import send_mail
try:
    send_mail('PythonAnywhere test', 'Email from your online Student Records system works.', settings.DEFAULT_FROM_EMAIL, [settings.EMAIL_HOST_USER])
    print('  Test email sent to', settings.EMAIL_HOST_USER)
except Exception as e:
    print('  !! Email test FAILED:', e)
"

echo "==> 6/6  Connecting the web app"
if [ -f "$WSGI_FILE" ]; then
    [ -f "$WSGI_FILE.original" ] || cp "$WSGI_FILE" "$WSGI_FILE.original"
    cat > "$WSGI_FILE" <<EOF
import os, sys
path = "$APP_DIR"
if path not in sys.path:
    sys.path.insert(0, path)
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
EOF
    touch "$WSGI_FILE"   # reloads the site
    echo "  WSGI file updated."
else
    echo "!! $WSGI_FILE not found. Create the web app on the Web tab first (Manual configuration, Python 3.11), then run this again."
    exit 1
fi

echo
echo "=================================================================="
echo " DONE. Last step on the Web tab:"
echo "   1. Virtualenv:  $APP_DIR/venv     (type it, press the tick)"
echo "   2. Security:    turn ON 'Force HTTPS'"
echo "   3. Click the green 'Reload $HOST' button"
echo " Then open  https://$HOST  and sign up as Administrator."
echo "=================================================================="
