import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cookbook.app import create_app
from cookbook.settings import Settings


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/recipes/tofu_rice_bowl",
        "/recipes/old_turnip_stew",
        "/recipes/almond_biscuits/export.pdf",
        "/recipes/old_turnip_stew/export.zip",
        "/tags",
        "/tags/korean",
        "/sources",
        "/sources/1",
        "/notes",
        "/api/recipes",
        "/api/recipes/tofu_rice_bowl",
    ],
)
def test_pages_are_found(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/recipes/no_such_recipe",
        "/tags/no_such_tag",
        "/sources/99",
        "/api/recipes/no_such_recipe",
        "/recipes/no_such_recipe/export.pdf",
        "/recipes/no_such_recipe/export.zip",
        "/images/5-00000000.webp",
        "/images/99-abcdef01.webp",
    ],
)
def test_unknown_things_are_not_found(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_listing_links_each_card_in_title_order(client: TestClient) -> None:
    page = client.get("/tags/asian").text

    assert re.findall(r'href="/recipes/(\w+)"', page) == ["chilli_oil_noodles", "tofu_rice_bowl"]


def test_recipe_page_shows_header_times_and_number_spans(client: TestClient) -> None:
    page = client.get("/recipes/tofu_rice_bowl").text

    assert '<div class="kicker label">Korean · Main</div>' in page
    assert (
        '<a href="https://example.com/tofu" rel="noreferrer">Allotment Weekly · Ada Example</a>'
        in page
    )
    assert re.findall(r"<dt class=\"label\">(\w+)</dt><dd>([^<]+)</dd>", page) == [
        ("Prep", "15min"),
        ("Cook", "2h 5min"),
        ("Total", "2h 20min"),
    ]
    assert (
        '<span class="q"><span class="n" data-value="2">2</span> x '
        '<span class="n" data-value="400" data-size>400</span>g</span>'
    ) in page
    assert '<span class="n" data-value="200" data-metric>200</span> g' in page
    assert '<h4 class="step-title">Fry the tofu</h4>' in page
    assert re.search(
        r'id="notes-step-2">\s*<div class="note">\s*<p>Use a cast iron pan</p>\s*'
        r'<div class="note-meta">\s*<time datetime="2026-01-03 10:00:00Z"'
        r' title="3 Jan 2026, 10:00">3 Jan 2026</time>\s*</div>',
        page,
    )
    assert "+ Note" not in page


def test_serves_dropdown_offers_multiples_of_a_range(client: TestClient) -> None:
    page = client.get("/recipes/tofu_rice_bowl").text

    assert re.findall(r'<option value="([^"]+)"( selected)?>([^<]+)</option>', page) == [
        ("0.5", "", "1–2"),
        ("1", " selected", "2–4"),
        ("1.5", "", "3–6"),
        ("2", "", "4–8"),
        ("3", "", "6–12"),
    ]
    assert '<span class="scaled" hidden>Recipe serves 2–4</span>' in page


def test_serves_dropdown_says_makes_for_a_yield(client: TestClient) -> None:
    page = client.get("/recipes/almond_biscuits").text

    assert '<label class="label" for="serves">makes</label>' in page
    assert '<option value="1" selected>24</option>' in page
    assert page.count("<option ") == 72
    assert '<span class="yield-unit">biscuits</span>' in page
    assert '<span class="scaled" hidden>Recipe makes 24 biscuits</span>' in page


def test_recipe_page_carries_metric_amounts_and_conversions(
    client: TestClient, recipes: sqlite3.Connection
) -> None:
    """The noodles get an imperial quantity and a Fahrenheit step to have something to convert."""
    recipes.executescript(
        """
        UPDATE ingredients SET quantity = '8 oz', amount_min = 226.8, amount_max = 226.8,
            unit = 'g' WHERE item = 'noodles';
        UPDATE steps SET text = 'Bake at 350°F in a 9-inch tin.' WHERE id = 3;
        """
    )

    noodles = client.get("/recipes/chilli_oil_noodles").text
    tofu = client.get("/recipes/tofu_rice_bowl").text

    assert (
        '<li data-tick="i1-1"><span class="q" data-metric-min="226.8" data-metric-max="226.8"'
        ' data-metric-unit="g"><span class="n" data-value="8">8</span> oz</span>'
    ) in noodles
    assert (
        '<p>Bake at 180°C, gas 4 in a <span class="conv" data-metric="23 cm">9-inch</span> tin.</p>'
    ) in noodles
    assert 'data-units="metric"' in noodles
    assert 'data-units="metric"' not in tofu
    assert '<li data-tick="s2">' in tofu
    assert 'aria-label="Step 2 done"' in tofu


def test_text_is_escaped(client: TestClient, recipes: sqlite3.Connection) -> None:
    recipes.execute("UPDATE recipe_notes SET body = '<b>hot</b>' WHERE id = 1")

    page = client.get("/recipes/tofu_rice_bowl").text

    assert "&lt;b&gt;hot&lt;/b&gt;" in page
    assert "<b>hot</b>" not in page


def test_image_is_served_with_an_immutable_cache_header(client: TestClient) -> None:
    response = client.get("/images/5-abcdef01.webp")

    assert response.content == bytes.fromhex(
        "524946461c000000574542505650384c100000002f038000000750b8284fff0311d1ff00"
    )
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_font_is_cached_for_a_year_and_css_revalidates(client: TestClient) -> None:
    font = client.get("/static/fonts/InterVariable.woff2")
    css = client.get("/static/site.css")

    assert font.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert css.headers["cache-control"] == "no-cache"


def test_healthz_reports_the_schema_version(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok", "schema_version": 3}


def test_app_refuses_to_start_on_an_unmigrated_database(tmp_path: Path) -> None:
    settings = Settings(db_path=tmp_path / "empty.db", secret_key="s" * 32)

    with pytest.raises(RuntimeError, match="schema version 0, this code expects 3"):
        create_app(settings)


def test_app_migrates_at_start_when_asked(tmp_path: Path) -> None:
    settings = Settings(db_path=tmp_path / "empty.db", secret_key="s" * 32, migrate=True)

    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").json() == {"status": "ok", "schema_version": 3}


def test_search_page_renders_results_and_filter_state(client: TestClient) -> None:
    """A full page for a plain request, with the chosen tag ticked and blank fields ignored."""
    response = client.get("/?q=tofu&tag=asian&cooked=no&max_total=&sort=&publication=")

    assert response.status_code == 200
    assert response.text.startswith("<!doctype html>")
    assert re.findall(r'class="card" href="/recipes/(\w+)"', response.text) == [
        "tofu_rice_bowl",
        "chilli_oil_noodles",
    ]
    assert '<input type="checkbox" name="tag" value="asian" checked>' in response.text
    assert (
        '<button type="button" class="filters-button label" data-opens="filters">Filters (2)'
        in (response.text)
    )
    assert response.headers["vary"] == "HX-Request, Cookie"


def test_htmx_gets_only_the_results_and_tag_counts(client: TestClient) -> None:
    response = client.get("/?tag=korean", headers={"HX-Request": "true"})

    assert not response.text.startswith("<!doctype html>")
    assert re.findall(r'class="card" href="/recipes/(\w+)"', response.text) == ["tofu_rice_bowl"]
    assert '<div id="tag-filters" hx-swap-oob="true">' in response.text


def test_htmx_history_restore_gets_the_full_page(client: TestClient) -> None:
    response = client.get(
        "/?tag=korean", headers={"HX-Request": "true", "HX-History-Restore-Request": "true"}
    )

    assert response.text.startswith("<!doctype html>")


def test_api_recipes_take_the_search_filters(client: TestClient) -> None:
    response = client.get("/api/recipes?q=tofu&sort=title")

    assert [card["slug"] for card in response.json()] == ["chilli_oil_noodles", "tofu_rice_bowl"]
