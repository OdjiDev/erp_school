from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImportMessage:
    sheet: str
    row: int
    message: str

    def __str__(self):
        if self.row:
            return f"{self.sheet}, ligne {self.row} : {self.message}"
        return f"{self.sheet} : {self.message}"


@dataclass
class ImportReport:
    created: Counter = field(default_factory=Counter)
    updated: Counter = field(default_factory=Counter)
    warnings: list[ImportMessage] = field(default_factory=list)
    errors: list[ImportMessage] = field(default_factory=list)

    @property
    def has_errors(self):
        return bool(self.errors)

    @property
    def created_items(self):
        return sorted(self.created.items())

    @property
    def updated_items(self):
        return sorted(self.updated.items())

    def add_created(self, label, count=1):
        self.created[label] += count

    def add_updated(self, label, count=1):
        self.updated[label] += count

    def add_warning(self, sheet, row, message):
        self.warnings.append(ImportMessage(sheet, row, message))

    def add_error(self, sheet, row, message):
        self.errors.append(ImportMessage(sheet, row, message))


def error_message(exc):
    """Message lisible pour les erreurs d'import."""
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError

    if isinstance(exc, ValidationError):
        if hasattr(exc, "error_dict"):
            parts = []
            for field, messages in exc.error_dict.items():
                parts.append(f"{field} : {' '.join(messages)}")
            return "; ".join(parts)
        return " ".join(exc.messages)
    if isinstance(exc, IntegrityError):
        return "Doublon ou contrainte d'unicité violée."
    return str(exc)
