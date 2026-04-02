from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd


PRODUCTS = [
    ("SKU-1001", "Sony Noise Cancelling Headphones", "Wireless over-ear headphones with adaptive noise cancelling.", "sony", "audio", 349.0, 0.91, 1, "premium_audio"),
    ("SKU-1002", "Bose Quiet Wireless Headphones", "Bluetooth noise cancelling headphones with all-day comfort.", "bose", "audio", 329.0, 0.89, 1, "premium_audio"),
    ("SKU-1003", "Logitech MX Keys Keyboard", "Wireless office keyboard for productivity and multi-device use.", "logitech", "computer_accessories", 119.0, 0.88, 0, "office"),
    ("SKU-1004", "Razer Gaming Mechanical Keyboard", "RGB mechanical keyboard with tactile switches for gaming.", "razer", "computer_accessories", 169.0, 0.84, 1, "gaming"),
    ("SKU-1005", "Apple Watch SE", "Smartwatch with fitness tracking and notifications.", "apple", "wearables", 249.0, 0.95, 1, "fitness"),
    ("SKU-1006", "Garmin Forerunner 255", "Running watch with GPS and advanced workout metrics.", "garmin", "wearables", 299.0, 0.86, 0, "fitness"),
    ("SKU-1007", "Dyson Cordless Vacuum", "Cordless vacuum cleaner with strong suction.", "dyson", "home_appliances", 399.0, 0.83, 1, "home_cleaning"),
    ("SKU-1008", "Shark Cordless Vacuum", "Cordless vacuum with auto-empty docking station.", "shark", "home_appliances", 379.0, 0.81, 0, "home_cleaning"),
]

SCENARIOS = [
    ("Q-1001", "wireless headphones", "audio", "SKU-1001"),
    ("Q-1002", "office keyboard", "computer_accessories", "SKU-1003"),
    ("Q-1003", "running watch", "wearables", "SKU-1006"),
    ("Q-1004", "cordless vacuum", "home_appliances", "SKU-1007"),
]

QUERY_RULES = {
    "rule_set_id": "catalog_rules_v1",
    "rules": [
        {
            "rule_id": "pin_sony_for_wireless_headphones",
            "condition": {"query_contains_any": ["wireless", "headphones"], "category": "audio"},
            "action": {"pin_sku": "SKU-1001"}
        },
        {
            "rule_id": "pin_garmin_for_running",
            "condition": {"query_contains_any": ["running", "runner", "training"], "category": "wearables"},
            "action": {"pin_sku": "SKU-1006"}
        },
        {
            "rule_id": "boost_office_keyboard",
            "condition": {"query_contains_any": ["office", "productivity"], "category": "computer_accessories"},
            "action": {"boost_collection": "office", "boost_value": 0.22}
        },
        {
            "rule_id": "boost_promoted_audio",
            "condition": {"query_contains_any": ["headphones", "audio"], "category": "audio"},
            "action": {"boost_promoted": True, "boost_value": 0.10}
        }
    ]
}

INDEX_SETTINGS = {
    "settings": {
        "analysis": {
            "analyzer": {
                "catalog_text_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"]
                }
            },
            "normalizer": {
                "lowercase_normalizer": {
                    "type": "custom",
                    "filter": ["lowercase", "asciifolding"]
                }
            }
        }
    }
}

INDEX_MAPPINGS = {
    "mappings": {
        "properties": {
            "sku": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "catalog_text_analyzer"},
            "description": {"type": "text", "analyzer": "catalog_text_analyzer"},
            "brand": {"type": "keyword", "normalizer": "lowercase_normalizer"},
            "category": {"type": "keyword", "normalizer": "lowercase_normalizer"},
            "price": {"type": "scaled_float", "scaling_factor": 100},
            "popularity_score": {"type": "float"},
            "is_promoted": {"type": "boolean"},
            "collection": {"type": "keyword", "normalizer": "lowercase_normalizer"}
        }
    }
}


def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", suffix=".csv", delete=False, dir=path.parent, encoding="utf-8") as tmp_file:
        temp_path = Path(tmp_file.name)
    try:
        df.to_csv(temp_path, index=False)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", suffix=".json", delete=False, dir=path.parent, encoding="utf-8") as tmp_file:
        temp_path = Path(tmp_file.name)
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def ensure_dataset(base_dir: str | Path) -> dict[str, str]:
    base_path = Path(base_dir)
    catalog_path = base_path / "data" / "raw" / "catalog_products.csv"
    scenarios_path = base_path / "data" / "raw" / "query_scenarios.csv"
    rules_path = base_path / "query_rules" / "query_rules_examples.json"
    settings_path = base_path / "index_configs" / "products_index_settings.json"
    mappings_path = base_path / "index_configs" / "products_index_mappings.json"

    catalog_df = pd.DataFrame(
        PRODUCTS,
        columns=[
            "sku",
            "title",
            "description",
            "brand",
            "category",
            "price",
            "popularity_score",
            "is_promoted",
            "collection",
        ],
    )
    scenarios_df = pd.DataFrame(
        SCENARIOS,
        columns=["scenario_id", "query_text", "category_filter", "expected_sku"],
    )

    _atomic_write_csv(catalog_df, catalog_path)
    _atomic_write_csv(scenarios_df, scenarios_path)
    _atomic_write_json(QUERY_RULES, rules_path)
    _atomic_write_json(INDEX_SETTINGS, settings_path)
    _atomic_write_json(INDEX_MAPPINGS, mappings_path)

    return {
        "catalog_path": str(catalog_path),
        "scenarios_path": str(scenarios_path),
        "rules_path": str(rules_path),
        "settings_path": str(settings_path),
        "mappings_path": str(mappings_path),
    }
