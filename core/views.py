from datetime import date
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q

from .models import (
    User, Student, Admin, AcademicAdvisor, Course, Enrollment,
    Fee, Payment, InstallmentPlan, AdvisorComment,
    FeeStructure, FeeStructureChangeLog, AuditLog, CreditOverloadRequest
)
from .services import (
    FeeCalculationEngine, validate_prerequisites,
    get_eligible_courses, get_smart_registration_courses,
    simulate_gpa, simulate_payment_penalty
)
from .audit import log_action
from .notifications import check_and_create_fee_notifications, check_course_notifications
from .recommendations import get_recommended_courses

def get_current_semester():
    m = date.today().month
    y = date.today().year
    if m >= 9:
        term = 'Fall'
    elif m >= 6:
        term = 'Summer'
    else:
        term = 'Spring'
    return f"{term} {y}"

CURRENT_SEMESTER = get_current_semester()
# Auth helpers
def get_logged_in_user(request):
    uid = request.session.get('user_id')
    if not uid:
        return None
    try:
        return User.objects.get(userID=uid)
    except User.DoesNotExist:
        return None


def login_required_custom(view_func):
    def wrapper(request, *args, **kwargs):
        if not get_logged_in_user(request):
            return redirect('login')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def role_required(role):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            user = get_logged_in_user(request)
            if not user:
                return redirect('login')
            if user.role != role:
                messages.error(request, "You do not have permission to access that page.")
                return redirect('login')
            return view_func(request, *args, **kwargs)
        wrapper.__name__ = view_func.__name__
        return wrapper
    return decorator
def login_view(request):
    if request.method == 'POST':
        email    = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        try:
            user = User.objects.get(email__iexact=email)
            if check_password(password, user.passwordHash):
                request.session['user_id'] = user.userID
                log_action(user, 'user_login', f"{user.role.title()} logged in.", request)
                if user.role == 'admin':
                    return redirect('admin_fee_structure')
                elif user.role == 'advisor':
                    return redirect('advisor_student_progress')
                return redirect('dashboard')
            else:
                messages.error(request, "Invalid password.")
        except User.DoesNotExist:
            messages.error(request, "No account found with that email.")
    return render(request, 'studenthq/login.html')


def signup_view(request):
    PROGRAMS = [
        'Computer Science',
        'Business Administration',
        'Economics',
        'Engineering',
    ]
    if request.method == 'POST':
        name       = request.POST.get('name', '').strip()
        email      = request.POST.get('email', '').strip().lower()
        password1  = request.POST.get('password1', '')
        password2  = request.POST.get('password2', '')
        program    = request.POST.get('program', '')
        year_level = request.POST.get('year_level', '1')
        student_id = request.POST.get('student_id', '').strip().upper()

        errors = []
        if not name:
            errors.append("Full name is required.")
        if not email:
            errors.append("Email is required.")
        if not student_id:
            errors.append("Student ID is required.")
        elif not re.fullmatch(r'A\d{8}', student_id):
            errors.append("Student ID must be in the format A00024499 (letter A followed by 8 digits).")
        if password1 != password2:
            errors.append("Passwords do not match.")
        if len(password1) < 8:
            errors.append("Password must be at least 8 characters.")
        if program not in PROGRAMS:
            errors.append("Please select a valid program.")
        if User.objects.filter(email=email).exists():
            errors.append("An account with that email already exists.")
        if Student.objects.filter(studentID=student_id).exists():
            errors.append("That Student ID is already registered.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'studenthq/signup.html', {
                'programs': PROGRAMS,
                'form_data': request.POST,
            })

        user = User.objects.create(
            name=name,
            email=email,
            passwordHash=make_password(password1),
            role='student',
        )
        Student.objects.create(
            studentID=student_id,
            user=user,
            program=program,
            yearLevel=int(year_level),
            cumulativeGPA=0.0,  # always starts at 0 — builds from completed courses
        )
        log_action(user, 'user_signup', f"Student account created for {email}.", request)
        messages.success(request, "Account created successfully. Please log in.")
        return redirect('login')

    return render(request, 'studenthq/signup.html', {
        'programs': [
            'Computer Science',
            'Business Administration',
            'Economics',
            'Engineering',
        ],
    })


def logout_view(request):
    request.session.flush()
    return redirect('login')
