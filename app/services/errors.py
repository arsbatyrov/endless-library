class NotFoundError(Exception):
    """Запрошенной сущности (книги, читателя, выдачи) нет."""


class BusinessRuleError(Exception):
    """Нарушено бизнес-правило (лимит, нет экземпляров, повторный возврат и т. п.)."""


class PermissionDeniedError(Exception):
    """The signed-in user's role does not allow this action (answered with 403)."""


class UnprocessableError(Exception):
    """The request is well-formed but a rule about one field is broken (answered with 422)."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
