PROGRAM_SEQUENCES = {
    'Computer Science': [
        ('CS101', 1, 'Fall'),
        ('CS102', 1, 'Spring'),
        ('CS201', 2, 'Fall'),
        ('CS202', 2, 'Spring'),
        ('CS301', 3, 'Fall'),
        ('CS302', 3, 'Spring'),
        ('CS401', 4, 'Fall'),
        ('CS402', 4, 'Spring'),
    ],
    'Business Administration': [
        ('BA101', 1, 'Fall'),
        ('BA102', 1, 'Spring'),
        ('BA201', 2, 'Fall'),
        ('BA202', 2, 'Spring'),
        ('BA301', 3, 'Fall'),
        ('BA302', 3, 'Spring'),
    ],
    'Economics': [
        ('EC101', 1, 'Fall'),
        ('EC102', 1, 'Spring'),
        ('EC201', 2, 'Fall'),
        ('EC202', 2, 'Spring'),
        ('EC301', 3, 'Fall'),
    ],
    'Engineering': [
        ('EN101', 1, 'Fall'),
        ('EN102', 1, 'Spring'),
        ('EN201', 2, 'Fall'),
        ('EN202', 2, 'Spring'),
        ('EN301', 3, 'Fall'),
    ],
}


def get_recommended_courses(student, current_semester_name):
    
    from .models import Course, Enrollment

    completed_ids = set(
        student.enrollments
        .filter(status='completed')
        .values_list('course__courseID', flat=True)
    )
    enrolled_ids = set(
        student.enrollments
        .filter(status='enrolled')
        .values_list('course__courseID', flat=True)
    )
    already_taken = completed_ids | enrolled_ids

    sequence = PROGRAM_SEQUENCES.get(student.program, [])
    recommendations = []

    for course_id, year, sem in sequence:
        if course_id in already_taken:
            continue
        try:
            course = Course.objects.prefetch_related('prerequisites__requiredCourse').get(courseID=course_id)
        except Course.DoesNotExist:
            continue

        required_ids = set(p.requiredCourse.courseID for p in course.prerequisites.all())
        prereqs_met  = required_ids.issubset(completed_ids)

        if prereqs_met:
            reason = (
                f"Recommended next for Year {year} {sem}. "
                f"All prerequisites met." if required_ids
                else f"No prerequisites required. Good starting point for Year {year}."
            )
        else:
            missing = required_ids - completed_ids
            reason = (
                f"Complete {', '.join(missing)} first before taking this course."
            )

        recommendations.append({
            'course':          course,
            'reason':          reason,
            'year_level':      year,
            'semester':        sem,
            'prerequisites_met': prereqs_met,
        })

        if len(recommendations) >= 6:
            break

    return recommendations
