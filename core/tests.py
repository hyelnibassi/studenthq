from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse

from .models import (
    User, Student, Admin, AcademicAdvisor, Course, Prerequisite,
    Enrollment, Fee, Payment, InstallmentPlan, AdvisorComment,
    FeeStructure, AuditLog, CreditOverloadRequest
)
from .services import (
    FeeCalculationEngine, validate_prerequisites,
    get_eligible_courses, simulate_gpa, simulate_payment_penalty
)
from .recommendations import get_recommended_courses
from .views import CURRENT_SEMESTER
from django.core.exceptions import ValidationError


def make_student(email='test@aun.edu.ng', name='Test Student', program='Computer Science'):
    user = User.objects.create(name=name, email=email, passwordHash='hashed', role='student')
    student = Student.objects.create(studentID='AUN-001', user=user, program=program, yearLevel=2, cumulativeGPA=3.0)
    return user, student


def make_fee_structure():
    return FeeStructure.objects.create(
        tuition_per_credit=50000, accommodation_on_campus=250000,
        accommodation_off_campus=180000, sports_fee=15000,
        lab_fee=25000, library_fee=20000, late_penalty_per_month=30000,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
class FeeCalculationTests(TestCase):

    def setUp(self):
        self.fs = make_fee_structure()
        self.engine = FeeCalculationEngine(self.fs)

    def test_basic_tuition_calculation(self):
        result = self.engine.compute(15, 'none', [])
        self.assertEqual(result['tuition'], 15 * 50000)

    def test_on_campus_accommodation(self):
        result = self.engine.compute(12, 'on-campus', [])
        self.assertEqual(result['accommodation_fee'], 250000)

    def test_off_campus_accommodation(self):
        result = self.engine.compute(12, 'off-campus', [])
        self.assertEqual(result['accommodation_fee'], 180000)

    def test_no_accommodation(self):
        result = self.engine.compute(12, 'none', [])
        self.assertEqual(result['accommodation_fee'], 0)

    def test_all_mandatory_fees(self):
        result = self.engine.compute(12, 'none', ['sports', 'lab', 'library'])
        self.assertEqual(result['mandatory_total'], 15000 + 25000 + 20000)

    def test_late_penalty_zero_months(self):
        result = self.engine.compute(15, 'none', [], months_overdue=0)
        self.assertEqual(result['penalty'], 0)

    def test_late_penalty_three_months(self):
        result = self.engine.compute(15, 'none', [], months_overdue=3)
        self.assertEqual(result['penalty'], 90000)

    def test_total_is_sum_of_parts(self):
        result = self.engine.compute(15, 'on-campus', ['sports', 'lab', 'library'], months_overdue=2)
        expected = (15 * 50000) + 250000 + (15000 + 25000 + 20000) + (2 * 30000)
        self.assertEqual(result['total'], expected)

    def test_zero_credits_edge_case(self):
        result = self.engine.compute(0, 'none', [])
        self.assertEqual(result['tuition'], 0)

    def test_aun_2025_2026_official_fee_rates(self):
        fs_2025 = FeeStructure()  # uses 2025/2026 defaults
        engine = FeeCalculationEngine(fs_2025)
        res = engine.compute(
            15, 'triple_with',
            ['sports', 'activity', 'health', 'ebooks', 'lab', 'technology', 'id_card'],
            months_overdue=0, is_law=False, meal_plan='14_meals',
        )
        self.assertEqual(res['tuition'], 1221000)
        self.assertEqual(res['accommodation_fee'], 375000)
        self.assertEqual(res['meal_fee'], 559598)
        self.assertEqual(res['mandatory_total'], 455200)
        self.assertEqual(res['total'], 1221000 + 375000 + 559598 + 455200)
        self.assertEqual(res['annual_total'], res['total'] * 2)

        law_res = engine.compute(18, 'none', [], is_law=True)
        self.assertEqual(law_res['tuition'], 1221000)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
class InstallmentSplitTests(TestCase):

    def setUp(self):
        self.fs = make_fee_structure()
        self.engine = FeeCalculationEngine(self.fs)

    def test_two_installments(self):
        plans = self.engine.split_installments(600000, 2)
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0]['amount'], 300000)

    def test_three_installments(self):
        plans = self.engine.split_installments(600000, 3)
        self.assertEqual(len(plans), 3)
        self.assertAlmostEqual(plans[0]['amount'], 200000)

    def test_invalid_installment_number(self):
        with self.assertRaises(ValueError):
            self.engine.split_installments(600000, 4)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
