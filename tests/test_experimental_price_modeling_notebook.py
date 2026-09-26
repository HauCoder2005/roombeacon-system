import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/drafts/03_experimental_price_modeling.ipynb"
REQUIREMENTS = ROOT / "notebooks/drafts/requirements-modeling.txt"


class ExperimentalModelingNotebookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cls.cells = cls.notebook["cells"]
        cls.markdown = "\n".join(
            "".join(cell.get("source", []))
            for cell in cls.cells
            if cell["cell_type"] == "markdown"
        )
        cls.code_cells = [
            "".join(cell.get("source", []))
            for cell in cls.cells
            if cell["cell_type"] == "code"
        ]
        cls.code = "\n".join(cls.code_cells)

    def test_report_has_required_ordered_sections_and_final_table(self):
        headings = [
            "## 1. Modeling Objective",
            "## 2. Modeling Dataset",
            "## 3. Feature Sets",
            "## 4. Train/Test Split",
            "## 5. Preprocessing",
            "## 6. Baseline",
            "## 7. Model Training",
            "## 8. Model Comparison",
            "## 9. Actual vs Predicted",
            "## 10. Residual Analysis",
            "## 11. Location Feature Contribution",
            "## 12. Error Analysis",
            "## 13. Limitations",
            "## 14. Final Comparison Table",
        ]
        positions = [self.markdown.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("MODEL COMPARISON RESULTS", self.markdown)

    def test_imports_are_confined_to_first_code_cell(self):
        for code in self.code_cells[1:]:
            self.assertIsNone(
                re.search(r"(?m)^\s*(?:from\s+\S+\s+import|import\s+\S+)", code)
            )

    def test_project_path_is_initialized_before_analytics_import(self):
        imports = self.code_cells[0]
        self.assertLess(
            imports.index("PROJECT_ROOT = setup_project_path()"),
            imports.index("from analytics.duckdb.connection import create_analytics_connection"),
        )

    def test_target_actions_and_leakage_guard_are_explicit(self):
        self.assertIn(
            "ACCEPTED_TARGET_ACTIONS = {'VALIDATED_EXISTING', 'REPARSE_ACCEPTED_CLEAN'}",
            self.code,
        )
        self.assertIn("price_validation_action.isin(ACCEPTED_TARGET_ACTIONS)", self.code)
        self.assertIn("FORBIDDEN_FEATURE_TOKENS", self.code)
        self.assertIn("price_per_m2", self.code)
        self.assertIn("TARGET_ACTION_LABELS", self.code)

    def test_split_is_created_once_before_model_fitting(self):
        split_position = self.code.index("train_idx, test_idx, SPLIT_STRATEGY")
        fit_position = self.code.index("model_pipeline.fit(")
        self.assertLess(split_position, fit_position)
        self.assertEqual(self.code.count("train_idx, test_idx, SPLIT_STRATEGY"), 1)
        self.assertIn("for feature_set_name, feature_columns in FEATURE_SETS.items()", self.code)
        self.assertIn("df_model.loc[train_idx, feature_columns]", self.code)
        self.assertIn("df_model.loc[test_idx, feature_columns]", self.code)

    def test_hist_gradient_boosting_never_receives_dense_one_hot(self):
        self.assertIn("OneHotEncoder", self.code)
        self.assertIn("sparse_output=True", self.code)
        self.assertIn("OrdinalEncoder", self.code)
        self.assertIn("HistGradientBoostingRegressor", self.code)
        self.assertIn("build_hist_pipeline", self.code)
        self.assertNotIn("sparse_output=False", self.code)
        self.assertIn("assert sparse.issparse", self.code)

    def test_final_table_contains_delta_metrics_and_adjacent_warning(self):
        for column in ["ΔMAE", "ΔRMSE", "ΔR²"]:
            self.assertIn(column, self.code)
        warning = (
            "Business duplicate analysis chưa hoàn tất, nên kết quả thử nghiệm có thể "
            "optimistic nếu cùng một property xuất hiện ở cả train và test."
        )
        self.assertIn(warning, self.markdown)

    def test_current_snapshot_scope_justifies_active_days(self):
        self.assertIn("current-snapshot price estimation", self.markdown)
        self.assertIn("active_days", self.code)

    def test_every_code_cell_is_valid_python(self):
        for index, source in enumerate(self.code_cells):
            compile(source, f"notebook-cell-{index}", "exec")

    def test_draft_dependencies_are_declared_without_changing_official_runtime(self):
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertIn("-r ../requirements.txt", requirements)
        self.assertIn("scikit-learn==1.9.1", requirements)
        self.assertIn("jinja2", requirements.lower())


if __name__ == "__main__":
    unittest.main()
