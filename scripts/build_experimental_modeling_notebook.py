"""Build the experimental RoomBeacon price-modeling notebook."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notebooks/drafts/03_experimental_price_modeling.ipynb"


def lines(source):
    return source.splitlines(keepends=True)


def markdown(source):
    return {"cell_type": "markdown", "metadata": {}, "source": lines(source)}


def code(source):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": lines(source),
    }


cells = [
    markdown("""# Experimental Price Modeling — RoomBeacon

**Trạng thái:** Thử nghiệm phân tích, không phải pipeline production.

Notebook này ước lượng giá thuê của **current snapshot** bằng dữ liệu đã được kiểm tra theo Task 11. Nó không ghi ngược dữ liệu, không lưu model và không thay đổi Task 01–11. Mục tiêu là so sánh baseline tabular models trên cùng một holdout, đồng thời đo đóng góp của thông tin vị trí có cấu trúc.
"""),
    code("""# Imports & Configuration — all notebook imports are intentionally centralized here.
from pathlib import Path
import sys
from time import perf_counter

PROJECT_ROOT = next(
    path for path in [Path.cwd(), *Path.cwd().parents]
    if (path / 'crawler').is_dir() and (path / 'analytics').is_dir()
)
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from IPython.display import display, Markdown
from dotenv import load_dotenv
from scipy import sparse
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from notebooks.utils import setup_project_path
PROJECT_ROOT = setup_project_path()

from analytics.duckdb.connection import create_analytics_connection
from notebooks.utils.address_parser import apply_address_parsing
from notebooks.utils.location_analysis import audit_coordinate_trust
from notebooks.utils.notebook_audit import load_snapshot, validate_numeric_candidates
from notebooks.utils.text_standardization import apply_text_standardization
from notebooks.utils.ward_normalization import apply_ward_mapping

load_dotenv(PROJECT_ROOT / '.env', override=False)
pd.set_option('display.max_rows', 25)
pd.set_option('display.max_columns', 20)
px.defaults.template = 'plotly_white'
pio.renderers.default = 'plotly_mimetype+notebook_connected'

RANDOM_STATE = 42
TEST_SIZE = 0.20
MIN_CATEGORY_FREQUENCY = 20
MAX_CATEGORIES = 200
DISTRICT_MIN_TEST_ROWS = 30
SCATTER_RENDER_ROWS = 5_000
ACCEPTED_TARGET_ACTIONS = {'VALIDATED_EXISTING', 'REPARSE_ACCEPTED_CLEAN'}
TARGET_ACTION_LABELS = {
    'VALIDATED_EXISTING': 'EXISTING_VALID',
    'REPARSE_ACCEPTED_CLEAN': 'REPARSE_ACCEPTED_CLEAN',
}
FORBIDDEN_FEATURE_TOKENS = ('price', 'target', 'label', 'prediction', 'residual')
"""),
    markdown("""## 1. Modeling Objective

Bài toán được định nghĩa là **current-snapshot price estimation**: ước lượng giá thuê tháng đã được Task 11 chấp nhận cho mỗi listing đang có trong snapshot hiện tại. Vì vậy `active_days` được dùng như một đặc trưng trạng thái của listing tại thời điểm snapshot; kết quả không được diễn giải như dự báo giá tương lai.

Đây là regression experiment để so sánh mô hình, không phải recommendation, causal analysis hay production scoring.
"""),
    code("""# Read one canonical snapshot through the existing read-only analytical boundary.
conn = create_analytics_connection(db_path=':memory:')
df_latest, raw_evidence, RUN_CONTEXT = load_snapshot(conn, PROJECT_ROOT)
N_CANDIDATE_ROWS = len(df_latest)
source_hash_before = pd.util.hash_pandas_object(df_latest, index=True).sum()
display(pd.Series(RUN_CONTEXT, name='Giá trị runtime').to_frame())
"""),
    markdown("""## 2. Modeling Dataset

`df_model` là DataFrame riêng cho thử nghiệm. Target chỉ nhận hai trạng thái Task 11:

