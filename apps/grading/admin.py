from django.contrib import admin

from apps.common.admin import TenantModelAdmin

from .models import (
    Assessment,
    BulletinSnapshot,
    Deliberation,
    Grade,
    GradeRevision,
    GradingPeriod,
    GradingPeriodAction,
)


@admin.register(GradingPeriod)
class GradingPeriodAdmin(TenantModelAdmin):
    list_display = ("name", "school", "academic_year", "sequence", "code", "is_closed")
    list_filter = ("school", "academic_year")
    search_fields = ("name", "code")
    readonly_fields = ("is_closed", "closed_at", "closed_by")


@admin.register(Assessment)
class AssessmentAdmin(TenantModelAdmin):
    list_display = (
        "title",
        "school",
        "period",
        "class_subject",
        "held_on",
        "is_published",
    )
    list_filter = ("school", "period", "is_published", "assessment_type")
    search_fields = ("title", "class_subject__subject__name")
    readonly_fields = ("is_published", "published_at", "published_by")


@admin.register(Grade)
class GradeAdmin(TenantModelAdmin):
    list_display = ("enrollment", "assessment", "score", "status")
    list_filter = ("school", "assessment__period", "status")
    search_fields = (
        "enrollment__student__first_name",
        "enrollment__student__last_name",
        "enrollment__student__matricule",
    )

    def has_change_permission(self, request, obj=None):
        if obj and (
            obj.assessment.is_published or obj.assessment.period.is_closed
        ):
            return False
        return super().has_change_permission(request, obj)


@admin.register(GradeRevision)
class GradeRevisionAdmin(TenantModelAdmin):
    list_display = ("grade", "previous_score", "new_score", "changed_by_label", "created_at")
    list_filter = ("school", "grade__assessment__period")
    search_fields = ("grade__enrollment__student__matricule", "reason", "changed_by_label")
    readonly_fields = tuple(field.name for field in GradeRevision._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Deliberation)
class DeliberationAdmin(TenantModelAdmin):
    list_display = ("enrollment", "period", "outcome", "decided_by", "decided_at")
    list_filter = ("school", "period", "outcome")
    search_fields = ("enrollment__student__matricule", "enrollment__student__first_name", "enrollment__student__last_name")
    readonly_fields = tuple(field.name for field in Deliberation._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GradingPeriodAction)
class GradingPeriodActionAdmin(TenantModelAdmin):
    list_display = ("period", "action", "performed_by_label", "created_at")
    list_filter = ("school", "period", "action")
    search_fields = ("period__name", "reason", "performed_by_label")
    readonly_fields = tuple(field.name for field in GradingPeriodAction._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BulletinSnapshot)
class BulletinSnapshotAdmin(TenantModelAdmin):
    list_display = ("enrollment", "period", "version", "generated_by_label", "created_at")
    list_filter = ("school", "period", "version")
    search_fields = ("enrollment__student__matricule", "enrollment__student__first_name", "enrollment__student__last_name")
    readonly_fields = tuple(field.name for field in BulletinSnapshot._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
