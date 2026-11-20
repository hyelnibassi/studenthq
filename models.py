from django.db import models
from django.contrib.auth.hashers import make_password


class User(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('admin', 'Admin'),
        ('advisor', 'Academic Advisor'),
    ]
    userID        = models.AutoField(primary_key=True)
    name          = models.CharField(max_length=255)
    email         = models.EmailField(unique=True)
    passwordHash  = models.CharField(max_length=255)
    role          = models.CharField(max_length=20, choices=ROLE_CHOICES)

    class Meta:
        db_table = 'user'

    def set_password(self, raw_password):
        self.passwordHash = make_password(raw_password)

    def __str__(self):
        return f"{self.name} ({self.role})"


class Student(models.Model):
    PROGRAM_CHOICES = [
        ('Computer Science', 'Computer Science'),
        ('Business Administration', 'Business Administration'),
        ('Economics', 'Economics'),
        ('Engineering', 'Engineering'),
    ]
    studentID     = models.CharField(max_length=50, primary_key=True)
    user          = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    program       = models.CharField(max_length=100, choices=PROGRAM_CHOICES)
    yearLevel     = models.IntegerField()
    cumulativeGPA = models.FloatField(default=0.0)

    class Meta:
        db_table = 'student'

    def __str__(self):
        return f"{self.user.name} — {self.program}"

    def credits_completed(self):
        return sum(
            e.course.credits for e in
            self.enrollments.filter(status='completed').select_related('course')
        )

    def graduation_percentage(self):
        return min(round((self.credits_completed() / 120) * 100), 100)


class Admin(models.Model):
    adminID    = models.AutoField(primary_key=True)
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    department = models.CharField(max_length=100)

    class Meta:
        db_table = 'admin'

    def __str__(self):
        return f"Admin: {self.user.name}"


class AcademicAdvisor(models.Model):
    advisorID  = models.AutoField(primary_key=True)
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='advisor_profile')
    department = models.CharField(max_length=100)

    class Meta:
        db_table = 'academic_advisor'

    def __str__(self):
        return f"Advisor: {self.user.name}"


class Course(models.Model):
    SCHOOL_CHOICES = [
        ('SAS', 'School of Arts & Sciences (SAS)'),
        ('SITC', 'School of Information Technology & Computing (SITC)'),
        ('SOE', 'School of Engineering (SOE)'),
        ('SBE', 'School of Business & Entrepreneurship (SBE)'),
        ('GENED', 'General Education (GENED)'),
    ]
    DEPARTMENT_CHOICES = [
        ('Business Administration', 'Business Administration'),
        ('Chemical Engineering', 'Chemical Engineering'),
        ('Civil Engineering', 'Civil Engineering'),
        ('Communications & Multimedia Design', 'Communications & Multimedia Design'),
        ('Computer Science', 'Computer Science'),
        ('Data Science', 'Data Science'),
        ('Economics', 'Economics'),
        ('Electrical & Electronics Engineering', 'Electrical & Electronics Engineering'),
        ('Engineering', 'Engineering'),
        ('English Language & Literature', 'English Language & Literature'),
        ('General Education', 'General Education'),
        ('Information Systems', 'Information Systems'),
        ('Natural & Environmental Sciences', 'Natural & Environmental Sciences'),
        ('Petroleum Chemistry', 'Petroleum Chemistry'),
        ('Politics & International Studies', 'Politics & International Studies'),
        ('Software Engineering', 'Software Engineering'),
        ('Telecommunications Engineering', 'Telecommunications Engineering'),
    ]
    SEMESTER_CHOICES = [
        ('Fall', 'Fall'),
        ('Spring', 'Spring'),
        ('Summer', 'Summer'),
    ]
    courseID        = models.CharField(max_length=20, primary_key=True)
    name            = models.CharField(max_length=255)
    credits         = models.IntegerField()
    school          = models.CharField(max_length=20, choices=SCHOOL_CHOICES, blank=True, default='')
    department      = models.CharField(max_length=100, choices=DEPARTMENT_CHOICES)
    category        = models.CharField(max_length=50, blank=True, default='')
    semesterOffered = models.CharField(max_length=20, choices=SEMESTER_CHOICES)
    description     = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'course'

    def __str__(self):
        return f"{self.courseID} — {self.name}"


class Prerequisite(models.Model):
    prereqID       = models.AutoField(primary_key=True)
    course         = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='prerequisites')
    requiredCourse = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='required_for')

    class Meta:
        db_table        = 'prerequisite'
        unique_together = ('course', 'requiredCourse')

    def __str__(self):
        return f"{self.course.courseID} requires {self.requiredCourse.courseID}"


class Enrollment(models.Model):
    STATUS_CHOICES = [
        ('enrolled',  'Enrolled'),
        ('completed', 'Completed'),
        ('dropped',   'Dropped'),
        ('failed',    'Failed'),
    ]
    GRADE_CHOICES = [
        ('A', 'A'), ('B+', 'B+'), ('B', 'B'),
        ('C+', 'C+'), ('C', 'C'), ('D+', 'D+'),
        ('D', 'D'), ('F', 'F'), ('IP', 'In Progress'),
    ]
    enrollID          = models.AutoField(primary_key=True)
    student           = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    course            = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    semester          = models.CharField(max_length=30)
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='enrolled')
    grade             = models.CharField(max_length=5, choices=GRADE_CHOICES, blank=True, null=True)
    registration_date = models.DateField(auto_now_add=True)

    class Meta:
        db_table        = 'enrollment'
        unique_together = ('student', 'course', 'semester')

    def grade_points(self):
        grade_map = {
            'A': 4.0, 'B+': 3.5, 'B': 3.0,
            'C+': 2.5, 'C': 2.0, 'D+': 1.5,
            'D': 1.0, 'F': 0.0, 'IP': None,
        }
        return grade_map.get(self.grade)

    def __str__(self):
        return f"{self.student.studentID} — {self.course.courseID} ({self.semester})"