@role_required('student')
def dashboard(request):
    user = get_logged_in_user(request)
    student = get_object_or_404(Student, user=user)
    current_semester = CURRENT_SEMESTER

    latest_fee = student.fees.filter(semester=current_semester).first()
    outstanding = latest_fee.outstanding() if latest_fee else 0

    upcoming = []
    if latest_fee:
        for plan in latest_fee.installment_plans.filter(is_approved=True):
            upcoming.append({'due_date': plan.dueDate, 'amount': plan.amountPerInstall, 'status': 'pending'})

    # Calculate real GPA from completed enrollments — never show stored/seeded value
    completed = student.enrollments.filter(status='completed').select_related('course')
    gpa_entries = [(e.grade_points(), e.course.credits) for e in completed if e.grade_points() is not None]
    live_gpa = (
        sum(gp * cr for gp, cr in gpa_entries) / sum(cr for _, cr in gpa_entries)
        if gpa_entries else None  # None means not yet earned
    )

    # Update stored cumulativeGPA to match live calculation
    if live_gpa is not None:
        student.cumulativeGPA = round(live_gpa, 2)
        student.save()

    try:
        check_and_create_fee_notifications(student)
        check_course_notifications(student, current_semester)
    except Exception:
        # don't break dashboard for notification errors
        pass

    notifications_qs = student.notifications.all().order_by('-date')[:10]

    try:
        recommendations = get_recommended_courses(student, current_semester)
    except Exception:
        recommendations = []

    return render(request, 'studenthq/dashboard.html', {
        'user': user,
        'student': student,
        'current_semester': current_semester,
        'outstanding_balance': outstanding,
        'credits_completed': student.credits_completed(),
        'graduation_percentage': student.graduation_percentage(),
        'upcoming_payments': upcoming,
        'notifications': notifications_qs,
        'recommendations': recommendations,
        'next_due_date': upcoming[0]['due_date'] if upcoming else None,
        'live_gpa': live_gpa,
    })
def get_fee_structure():
    try:
        return FeeStructure.objects.filter(pk=1).first() or FeeStructure()
    except Exception:
        return FeeStructure()


@role_required('student')
def fee_calculator(request):
    user      = get_logged_in_user(request)
    result    = None
    fs        = get_fee_structure()
    engine    = FeeCalculationEngine(fs)
    form_data = {
        'credit_hours': 15,
        'program_type': 'standard',
        'accommodation': 'triple_with',
        'meal_plan': '7_meals',
        'fees': ['sports', 'activity', 'health', 'technology'],
        'months_overdue': 0,
    }

    if request.method == 'POST':
        credit_hours   = int(request.POST.get('credit_hours', 15))
        program_type   = request.POST.get('program_type', 'standard')
        is_law         = (program_type == 'law')
        accommodation  = request.POST.get('accommodation', 'none')
        meal_plan      = request.POST.get('meal_plan', 'none')
        fees_selected  = request.POST.getlist('fees')
        months_overdue = int(request.POST.get('months_overdue', 0))

        # AUN Policy Note #3: On-campus residents must have at least 7 meals/week
        on_campus_keys = {'double_with', 'double_without', 'triple_with', 'triple_without', 'four_with', 'on-campus'}
        if accommodation in on_campus_keys and meal_plan == 'none':
            meal_plan = '7_meals'
            messages.info(request, "Per AUN policy, students living in residence halls are required to have a meal plan (minimum 7 meals/week). Automatically applied 7 Meals/Week.")

        form_data = {
            'credit_hours':   credit_hours,
            'program_type':   program_type,
            'accommodation':  accommodation,
            'meal_plan':      meal_plan,
            'fees':           fees_selected,
            'months_overdue': months_overdue,
        }
        result = engine.compute(
            credit_hours, accommodation, fees_selected,
            months_overdue=months_overdue, is_law=is_law, meal_plan=meal_plan
        )

    return render(request, 'studenthq/fee_calculator.html', {
        'user': user,
        'result': result,
        'form_data': form_data,
        'fee_structure': fs,
    })
