"""
Management command: python manage.py seed_data
Seeds the database with AUN course catalog, fee structure, and test accounts
for all 4 programs specified in the SDP technical report.
Run this once after migrations to get real data in every page.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from datetime import date
from core.models import (
    User, Student, Admin, AcademicAdvisor,
    Course, Prerequisite, Enrollment, Fee, FeeStructure
)


class Command(BaseCommand):
    help = 'Seeds Student HQ with AUN course catalog and test accounts'

    def handle(self, *args, **options):
        self.stdout.write('Seeding fee structure...')
        FeeStructure.objects.get_or_create(pk=1, defaults={
            'tuition_per_credit': 50000,
            'accommodation_on_campus': 250000,
            'accommodation_off_campus': 180000,
            'sports_fee': 15000,
            'lab_fee': 25000,
            'library_fee': 20000,
            'late_penalty_per_month': 30000,
        })

        self.stdout.write('Seeding courses...')
        courses_data = [
            # Computer Science
            ('CS101', 'Introduction to Programming', 3, 'Computer Science', 'Fall', 'Fundamentals of programming using Python.'),
            ('CS102', 'Discrete Mathematics', 3, 'Computer Science', 'Spring', 'Logic, sets, relations, and graph theory.'),
            ('CS201', 'Data Structures', 3, 'Computer Science', 'Fall', 'Arrays, linked lists, trees, graphs, and algorithms.'),
            ('CS202', 'Computer Architecture', 3, 'Computer Science', 'Spring', 'CPU design, memory hierarchy, and instruction sets.'),
            ('CS301', 'Algorithms', 3, 'Computer Science', 'Fall', 'Algorithm design, analysis, and complexity.'),
            ('CS302', 'Database Systems', 3, 'Computer Science', 'Spring', 'Relational databases, SQL, and normalization.'),
            ('CS401', 'Software Engineering', 3, 'Computer Science', 'Fall', 'SDLC, Agile, testing, and project management.'),
            ('CS402', 'Artificial Intelligence', 3, 'Computer Science', 'Spring', 'Search, knowledge representation, and machine learning basics.'),
            # Business Administration
            ('BA101', 'Introduction to Business', 3, 'Business Administration', 'Fall', 'Business environment, ethics, and strategy.'),
            ('BA102', 'Principles of Management', 3, 'Business Administration', 'Spring', 'Planning, organizing, leading, and controlling.'),
            ('BA201', 'Financial Accounting', 3, 'Business Administration', 'Fall', 'Financial statements and accounting principles.'),
            ('BA202', 'Marketing Fundamentals', 3, 'Business Administration', 'Spring', 'Product, price, place, and promotion strategies.'),
            ('BA301', 'Corporate Finance', 3, 'Business Administration', 'Fall', 'Capital structure, valuation, and investment decisions.'),
            ('BA302', 'Operations Management', 3, 'Business Administration', 'Spring', 'Supply chain, quality control, and process optimization.'),
            # Economics
            ('EC101', 'Microeconomics', 3, 'Economics', 'Fall', 'Consumer theory, firm behavior, and market structures.'),
            ('EC102', 'Macroeconomics', 3, 'Economics', 'Spring', 'GDP, inflation, unemployment, and fiscal policy.'),
            ('EC201', 'Statistics for Economists', 3, 'Economics', 'Fall', 'Descriptive statistics, probability, and inference.'),
            ('EC202', 'Econometrics', 3, 'Economics', 'Spring', 'Regression analysis and economic data interpretation.'),
            ('EC301', 'Development Economics', 3, 'Economics', 'Fall', 'Poverty, inequality, and growth in developing economies.'),
            # Engineering
            ('EN101', 'Engineering Mathematics I', 3, 'Engineering', 'Fall', 'Calculus, vectors, and differential equations.'),
            ('EN102', 'Engineering Physics', 3, 'Engineering', 'Spring', 'Mechanics, thermodynamics, and electromagnetism.'),
            ('EN201', 'Engineering Mathematics II', 3, 'Engineering', 'Fall', 'Linear algebra, Fourier analysis, and Laplace transforms.'),
            ('EN202', 'Circuit Analysis', 3, 'Engineering', 'Spring', 'DC and AC circuits, Kirchhoff laws, and network theorems.'),
            ('EN301', 'Signals and Systems', 3, 'Engineering', 'Fall', 'Continuous and discrete signals, filtering, and transforms.'),
        ]

        course_objs = {}
        for cid, name, credits, dept, sem, desc in courses_data:
            obj, _ = Course.objects.get_or_create(
                courseID=cid,
                defaults={
                    'name': name, 'credits': credits,
                    'department': dept, 'semesterOffered': sem, 'description': desc,
                }
            )
            course_objs[cid] = obj

        self.stdout.write('Seeding prerequisites...')
        prereq_pairs = [
            ('CS201', 'CS101'), ('CS301', 'CS201'), ('CS302', 'CS201'),
            ('CS401', 'CS301'), ('CS402', 'CS301'),
            ('BA201', 'BA101'), ('BA301', 'BA201'), ('BA302', 'BA102'),
            ('EC201', 'EC101'), ('EC202', 'EC201'), ('EC301', 'EC102'),
            ('EN201', 'EN101'), ('EN202', 'EN101'), ('EN301', 'EN201'),
        ]
        for course_id, req_id in prereq_pairs:
            Prerequisite.objects.get_or_create(
                course=course_objs[course_id],
                requiredCourse=course_objs[req_id],
            )

        self.stdout.write('Seeding test accounts...')

        # Admin account
        if not User.objects.filter(email='admin@aun.edu.ng').exists():
            admin_user = User.objects.create(
                name='AUN Admin', email='admin@aun.edu.ng',
                passwordHash=make_password('admin1234'), role='admin',
            )
            Admin.objects.create(user=admin_user, department='Finance')
            self.stdout.write('  Admin: admin@aun.edu.ng / admin1234')

        # Advisor account
        if not User.objects.filter(email='advisor@aun.edu.ng').exists():
            adv_user = User.objects.create(
                name='Dr. Sarah James', email='advisor@aun.edu.ng',
                passwordHash=make_password('advisor1234'), role='advisor',
            )
            AcademicAdvisor.objects.create(user=adv_user, department='Computer Science')
            self.stdout.write('  Advisor: advisor@aun.edu.ng / advisor1234')

        # Student accounts for each program
        students_data = [
            ('AUN-2026-001', 'student@aun.edu.ng', 'student1234', 'Chidi Okeke',        'Computer Science',       2),
            ('AUN-2026-002', 'ba@aun.edu.ng',      'student1234', 'Amina Garba',        'Business Administration', 1),
            ('AUN-2026-003', 'econ@aun.edu.ng',    'student1234', 'Emeka Obi',          'Economics',               3),
            ('AUN-2026-004', 'eng@aun.edu.ng',     'student1234', 'Fatima Mohammed',    'Engineering',             2),
        ]

        for sid, email, pwd, name, program, year in students_data:
            if not User.objects.filter(email=email).exists():
                u = User.objects.create(
                    name=name, email=email,
                    passwordHash=make_password(pwd), role='student',
                )
                s = Student.objects.create(
                    studentID=sid, user=u,
                    program=program, yearLevel=year, cumulativeGPA=0.0,
                )
                # Add some completed courses so pages have real data
                completed = {
                    'Computer Science': [('CS101', 'A'), ('CS102', 'B+')],
                    'Business Administration': [('BA101', 'B')],
                    'Economics': [('EC101', 'A'), ('EC102', 'B'), ('EC201', 'B+')],
                    'Engineering': [('EN101', 'A'), ('EN102', 'B+')],
                }
                for course_id, grade in completed.get(program, []):
                    Enrollment.objects.get_or_create(
                        student=s, course=course_objs[course_id],
                        semester='Fall 2023',
                        defaults={'status': 'completed', 'grade': grade},
                    )
                # Add a fee record
                Fee.objects.get_or_create(
                    student=s, semester='Fall 2026',
                    defaults={
                        'tuitionAmount': 750000,
                        'accommodationFee': 250000,
                        'mandatoryFees': 60000,
                        'latePenalty': 0,
                        'totalAmount': 1060000,
                    }
                )
                self.stdout.write(f'  Student: {email} / {pwd}')

        self.stdout.write(self.style.SUCCESS('\nDone. Run the server and log in with any account above.'))
