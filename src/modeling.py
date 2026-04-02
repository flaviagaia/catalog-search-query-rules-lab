from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.sample_data import ensure_dataset


def _normalize(values: np.ndarray) -> np.ndarray:
    values = values.astype("float32")
    minimum = float(values.min())
    maximum = float(values.max())
    if maximum - minimum < 1e-8:
        return np.zeros_like(values, dtype="float32")
    return (values - minimum) / (maximum - minimum)


def _apply_query_rules(
    scenario: pd.Series,
    rules_payload: dict,
    catalog: pd.DataFrame,
    base_scores: np.ndarray,
) -> np.ndarray:
    adjusted = base_scores.copy().astype("float32")
    query_text = scenario["query_text"].lower()
    category_filter = scenario["category_filter"]

    for rule in rules_payload["rules"]:
        condition = rule["condition"]
        category_ok = category_filter == condition.get("category", category_filter)
        query_ok = any(token in query_text for token in condition.get("query_contains_any", []))
        if not (category_ok and query_ok):
            continue

        action = rule["action"]
        if "pin_sku" in action:
            adjusted[catalog.index[catalog["sku"] == action["pin_sku"]][0]] += 10.0
        if action.get("boost_promoted"):
            adjusted += catalog["is_promoted"].to_numpy(dtype="float32") * float(action["boost_value"])
        if "boost_collection" in action:
            adjusted += (
                (catalog["collection"] == action["boost_collection"]).to_numpy(dtype="float32")
                * float(action["boost_value"])
            )

    return adjusted


def run_pipeline(base_dir: str | Path) -> dict:
    base_path = Path(base_dir)
    dataset = ensure_dataset(base_path)
    catalog = pd.read_csv(dataset["catalog_path"])
    scenarios = pd.read_csv(dataset["scenarios_path"])
    rules_payload = json.loads(Path(dataset["rules_path"]).read_text(encoding="utf-8"))

    corpus = (catalog["title"] + " " + catalog["description"] + " " + catalog["brand"] + " " + catalog["category"]).tolist()
    vectorizer = TfidfVectorizer(ngram_range=(1, 2))
    doc_matrix = vectorizer.fit_transform(corpus)

    baseline_results = []
    ruled_results = []

    for _, scenario in scenarios.iterrows():
        query_vector = vectorizer.transform([scenario["query_text"]])
        lexical_scores = cosine_similarity(query_vector, doc_matrix).reshape(-1)
        lexical_component = _normalize(lexical_scores)
        popularity_component = _normalize(catalog["popularity_score"].to_numpy(dtype="float32"))
        promoted_component = catalog["is_promoted"].to_numpy(dtype="float32")

        base_scores = (
            0.70 * lexical_component
            + 0.20 * popularity_component
            + 0.10 * promoted_component
        )

        category_mask = (catalog["category"] == scenario["category_filter"]).to_numpy()
        filtered_base_scores = np.where(category_mask, base_scores, -1.0)
        ruled_scores = _apply_query_rules(scenario, rules_payload, catalog, filtered_base_scores)

        baseline_ranked = catalog.copy()
        baseline_ranked["score"] = np.round(filtered_base_scores, 4)
        baseline_ranked = baseline_ranked.sort_values(by="score", ascending=False).reset_index(drop=True)

        ruled_ranked = catalog.copy()
        ruled_ranked["score"] = np.round(ruled_scores, 4)
        ruled_ranked = ruled_ranked.sort_values(by="score", ascending=False).reset_index(drop=True)

        baseline_results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "query_text": scenario["query_text"],
                "expected_sku": scenario["expected_sku"],
                "top_sku": baseline_ranked.loc[0, "sku"],
            }
        )
        ruled_results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "query_text": scenario["query_text"],
                "expected_sku": scenario["expected_sku"],
                "top_sku": ruled_ranked.loc[0, "sku"],
            }
        )

    baseline_df = pd.DataFrame(baseline_results)
    ruled_df = pd.DataFrame(ruled_results)

    baseline_hit_rate = float((baseline_df["top_sku"] == baseline_df["expected_sku"]).mean())
    rules_hit_rate = float((ruled_df["top_sku"] == ruled_df["expected_sku"]).mean())

    processed_dir = base_path / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    before_path = processed_dir / "baseline_results.csv"
    after_path = processed_dir / "rules_results.csv"
    report_path = processed_dir / "query_rules_lab_report.json"

    baseline_df.to_csv(before_path, index=False)
    ruled_df.to_csv(after_path, index=False)

    summary = {
        "dataset_source": "catalog_query_rules_sample",
        "product_count": int(len(catalog)),
        "scenario_count": int(len(scenarios)),
        "baseline_hit_rate_at_1": round(baseline_hit_rate, 4),
        "rules_hit_rate_at_1": round(rules_hit_rate, 4),
        "improvement": round(rules_hit_rate - baseline_hit_rate, 4),
        "baseline_artifact": str(before_path),
        "rules_artifact": str(after_path),
        "report_artifact": str(report_path),
        "rules_definition_artifact": dataset["rules_path"],
        "settings_artifact": dataset["settings_path"],
        "mappings_artifact": dataset["mappings_path"],
    }
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