@role_required('student')
def payment_history(request):
    user     = get_logged_in_user(request)
    student  = get_object_or_404(Student, user=user)
    qs       = student.payments.all().order_by('-paymentDate')
    paginator = Paginator(qs, 10)
    page_obj  = paginator.get_page(request.GET.get('page'))

    total_paid     = sum(p.amountPaid for p in qs.filter(status='completed'))
    total_penalties = sum(f.latePenalty for f in student.fees.all())
    latest_fee     = student.fees.last()
    outstanding    = latest_fee.outstanding() if latest_fee else 0

    return render(request, 'studenthq/payment_history.html', {
        'user': user, 'student': student, 'payments': page_obj,
        'total_paid': total_paid, 'outstanding_balance': outstanding,
        'total_penalties': total_penalties,
    })


@role_required('student')
def payment_history_export(request):
    import csv
    from django.http import HttpResponse
    user = get_logged_in_user(request)
    student  = get_object_or_404(Student, user=user)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payment_history.csv"'
    writer   = csv.writer(response)
    writer.writerow(['Payment ID', 'Date', 'Amount (N)', 'Type', 'Status'])
    for p in student.payments.all().order_by('-paymentDate'):
        writer.writerow([p.paymentID, p.paymentDate, p.amountPaid, p.payment_type, p.status])
    log_action(user, 'user_action', f"Student {student.studentID} exported payment history.", request)
    return response
@role_required('student')
def installment_plan(request):
    user       = get_logged_in_user(request)
    student    = get_object_or_404(Student, user=user)
    latest_fee = student.fees.filter(semester=CURRENT_SEMESTER).first()
    active_plan = student.installment_plans.filter(is_approved=True).last()
    return render(request, 'studenthq/installment_plan.html', {
        'user': user, 'student': student,
        'fee': latest_fee, 'active_plan': active_plan,
    })


@role_required('student')
def create_installment_plan(request):
    if request.method == 'POST':
        user    = get_logged_in_user(request)
        student = get_object_or_404(Student, user=user)
        num     = int(request.POST.get('num_installments', 2))
        fee     = student.fees.filter(semester=CURRENT_SEMESTER).first()
        if fee and num in (2, 3):
            amount_per = fee.outstanding() / num
            plan = InstallmentPlan.objects.create(
                fee=fee, student=student,
                numInstallments=num,
                dueDate=date.today(),
                amountPerInstall=amount_per,
                semester=CURRENT_SEMESTER,
                is_approved=False,
            )
            log_action(user, 'installment_plan_request',
                f"Student {student.studentID} requested {num} installment plan(s) for {CURRENT_SEMESTER}.", request)
            messages.success(request,
                f"Installment plan submitted: {num} payments of \u20a6{amount_per:,.0f} each. "
                "Awaiting admin approval.")
        else:
            messages.error(request, "Could not create plan. Check your fee status.")
    return redirect('installment_plan')


@role_required('student')
def request_deferral(request):
    if request.method == 'POST':
        user    = get_logged_in_user(request)
        student = get_object_or_404(Student, user=user)
        reason  = request.POST.get('reason', '').strip()
        fee     = student.fees.filter(semester=CURRENT_SEMESTER).first()
        if fee and reason:
            plan = InstallmentPlan.objects.create(
                fee=fee, student=student,
                numInstallments=2,
                dueDate=date.today(),
                amountPerInstall=fee.outstanding() / 2,
                is_approved=False,
                reason=reason,
                semester=CURRENT_SEMESTER,
            )
            log_action(user, 'deferral_request',
                f"Student {student.studentID} requested deferral for {CURRENT_SEMESTER}.", request)
            messages.success(request, "Deferral request submitted. Awaiting admin approval.")
        else:
            messages.error(request, "No active fee or reason provided.")
    return redirect('installment_plan')
@role_required('student')
def course_catalog(request):
    user   = get_logged_in_user(request)
    qs     = Course.objects.prefetch_related('prerequisites__requiredCourse').all().order_by('courseID')
    school = request.GET.get('school', '').strip()
    dept   = request.GET.get('department', '').strip()
    sem    = request.GET.get('semester', '').strip()
    search = request.GET.get('search', '').strip()
    if school:
        qs = qs.filter(school=school)
    if dept:
        qs = qs.filter(department=dept)
    if sem:
        qs = qs.filter(semesterOffered=sem)
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(courseID__icontains=search)
            | Q(description__icontains=search)
        )
    total_courses = qs.count()
    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))
    # provide fee structure for dynamic fee display
    fs = get_fee_structure()
    # annotate page courses with computed fee totals
    for course in page_obj.object_list:
        try:
            course.fee_total = int(course.credits * fs.tuition_per_credit)
        except Exception:
            course.fee_total = 0

    departments = (
        Course.objects.values_list('department', flat=True)
        .distinct()
        .order_by('department')
    )
    return render(request, 'studenthq/course_catalog.html', {
        'user': user,
        'courses': page_obj,
        'fee_structure': fs,
        'schools': Course.SCHOOL_CHOICES,
        'departments': departments,
        'total_courses': total_courses,
    })
