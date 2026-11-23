from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('',         views.login_view,  name='login'),
    path('signup/',  views.signup_view, name='signup'),
    path('logout/',  views.logout_view, name='logout'),

    # Student
    path('dashboard/',           views.dashboard,    name='dashboard'),
    path('profile/',             views.profile_view, name='profile'),
    path('profile/password/',    views.change_password, name='change_password'),

    # Fees
    path('fees/calculator/',           views.fee_calculator,          name='fee_calculator'),
    path('fees/history/',              views.payment_history,         name='payment_history'),
    path('fees/history/export/',       views.payment_history_export,  name='payment_history_export'),
    path('fees/installment/',          views.installment_plan,        name='installment_plan'),
    path('fees/installment/create/',   views.create_installment_plan, name='create_installment_plan'),
    path('fees/installment/deferral/', views.request_deferral,        name='request_deferral'),
    path('fees/penalty-simulator/',    views.payment_simulator,       name='payment_simulator'),

    # Courses
    path('courses/catalog/',   views.course_catalog,      name='course_catalog'),
    path('courses/register/',  views.course_registration, name='course_registration'),

    # Academic
    path('academic/progress/',      views.academic_progress, name='academic_progress'),
    path('academic/gpa-simulator/', views.gpa_simulator,     name='gpa_simulator'),

    # Admin
    path('admin/fee-structure/',                        views.admin_fee_structure,        name='admin_fee_structure'),
    path('admin/payments/',                             views.admin_payment_verification, name='admin_payment_verification'),
    path('admin/payments/verify/<int:payment_id>/',     views.verify_payment,             name='verify_payment'),
    path('admin/payments/deferral/<int:plan_id>/',      views.approve_deferral,           name='approve_deferral'),
    path('admin/courses/',                              views.admin_course_catalog,       name='admin_course_catalog'),
    path('admin/reports/',                              views.admin_financial_report,     name='admin_financial_report'),
    path('admin/reports/export/',                       views.admin_financial_report_export, name='admin_financial_report_export'),
    path('admin/audit-log/',                            views.audit_log_view,             name='audit_log'),

    # Advisor
    path('advisor/students/',                 views.advisor_student_progress, name='advisor_student_progress'),
    path('advisor/comment/<str:student_id>/', views.advisor_comment,          name='advisor_comment'),
]