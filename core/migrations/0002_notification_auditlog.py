
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('notifID', models.AutoField(primary_key=True, serialize=False)),
                ('message', models.TextField()),
                ('type', models.CharField(choices=[('info', 'Info'), ('warning', 'Warning'), ('danger', 'Danger')], default='info', max_length=20)),
                ('date', models.DateField(auto_now_add=True)),
                ('is_read', models.BooleanField(default=False)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='core.student')),
            ],
            options={
                'db_table': 'notification',
            },
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('logID', models.AutoField(primary_key=True, serialize=False)),
                ('action', models.CharField(choices=[('fee_structure_update', 'Fee Structure Update'), ('course_add', 'Course Added'), ('course_delete', 'Course Deleted'), ('user_action', 'User Action')], max_length=100)),
                ('description', models.TextField()),
                ('ip_address', models.CharField(blank=True, max_length=45, null=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to='core.user')),
            ],
            options={
                'db_table': 'audit_log',
            },
        ),
    ]
