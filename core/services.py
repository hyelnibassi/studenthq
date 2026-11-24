from datetime import date
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
class FeeCalculationEngine:
    LATE_PENALTY_PER_MONTH = 30000  # Fixed by AUN institutional policy

    def __init__(self, fee_structure):
        self.fs = fee_structure

    def compute(self, credit_hours, accommodation, fees_selected, months_overdue=0):
        """
        Compute total semester fee.
        accommodation: 'on-campus' | 'off-campus' | 'none'
        fees_selected: list containing any of 'sports', 'lab', 'library'
        months_overdue: int >= 0
        Returns a dict with full breakdown.
        """
        tuition = credit_hours * self.fs.tuition_per_credit

        if accommodation == 'on-campus':
            acc_fee = self.fs.accommodation_on_campus
            acc_label = 'On-Campus'
        elif accommodation == 'off-campus':
            acc_fee = self.fs.accommodation_off_campus
            acc_label = 'Off-Campus'
        else:
            acc_fee = 0
            acc_label = 'None'

        sports = self.fs.sports_fee if 'sports' in fees_selected else 0
        lab = self.fs.lab_fee if 'lab' in fees_selected else 0
        library = self.fs.library_fee if 'library' in fees_selected else 0
        mandatory = sports + lab + library

        penalty = max(0, months_overdue) * self.LATE_PENALTY_PER_MONTH
        total = tuition + acc_fee + mandatory + penalty

        return {
            'credit_hours': credit_hours,
            'tuition': tuition,
            'accommodation_fee': acc_fee,
            'accommodation_type': acc_label,
            'sports_fee': sports,
            'lab_fee': lab,
            'library_fee': library,
            'mandatory_total': mandatory,
            'penalty': penalty,
            'months_overdue': months_overdue,
            'total': total,
        }

    def split_installments(self, total, num_installments):
        
        if num_installments not in (2, 3):
            raise ValueError("Installments must be 2 or 3 as per AUN policy.")
        amount_per = total / num_installments
        today = date.today()
        return [
            {
                'installment': i + 1,
                'due_date': today + relativedelta(months=i),
                'amount': amount_per,
            }
            for i in range(num_installments)
        ]
def validate_prerequisites(student, course):
    """
    Checks whether a student has completed all prerequisites for a course.
    Raises ValidationError listing missing prerequisites if any are unmet.
    Returns True if all prerequisites are satisfied.
    """
    required = course.prerequisites.select_related('requiredCourse').all()
    if not required.exists():
        return True

    completed_course_ids = set(
        student.enrollments
        .filter(status='completed')
        .values_list('course__courseID', flat=True)
    )

    missing = [
        p.requiredCourse.courseID
        for p in required
        if p.requiredCourse.courseID not in completed_course_ids
    ]

    if missing:
        raise ValidationError(
            f"Cannot register for {course.courseID}. "
            f"Missing prerequisites: {', '.join(missing)}"
        )
    return True


PROGRAM_DEPARTMENT_MAP = {
    'Computer Science': {
        'primary': {'Computer Science'},
        'related': {'Software Engineering', 'Data Science', 'Information Systems'},
    },
    'Business Administration': {
        'primary': {'Business Administration'},
        'related': {'Economics'},
    },
    'Economics': {
        'primary': {'Economics'},
        'related': {'Business Administration'},
    },
    'Engineering': {
        'primary': {
            'Engineering',
            'Electrical & Electronics Engineering',
            'Chemical Engineering',
            'Civil Engineering',
            'Telecommunications Engineering',
        },
        'related': {'Computer Science', 'Petroleum Chemistry'},
    },
}


def get_eligible_courses(student, available_courses):
    """
    Returns list of dicts: {course, eligible (bool), missing_prereqs (str)}.
    Uses prefetched prerequisites to avoid N+1 queries.
    """
    completed_ids = set(
        student.enrollments
        .filter(status='completed')
        .values_list('course__courseID', flat=True)
    )

    result = []
    for course in available_courses:
        required = course.prerequisites.all()
        missing = [p.requiredCourse.courseID for p in required if p.requiredCourse.courseID not in completed_ids]
        result.append({
            'course': course,
            'eligible': len(missing) == 0,
            'missing_prereqs': ', '.join(missing) if missing else '',
        })
    return result