class Fee(models.Model):
    feeID            = models.AutoField(primary_key=True)
    student          = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='fees')
    semester         = models.CharField(max_length=30)
    tuitionAmount    = models.FloatField(default=0.0)
    accommodationFee = models.FloatField(default=0.0)
    mandatoryFees    = models.FloatField(default=0.0)
    latePenalty      = models.FloatField(default=0.0)
    totalAmount      = models.FloatField(default=0.0)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fee'

    def compute(self):
        self.totalAmount = (
            self.tuitionAmount + self.accommodationFee
            + self.mandatoryFees + self.latePenalty
        )
        return self.totalAmount

    def outstanding(self):
        paid = sum(p.amountPaid for p in self.payments.filter(status='completed'))
        return max(self.totalAmount - paid, 0)

    def __str__(self):
        return f"Fee #{self.feeID} — {self.student.studentID} ({self.semester})"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('completed', 'Completed'),
        ('rejected',  'Rejected'),
    ]
    paymentID    = models.AutoField(primary_key=True)
    fee          = models.ForeignKey(Fee, on_delete=models.CASCADE, related_name='payments')
    student      = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='payments')
    amountPaid   = models.FloatField()
    paymentDate  = models.DateField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_type = models.CharField(max_length=50, default='Tuition Payment')

    class Meta:
        db_table = 'payment'

    def __str__(self):
        return f"Payment #{self.paymentID} — ₦{self.amountPaid} ({self.status})"


class InstallmentPlan(models.Model):
    planID           = models.AutoField(primary_key=True)
    fee              = models.ForeignKey(Fee, on_delete=models.CASCADE, related_name='installment_plans')
    student          = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='installment_plans')
    numInstallments  = models.IntegerField(choices=[(2, '2 Installments'), (3, '3 Installments')])
    dueDate          = models.DateField()
    amountPerInstall = models.FloatField()
    is_approved      = models.BooleanField(default=False)
    reason           = models.TextField(blank=True, default='')
    semester         = models.CharField(max_length=30, default='')
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'installment_plan'

    def __str__(self):
        return f"Plan #{self.planID} — {self.numInstallments} installments"


class AdvisorComment(models.Model):
    commentID  = models.AutoField(primary_key=True)
    student    = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='advisor_comments')
    advisor    = models.ForeignKey(AcademicAdvisor, on_delete=models.CASCADE, related_name='comments')
    comment    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'advisor_comment'

    def __str__(self):
        return f"Comment by {self.advisor.user.name} on {self.student.user.name}"


class FeeStructure(models.Model):
    """Singleton table — always use pk=1. Admin can update via the fee structure page."""
    tuition_per_credit       = models.FloatField(default=50000)
    accommodation_on_campus  = models.FloatField(default=250000)
    accommodation_off_campus = models.FloatField(default=180000)
    sports_fee               = models.FloatField(default=15000)
    lab_fee                  = models.FloatField(default=25000)
    library_fee              = models.FloatField(default=20000)
    late_penalty_per_month   = models.FloatField(default=30000)
    updated_at               = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fee_structure'

    def __str__(self):
        return f"Fee Structure (updated {self.updated_at})"


class FeeStructureChangeLog(models.Model):
    field_name  = models.CharField(max_length=100)
    old_value   = models.FloatField()
    new_value   = models.FloatField()
    changed_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    changed_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fee_structure_change_log'


class Notification(models.Model):
    NOTIF_TYPES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('danger', 'Danger'),
    ]
    notifID = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    type = models.CharField(max_length=20, choices=NOTIF_TYPES, default='info')
    date = models.DateField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        db_table = 'notification'


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('fee_structure_update', 'Fee Structure Update'),
        ('course_add', 'Course Added'),
        ('course_delete', 'Course Deleted'),
        ('payment_verified', 'Payment Verified'),
        ('payment_rejected', 'Payment Rejected'),
        ('deferral_approved', 'Deferral Approved'),
        ('deferral_rejected', 'Deferral Rejected'),
        ('installment_plan_request', 'Installment Plan Requested'),
        ('deferral_request', 'Deferral Requested'),
        ('advisor_comment', 'Advisor Comment Added'),
        ('user_login', 'User Login'),
        ('user_signup', 'User Signup'),
        ('financial_report_export', 'Financial Report Exported'),
        ('user_action', 'User Action'),
    ]
    logID       = models.AutoField(primary_key=True)
    user        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action      = models.CharField(max_length=100, choices=ACTION_CHOICES)
    description = models.TextField()
    ip_address  = models.CharField(max_length=45, blank=True, null=True)
    timestamp   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'

    def __str__(self):
        return f"AuditLog #{self.logID} — {self.action} by {self.user}"
