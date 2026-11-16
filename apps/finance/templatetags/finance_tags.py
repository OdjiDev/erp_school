from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def fcfa(value):
    """Formate un montant en francs CFA avec séparateurs de milliers."""
    if value is None or value == "":
        return "0 FCFA"
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    if amount == amount.to_integral_value():
        text = f"{amount:,.0f}".replace(",", " ")
    else:
        text = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} FCFA"