class PrerequisiteValidationTests(TestCase):

    def setUp(self):
        _, self.student = make_student()
        self.cs101 = Course.objects.create(courseID='CS101', name='Intro to CS', credits=3, department='Computer Science', semesterOffered='Fall')
        self.cs201 = Course.objects.create(courseID='CS201', name='Data Structures', credits=3, department='Computer Science', semesterOffered='Spring')
        Prerequisite.objects.create(course=self.cs201, requiredCourse=self.cs101)

    def test_eligible_when_prerequisite_complete(self):
        Enrollment.objects.create(student=self.student, course=self.cs101, semester='Fall 2023', status='completed', grade='A')
        self.assertTrue(validate_prerequisites(self.student, self.cs201))

    def test_blocked_when_prerequisite_missing(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_prerequisites(self.student, self.cs201)
        self.assertIn('CS101', str(ctx.exception))

    def test_no_prerequisites_always_eligible(self):
        self.assertTrue(validate_prerequisites(self.student, self.cs101))

    def test_enrolled_but_not_completed_does_not_qualify(self):
        Enrollment.objects.create(student=self.student, course=self.cs101, semester='Fall 2026', status='enrolled')
        with self.assertRaises(ValidationError):
            validate_prerequisites(self.student, self.cs201)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
class GPASimulatorTests(TestCase):

    def setUp(self):
        _, self.student = make_student(email='gpa@aun.edu.ng')
        cs101 = Course.objects.create(courseID='CS101', name='Intro to CS', credits=3, department='Computer Science', semesterOffered='Fall')
        Enrollment.objects.create(student=self.student, course=cs101, semester='Fall 2023', status='completed', grade='A')

    def test_projected_gpa_higher_than_current(self):
        result = simulate_gpa(self.student, [{'name': 'Math', 'credits': 3, 'grade': 'A'}])
        self.assertGreaterEqual(result['projected_gpa'], result['current_gpa'])

    def test_f_grade_lowers_gpa(self):
        result = simulate_gpa(self.student, [{'name': 'Math', 'credits': 3, 'grade': 'F'}])
        self.assertLess(result['projected_gpa'], result['current_gpa'])

    def test_empty_hypothetical_returns_current(self):
        result = simulate_gpa(self.student, [])
        self.assertEqual(result['projected_gpa'], result['current_gpa'])

    def test_grade_point_map_accuracy(self):
        result = simulate_gpa(self.student, [{'name': 'Algo', 'credits': 3, 'grade': 'B+'}])
        course = next(c for c in result['courses'] if c['name'] == 'Algo')
        self.assertEqual(course['grade_point'], 3.5)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
class PaymentPenaltySimulatorTests(TestCase):

    def test_no_penalty_if_on_time(self):
        due = date.today()
        planned = date.today()
        result = simulate_payment_penalty(500000, due, planned)
        self.assertEqual(result['penalty'], 0)
        self.assertEqual(result['total'], 500000)

    def test_one_month_late(self):
        due = date(2026, 1, 1)
        planned = date(2026, 2, 1)
        result = simulate_payment_penalty(500000, due, planned)
        self.assertEqual(result['penalty'], 30000)
        self.assertEqual(result['total'], 530000)

    def test_three_months_late(self):
        due = date(2026, 1, 1)
        planned = date(2026, 4, 1)
        result = simulate_payment_penalty(500000, due, planned)
        self.assertEqual(result['penalty'], 90000)
        self.assertEqual(result['total'], 590000)

    def test_partial_month_counts_as_full(self):
        due = date(2026, 1, 1)
        planned = date(2026, 2, 15)
        result = simulate_payment_penalty(500000, due, planned)
        self.assertGreaterEqual(result['months_overdue'], 2)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
class AuthTests(TestCase):

    def setUp(self):
        self.client = Client()
        from django.contrib.auth.hashers import make_password
        self.user = User.objects.create(
            name='Auth User', email='auth@aun.edu.ng',
            passwordHash=make_password('testpass123'), role='student'
        )
        self.student = Student.objects.create(
            studentID='AUN-AUTH', user=self.user,
            program='Computer Science', yearLevel=1, cumulativeGPA=0.0
        )

    def test_login_correct_credentials(self):
        response = self.client.post(reverse('login'), {'email': 'auth@aun.edu.ng', 'password': 'testpass123'})
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_wrong_password(self):
        response = self.client.post(reverse('login'), {'email': 'auth@aun.edu.ng', 'password': 'wrongpass'})
        self.assertEqual(response.status_code, 200)

    def test_login_nonexistent_email(self):
        response = self.client.post(reverse('login'), {'email': 'nobody@aun.edu.ng', 'password': 'pass'})
        self.assertEqual(response.status_code, 200)

    def test_dashboard_redirects_if_not_logged_in(self):
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('login'))

    def test_signup_student_id_format_validation(self):
        # Invalid format should fail
        bad = self.client.post(reverse('signup'), {
            'name': 'New Student',
            'student_id': 'AUN-2026-999',
            'email': 'newstud@aun.edu.ng',
            'program': 'Computer Science',
            'year_level': '1',
            'password1': 'securepass123',
            'password2': 'securepass123',
        })
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(Student.objects.filter(studentID='AUN-2026-999').exists())

        # Valid A00024499 format should succeed
        good = self.client.post(reverse('signup'), {
            'name': 'New Student',
            'student_id': 'A00024499',
            'email': 'newstud@aun.edu.ng',
            'program': 'Computer Science',
            'year_level': '1',
            'password1': 'securepass123',
            'password2': 'securepass123',
        })
        self.assertRedirects(good, reverse('login'))
        self.assertTrue(Student.objects.filter(studentID='A00024499').exists())