@role_required('student')
def course_registration(request):
    user     = get_logged_in_user(request)
    student  = get_object_or_404(Student, user=user)
    registered       = student.enrollments.filter(semester=CURRENT_SEMESTER).select_related('course')
    registered_ids   = set(e.course.courseID for e in registered)
    credits_registered = sum(e.course.credits for e in registered)

    # Default maximum: 18 credits (or approved overload limit for this semester)
    approved_overload = (
        student.overload_requests
        .filter(semester=CURRENT_SEMESTER, status='approved')
        .order_by('-requested_credits')
        .first()
    )
    latest_overload_request = (
        student.overload_requests
        .filter(semester=CURRENT_SEMESTER)
        .order_by('-created_at')
        .first()
    )
    max_credits = approved_overload.requested_credits if approved_overload else 18
    credits_remaining = max(max_credits - credits_registered, 0)

    if request.method == 'POST':
        selected_ids   = request.POST.getlist('course_ids')
        enrolled_count = 0
        errors         = []

        # Validate total credits before registering
        selected_courses = list(
            Course.objects.filter(courseID__in=selected_ids)
            .exclude(courseID__in=registered_ids)
            .prefetch_related('prerequisites__requiredCourse')
        )
        added_credits = sum(c.credits for c in selected_courses)
        if credits_registered + added_credits > max_credits:
            messages.error(
                request,
                f"Credit limit exceeded: selecting {added_credits} credit(s) would bring your total to "
                f"{credits_registered + added_credits} credits (maximum allowed: {max_credits}). "
                "Please submit a Credit Overload Request below if you need more than 18 credits."
            )
            return redirect('course_registration')

        for course in selected_courses:
            try:
                validate_prerequisites(student, course)
                Enrollment.objects.create(
                    student=student, course=course,
                    semester=CURRENT_SEMESTER, status='enrolled',
                )
                enrolled_count += 1
            except ValidationError as e:
                errors.append(str(e.message))
            except IntegrityError:
                errors.append(f"{course.courseID} is already registered.")

        if enrolled_count:
            log_action(
                user, 'user_action',
                f"Student {student.studentID} registered {enrolled_count} new course(s) for {CURRENT_SEMESTER}.",
                request,
            )
            messages.success(request, f"Successfully registered {enrolled_count} course(s).")
        if errors:
            for err in errors:
                messages.error(request, err)
        return redirect('course_registration')

    # Smart recommendations (always computed from all unregistered courses)
    base_available = (
        Course.objects.exclude(courseID__in=registered_ids)
        .prefetch_related('prerequisites__requiredCourse')
    )
    all_ranked = get_smart_registration_courses(student, base_available)
    recommended_courses = [item for item in all_ranked if item['is_recommended']][:6]

    # Search & filter across ALL available courses (including free electives)
    search = request.GET.get('search', '').strip()
    school = request.GET.get('school', '').strip()
    dept   = request.GET.get('department', '').strip()

    filtered_items = all_ranked
    if school:
        filtered_items = [i for i in filtered_items if i['course'].school == school]
    if dept:
        filtered_items = [i for i in filtered_items if i['course'].department == dept]
    if search:
        q_low = search.lower()
        filtered_items = [
            i for i in filtered_items
            if q_low in i['course'].courseID.lower()
            or q_low in i['course'].name.lower()
            or q_low in i['course'].department.lower()
            or q_low in (i['course'].description or '').lower()
        ]

    # Paginate 8 courses per page
    paginator = Paginator(filtered_items, 8)
    page_obj  = paginator.get_page(request.GET.get('page'))

    departments = (
        Course.objects.values_list('department', flat=True)
        .distinct()
        .order_by('department')
    )

    return render(request, 'studenthq/course_registration.html', {
        'user': user,
        'student': student,
        'available_courses': page_obj,
        'total_available': len(filtered_items),
        'recommended_courses': recommended_courses,
        'registered_courses': registered,
        'registered_ids': registered_ids,
        'credits_registered': credits_registered,
        'max_credits': max_credits,
        'credits_remaining': credits_remaining,
        'latest_overload_request': latest_overload_request,
        'current_semester': CURRENT_SEMESTER,
        'schools': Course.SCHOOL_CHOICES,
        'departments': departments,
    })