- `VALIDATED_EXISTING` — được trình bày là `EXISTING_VALID` trong báo cáo;
- `REPARSE_ACCEPTED_CLEAN`.

Các trạng thái suspicious, invalid, unknown lineage và null không đi vào target. Không có bước tự parse giá mới, không lọc outlier ngoài quality gate đã có, và không ghi bất kỳ giá trị nào về snapshot nguồn.
"""),
    code("""# Reproduce the implemented Task 08–11 transformations without mutating source data.
df_stage = df_latest.copy()
df_stage = apply_text_standardization(
    df_stage, 'best_address_text', 'best_address_text_normalized'
)
df_stage = apply_address_parsing(df_stage, 'best_address_text_normalized')
df_stage = apply_ward_mapping(
    df_stage, 'ward_text_extracted', 'district_text_extracted'
)
df_stage = audit_coordinate_trust(df_stage)

price_audit = validate_numeric_candidates(df_latest, raw_evidence, 'price')
area_audit = validate_numeric_candidates(df_latest, raw_evidence, 'area')
df_stage['price_amount_clean_candidate'] = price_audit.clean_candidate
df_stage['price_validation_action'] = price_audit.action
df_stage['area_value_clean_candidate'] = area_audit.clean_candidate
df_stage['area_validation_action'] = area_audit.action

accepted_target_mask = (
    df_stage.price_validation_action.isin(ACCEPTED_TARGET_ACTIONS)
    & df_stage.price_amount_clean_candidate.notna()
)
assert accepted_target_mask.equals(
    price_audit.action.isin(ACCEPTED_TARGET_ACTIONS) & price_audit.clean_candidate.notna()
)

model_columns = [
    'rental_post_id', 'source_code', 'best_address_source', 'full_address_text',
    'area_value_clean_candidate', 'active_days', 'latest_observed_at',
    'district_text_extracted', 'ward_current', 'has_trusted_coordinate',
    'price_amount_clean_candidate', 'price_validation_action',
]
if 'duplicate_group_id' in df_stage.columns:
    model_columns.append('duplicate_group_id')

df_model = df_stage.loc[accepted_target_mask, model_columns].copy()
df_model = df_model.rename(columns={
    'area_value_clean_candidate': 'area_value_clean',
    'district_text_extracted': 'district_clean',
    'price_amount_clean_candidate': 'target_price_vnd',
})
df_model['target_action'] = df_model.price_validation_action.map(TARGET_ACTION_LABELS)
df_model['has_detailed_address'] = (
    df_model.full_address_text.astype('string').str.strip().replace('', pd.NA).notna()
)
df_model['target_price_vnd'] = pd.to_numeric(df_model.target_price_vnd, errors='raise')
df_model['area_value_clean'] = pd.to_numeric(df_model.area_value_clean, errors='coerce')
df_model['active_days'] = pd.to_numeric(df_model.active_days, errors='coerce')
df_model['latest_observed_at'] = pd.to_datetime(df_model.latest_observed_at, errors='coerce')

for column in ['source_code', 'best_address_source', 'district_clean', 'ward_current']:
    df_model[column] = df_model[column].astype(object).where(df_model[column].notna(), np.nan)

assert df_model.rental_post_id.is_unique
assert df_model.target_action.isin({'EXISTING_VALID', 'REPARSE_ACCEPTED_CLEAN'}).all()
assert np.isfinite(df_model.target_price_vnd).all()
assert df_model.target_price_vnd.gt(0).all()
assert pd.util.hash_pandas_object(df_latest, index=True).sum() == source_hash_before

coverage = pd.DataFrame({
    'Trường': ['Target giá hợp lệ', 'Diện tích sạch', 'Quận/Huyện', 'Phường/Xã',
               'Tọa độ đáng tin cậy'],
    'Số dòng có dữ liệu': [
        len(df_model), df_model.area_value_clean.notna().sum(),
        df_model.district_clean.notna().sum(), df_model.ward_current.notna().sum(),
        df_model.has_trusted_coordinate.sum(),
    ],
})
coverage['Tỷ lệ trên modeling rows (%)'] = coverage['Số dòng có dữ liệu'] / len(df_model) * 100
sample_size_report = pd.Series({
    'Total candidate rows': N_CANDIDATE_ROWS,
    'Rows usable for target': len(df_model),
    'Excluded by target gate': N_CANDIDATE_ROWS - len(df_model),
}, name='Số dòng')
display(sample_size_report.to_frame(), coverage)
"""),
    markdown("""## 3. Feature Sets

