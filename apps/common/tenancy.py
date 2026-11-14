from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.db import models, transaction
from django.db.models import Q

from .models import TimeStampedModel


@dataclass(frozen=True)
class TenantScope:
    organization_id: object
    school_id: object = None


_current_tenant = ContextVar("current_tenant_scope", default=None)


def get_current_tenant():
    return _current_tenant.get()


@contextmanager
def tenant_scope(organization_id, school_id=None):
    """Set a tenant scope for the current request, task, or operation."""
    if organization_id is None:
        raise ValueError("organization_id is required for a tenant scope")

    current = get_current_tenant()
    if current:
        if current.organization_id != organization_id:
            raise ValueError("A nested tenant scope cannot change organization")
        if current.school_id is not None and current.school_id != school_id:
            raise ValueError("A nested tenant scope cannot widen or change school")

    token = _current_tenant.set(TenantScope(organization_id, school_id))
    try:
        yield get_current_tenant()
    finally:
        _current_tenant.reset(token)


class TenantQuerySet(models.QuerySet):
    def _scoped_queryset(self):
        scope = get_current_tenant()
        if scope is None:
            return self.none()

        custom_filter = getattr(self.model, "tenant_scope_q", None)
        if custom_filter:
            scope_filter = custom_filter(scope)
            return self.filter(scope_filter) if scope_filter is not None else self.none()

        lookups = getattr(self.model, "TENANT_SCOPE_LOOKUPS", {})
        level = "school" if scope.school_id is not None else "organization"
        entry = lookups.get(level) or lookups.get("organization")
        if entry is None:
            raise ImproperlyConfigured(
                f"{self.model.__name__} must declare TENANT_SCOPE_LOOKUPS"
            )
        lookup, scope_attribute = entry
        return self.filter(**{lookup: getattr(scope, scope_attribute)})

    def create(self, **kwargs):
        if get_current_tenant() is None:
            raise RuntimeError("Creating tenant data requires an active tenant scope")
        with transaction.atomic(using=self.db):
            instance = self.model(**kwargs)
            instance.save(force_insert=True, using=self.db)
            if not self.filter(pk=instance.pk).exists():
                raise RuntimeError("The new row is outside the active tenant scope")
        return instance

    def update(self, **kwargs):
        if get_current_tenant() is None:
            return 0
        primary_keys = list(set(self.values_list("pk", flat=True)))
        with transaction.atomic(using=self.db):
            updated = super().update(**kwargs)
            visible_count = self.model.objects.filter(
                pk__in=primary_keys
            ).count()
            if visible_count != len(primary_keys):
                raise RuntimeError("An update crossed the active tenant scope")
        return updated

    def bulk_create(self, objs, *args, **kwargs):
        if get_current_tenant() is None:
            raise RuntimeError("Creating tenant data requires an active tenant scope")
        objs = list(objs)
        with transaction.atomic(using=self.db):
            created = super().bulk_create(objs, *args, **kwargs)
            primary_keys = [obj.pk for obj in created]
            if self.filter(pk__in=primary_keys).count() != len(primary_keys):
                raise RuntimeError("A bulk insert crossed the active tenant scope")
        return created

    def bulk_update(self, objs, fields, *args, **kwargs):
        if get_current_tenant() is None:
            return 0
        with transaction.atomic(using=self.db):
            return super().bulk_update(objs, fields, *args, **kwargs)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    def get_queryset(self):
        return super().get_queryset()._scoped_queryset()


class TenantModel(TimeStampedModel):
    """Base class for rows that must always be queried inside a tenant scope."""

    objects = TenantManager()
    all_objects = models.Manager()

    def save(self, *args, **kwargs):
        if get_current_tenant() is None:
            return super().save(*args, **kwargs)

        using = kwargs.get("using") or self._state.db
        with transaction.atomic(using=using):
            result = super().save(*args, **kwargs)
            if not type(self).objects.filter(pk=self.pk).exists():
                raise RuntimeError("Saving this row would cross the active tenant scope")
        return result

    def delete(self, *args, **kwargs):
        if get_current_tenant() is not None and not type(self).objects.filter(
            pk=self.pk
        ).exists():
            raise RuntimeError("Deleting this row would cross the active tenant scope")
        return super().delete(*args, **kwargs)

    class Meta:
        abstract = True
