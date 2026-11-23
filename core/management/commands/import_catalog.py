"""
Management command: python manage.py import_catalog
Imports the AUN 2022–2025 course catalog (SAS, SITC, SOE, and General Education)
from core/data/aun_catalog_2022_2025.json into the Course table idempotently.
"""
import json
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from core.models import Course


class Command(BaseCommand):
    help = 'Imports the AUN 2022-2025 course catalog (SAS, SITC, SOE) into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=os.path.join(settings.BASE_DIR, 'core', 'data', 'aun_catalog_2022_2025.json'),
            help='Path to the catalog JSON file',
        )

    def handle(self, *args, **options):
        json_path = options['file']
        if not os.path.exists(json_path):
            self.stderr.write(self.style.ERROR(f'Catalog file not found: {json_path}'))
            return

        with open(json_path, 'r', encoding='utf-8') as f:
            catalog_items = json.load(f)

        created_count = 0
        updated_count = 0

        for item in catalog_items:
            _, created = Course.objects.update_or_create(
                courseID=item['courseID'],
                defaults={
                    'name': item['name'],
                    'credits': item['credits'],
                    'school': item.get('school', ''),
                    'department': item['department'],
                    'category': item.get('category', ''),
                    'semesterOffered': item.get('semesterOffered', 'Fall'),
                    'description': item.get('description', ''),
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'AUN 2022-2025 catalog import complete: {created_count} created, {updated_count} updated '
                f'({Course.objects.count()} total courses in database).'
            )
        )
