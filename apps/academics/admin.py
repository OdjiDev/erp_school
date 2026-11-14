from django.contrib import admin

from apps.common.admin import TenantModelAdmin, TenantTabularInline

from .models import (
    AcademicYear,
    ClassSubject,
    Curriculum,
    CurriculumSubject,
    Level,
    SchoolClass,
    Series,
    Subject,
)


class CurriculumSubjectInline(TenantTabularInline):
    model = CurriculumSubject
    extra = 0


@admin.register(AcademicYear)
class AcademicYearAdmin(TenantModelAdmin):
    list_display = ("school", "name", "start_date", "end_date", "is_current")
    list_filter = ("school", "is_current")
    search_fields = ("name", "school__name", "school__code")


@admin.register(Level)
class LevelAdmin(TenantModelAdmin):
    list_display = ("school", "code", "name", "order")
    list_filter = ("school",)
    search_fields = ("code", "name", "school__name")


@admin.register(Series)
class SeriesAdmin(TenantModelAdmin):
    list_display = ("level", "code", "name")
    list_filter = ("level__school", "level")
    search_fields = ("code", "name", "level__name")


@admin.register(Subject)
class SubjectAdmin(TenantModelAdmin):
    list_display = ("school", "code", "name")
    list_filter = ("school",)
    search_fields = ("code", "name", "school__name")


@admin.register(Curriculum)
class CurriculumAdmin(TenantModelAdmin):
    list_display = ("school", "academic_year", "level", "series", "is_active")
    list_filter = ("school", "academic_year", "level", "is_active")
    search_fields = ("level__name", "series__name", "school__name")
    inlines = [CurriculumSubjectInline]


@admin.register(SchoolClass)
class SchoolClassAdmin(TenantModelAdmin):
    list_display = (
        "school",
        "display_name",
        "academic_year",
        "level",
        "series",
        "section",
        "capacity",
        "site",
    )
    list_filter = ("school", "academic_year", "level", "series", "site")
    search_fields = ("name", "section", "school__name", "school__code")


@admin.register(ClassSubject)
class ClassSubjectAdmin(TenantModelAdmin):
    list_display = ("school_class", "subject", "teacher")
    list_filter = ("school_class__school", "subject")
    search_fields = ("school_class__name", "subject__name", "teacher__username")
