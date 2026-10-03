"""Помощники для управления сетью в UI-тестах."""

from playwright.sync_api import Error, Page, Route


class HeldRequests:
    """«Подвешивает» запросы к адресу, пока тест не вызовет release().

    Позволяет увидеть промежуточные состояния интерфейса (например, «Загрузка…»), которые
    в обычной работе мелькают за миллисекунды.

    Почему release() отпускает все запросы, а не первый: в режиме разработки React
    (StrictMode) эффект загрузки запускается дважды, и первый запрос страница отменяет
    сама. Отпускать нужно тот, что остался, а отменённый просто игнорируется.
    """

    def __init__(self, page: Page, url_pattern: str):
        self._page = page
        self._routes: list[Route] = []
        page.route(url_pattern, lambda route: self._routes.append(route))

    def release(self) -> None:
        for _ in range(40):  # ждём (до 2 секунд), пока хотя бы один запрос дойдёт до перехватчика
            if self._routes:
                break
            self._page.wait_for_timeout(50)
        assert self._routes, "ни один запрос не был перехвачен"
        for route in self._routes:
            try:
                route.continue_()
            except Error:
                pass  # запрос уже отменён страницей: продолжать нечего
        self._routes.clear()
