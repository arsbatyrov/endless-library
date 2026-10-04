"""Дымовые проверки: приложение открывается и базово работает."""

import pytest
from playwright.sync_api import expect


def test_app_opens_with_books_tab_selected(app):
    app.open()

    expect(app.page.get_by_role("heading", name="Endless Library", level=1)).to_be_visible()
    expect(app.tab("books")).to_have_attribute("aria-selected", "true")
    expect(app.books.empty).to_be_visible()


@pytest.mark.parametrize(
    "section, empty_locator",
    [
        ("books", lambda app: app.books.empty),
        ("readers", lambda app: app.readers.empty),
        ("loans", lambda app: app.loans.pick_reader_hint),
    ],
    ids=["books", "readers", "loans"],
)
def test_every_section_opens_and_shows_its_empty_state(app, section, empty_locator):
    app.open()

    app.tab(section).click()

    expect(app.tab(section)).to_have_attribute("aria-selected", "true")
    expect(empty_locator(app)).to_be_visible()


def test_data_created_through_api_is_visible_in_the_ui(app, api):
    api.create_book(title="Война и мир", author="Лев Толстой", year=1869, copies=3)

    app.open()

    expect(app.books.rows).to_have_count(1)
    expect(app.books.row("Война и мир")).to_contain_text("Лев Толстой")
