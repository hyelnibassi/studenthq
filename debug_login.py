import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studenthq.settings')
import django
django.setup()
from core.models import User
from django.contrib.auth.hashers import check_password

for email, pwd in [('student@aun.edu.ng', 'student1234'), ('admin@aun.edu.ng', 'admin1234'), ('advisor@aun.edu.ng', 'advisor1234')]:
    try:
        u = User.objects.get(email=email)
        print(email, 'exists, role=', u.role, 'hash=', u.passwordHash[:20], '...')
        print('check_password:', check_password(pwd, u.passwordHash))
    except User.DoesNotExist:
        print(email, 'missing')