Hai feature set dùng cùng một tập row:

- **Base:** diện tích sạch, `active_days`, nguồn listing, nguồn địa chỉ tốt nhất và hai cờ availability.
- **Base + Location:** Base cộng Quận/Huyện và Phường/Xã đã ánh xạ.

Không dùng raw free text, distance (không có reference location thật cho toàn bộ experiment), `price_per_m2`, hay bất kỳ trường nào suy ra từ target.
"""),
    code("""# Declare feature sets once and reject target-derived names before any split or fit.
BASE_FEATURES = [
    'area_value_clean', 'active_days', 'source_code', 'best_address_source',
    'has_detailed_address', 'has_trusted_coordinate',
]
LOCATION_FEATURES = ['district_clean', 'ward_current']
FEATURE_SETS = {
    'Base': BASE_FEATURES,
    'Base + Location': BASE_FEATURES + LOCATION_FEATURES,
}
NUMERIC_FEATURES = {
    'area_value_clean', 'active_days', 'has_detailed_address', 'has_trusted_coordinate'
}

all_model_features = sorted({feature for features in FEATURE_SETS.values() for feature in features})
leaking_features = [
    feature for feature in all_model_features
    if any(token in feature.lower() for token in FORBIDDEN_FEATURE_TOKENS)
]
assert not leaking_features, f'Target leakage features detected: {leaking_features}'
assert 'price_per_m2' not in all_model_features
assert set(FEATURE_SETS['Base']).issubset(FEATURE_SETS['Base + Location'])

feature_manifest = pd.DataFrame([
    {
        'Feature Set': feature_set,
        'Feature': feature,
        'Kiểu': 'Numeric/Boolean' if feature in NUMERIC_FEATURES else 'Categorical',
    }
    for feature_set, features in FEATURE_SETS.items()
    for feature in features
])
display(feature_manifest)
"""),
    markdown("""## 4. Train/Test Split

Split được tạo **một lần trước preprocessing** và tái sử dụng cho mọi model/feature set:

1. Group-aware 80/20 nếu `duplicate_group_id` tồn tại và usable;
2. nếu chưa có group, time-aware holdout: 20% observations mới nhất theo `latest_observed_at`;
3. deterministic random split (`random_state=42`) chỉ khi timestamp không đủ semantic.

Không tune trên test set.
"""),
    code("""# Produce one shared row split before any transformer is fitted.