@role_required('student')
def request_credit_overload(request):
    if request.method == 'POST':
        user    = get_logged_in_user(request)
        student = get_object_or_404(Student, user=user)
        reason  = request.POST.get('reason', '').strip()
        try:
            requested_credits = int(request.POST.get('requested_credits', 21))
        except (ValueError, TypeError):
            requested_credits = 21

        if requested_credits < 19 or requested_credits > 24:
            messages.error(request, "Overload request must be between 19 and 24 credit hours.")
        elif not reason:
            messages.error(request, "Please provide an academic justification for your credit overload request.")
        else:
            CreditOverloadRequest.objects.create(
                student=student,
                semester=CURRENT_SEMESTER,
                requested_credits=requested_credits,
                reason=reason,
                status='pending',
            )
            log_action(
                user, 'credit_overload_request',
                f"Student {student.studentID} requested a credit overload of {requested_credits} credits for {CURRENT_SEMESTER}.",
                request,
            )
            messages.success(
                request,
                f"Credit overload request for {requested_credits} credits submitted for advisor/registry review."
            )
    return redirect('course_registration')
@role_required('student')
def academic_progress(request):
    user     = get_logged_in_user(request)
    student  = get_object_or_404(Student, user=user)
    transcript       = student.enrollments.filter(status='completed').select_related('course').order_by('semester')
    current_courses  = student.enrollments.filter(semester=CURRENT_SEMESTER).select_related('course')
    completed_credits = student.credits_completed()
    graduation_pct   = student.graduation_percentage()
    gpa_entries = [(e.grade_points(), e.course.credits) for e in transcript if e.grade_points() is not None]
    current_gpa = (
        sum(gp * cr for gp, cr in gpa_entries) / sum(cr for _, cr in gpa_entries)
        if gpa_entries else 0.0
    )
    return render(request, 'studenthq/academic_progress.html', {
        'user': user, 'student': student,
        'transcript':          transcript,
        'current_courses':     current_courses,
        'credits_completed':   completed_credits,
        'graduation_percentage': graduation_pct,
        'current_gpa':         round(current_gpa, 2),
        'core_completed':      min(completed_credits, 60),
        'core_required':       60,
        'electives_completed': max(0, min(completed_credits - 60, 30)),
        'electives_required':  30,
        'gen_ed_completed':    max(0, min(completed_credits - 90, 30)),
        'gen_ed_required':     30,
    })
@role_required('student')
def gpa_simulator(request):
    user    = get_logged_in_user(request)
    student = get_object_or_404(Student, user=user)
    result  = None
    form_courses  = []
    grade_options = ['A', 'B+', 'B', 'C+', 'C', 'D+', 'D', 'F']

    if request.method == 'POST':
        names        = request.POST.getlist('course_name')
        credits_list = request.POST.getlist('credits')
        grades       = request.POST.getlist('grade')
        hypothetical = []
        for name, credits, grade in zip(names, credits_list, grades):
            if name and credits and grade:
                hypothetical.append({'name': name, 'credits': int(credits), 'grade': grade})
                form_courses.append({'name': name, 'credits': credits, 'grade': grade})
        if hypothetical:
            result = simulate_gpa(student, hypothetical)

    return render(request, 'studenthq/gpa_simulator.html', {
        'user': user, 'student': student,
        'result':           result,
        'form_courses':     form_courses,
        'grade_options':    grade_options,
        'credits_completed': student.credits_completed(),
    })