class AdvisorTests(TestCase):

    def setUp(self):
        from django.contrib.auth.hashers import make_password
        self.client = Client()
        self.admin_user = User.objects.create(name='Admin User', email='admin@aun.edu.ng', passwordHash=make_password('adminpass'), role='admin')
        Admin.objects.create(user=self.admin_user, department='Finance')
        self.advisor_user = User.objects.create(name='Advisor User', email='advisor@aun.edu.ng', passwordHash=make_password('advisorpass'), role='advisor')
        self.advisor = AcademicAdvisor.objects.create(user=self.advisor_user, department='Computer Science')
        self.student_user = User.objects.create(name='Adv Student', email='advstudent@aun.edu.ng', passwordHash=make_password('studentpass'), role='student')
        self.student = Student.objects.create(studentID='AUN-XYZ', user=self.student_user, program='Computer Science', yearLevel=2, cumulativeGPA=3.2)
        self.course = Course.objects.create(courseID='CS101', name='Intro to CS', credits=3, department='Computer Science', semesterOffered='Fall')
        self.comment = AdvisorComment.objects.create(student=self.student, advisor=self.advisor, comment='Keep up the good work.')

    def test_advisor_student_progress_access(self):
        self.client.post(reverse('login'), {'email': 'advisor@aun.edu.ng', 'password': 'advisorpass'})
        response = self.client.get(reverse('advisor_student_progress'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Adv Student')

    def test_advisor_student_search(self):
        self.client.post(reverse('login'), {'email': 'advisor@aun.edu.ng', 'password': 'advisorpass'})
        response = self.client.get(reverse('advisor_student_progress') + '?q=Adv')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Adv Student')

    def test_advisor_add_comment(self):
        self.client.post(reverse('login'), {'email': 'advisor@aun.edu.ng', 'password': 'advisorpass'})
        response = self.client.post(reverse('advisor_comment', args=[self.student.studentID]), {'comment': 'Needs improvement.'})
        self.assertRedirects(response, reverse('advisor_student_progress'))
        self.assertTrue(AdvisorComment.objects.filter(student=self.student, comment='Needs improvement.').exists())
        self.assertTrue(AuditLog.objects.filter(action='advisor_comment', description__icontains=str(self.student.studentID)).exists())


class AuditLoggingTests(TestCase):

    def setUp(self):
        from django.contrib.auth.hashers import make_password
        self.client = Client()
        self.admin_user = User.objects.create(
            name='Audit Admin', email='auditadmin@aun.edu.ng',
            passwordHash=make_password('adminpass123'), role='admin'
        )
        Admin.objects.create(user=self.admin_user, department='Finance')
        self.student_user = User.objects.create(
            name='Audit Student', email='auditstudent@aun.edu.ng',
            passwordHash=make_password('studentpass123'), role='student'
        )
        self.student = Student.objects.create(
            studentID='AUN-AUDIT', user=self.student_user,
            program='Computer Science', yearLevel=2, cumulativeGPA=2.8
        )
        self.fee = Fee.objects.create(
            student=self.student, semester=CURRENT_SEMESTER,
            tuitionAmount=400000, accommodationFee=200000,
            mandatoryFees=50000, latePenalty=0, totalAmount=650000
        )
        self.payment = Payment.objects.create(
            fee=self.fee, student=self.student,
            amountPaid=150000, paymentDate=date.today(), status='pending'
        )
        self.plan = InstallmentPlan.objects.create(
            fee=self.fee, student=self.student,
            numInstallments=2, dueDate=date.today(), amountPerInstall=325000,
            is_approved=False, reason='Need additional time', semester=CURRENT_SEMESTER
        )

    def test_admin_verify_payment_creates_audit_log(self):
        self.client.post(reverse('login'), {'email': 'auditadmin@aun.edu.ng', 'password': 'adminpass123'})
        response = self.client.post(reverse('verify_payment', args=[self.payment.paymentID]), {'action': 'verify'})
        self.assertRedirects(response, reverse('admin_payment_verification'))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'completed')
        self.assertTrue(AuditLog.objects.filter(action='payment_verified', description__icontains=str(self.payment.paymentID)).exists())

    def test_admin_reject_payment_creates_audit_log(self):
        self.client.post(reverse('login'), {'email': 'auditadmin@aun.edu.ng', 'password': 'adminpass123'})
        response = self.client.post(reverse('verify_payment', args=[self.payment.paymentID]), {'action': 'reject'})
        self.assertRedirects(response, reverse('admin_payment_verification'))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'rejected')
        self.assertTrue(AuditLog.objects.filter(action='payment_rejected', description__icontains=str(self.payment.paymentID)).exists())

    def test_admin_approve_deferral_creates_audit_log(self):
        self.client.post(reverse('login'), {'email': 'auditadmin@aun.edu.ng', 'password': 'adminpass123'})
        response = self.client.post(reverse('approve_deferral', args=[self.plan.planID]), {'action': 'approve'})
        self.assertRedirects(response, reverse('admin_payment_verification'))
        self.plan.refresh_from_db()
        self.assertTrue(self.plan.is_approved)
        self.assertTrue(AuditLog.objects.filter(action='deferral_approved', description__icontains=self.student.studentID).exists())

    def test_admin_reject_deferral_creates_audit_log(self):
        second_plan = InstallmentPlan.objects.create(
            fee=self.fee, student=self.student, numInstallments=2,
            dueDate=date.today(), amountPerInstall=325000,
            is_approved=False, reason='Second request', semester=CURRENT_SEMESTER
        )
        self.client.post(reverse('login'), {'email': 'auditadmin@aun.edu.ng', 'password': 'adminpass123'})
        response = self.client.post(reverse('approve_deferral', args=[second_plan.planID]), {'action': 'reject'})
        self.assertRedirects(response, reverse('admin_payment_verification'))
        self.assertFalse(InstallmentPlan.objects.filter(planID=second_plan.planID).exists())
        self.assertTrue(AuditLog.objects.filter(action='deferral_rejected', description__icontains=str(self.student.studentID)).exists())

    def test_financial_report_export_creates_audit_log(self):
        self.client.post(reverse('login'), {'email': 'auditadmin@aun.edu.ng', 'password': 'adminpass123'})
        response = self.client.get(reverse('admin_financial_report_export'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='financial_report_export', description__icontains='exported').exists())

    def test_student_payment_history_export_creates_audit_log(self):
        self.client.post(reverse('login'), {'email': 'auditstudent@aun.edu.ng', 'password': 'studentpass123'})
        response = self.client.get(reverse('payment_history_export'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='user_action', description__icontains=str(self.student.studentID)).exists())

    def test_student_profile_update_creates_audit_log(self):
        self.client.post(reverse('login'), {'email': 'auditstudent@aun.edu.ng', 'password': 'studentpass123'})
        response = self.client.post(reverse('profile'), {'name': 'Updated Name', 'program': 'Economics', 'year_level': '3'})
        self.assertRedirects(response, reverse('profile'))
        self.assertTrue(AuditLog.objects.filter(action='user_action', description__icontains=str(self.student.studentID)).exists())

    def test_student_change_password_creates_audit_log(self):
        self.client.post(reverse('login'), {'email': 'auditstudent@aun.edu.ng', 'password': 'studentpass123'})
        response = self.client.post(reverse('change_password'), {
            'current_password': 'studentpass123',
            'new_password1': 'newsecurepass123',
            'new_password2': 'newsecurepass123'
        })
        self.assertRedirects(response, reverse('profile'))
        self.assertTrue(AuditLog.objects.filter(action='user_action', description__icontains=str(self.student.user.userID)).exists())

