from apps.academics.models import AcademicYear


def current_academic_year(school):
    """Année courante, sinon la plus récente."""
    return (
        AcademicYear.objects.filter(school=school, is_current=True)
        .order_by("-start_date")
        .first()
        or AcademicYear.objects.filter(school=school)
        .order_by("-start_date")
        .first()
    )