@role_required('student')
def payment_simulator(request):
    user      = get_logged_in_user(request)
    result    = None
    form_data = {}
    if request.method == 'POST':
        try:
            amount_due   = float(request.POST.get('amount_due', 0))
            due_date     = date.fromisoformat(request.POST.get('due_date'))
            planned_date = date.fromisoformat(request.POST.get('planned_date'))
            form_data = {
                'amount_due':   amount_due,
                'due_date':     request.POST.get('due_date'),
                'planned_date': request.POST.get('planned_date'),
            }
            result = simulate_payment_penalty(amount_due, due_date, planned_date)
        except (ValueError, TypeError):
            messages.error(request, "Invalid input. Please check your dates and amount.")
    return render(request, 'studenthq/payment_penalty_simulator.html', {
        'user': user, 'result': result, 'form_data': form_data,
    })
@role_required('admin')
def admin_fee_structure(request):
    user           = get_logged_in_user(request)
    fs, _          = FeeStructure.objects.get_or_create(pk=1)
    change_history = FeeStructureChangeLog.objects.select_related('changed_by').order_by('-changed_at')[:20]

    if request.method == 'POST':
        fields = [
            'tuition_per_credit', 'law_tuition_flat',
            'housing_double_with_facilities', 'housing_double_without_facilities',
            'housing_triple_with_facilities', 'housing_triple_without_facilities',
            'housing_four_with_facilities',
            'accommodation_on_campus', 'accommodation_off_campus',
            'meal_plan_21', 'meal_plan_14', 'meal_plan_7',
            'sports_fee', 'student_activity_fee', 'health_insurance_fee',
            'ebooks_fee', 'lab_fee', 'technology_fee', 'student_id_card_fee',
            'library_fee',
        ]
        changed_any = False
        for field in fields:
            try:
                new_val = float(request.POST.get(field, getattr(fs, field)))
            except (ValueError, TypeError):
                continue
            old_val = getattr(fs, field)
            if new_val != old_val:
                FeeStructureChangeLog.objects.create(
                    field_name=field, old_value=old_val,
                    new_value=new_val, changed_by=user,
                )
                setattr(fs, field, new_val)
                changed_any = True
        if changed_any:
            fs.save()
            log_action(user, 'fee_structure_update',
                f"Admin updated fee structure values.", request)
            messages.success(request, "Fee structure updated successfully.")
        else:
            messages.info(request, "No fee structure changes were made.")
        return redirect('admin_fee_structure')

    return render(request, 'studenthq/admin_fee_structure.html', {
        'user': user, 'fee_structure': fs, 'change_history': change_history,
    })


@role_required('admin')
def admin_payment_verification(request):
    user             = get_logged_in_user(request)
    pending_payments = Payment.objects.filter(status='pending').select_related('student__user')
    deferral_requests = InstallmentPlan.objects.filter(is_approved=False, reason__gt='').select_related('student__user')
    return render(request, 'studenthq/admin_payment_verification.html', {
        'user': user,
        'pending_payments':   pending_payments,
        'deferral_requests':  deferral_requests,
    })


@role_required('admin')
def verify_payment(request, payment_id):
    if request.method == 'POST':
        user = get_logged_in_user(request)
        payment = get_object_or_404(Payment, paymentID=payment_id)
        action  = request.POST.get('action')
        if action == 'verify':
            payment.status = 'completed'
            payment.save()
            log_action(user,
                'payment_verified', f"Admin verified payment #{payment_id} for student {payment.student.studentID}.", request)
            messages.success(request, f"Payment #{payment_id} verified.")
        elif action == 'reject':
            payment.status = 'rejected'
            payment.save()
            log_action(user,
                'payment_rejected', f"Admin rejected payment #{payment_id} for student {payment.student.studentID}.", request)
            messages.warning(request, f"Payment #{payment_id} rejected.")
    return redirect('admin_payment_verification')


@role_required('admin')
def approve_deferral(request, plan_id):
    if request.method == 'POST':
        user = get_logged_in_user(request)
        plan   = get_object_or_404(InstallmentPlan, planID=plan_id)
        action = request.POST.get('action')
        if action == 'approve':
            plan.is_approved = True
            plan.save()
            log_action(user,
                'deferral_approved', f"Admin approved deferral request #{plan_id} for student {plan.student.studentID}.", request)
            messages.success(request, "Deferral request approved.")
        elif action == 'reject':
            student_id = plan.student.studentID
            plan.delete()
            log_action(user,
                'deferral_rejected', f"Admin rejected deferral request #{plan_id} for student {student_id}.", request)
            messages.warning(request, "Deferral request rejected and removed.")
    return redirect('admin_payment_verification')