class NotificationsRecommendationsTests(TestCase):

    def setUp(self):
        from django.contrib.auth.hashers import make_password
        self.client = Client()
        self.user = User.objects.create(name='Test Student', email='notify@aun.edu.ng', passwordHash=make_password('testpass123'), role='student')
        self.student = Student.objects.create(studentID='AUN-NOT', user=self.user, program='Computer Science', yearLevel=1, cumulativeGPA=3.0)
        self.fee = Fee.objects.create(student=self.student, semester='Fall 2026', tuitionAmount=500000, accommodationFee=250000, mandatoryFees=60000, latePenalty=30000, totalAmount=810000)

    def test_dashboard_creates_fee_notification(self):
        self.client.post(reverse('login'), {'email': 'notify@aun.edu.ng', 'password': 'testpass123'})
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'outstanding balance')

    def test_get_recommended_courses_for_student(self):
        # Create the sequence course and prerequisite data used by recommendations.
        cs101 = Course.objects.create(courseID='CS101', name='Intro to CS', credits=3, department='Computer Science', semesterOffered='Fall')
        cs102 = Course.objects.create(courseID='CS102', name='Discrete Math', credits=3, department='Computer Science', semesterOffered='Spring')
        recommendations = get_recommended_courses(self.student, 'Fall 2026')
        self.assertTrue(isinstance(recommendations, list))
        self.assertGreaterEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]['course'].courseID, 'CS101')


