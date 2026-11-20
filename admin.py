from django.contrib import admin
from .models import (
    User, Student, Admin, AcademicAdvisor, Course, Prerequisite,
    Enrollment, Fee, Payment, InstallmentPlan, AdvisorComment,
    FeeStructure, FeeStructureChangeLog
)

admin.site.register(User)
admin.site.register(Student)
admin.site.register(Admin)
admin.site.register(AcademicAdvisor)
admin.site.register(Course)
admin.site.register(Prerequisite)
admin.site.register(Enrollment)
admin.site.register(Fee)
admin.site.register(Payment)
admin.site.register(InstallmentPlan)
admin.site.register(AdvisorComment)
admin.site.register(FeeStructure)
admin.site.register(FeeStructureChangeLog)