@role_required('student')
def profile_view(request):
    from django.contrib.auth.hashers import make_password
    user = get_logged_in_user(request)

    student = get_object_or_404(Student, user=user)

    if request.method == 'POST':
        name       = request.POST.get('name', '').strip()
        program    = request.POST.get('program', '')
        year_level = request.POST.get('year_level', student.yearLevel)
        if name:
            user.name = name
            user.save()
        if program:
            student.program   = program
            student.yearLevel = int(year_level)
            student.save()
        log_action(user, 'user_action', f"Student {student.studentID} updated profile.", request)
        messages.success(request, "Profile updated successfully.")
        return redirect('profile')

    return render(request, 'studenthq/profile.html', {'user': user, 'student': student})


@role_required('student')
def change_password(request):
    user = get_logged_in_user(request)
    if request.method == 'POST':
        current  = request.POST.get('current_password', '')
        new1     = request.POST.get('new_password1', '')
        new2     = request.POST.get('new_password2', '')

        if not check_password(current, user.passwordHash):
            messages.error(request, "Current password is incorrect.")
        elif new1 != new2:
            messages.error(request, "New passwords do not match.")
        elif len(new1) < 8:
            messages.error(request, "Password must be at least 8 characters.")
        else:
            user.passwordHash = make_password(new1)
            user.save()
            log_action(user, 'user_action', f"Student {user.userID} changed password.", request)
            messages.success(request, "Password updated successfully.")
    return redirect('profile')
@role_required('admin')
def admin_financial_report(request):
    user = get_logged_in_user(request)

    all_fees = Fee.objects.select_related('student__user').all()

    total_fees_issued  = sum(f.totalAmount for f in all_fees)
    total_collected    = sum(
        p.amountPaid for p in
        Payment.objects.filter(status='completed')
    )
    total_outstanding  = sum(f.outstanding() for f in all_fees)
    total_penalties    = sum(f.latePenalty for f in all_fees)
    students_with_outstanding = sum(1 for f in all_fees if f.outstanding() > 0)
    pending_count      = Payment.objects.filter(status='pending').count()

    # Build fee summary rows with amount paid calculated
    fee_summary = []
    for f in all_fees.order_by('student__studentID'):
        paid = sum(
            p.amountPaid for p in f.payments.filter(status='completed')
        )
        f.amount_paid = paid
        f.outstanding = f.outstanding()
        fee_summary.append(f)

    recent_payments = Payment.objects.select_related(
        'student__user'
    ).order_by('-paymentDate')[:50]

    return render(request, 'studenthq/admin_financial_report.html', {
        'user':                    user,
        'total_fees_issued':       total_fees_issued,
        'total_collected':         total_collected,
        'total_outstanding':       total_outstanding,
        'total_penalties':         total_penalties,
        'students_with_outstanding': students_with_outstanding,
        'pending_count':           pending_count,
        'fee_summary':             fee_summary,
        'recent_payments':         recent_payments,
    })


@role_required('admin')
def admin_financial_report_export(request):
    import csv
    from django.http import HttpResponse
    user = get_logged_in_user(request)
    log_action(user, 'financial_report_export',
        "Admin exported financial report to CSV.", request)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="financial_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Student ID', 'Name', 'Program', 'Semester',
                     'Total Due', 'Total Paid', 'Outstanding', 'Penalty'])
    for f in Fee.objects.select_related('student__user').all():
        paid = sum(p.amountPaid for p in f.payments.filter(status='completed'))
        writer.writerow([
            f.student.studentID, f.student.user.name,
            f.student.program, f.semester,
            f.totalAmount, paid, f.outstanding(), f.latePenalty,
        ])
    return response