def create_shared_split(frame):
    if 'duplicate_group_id' in frame and frame.duplicate_group_id.notna().any():
        groups = frame.duplicate_group_id.astype(object).copy()
        missing_group = groups.isna()
        groups.loc[missing_group] = frame.loc[missing_group, 'rental_post_id'].map(
            lambda value: f'__singleton__{value}'
        )
        splitter = GroupShuffleSplit(
            n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_STATE
        )
        train_pos, test_pos = next(splitter.split(frame, groups=groups))
        return frame.index[train_pos], frame.index[test_pos], 'GROUP_AWARE'

    timestamps = frame.latest_observed_at
    if timestamps.notna().all() and timestamps.nunique() > 1:
        ordered = frame.assign(_time=timestamps).sort_values(
            ['_time', 'rental_post_id'], kind='mergesort'
        )
        test_rows = max(1, int(np.ceil(len(ordered) * TEST_SIZE)))
        return ordered.index[:-test_rows], ordered.index[-test_rows:], 'TIME_AWARE_LATEST_HOLDOUT'

    train_labels, test_labels = train_test_split(
        frame.index.to_numpy(), test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    return pd.Index(train_labels), pd.Index(test_labels), 'DETERMINISTIC_RANDOM_FALLBACK'


train_idx, test_idx, SPLIT_STRATEGY = create_shared_split(df_model)
assert len(train_idx) + len(test_idx) == len(df_model)
assert set(train_idx).isdisjoint(test_idx)
assert set(train_idx) | set(test_idx) == set(df_model.index)

y_train = df_model.loc[train_idx, 'target_price_vnd'].astype(float)
y_test = df_model.loc[test_idx, 'target_price_vnd'].astype(float)
split_report = pd.Series({
    'Split strategy': SPLIT_STRATEGY,
    'Modeling rows': len(df_model),
    'Train rows': len(train_idx),
    'Test rows': len(test_idx),
    'Train percentage': len(train_idx) / len(df_model) * 100,
    'Test percentage': len(test_idx) / len(df_model) * 100,
    'Train latest timestamp': df_model.loc[train_idx, 'latest_observed_at'].max(),
    'Test earliest timestamp': df_model.loc[test_idx, 'latest_observed_at'].min(),
}, name='Giá trị')
display(split_report.to_frame())
"""),
    markdown("""## 5. Preprocessing

Imputation chỉ diễn ra bên trong model pipeline sau split; không ghi ngược vào `df_model` hay source snapshot.

- Ridge, Dummy và Random Forest: median imputation cho numeric; explicit missing category + **sparse one-hot** cho categorical. Ridge scale numeric với `with_mean=False`.
- HistGradientBoosting: median imputation và **ordinal categorical encoding có giới hạn cardinality**. Model này không nhận one-hot matrix đã densify.

Unknown categories trong test set được xử lý mà không học lại encoder.
"""),
    code("""# Build model-specific preprocessing without fitting it yet.
def split_feature_types(feature_columns):
    numeric = [feature for feature in feature_columns if feature in NUMERIC_FEATURES]
    categorical = [feature for feature in feature_columns if feature not in NUMERIC_FEATURES]
    return numeric, categorical


def build_sparse_pipeline(feature_columns, model_name, estimator):
    numeric, categorical = split_feature_types(feature_columns)
    numeric_steps = [('impute', SimpleImputer(strategy='median'))]
    if model_name == 'Ridge':
        numeric_steps.append(('scale', StandardScaler(with_mean=False)))
    categorical_pipeline = Pipeline([
        ('impute', SimpleImputer(strategy='constant', fill_value='(missing)')),
        ('encode', OneHotEncoder(
            handle_unknown='ignore', sparse_output=True,
            min_frequency=MIN_CATEGORY_FREQUENCY, max_categories=MAX_CATEGORIES,
        )),
    ])
    preprocessor = ColumnTransformer(
        [('numeric', Pipeline(numeric_steps), numeric),
         ('categorical', categorical_pipeline, categorical)],
        sparse_threshold=1.0,
    )
    return Pipeline([('preprocess', preprocessor), ('model', estimator)])


def build_hist_pipeline(feature_columns, estimator):
    numeric, categorical = split_feature_types(feature_columns)
    categorical_pipeline = Pipeline([
        ('impute', SimpleImputer(strategy='constant', fill_value='(missing)')),
        ('encode', OrdinalEncoder(
            handle_unknown='use_encoded_value', unknown_value=-1,
            encoded_missing_value=-1, min_frequency=MIN_CATEGORY_FREQUENCY,
            max_categories=254, dtype=np.float64,
        )),
    ])
    preprocessor = ColumnTransformer([
        ('numeric', SimpleImputer(strategy='median'), numeric),
        ('categorical', categorical_pipeline, categorical),
    ])
    categorical_positions = list(range(len(numeric), len(numeric) + len(categorical)))
    estimator.set_params(categorical_features=categorical_positions)
    return Pipeline([('preprocess', preprocessor), ('model', estimator)])
"""),
    markdown("""## 6. Baseline

`DummyRegressor(strategy="median")` là baseline bắt buộc. Mọi kết quả chỉ có ý nghĩa khi được so với baseline trên đúng test rows và target VND gốc.
"""),
    markdown("""## 7. Model Training

Bốn model được chạy với cấu hình cố định, không grid search và không chọn hyperparameter theo test results. Mỗi model chạy trên cả Base và Base + Location, tạo tám thí nghiệm dùng chung `train_idx`/`test_idx`.
"""),
    code("""# Fit all experiments on the shared train rows and evaluate on shared test rows.
def fresh_estimators():
    return {
        'Dummy Median': DummyRegressor(strategy='median'),
        'Ridge': Ridge(alpha=1.0),
        'Random Forest': RandomForestRegressor(
            n_estimators=120, max_depth=18, min_samples_leaf=3,
            max_features=0.8, n_jobs=-1, random_state=RANDOM_STATE,
        ),
        'HistGradientBoosting': HistGradientBoostingRegressor(
            learning_rate=0.08, max_iter=150, max_leaf_nodes=31,
            l2_regularization=1.0, random_state=RANDOM_STATE,
        ),
    }


result_rows = []
predictions = {}
for feature_set_name, feature_columns in FEATURE_SETS.items():
    X_train = df_model.loc[train_idx, feature_columns]
    X_test = df_model.loc[test_idx, feature_columns]
    assert X_train.index.equals(train_idx)
    assert X_test.index.equals(test_idx)

    for model_name, estimator in fresh_estimators().items():
        if model_name == 'HistGradientBoosting':
            model_pipeline = build_hist_pipeline(feature_columns, estimator)
        else:
            model_pipeline = build_sparse_pipeline(feature_columns, model_name, estimator)

        train_started = perf_counter()
        model_pipeline.fit(X_train, y_train)
        train_seconds = perf_counter() - train_started

        if model_name != 'HistGradientBoosting':
            sparse_probe = model_pipeline.named_steps['preprocess'].transform(X_test.iloc[:10])
            assert sparse.issparse(sparse_probe), 'One-hot pipeline must remain sparse'

        predict_started = perf_counter()
        y_pred = model_pipeline.predict(X_test)
        predict_seconds = perf_counter() - predict_started

        assert len(y_pred) == len(test_idx)
        assert np.isfinite(y_pred).all()
        predictions[(feature_set_name, model_name)] = np.asarray(y_pred, dtype=float)
        result_rows.append({
            'Model': model_name,
            'Feature Set': feature_set_name,
            'Test Rows': len(test_idx),
            'MAE': float(mean_absolute_error(y_test, y_pred)),
            'RMSE': float(mean_squared_error(y_test, y_pred) ** 0.5),
            'R²': float(r2_score(y_test, y_pred)),
            'Train Time': float(train_seconds),
            'Predict Time': float(predict_seconds),
        })

results_raw = pd.DataFrame(result_rows)
base_reference = results_raw.loc[
    results_raw['Feature Set'].eq('Base'), ['Model', 'MAE', 'RMSE', 'R²']
].set_index('Model')
for metric in ['MAE', 'RMSE', 'R²']:
    results_raw[f'Δ{metric}'] = results_raw.apply(
        lambda row: row[metric] - base_reference.loc[row['Model'], metric], axis=1
    )

assert results_raw['Test Rows'].nunique() == 1
assert len(results_raw) == len(FEATURE_SETS) * len(fresh_estimators())
assert not results_raw[['MAE', 'RMSE', 'R²']].isna().any().any()
"""),
    markdown("""## 8. Model Comparison

MAE là metric xếp hạng chính vì có đơn vị VND/tháng và ít nhạy với lỗi cực lớn hơn RMSE. RMSE và R² vẫn được báo độc lập; không tạo “accuracy %” cho regression.
"""),
    code("""# Compare all model/feature-set pairs by MAE on the original VND scale.
results_ranked = results_raw.sort_values(['MAE', 'RMSE'], kind='mergesort').reset_index(drop=True)
results_ranked['Thí nghiệm'] = results_ranked['Model'] + ' — ' + results_ranked['Feature Set']
mae_chart = results_ranked.sort_values('MAE', ascending=False)
fig = px.bar(
    mae_chart, x='MAE', y='Thí nghiệm', orientation='h', text='MAE',
    title='So sánh sai số tuyệt đối trung bình (MAE)',
    labels={'MAE': 'MAE (VND/tháng)', 'Thí nghiệm': 'Mô hình và bộ đặc trưng'},
    hover_data={'RMSE': ':,.0f', 'R²': ':.4f', 'Test Rows': ':,'},
)
fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside', cliponaxis=False)
fig.update_layout(height=500, margin={'l': 30, 'r': 100, 't': 80, 'b': 50})
fig.show()

best_mae_row = results_raw.loc[results_raw.MAE.idxmin()]
best_rmse_row = results_raw.loc[results_raw.RMSE.idxmin()]
best_r2_row = results_raw.loc[results_raw['R²'].idxmax()]
display(Markdown(
    f"**MAE thấp nhất:** {best_mae_row['Model']} — {best_mae_row['Feature Set']}  "
    f"  \\n**RMSE thấp nhất:** {best_rmse_row['Model']} — {best_rmse_row['Feature Set']}  "
    f"  \\n**R² cao nhất:** {best_r2_row['Model']} — {best_r2_row['Feature Set']}"
))
"""),
    markdown("""## 9. Actual vs Predicted

Scatter chỉ dành cho thí nghiệm có MAE thấp nhất. Metric vẫn được tính trên toàn bộ test set; nếu test set lớn, chỉ phần rendering được sample tiền định để biểu đồ dễ đọc.
"""),
    code("""# Plot a deterministic rendering sample for the MAE winner; metrics remain full-test.
best_key = (best_mae_row['Feature Set'], best_mae_row['Model'])
best_predictions = predictions[best_key]
prediction_frame = pd.DataFrame({
    'Giá thực tế': y_test.to_numpy(),
    'Giá dự đoán': best_predictions,
}, index=test_idx)
if len(prediction_frame) > SCATTER_RENDER_ROWS:
    scatter_frame = prediction_frame.sample(SCATTER_RENDER_ROWS, random_state=RANDOM_STATE)
else:
    scatter_frame = prediction_frame

lower_bound = min(scatter_frame['Giá thực tế'].min(), scatter_frame['Giá dự đoán'].min())
upper_bound = max(scatter_frame['Giá thực tế'].max(), scatter_frame['Giá dự đoán'].max())
fig = px.scatter(
    scatter_frame, x='Giá thực tế', y='Giá dự đoán', opacity=0.35,
    title=f"Giá thực tế và dự đoán — {best_key[1]} / {best_key[0]}",
    labels={'Giá thực tế': 'Giá thực tế (VND/tháng)',
            'Giá dự đoán': 'Giá dự đoán (VND/tháng)'},
)
fig.add_trace(go.Scatter(
    x=[lower_bound, upper_bound], y=[lower_bound, upper_bound], mode='lines',
    name='Dự đoán hoàn hảo', line={'color': '#C0392B', 'dash': 'dash'},
))
fig.update_layout(height=520)
fig.show()
"""),
    markdown("""## 10. Residual Analysis

Residual được định nghĩa `actual - predicted`: số dương nghĩa là model dự đoán thấp hơn giá thực tế; số âm nghĩa là model dự đoán cao hơn.
"""),
    code("""# Inspect full-test residuals for the MAE winner.
prediction_frame['Residual'] = prediction_frame['Giá thực tế'] - prediction_frame['Giá dự đoán']
fig = px.histogram(
    prediction_frame, x='Residual', nbins=60,
    title=f"Phân bố residual — {best_key[1]} / {best_key[0]}",
    labels={'Residual': 'Residual: thực tế − dự đoán (VND/tháng)', 'count': 'Số tin đăng'},
)
fig.add_vline(x=0, line_dash='dash', line_color='#C0392B')
fig.update_layout(yaxis_title='Số tin đăng', height=450, bargap=0.04)
fig.show()
display(prediction_frame.Residual.describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).to_frame())
"""),
    markdown("""## 11. Location Feature Contribution