class CatalogImportAndFilterTests(TestCase):

    def setUp(self):
        from django.contrib.auth.hashers import make_password
        self.client = Client()
        self.user = User.objects.create(
            name='Catalog Student', email='catstudent@aun.edu.ng',
            passwordHash=make_password('studentpass123'), role='student'
        )
        Student.objects.create(
            studentID='AUN-CAT', user=self.user,
            program='Computer Science', yearLevel=2, cumulativeGPA=3.5
        )

    def test_import_catalog_command_and_filtering(self):
        from django.core.management import call_command
        call_command('import_catalog')
        self.assertGreaterEqual(Course.objects.count(), 500)
        self.assertTrue(Course.objects.filter(courseID='CSC202', school='SITC').exists())
        self.assertTrue(Course.objects.filter(school='SOE').exists())
        self.assertTrue(Course.objects.filter(school='SAS').exists())

        self.client.post(reverse('login'), {'email': 'catstudent@aun.edu.ng', 'password': 'studentpass123'})
        resp = self.client.get(reverse('course_catalog') + '?school=SITC&search=CSC202')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'CSC202')


class CourseRegistrationSmartFeaturesTests(TestCase):

    def setUp(self):
        from django.contrib.auth.hashers import make_password
        self.client = Client()
        self.user = User.objects.create(
            name='Reg Student', email='regstudent@aun.edu.ng',
            passwordHash=make_password('studentpass123'), role='student'
        )
        self.student = Student.objects.create(
            studentID='AUN-REG', user=self.user,
            program='Computer Science', yearLevel=2, cumulativeGPA=3.6
        )
        # Create 10 courses: 1 completed CS, 2 eligible CS, 1 CS with unmet prereq, 6 free electives
        self.cs101 = Course.objects.create(courseID='CS101', name='Intro to CS', credits=3, school='SITC', department='Computer Science', semesterOffered='Fall')
        self.cs201 = Course.objects.create(courseID='CS201', name='Data Structures', credits=3, school='SITC', department='Computer Science', semesterOffered='Fall')
        self.cs301 = Course.objects.create(courseID='CS301', name='Algorithms', credits=3, school='SITC', department='Computer Science', semesterOffered='Fall')
        self.cs401 = Course.objects.create(courseID='CS401', name='Capstone', credits=3, school='SITC', department='Computer Science', semesterOffered='Spring')
        Prerequisite.objects.create(course=self.cs201, requiredCourse=self.cs101)
        Prerequisite.objects.create(course=self.cs401, requiredCourse=self.cs301)
        Enrollment.objects.create(student=self.student, course=self.cs101, semester='Fall 2024', status='completed', grade='A')

        for i in range(1, 8):
            Course.objects.create(
                courseID=f'ECO10{i}', name=f'Economics Elective {i}',
                credits=3, school='SAS', department='Economics', semesterOffered='Fall'
            )

        self.client.post(reverse('login'), {'email': 'regstudent@aun.edu.ng', 'password': 'studentpass123'})

    def test_pagination_8_per_page_and_smart_priority_order(self):
        resp = self.client.get(reverse('course_registration'))
        self.assertEqual(resp.status_code, 200)
        page_obj = resp.context['available_courses']
        self.assertEqual(len(page_obj.object_list), 8)
        # First items must be uncompleted eligible CS courses (CS201, CS301) before CS401 (unmet prereq) and ECO electives
        codes = [item['course'].courseID for item in page_obj.object_list]
        self.assertEqual(codes[0], 'CS201')
        self.assertEqual(codes[1], 'CS301')
        self.assertIn('CS401', codes[:4])

    def test_search_finds_free_electives_outside_program(self):
        resp = self.client.get(reverse('course_registration') + '?search=ECO105')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ECO105')
        self.assertEqual(resp.context['total_available'], 1)

    def test_credit_limit_18_enforced_and_overload_request(self):
        # Try registering 7 courses (21 credits > 18 default max) -> blocked
        resp = self.client.post(reverse('course_registration'), {
            'course_ids': ['CS201', 'CS301', 'ECO101', 'ECO102', 'ECO103', 'ECO104', 'ECO105']
        })
        self.assertRedirects(resp, reverse('course_registration'))
        self.assertEqual(Enrollment.objects.filter(student=self.student, semester=CURRENT_SEMESTER).count(), 0)

        # Submit a credit overload request for 21 credits
        ov_resp = self.client.post(reverse('request_credit_overload'), {
            'requested_credits': '21',
            'reason': 'Graduating on schedule with strong GPA.',
        })
        self.assertRedirects(ov_resp, reverse('course_registration'))
        req = CreditOverloadRequest.objects.filter(student=self.student, semester=CURRENT_SEMESTER).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.requested_credits, 21)
        self.assertEqual(req.status, 'pending')

        # Once approved, student can register up to 21 credits
        req.status = 'approved'
        req.save()
        resp2 = self.client.post(reverse('course_registration'), {
            'course_ids': ['CS201', 'CS301', 'ECO101', 'ECO102', 'ECO103', 'ECO104', 'ECO105']
        })
        self.assertRedirects(resp2, reverse('course_registration'))
        self.assertEqual(Enrollment.objects.filter(student=self.student, semester=CURRENT_SEMESTER).count(), 7)