@role_required('admin')
def admin_course_catalog(request):
    user = get_logged_in_user(request)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            course_id   = request.POST.get('courseID', '').strip().upper()
            name        = request.POST.get('name', '').strip()
            credits     = int(request.POST.get('credits', 3))
            school      = request.POST.get('school', '').strip()
            department  = request.POST.get('department', '')
            category    = request.POST.get('category', '').strip()
            semester    = request.POST.get('semesterOffered', '')
            description = request.POST.get('description', '')

            if Course.objects.filter(courseID=course_id).exists():
                messages.error(request, f"Course ID {course_id} already exists.")
            else:
                Course.objects.create(
                    courseID=course_id, name=name, credits=credits,
                    school=school, department=department, category=category,
                    semesterOffered=semester, description=description,
                )
                log_action(user, 'course_add',
                    f"Admin added new course: {course_id} — {name}", request)
                messages.success(request, f"Course {course_id} added successfully.")

        elif action == 'delete':
            course_id = request.POST.get('courseID', '')
            try:
                course = Course.objects.get(courseID=course_id)
                course.delete()
                log_action(user, 'course_delete',
                    f"Admin deleted course: {course_id}", request)
                messages.success(request, f"Course {course_id} deleted.")
            except Course.DoesNotExist:
                messages.error(request, "Course not found.")

        return redirect('admin_course_catalog')

    courses_qs = Course.objects.all().order_by('school', 'department', 'courseID')
    school = request.GET.get('school', '').strip()
    dept   = request.GET.get('department', '').strip()
    search = request.GET.get('search', '').strip()
    if school:
        courses_qs = courses_qs.filter(school=school)
    if dept:
        courses_qs = courses_qs.filter(department=dept)
    if search:
        courses_qs = courses_qs.filter(
            Q(courseID__icontains=search) | Q(name__icontains=search)
        )
    paginator  = Paginator(courses_qs, 25)
    page_obj   = paginator.get_page(request.GET.get('page'))

    return render(request, 'studenthq/admin_course_catalog.html', {
        'user': user,
        'courses': page_obj,
        'schools': Course.SCHOOL_CHOICES,
        'departments': Course.DEPARTMENT_CHOICES,
    })
# Academic Advisor
@role_required('advisor')
def advisor_student_progress(request):
    user     = get_logged_in_user(request)
    advisor  = get_object_or_404(AcademicAdvisor, user=user)
    students = []
    q        = request.GET.get('q', '')
    program  = request.GET.get('program', '')

    qs = Student.objects.select_related('user').all()
    if q:
        qs = qs.filter(
            Q(user__name__icontains=q) | Q(studentID__icontains=q)
        )
    if program:
        qs = qs.filter(program=program)
    for s in qs:
        s.transcript        = s.enrollments.filter(status='completed').select_related('course').order_by('semester')
        s.current_courses   = s.enrollments.filter(semester=CURRENT_SEMESTER).select_related('course')
        s.credits_done      = s.credits_completed()
        s.graduation_pct    = s.graduation_percentage()
        # compute live GPA for advisor view (do not overwrite stored cumulativeGPA)
        gpa_entries = [(e.grade_points(), e.course.credits) for e in s.transcript if e.grade_points() is not None]
        s.live_gpa = (
            round(sum(gp * cr for gp, cr in gpa_entries) / sum(cr for _, cr in gpa_entries), 2)
            if gpa_entries else None
        )
        s.current_semester  = CURRENT_SEMESTER
        s.comments = s.advisor_comments.select_related('advisor__user').order_by('-created_at')[:5]
        students.append(s)
    return render(request, 'studenthq/advisor_student_progress.html', {
        'user': user, 'advisor': advisor, 'students': students,
    })




@role_required('advisor')
def advisor_comment(request, student_id):
    if request.method == 'POST':
        user         = get_logged_in_user(request)
        advisor      = get_object_or_404(AcademicAdvisor, user=user)
        student      = get_object_or_404(Student, studentID=student_id)
        comment_text = request.POST.get('comment', '').strip()
        if comment_text:
            AdvisorComment.objects.create(
                student=student, advisor=advisor, comment=comment_text,
            )
            log_action(user, 'advisor_comment',
                f"Advisor {advisor.user.name} added comment for student {student.studentID}.", request)
            messages.success(request, "Comment added.")
    return redirect('advisor_student_progress')
@role_required('admin')
def audit_log_view(request):
    user      = get_logged_in_user(request)
    logs_qs   = AuditLog.objects.select_related('user').order_by('-timestamp')
    paginator = Paginator(logs_qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'studenthq/audit_log.html', {
        'user': user, 'logs': page_obj,
    })