Các delta dưới đây luôn lấy **Base + Location trừ Base** cho cùng model và cùng test rows:

- ΔMAE, ΔRMSE âm là cải thiện;
- ΔR² dương là cải thiện.
"""),
    code("""# Isolate the controlled Base versus Base + Location comparison.
location_comparison = results_raw.loc[
    results_raw['Feature Set'].eq('Base + Location'),
    ['Model', 'Test Rows', 'MAE', 'RMSE', 'R²', 'ΔMAE', 'ΔRMSE', 'ΔR²'],
].sort_values('ΔMAE')
display(location_comparison.style.format({
    'MAE': '{:,.0f}', 'RMSE': '{:,.0f}', 'R²': '{:.4f}',
    'ΔMAE': '{:+,.0f}', 'ΔRMSE': '{:+,.0f}', 'ΔR²': '{:+.4f}',
}))

location_improved_count = int(
    (location_comparison['ΔMAE'].lt(0)
     & location_comparison['ΔRMSE'].lt(0)
     & location_comparison['ΔR²'].gt(0)).sum()
)
display(Markdown(
    f"Structured location cải thiện đồng thời cả ba metric cho "
    f"**{location_improved_count}/{len(location_comparison)}** models."
))
"""),
    markdown("""## 12. Error Analysis

