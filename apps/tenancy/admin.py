from django.contrib import admin

from apps.common.admin import TenantModelAdmin

from .models import Membership, Organization, School, Site


@admin.register(Organization)
class OrganizationAdmin(TenantModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(School)
class SchoolAdmin(TenantModelAdmin):
    list_display = ("name", "code", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "code", "organization__name")


@admin.register(Site)
class SiteAdmin(TenantModelAdmin):
    list_display = ("name", "code", "school", "is_primary")
    list_filter = ("school__organization", "school", "is_primary")
    search_fields = ("name", "code", "school__name")


@admin.register(Membership)
class MembershipAdmin(TenantModelAdmin):
    list_display = ("user", "organization", "school", "role", "is_active")
    list_filter = ("organization", "role", "is_active")
    search_fields = ("user__username", "user__email", "organization__name", "school__name")
