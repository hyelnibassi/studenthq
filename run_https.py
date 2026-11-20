"""
Launch Student HQ over an encrypted HTTPS (TLS) connection locally.

Usage:
    .\venv\Scripts\python.exe run_https.py

Serves the Django application at https://127.0.0.1:8443/ using the TLS
certificate in certs/localhost.crt and certs/localhost.key with Django's
HTTPS security settings (SECURE_SSL_REDIRECT, secure cookies, HSTS) enabled.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CERT_FILE = BASE_DIR / 'certs' / 'localhost.crt'
KEY_FILE = BASE_DIR / 'certs' / 'localhost.key'


def main():
    if not CERT_FILE.exists() or not KEY_FILE.exists():
        print(f"ERROR: TLS certificate files not found at {CERT_FILE} and {KEY_FILE}.")
        sys.exit(1)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studenthq.settings')
    os.environ['ENABLE_HTTPS'] = 'True'

    import django
    django.setup()

    from django.conf import settings
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.wsgi import get_wsgi_application
    from werkzeug.serving import run_simple

    app = get_wsgi_application()
    if settings.DEBUG:
        app = StaticFilesHandler(app)

    host = os.getenv('HTTPS_HOST', '127.0.0.1')
    port = int(os.getenv('HTTPS_PORT', '8443'))

    print(f"Starting Student HQ with TLS encryption at https://{host}:{port}/")
    print(f"Certificate: {CERT_FILE}")
    run_simple(
        hostname=host,
        port=port,
        application=app,
        ssl_context=(str(CERT_FILE), str(KEY_FILE)),
        use_reloader=True,
        use_debugger=False,
        threaded=True,
    )


if __name__ == '__main__':
    main()