Top 20 lỗi tuyệt đối lớn nhất giúp nhận diện nơi cần review dữ liệu hoặc model. MAE theo Quận/Huyện chỉ hiển thị nhóm có ít nhất 30 test rows; chênh lệch giữa địa bàn không được diễn giải là quan hệ nhân quả.
"""),
    code("""# Review the largest errors and district-level MAE for adequately sized test groups.
error_analysis = df_model.loc[test_idx, [
    'rental_post_id', 'area_value_clean', 'district_clean', 'ward_current', 'source_code'
]].copy()
error_analysis['actual_price'] = y_test.to_numpy()
error_analysis['predicted_price'] = best_predictions
error_analysis['absolute_error'] = np.abs(
    error_analysis.actual_price - error_analysis.predicted_price
)
top_errors = error_analysis.sort_values('absolute_error', ascending=False).head(20)
display(top_errors[[
    'rental_post_id', 'actual_price', 'predicted_price', 'absolute_error',
    'area_value_clean', 'district_clean', 'ward_current', 'source_code',
]].style.format({
    'actual_price': '{:,.0f}', 'predicted_price': '{:,.0f}',
    'absolute_error': '{:,.0f}', 'area_value_clean': '{:,.1f}',
}))

district_error = (
    error_analysis.dropna(subset=['district_clean'])
    .groupby('district_clean', as_index=False)
    .agg(test_count=('absolute_error', 'size'), MAE=('absolute_error', 'mean'))
    .query('test_count >= @DISTRICT_MIN_TEST_ROWS')
    .sort_values('MAE', ascending=False)
)
if district_error.empty:
    display(Markdown(
        f'**MAE theo Quận/Huyện không hiển thị:** không nhóm nào đạt '
        f'{DISTRICT_MIN_TEST_ROWS} test rows.'
    ))
