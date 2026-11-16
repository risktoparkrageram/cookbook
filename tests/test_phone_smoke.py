import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, expect, sync_playwright

from cookbook.app import create_app
from cookbook.settings import Settings

pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def site(recipes: sqlite3.Connection, admin: str, database_path: Path) -> Iterator[str]:
    """The app served by uvicorn on a free port, over the fixture recipes and account."""
    settings = Settings(db_path=database_path, secret_key="s" * 32, failed_login_delay_s=0)
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=0, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


@pytest.fixture
def phone(browser: Browser) -> Iterator[Page]:
    """A page at an iPhone's 375 px width, with touch."""
    context = browser.new_context(
        viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True
    )
    yield context.new_page()
    context.close()


def test_search_updates_the_results_and_the_address_as_you_type(site: str, phone: Page) -> None:
    errors: list[str] = []
    phone.on("pageerror", lambda error: errors.append(str(error)))
    phone.goto(site)

    phone.fill("input[name=q]", "noodl")
    expect(phone).to_have_url(re.compile(r"\?q=noodl$"))
    phone.click(".filters-button")
    phone.locator("#tag-filters label", has_text="quick").click()
    expect(phone).to_have_url(re.compile(r"\?q=noodl&tag=quick$"))

    cards = phone.locator(".card").evaluate_all("cards => cards.map(card => card.pathname)")
    assert cards == ["/recipes/chilli_oil_noodles"]
    assert errors == []


def test_cook_mode_scales_converts_and_remembers_ticks(
    site: str, phone: Page, recipes: sqlite3.Connection
) -> None:
    """
    Halving shows fractions; the noodles get a pound range to convert.

    Doubling that range crosses 1000 g at one end only, which must stay in grams.
    """
    recipes.execute(
        "UPDATE ingredients SET quantity = '1–2 lbs', amount_min = 453.59237,"
        " amount_max = 907.18474, unit = 'g' WHERE item = 'noodles'"
    )
    errors: list[str] = []
    phone.on("pageerror", lambda error: errors.append(str(error)))
    phone.goto(f"{site}/recipes/tofu_rice_bowl")
    quantities = phone.locator("ul.ing .q")

    phone.select_option("#serves", label="1–2")
    expect(quantities).to_have_text(["100 g", "1 x 400g", "¾ tbsp", ""])
    phone.select_option("#serves", label="4–8")
    expect(quantities).to_have_text(["400 g", "4 x 400g", "3 tbsp", ""])
    expect(phone.locator(".scaled")).to_have_text("Recipe serves 2–4")
    phone.locator("ul.ing li").first.click()
    phone.click(".toggle [data-tab=method]")
    phone.locator("ol.steps > li").first.locator("p").click()
    phone.locator("ol.steps > li").first.locator(".step-tick").click()
    phone.reload()
    phone.click(".toggle [data-tab=method]")

    expect(phone.locator("ol.steps > li.done .num")).to_have_text(["01"])
    expect(phone.locator("ol.steps > li.current .num")).to_have_text(["02"])
    expect(phone.locator("ul.ing li.done .item")).to_have_text(["firm tofu"])
    expect(quantities.first).to_have_text("400 g")
    phone.click(".reset")
    expect(phone.locator("li.done")).to_have_count(0)
    expect(quantities.first).to_have_text("200 g")

    phone.goto(f"{site}/recipes/chilli_oil_noodles")
    noodles = phone.locator("ul.ing .q").first
    phone.click("[data-units=metric]")
    expect(noodles).to_have_text("≈ 455–905 g")
    phone.select_option("#serves", label="4")
    expect(noodles).to_have_text("≈ 905–1815 g")
    phone.reload()
    expect(noodles).to_have_text("≈ 905–1815 g")
    assert errors == []


def test_signed_in_cook_adds_and_deletes_a_step_note(
    site: str, phone: Page, recipes: sqlite3.Connection
) -> None:
    phone.on("dialog", lambda dialog: dialog.accept())
    phone.goto(f"{site}/recipes/tofu_rice_bowl")
    phone.click("footer a")
    phone.fill("input[name=email]", "cook@example.com")
    phone.fill("input[name=password]", "correct horse battery")
    phone.click("button.submit")
    expect(phone).to_have_url(f"{site}/recipes/tofu_rice_bowl")
    phone.click(".toggle [data-tab=method]")
    first_step_notes = phone.locator("#notes-step-1")

    first_step_notes.locator(".add-note summary").click()
    first_step_notes.locator("textarea").fill("Weigh the tofu down with a pan")
    first_step_notes.locator("button", has_text="Save").click()
    expect(first_step_notes.locator(".note > p")).to_have_text(["Weigh the tofu down with a pan"])
    first_step_notes.locator(".note-edit summary").click()
    first_step_notes.locator("button", has_text="Delete").click()
    expect(first_step_notes.locator(".note")).to_have_count(0)

    count = recipes.execute("SELECT count(*) FROM recipe_notes WHERE step_id = 1").fetchone()[0]
    assert count == 0


def test_signed_in_cook_ticks_a_recipe_cooked(
    site: str, phone: Page, recipes: sqlite3.Connection
) -> None:
    phone.goto(f"{site}/login?next=/recipes/tofu_rice_bowl")
    phone.fill("input[name=email]", "cook@example.com")
    phone.fill("input[name=password]", "correct horse battery")
    phone.click("button.submit")
    tick = phone.locator(".cooked-tick")

    tick.click()
    expect(tick).to_have_attribute("aria-pressed", "true")
    phone.goto(site)

    statuses = phone.locator(".card .status").all_inner_texts()
    assert statuses == ["COOKED", "NEW", "COOKED"]
    cooked = recipes.execute("SELECT recipe_id FROM cooked_recipes ORDER BY 1").fetchall()
    assert [row[0] for row in cooked] == [1, 3]


def test_theme_survives_a_reload_and_both_inter_faces_load(site: str, phone: Page) -> None:
    phone.goto(site)
    phone.click(".theme")
    phone.reload()

    assert phone.evaluate("document.documentElement.dataset.theme") == "dark"
    faces = phone.evaluate(
        """async () => {
            const loaded = [];
            for (const font of ["15px Inter", "italic 15px Inter"]) {
              loaded.push((await document.fonts.load(font)).length);
            }
            return loaded;
        }"""
    )
    assert faces == [1, 1]


def test_tap_targets_are_at_least_44_px(site: str, phone: Page) -> None:
    phone.goto(f"{site}/login?next=/recipes/tofu_rice_bowl")
    phone.fill("input[name=email]", "cook@example.com")
    phone.fill("input[name=password]", "correct horse battery")
    phone.click("button.submit")
    visible_by_tab = {
        "ingredients": [
            "nav.bar a",
            ".toggle button",
            ".theme",
            ".cooked-tick",
            "#serves",
            ".exports a",
        ],
        "method": [
            "ol.steps .step-tick",
            "ol.steps .add-note summary",
            "ol.steps .note-edit summary",
        ],
    }

    heights = {}
    for tab, selectors in visible_by_tab.items():
        phone.click(f".toggle [data-tab={tab}]")
        for selector in selectors:
            heights[selector] = min(
                phone.locator(selector).evaluate_all(
                    "elements => elements.map(element => element.getBoundingClientRect().height)"
                )
            )

    assert {selector: height for selector, height in heights.items() if height < 44} == {}
