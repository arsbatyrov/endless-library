class NotFoundError(Exception):
    """Запрошенной сущности (книги, читателя, выдачи) нет."""


class BusinessRuleError(Exception):
    """Нарушено бизнес-правило (лимит, нет экземпляров, повторный возврат и т. п.)."""