else:
    fig = px.bar(
        district_error, x='MAE', y='district_clean', orientation='h', text='MAE',
        title=f'MAE theo Quận/Huyện — tối thiểu {DISTRICT_MIN_TEST_ROWS} test rows',
        labels={'district_clean': 'Quận/Huyện', 'MAE': 'MAE (VND/tháng)'},
        hover_data={'test_count': ':,'},
    )
    fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside', cliponaxis=False)
    fig.update_layout(height=max(420, 28 * len(district_error)))
    fig.show()
    display(district_error)
"""),
    markdown("""## 13. Limitations

- Đây là current-snapshot experiment, không phải forecast ngoài thời gian hoặc kiểm thử production.
- Task 12 chưa có business duplicate grouping hoàn chỉnh. Time split giảm leakage thời gian nhưng không chứng minh entity independence.
- Address-derived district/ward phụ thuộc parser và internal ward mapping; missing category là tín hiệu availability, không phải địa bàn thực.
- Giá trị accepted vẫn có thể có outlier hợp lệ về nghiệp vụ; notebook không tự ý loại chúng.
- Feature importance/causal claims không thuộc phạm vi thử nghiệm này.

**Business duplicate analysis chưa hoàn tất, nên kết quả thử nghiệm có thể optimistic nếu cùng một property xuất hiện ở cả train và test.**
"""),
    markdown("""## 14. Final Comparison Table

