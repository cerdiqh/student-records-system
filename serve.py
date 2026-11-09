"""
Production server for Windows (and Linux): python serve.py

Uses Waitress, a production-grade WSGI server, instead of Django's development
server. Listens on all network interfaces so other computers on the same
network can open http://<this-computer's-IP>:8000
"""
import os

from waitress import serve

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.wsgi import application  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Student Academic Records running on http://0.0.0.0:{port}  (Ctrl+C to stop)")
    serve(application, host="0.0.0.0", port=port, threads=8)
