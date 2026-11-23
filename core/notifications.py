from datetime import date, timedelta
from .models import Notification, Fee, Student


def create_notification(student, message, notif_type='info'):
    """Create a notification for a student. Avoids duplicates on same day."""
    exists = Notification.objects.filter(
        student=student,
        message=message,
        date=date.today()
    ).exists()
    if not exists:
        Notification.objects.create(
            student=student,
            message=message,
            type=notif_type,
        )


def check_and_create_fee_notifications(student):
    
    today = date.today()

    for fee in student.fees.all():
        outstanding = fee.outstanding()
        if outstanding <= 0:
            continue

        # Check installment plan due dates
        for plan in fee.installment_plans.filter(is_approved=True):
            days_until = (plan.dueDate - today).days
            if days_until < 0:
                create_notification(
                    student,
                    f"OVERDUE: Installment payment of \u20a6{plan.amountPerInstall:,.0f} "
                    f"for {fee.semester} was due on {plan.dueDate}. "
                    f"A \u20a630,000 penalty applies per month overdue.",
                    'danger'
                )
            elif days_until <= 7:
                create_notification(
                    student,
                    f"Payment due in {days_until} day(s): \u20a6{plan.amountPerInstall:,.0f} "
                    f"for {fee.semester} is due on {plan.dueDate}.",
                    'warning'
                )

        # Check if fee has a late penalty accumulating
        if fee.latePenalty > 0:
            create_notification(
                student,
                f"Late payment penalty of \u20a6{fee.latePenalty:,.0f} has been applied "
                f"to your {fee.semester} fees. Pay immediately to stop further penalties.",
                'danger'
            )

        # Check if outstanding balance with no plan
        if outstanding > 0 and not fee.installment_plans.filter(is_approved=True).exists():
            create_notification(
                student,
                f"You have an outstanding balance of \u20a6{outstanding:,.0f} "
                f"for {fee.semester}. Set up a payment plan to avoid late penalties.",
                'warning'
            )


def check_course_notifications(student, current_semester):
    
    enrolled = student.enrollments.filter(semester=current_semester)
    if not enrolled.exists():
        create_notification(
            student,
            f"You have not registered for any courses in {current_semester}. "
            f"Visit Course Registration to enrol before the deadline.",
            'warning'
        )