### MODEL COMPARISON RESULTS

⚠️ **Business duplicate analysis chưa hoàn tất, nên kết quả thử nghiệm có thể optimistic nếu cùng một property xuất hiện ở cả train và test.**

Bảng được sort theo MAE tăng dần. ΔMAE/ΔRMSE/ΔR² là chênh lệch so với Base của chính model đó; dòng Base có delta bằng 0. Raw values vẫn được giữ trong `results_raw`.
"""),
    code("""# Render the final ranked table, metric winners and concise experimental summary.
final_columns = [
    'Model', 'Feature Set', 'Test Rows', 'MAE', 'RMSE', 'R²',
    'ΔMAE', 'ΔRMSE', 'ΔR²', 'Train Time', 'Predict Time',
]
final_results = results_raw[final_columns].sort_values(
    ['MAE', 'RMSE'], kind='mergesort'
).reset_index(drop=True)

def highlight_metric_winners(data):
    styles = pd.DataFrame('', index=data.index, columns=data.columns)
    styles.loc[data.MAE.idxmin(), 'MAE'] = 'background-color: #D5F5E3; font-weight: bold'
    styles.loc[data.RMSE.idxmin(), 'RMSE'] = 'background-color: #D5F5E3; font-weight: bold'
    styles.loc[data['R²'].idxmax(), 'R²'] = 'background-color: #D5F5E3; font-weight: bold'
    return styles


display(final_results.style.apply(highlight_metric_winners, axis=None).format({
    'Test Rows': '{:,}',
    'MAE': '{:,.0f}', 'RMSE': '{:,.0f}', 'R²': '{:.4f}',
    'ΔMAE': '{:+,.0f}', 'ΔRMSE': '{:+,.0f}', 'ΔR²': '{:+.4f}',
    'Train Time': '{:.3f} s', 'Predict Time': '{:.3f} s',
}))

baseline_row = results_raw.loc[
    results_raw.Model.eq('Dummy Median') & results_raw['Feature Set'].eq('Base')
].iloc[0]
best_location_row = location_comparison.iloc[0]
location_statement = (
    'cải thiện MAE' if best_location_row['ΔMAE'] < 0 else 'không cải thiện MAE'
)

assert pd.util.hash_pandas_object(df_latest, index=True).sum() == source_hash_before
assert final_results['Test Rows'].eq(len(test_idx)).all()
assert not any(
    any(token in feature.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    for feature in all_model_features
)
conn.close()

display(Markdown(
    f"- **Baseline MAE:** {baseline_row.MAE:,.0f} VND/tháng.  "
    f"  \\n- **MAE thấp nhất:** {best_mae_row['Model']} — {best_mae_row['Feature Set']} "
    f"({best_mae_row.MAE:,.0f} VND/tháng).  "
    f"  \\n- **RMSE thấp nhất:** {best_rmse_row['Model']} — {best_rmse_row['Feature Set']} "
    f"({best_rmse_row.RMSE:,.0f} VND/tháng).  "
    f"  \\n- **R² cao nhất:** {best_r2_row['Model']} — {best_r2_row['Feature Set']} "
    f"({best_r2_row['R²']:.4f}).  "
    f"  \\n- **Location:** {best_location_row.Model} {location_statement}; "
    f"ΔMAE {best_location_row['ΔMAE']:+,.0f}, "
    f"ΔRMSE {best_location_row['ΔRMSE']:+,.0f}, ΔR² {best_location_row['ΔR²']:+.4f}.  "
    f"  \\n- **Giới hạn quan trọng:** duplicate/entity leakage có thể còn tồn tại; "
    f"kết quả không phải production-ready."
))
"""),
]


notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUTPUT.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