def get_smart_registration_courses(student, available_courses):
    """
    Ranks courses for Course Registration in priority order:
      1. Belongs to the student's degree catalog / program of study
      2. Not yet completed by the student (highest priority)
      3. Prerequisites already satisfied
    Also preserves free electives and other courses so students can search & select them.
    """
    completed_ids = set(
        student.enrollments
        .filter(status='completed')
        .values_list('course__courseID', flat=True)
    )
    prog_info = PROGRAM_DEPARTMENT_MAP.get(student.program, {'primary': {student.program}, 'related': set()})
    primary_depts = prog_info['primary']
    related_depts = prog_info['related']

    items = []
    for course in available_courses:
        required = course.prerequisites.all()
        missing = [p.requiredCourse.courseID for p in required if p.requiredCourse.courseID not in completed_ids]
        eligible = len(missing) == 0
        is_completed = course.courseID in completed_ids
        is_primary_program = course.department in primary_depts
        is_related_program = course.department in related_depts
        in_program = is_primary_program or is_related_program

        # Priority tuple (lower sorts first):
        # (not in primary/related program, is already completed, not eligible, not primary exact dept, courseID)
        rank = (
            0 if is_primary_program else (1 if is_related_program else 2),
            1 if is_completed else 0,
            0 if eligible else 1,
            course.courseID,
        )

        if is_primary_program and not is_completed and eligible:
            tag = 'Program Core'
        elif is_related_program and not is_completed and eligible:
            tag = 'School Elective'
        elif in_program and not is_completed:
            tag = 'Program (Prereq Needed)'
        elif is_completed:
            tag = 'Completed'
        else:
            tag = 'Free Elective'

        items.append({
            'course': course,
            'eligible': eligible,
            'missing_prereqs': ', '.join(missing) if missing else '',
            'in_program': in_program,
            'is_primary_program': is_primary_program,
            'is_completed': is_completed,
            'is_recommended': in_program and (not is_completed) and eligible,
            'tag': tag,
            '_rank': rank,
        })

    items.sort(key=lambda x: x['_rank'])
    return items
GRADE_POINT_MAP = {
    'A': 4.0, 'B+': 3.5, 'B': 3.0,
    'C+': 2.5, 'C': 2.0, 'D+': 1.5,
    'D': 1.0, 'F': 0.0,
}


def simulate_gpa(student, hypothetical_courses):
    """
    Projects cumulative GPA after adding hypothetical courses.

    student: Student model instance
    hypothetical_courses: list of dicts — [{'name': str, 'credits': int, 'grade': str}, ...]

    Returns dict with:
        projected_gpa, current_gpa, change, semester_gpa, courses (with contribution)
    """
    completed = student.enrollments.filter(status='completed').select_related('course')
    existing_points = sum(
        e.grade_points() * e.course.credits
        for e in completed if e.grade_points() is not None
    )
    existing_credits = sum(
        e.course.credits for e in completed if e.grade_points() is not None
    )

    hypo_details = []
    hypo_points = 0
    hypo_credits = 0

    for c in hypothetical_courses:
        grade = c.get('grade', 'F')
        credits = int(c.get('credits', 3))
        gp = GRADE_POINT_MAP.get(grade, 0.0)
        contribution = gp * credits
        hypo_points += contribution
        hypo_credits += credits
        hypo_details.append({
            'name': c.get('name', 'Unknown Course'),
            'credits': credits,
            'grade': grade,
            'grade_point': gp,
            'contribution': contribution,
        })

    total_credits = existing_credits + hypo_credits
    total_points = existing_points + hypo_points

    current_gpa = (existing_points / existing_credits) if existing_credits > 0 else 0.0
    projected_gpa = (total_points / total_credits) if total_credits > 0 else 0.0
    semester_gpa = (hypo_points / hypo_credits) if hypo_credits > 0 else 0.0

    return {
        'current_gpa': round(current_gpa, 2),
        'projected_gpa': round(projected_gpa, 2),
        'semester_gpa': round(semester_gpa, 2),
        'change': round(projected_gpa - current_gpa, 2),
        'courses': hypo_details,
        'hypo_credits': hypo_credits,
    }
PENALTY_PER_MONTH = 30000  # Fixed AUN policy — cannot be changed


def simulate_payment_penalty(amount_due, due_date, planned_date):
    """
    Calculates total amount owed if payment is made on planned_date
    when it was due on due_date.

    Returns dict with months_overdue, penalty, total, and comparison scenarios.
    """
    if planned_date <= due_date:
        months_overdue = 0
    else:
        delta = relativedelta(planned_date, due_date)
        months_overdue = delta.months + (delta.years * 12)
        if delta.days > 0:
            months_overdue += 1  # partial month counts as full month

    penalty = months_overdue * PENALTY_PER_MONTH
    total = amount_due + penalty

    return {
        'amount_due': amount_due,
        'months_overdue': months_overdue,
        'penalty': penalty,
        'total': total,
        'scenario_1': amount_due + (1 * PENALTY_PER_MONTH),
        'scenario_2': amount_due + (2 * PENALTY_PER_MONTH),
        'scenario_3': amount_due + (3 * PENALTY_PER_MONTH),
    }
