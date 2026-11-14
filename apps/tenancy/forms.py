from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from apps.academics.models import AcademicYear
from apps.academics.utils import current_academic_year
from .models import Membership, Role, School

User = get_user_model()

SCHOOL_STAFF_ROLES = [
    Role.SCHOOL_ADMIN.value,
    Role.SECRETARY.value,
    Role.ACCOUNTANT.value,
    Role.TEACHER.value,
    Role.SURVEILLANT.value,
    Role.AUDITOR.value,
]


def staff_role_choices(can_manage_organization):
    labels = dict(Role.choices)
    roles = list(SCHOOL_STAFF_ROLES)
    if can_manage_organization:
        roles.insert(0, Role.ORG_ADMIN.value)
    return [(role, labels[role]) for role in roles]


class ExcelImportForm(forms.Form):
    fichier = forms.FileField(
        label="Classeur Excel",
        help_text=(
            "Fichier .xlsx contenant les feuilles Matieres, Coefficients "
            "et Eleves."
        ),
    )
    annee = forms.ModelChoiceField(
        label="Année scolaire",
        queryset=AcademicYear.objects.none(),
    )
    dry_run = forms.BooleanField(
        label="Simulation uniquement (aucune donnée enregistrée)",
        required=False,
        initial=True,
    )
    creer_classes = forms.BooleanField(
        label="Créer les classes manquantes",
        required=False,
        initial=True,
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        if school is None:
            return

        self.fields["annee"].queryset = AcademicYear.objects.filter(
            school=school
        ).order_by("-start_date")
        self.fields["annee"].empty_label = None
        current = current_academic_year(school)
        if current is not None:
            self.fields["annee"].initial = current.pk

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if not fichier.name.lower().endswith(".xlsx"):
            raise forms.ValidationError(
                "Le fichier doit être un classeur Excel au format .xlsx."
            )
        if fichier.size > 10 * 1024 * 1024:
            raise forms.ValidationError(
                "Le fichier ne doit pas dépasser 10 Mo."
            )
        return fichier


class StaffUserCreateForm(UserCreationForm):
    role = forms.ChoiceField(label="Rôle", choices=[])
    scope = forms.ChoiceField(
        label="Portée du rôle",
        choices=[
            ("school", "Cette école"),
            ("organization", "Toute l'organisation"),
        ],
        initial="school",
        help_text=(
            "Un rôle au niveau de l'organisation s'applique à toutes les "
            "écoles du client."
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "Identifiant de connexion",
            "first_name": "Prénoms",
            "last_name": "Nom",
            "email": "Email",
        }

    def __init__(
        self, *args, school=None, can_manage_organization=False, **kwargs
    ):
        self.school = school
        self.can_manage_organization = can_manage_organization
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = staff_role_choices(
            can_manage_organization
        )
        if not can_manage_organization:
            self.fields["scope"].choices = [("school", "Cette école")]
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = False

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Cet identifiant de connexion existe déjà.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        scope = cleaned_data.get("scope")
        if role == Role.ORG_ADMIN.value and scope != "organization":
            self.add_error(
                "scope",
                "Un administrateur client doit avoir une portée "
                "« toute l'organisation ».",
            )
        if not self.can_manage_organization and scope != "school":
            self.add_error(
                "scope", "Vous ne pouvez créer que des comptes de cette école."
            )
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.email = self.cleaned_data.get("email", "").strip()
        user.is_active = True
        if commit:
            user.save()
            scope = self.cleaned_data["scope"]
            Membership.all_objects.create(
                user=user,
                organization=self.school.organization,
                school=self.school if scope == "school" else None,
                role=self.cleaned_data["role"],
            )
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "is_active"]
        labels = {
            "first_name": "Prénoms",
            "last_name": "Nom",
            "email": "Email",
            "is_active": "Compte actif",
        }

    def __init__(self, *args, can_deactivate=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = False
        if not can_deactivate:
            self.fields["is_active"].disabled = True
            self.fields["is_active"].help_text = (
                "Seul un administrateur client peut désactiver un compte."
            )


class MembershipForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = ["role", "school", "is_active"]
        labels = {
            "role": "Rôle",
            "school": "Portée",
            "is_active": "Rôle actif",
        }
        help_texts = {
            "school": (
                "Laisser vide pour attribuer le rôle à toutes les écoles "
                "de l'organisation."
            ),
        }

    def __init__(
        self,
        *args,
        school=None,
        user=None,
        can_manage_organization=False,
        **kwargs,
    ):
        self.school = school
        self.membership_user = user
        super().__init__(*args, **kwargs)
        self.instance.organization = school.organization
        if not self.instance._state.adding:
            self.membership_user = self.instance.user
        self.fields["role"].choices = staff_role_choices(
            can_manage_organization
        )
        # Le formulaire agit dans le périmètre de l'école courante. Un
        # administrateur client qui veut gérer une autre école y accède
        # directement ; le rôle sans école reste disponible pour toute
        # l'organisation.
        self.fields["school"].queryset = School.all_objects.filter(
            pk=school.pk
        )
        if not can_manage_organization:
            self.fields["school"].initial = school.pk
            self.fields["school"].disabled = True
            self.fields["school"].help_text = (
                "Vous ne pouvez attribuer que des rôles dans cette école."
            )

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        membership_school = cleaned_data.get("school")
        if role == Role.ORG_ADMIN.value and membership_school is not None:
            self.add_error(
                "school",
                "Un administrateur client agit sur toute l'organisation.",
            )
        if self.membership_user is not None and role:
            duplicates = Membership.all_objects.filter(
                user=self.membership_user,
                organization=self.school.organization,
                role=role,
                school=membership_school,
            )
            if not self.instance._state.adding:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    "role", "Ce rôle est déjà attribué à cet utilisateur."
                )
        return cleaned_data
