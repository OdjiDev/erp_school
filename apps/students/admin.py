from django.contrib import admin, messages

from apps.common.admin import TenantModelAdmin, TenantTabularInline

from .models import (
    Enrollment,
    EnrollmentStatus,
    Guardian,
    Student,
    StudentGuardian,
)


class StudentGuardianInline(TenantTabularInline):
    model = StudentGuardian
    fk_name = "student"
    extra = 0
    autocomplete_fields = ("guardian",)


class EnrollmentInline(TenantTabularInline):
    model = Enrollment
    fk_name = "student"
    extra = 0
    exclude = ("school",)
    autocomplete_fields = ("academic_year", "school_class")


@admin.register(Student)
class StudentAdmin(TenantModelAdmin):
    list_display = (
        "matricule",
        "last_name",
        "first_name",
        "gender",
        "date_of_birth",
        "status",
        "school",
    )
    list_filter = ("school__organization", "school", "status", "gender")
    search_fields = (
        "matricule",
        "first_name",
        "last_name",
        "school__name",
        "school__code",
    )
    list_select_related = ("school",)
    inlines = [StudentGuardianInline, EnrollmentInline]


class GuardianStudentInline(TenantTabularInline):
    model = StudentGuardian
    fk_name = "guardian"
    extra = 0
    autocomplete_fields = ("student",)


@admin.register(Guardian)
class GuardianAdmin(TenantModelAdmin):
    list_display = ("last_name", "first_name", "phone", "organization")
    list_filter = ("organization",)
    search_fields = ("last_name", "first_name", "phone", "email")
    list_select_related = ("organization",)
    inlines = [GuardianStudentInline]


@admin.register(StudentGuardian)
class StudentGuardianAdmin(TenantModelAdmin):
    list_display = (
        "student",
        "guardian",
        "relationship",
        "is_primary",
        "is_financial_responsible",
    )
    list_filter = ("relationship", "is_primary", "is_financial_responsible")
    search_fields = (
        "student__matricule",
        "student__last_name",
        "student__first_name",
        "guardian__last_name",
        "guardian__first_name",
        "guardian__phone",
    )
    autocomplete_fields = ("student", "guardian")


@admin.register(Enrollment)
class EnrollmentAdmin(TenantModelAdmin):
    list_display = (
        "student",
        "school_class",
        "academic_year",
        "status",
        "enrolled_on",
        "exited_on",
    )
    list_filter = (
        "school",
        "academic_year",
        "school_class__level",
        "status",
    )
    search_fields = (
        "student__matricule",
        "student__last_name",
        "student__first_name",
        "school_class__name",
    )
    autocomplete_fields = ("student", "academic_year", "school_class")
    exclude = ("school",)
    list_select_related = ("student", "school_class", "academic_year")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.status == EnrollmentStatus.ACTIVE and obj.school_class.is_full:
            messages.warning(
                request,
                (
                    f"La classe {obj.school_class.display_name} est pleine "
                    f"({obj.school_class.enrolled_count}/"
                    f"{obj.school_class.capacity}). "
                    "L'inscription dépasse la capacité prévue."
                ),
            )
