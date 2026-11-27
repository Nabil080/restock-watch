import json
import math
from pathlib import Path

import pytest

from config import ConfigError, load_config, parse_config

EXAMPLE = Path(__file__).parent.parent / "config.example.json"


def config_with(**product):
    return {"products": [{"name": "Console", "urls": ["https://www.shop.com/p/1"], **product}]}


def test_example_config_loads():
    config = load_config(EXAMPLE)
    assert config.products
    assert config.minutes_between_checks[0] >= 1


def test_defaults():
    config = parse_config(config_with())
    product = config.products[0]
    assert (product.min_price, product.max_price) == (0, math.inf)
    assert product.pages[0].shop == "shop.com"
    assert config.ntfy_server == "https://ntfy.sh"
    assert config.browser == "msedge"


def test_url_with_options():
    config = parse_config(config_with(urls=[{"url": "https://amazon.fr/dp/1", "selector": "#buybox", "shop": "Amazon"}]))
    page = config.products[0].pages[0]
    assert (page.shop, page.selector) == ("Amazon", "#buybox")


@pytest.mark.parametrize("product, message", [
    ({"max_prise": 650}, "Unknown setting 'max_prise'"),
    ({"max_price": "650 €"}, "must be a number"),
    ({"min_price": 700, "max_price": 650}, "min_price is above max_price"),
    ({"urls": []}, "at least one product link"),
    ({"urls": ["www.shop.com"]}, "should start with https://"),
])
def test_product_mistakes(product, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(config_with(**product))


def test_bad_webhook():
    with pytest.raises(ConfigError, match="discord_webhook"):
        parse_config({**config_with(), "discord_webhook": "https://example.com/hook"})


def test_bad_interval():
    with pytest.raises(ConfigError, match="minutes_between_checks"):
        parse_config({**config_with(), "minutes_between_checks": [5, 2]})


def test_invalid_json_gives_the_line(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{\n  "products": []\n  "ntfy_topic": "x"\n}', encoding="utf-8")
    with pytest.raises(ConfigError, match="line 3"):
        load_config(path)


def test_notepad_bom_is_accepted(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config_with()), encoding="utf-8-sig")
    assert load_config(path).products[0].name == "Console"
