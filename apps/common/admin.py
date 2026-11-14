from django.contrib import admin


class TenantAdminQuerysetMixin:
    """Give platform staff an explicit, auditable cross-tenant admin path."""

    def get_queryset(self, request):
        queryset = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        return queryset.order_by(*ordering) if ordering else queryset

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        related_model = db_field.remote_field.model
        if formfield and hasattr(related_model, "all_objects"):
            formfield.queryset = related_model.all_objects.all()
        return formfield

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
        related_model = db_field.remote_field.model
        if formfield and hasattr(related_model, "all_objects"):
            formfield.queryset = related_model.all_objects.all()
        return formfield


class TenantModelAdmin(TenantAdminQuerysetMixin, admin.ModelAdmin):
    pass


class TenantTabularInline(TenantAdminQuerysetMixin, admin.TabularInline):
    pass
