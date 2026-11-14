from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from apps.common.tenancy import TenantModel


class Organization(TenantModel):
    """Client de la plateforme. Les écoles lui appartiennent."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("pk", "organization_id"),
        "school": ("pk", "organization_id"),
    }

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "client"
        verbose_name_plural = "clients"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:80]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class School(TenantModel):
    """Établissement. Le nom peut être identique à celui d'une autre école."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("organization_id", "organization_id"),
        "school": ("pk", "school_id"),
    }

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="schools"
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40)
    slug = models.SlugField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["organization__name", "name", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uniq_school_code_per_organization",
            ),
            models.UniqueConstraint(
                fields=["organization", "slug"],
                name="uniq_school_slug_per_organization",
            ),
        ]

    def clean(self):
        if not self.code or not self.code.strip():
            raise ValidationError({"code": "Le code de l'école est obligatoire."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.code}")[:100]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} [{self.code}]"


class Site(TenantModel):
    """Campus ou site d'un établissement."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="sites")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40)
    address = models.TextField(blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["school__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uniq_site_code_per_school"
            )
        ]

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.school.name} — {self.name} [{self.code}]"


class Role(models.TextChoices):
    PLATFORM_ADMIN = "platform_admin", "Administrateur plateforme"
    ORG_ADMIN = "org_admin", "Administrateur client"
    SCHOOL_ADMIN = "school_admin", "Direction d'école"
    SECRETARY = "secretary", "Secrétariat"
    ACCOUNTANT = "accountant", "Comptable"
    TEACHER = "teacher", "Enseignant"
    SURVEILLANT = "surveillant", "Surveillant"
    PARENT = "parent", "Parent"
    STUDENT = "student", "Élève"
    AUDITOR = "auditor", "Auditeur"


class Membership(TenantModel):
    """Rôle d'un utilisateur, au niveau client ou école."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("organization_id", "organization_id"),
    }

    @classmethod
    def tenant_scope_q(cls, scope):
        scope_filter = Q(organization_id=scope.organization_id)
        if scope.school_id is not None:
            scope_filter &= Q(school__isnull=True) | Q(school_id=scope.school_id)
        return scope_filter

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="memberships",
        null=True,
        blank=True,
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["organization__name", "school__name", "role"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization", "school", "role"],
                condition=models.Q(school__isnull=False),
                name="uniq_membership_school_role",
            ),
            models.UniqueConstraint(
                fields=["user", "organization", "role"],
                condition=models.Q(school__isnull=True),
                name="uniq_membership_org_role",
            ),
        ]

    def clean(self):
        if self.school and self.school.organization_id != self.organization_id:
            raise ValidationError(
                {"school": "L'école doit appartenir à l'organisation indiquée."}
            )

    def __str__(self):
        scope = self.school.code if self.school else "toute l'organisation"
        return f"{self.user} — {self.get_role_display()} ({scope})"
