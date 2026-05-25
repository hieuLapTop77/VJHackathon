"""
kaggle/src/shap_analysis.py — SHAP feature importance for the best model.
"""
import os
import sys
import warnings
warnings.filterwarnings("ignore")

import matplotlib.pyplot as plt
import shap

_KAGGLE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_KAGGLE_DIR)
sys.path.insert(0, _PROJECT_ROOT)

from kaggle.src.config import OUTPUT_DIR, RANDOM_STATE


def run_shap(models_dict: dict, X_test, feature_names: list,
             best_model_name: str = None, save: bool = True):
    if best_model_name is None:
        tree_models = [n for n in models_dict if hasattr(models_dict[n], "feature_importances_")]
        if not tree_models:
            print("[shap] No tree-based model found. Skipping SHAP.")
            return None
        best_model_name = tree_models[0]
        print(f"[shap] No best_model_name provided -- using first tree model: {best_model_name}")

    model = models_dict.get(best_model_name)
    if model is None:
        print(f"[shap] '{best_model_name}' not found in models_dict.")
        for name, m in models_dict.items():
            if hasattr(m, "feature_importances_"):
                best_model_name = name
                model = m
                break
        if model is None:
            print("[shap] No tree-based model available. Skipping SHAP.")
            return None

    print(f"\n[shap] Computing SHAP values for: {best_model_name}")

    sample = X_test.sample(min(500, len(X_test)), random_state=RANDOM_STATE)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(sample)

    plt.figure(figsize=(12, 7))
    shap.summary_plot(shap_values, sample, feature_names=feature_names,
                      show=False, max_display=15)
    plt.title(f"SHAP Feature Impact -- {best_model_name} (Best Model)", fontsize=13)
    plt.tight_layout()

    if save:
        path = os.path.join(OUTPUT_DIR, "shap_summary_best_model.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"[shap] Saved: {path}")

    plt.show()
    return shap_values
