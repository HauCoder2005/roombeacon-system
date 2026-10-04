"""Build Notebook 03 with a split-free post-Silver feature contract."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
def md(text): return {"cell_type":"markdown","metadata":{},"source":text.splitlines(True)}
def code(text): return {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":text.splitlines(True)}

cells=[
md("""# RoomBeacon — Post-Silver Processing and Feature Contract

This notebook consumes canonical Silver, performs post-Silver analytical feature work, and publishes a safe modeling contract. It does **not** create train/validation/test partitions, select models, or persist a redundant modeling dataset. Notebook 04 exclusively owns group-aware chronological splitting and model evaluation."""),
code("""from pathlib import Path
import sys
PROJECT_ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'crawler').is_dir() and (p/'analytics').is_dir())
sys.path.insert(0,str(PROJECT_ROOT))
import numpy as np,pandas as pd,duckdb
from dotenv import load_dotenv
from IPython.display import display,Markdown
load_dotenv(PROJECT_ROOT/'.env',override=False)
from analytics.duckdb.connection import resolve_runtime_path
from roombeacon_crawler.config.get_env import env
from notebooks.utils.location_analysis import haversine_distance_km
from notebooks.utils.modeling_benchmark import TARGET,FORBIDDEN_PREDICTORS,audit_features,build_feature_sets
pd.set_option('display.max_columns',30); SEED=42"""),
md("## 01 Load Canonical Silver"),
code("""SILVER_PATH=resolve_runtime_path(env.processing.silver_dir)/'rental_listings.parquet'
assert SILVER_PATH.exists(),f'Canonical Silver not found: {SILVER_PATH}'
with duckdb.connect(':memory:') as con: silver_df=con.execute('select * from read_parquet(?)',[str(SILVER_PATH)]).df()
assert len(silver_df)>0 and silver_df.rental_post_id.notna().all() and silver_df.rental_post_id.is_unique
display(pd.Series({'path':str(SILVER_PATH),'rows':len(silver_df),'columns':len(silver_df.columns)},name='value').to_frame())"""),
md("## 02 Analytical eligibility and diagnostic-only variables"),
code("""processed_df=silver_df.copy()
processed_df['analytical_price_eligible']=processed_df[TARGET].notna()
processed_df['analytical_area_eligible']=processed_df.area_value_clean.notna()
processed_df['model_base_eligible']=processed_df.analytical_price_eligible&processed_df.analytical_area_eligible&processed_df.row_quality_status.ne('REQUIRES_REVIEW')
price=pd.to_numeric(processed_df[TARGET],errors='coerce'); area=pd.to_numeric(processed_df.area_value_clean,errors='coerce')
processed_df['price_per_area_analysis']=price/area.where(area.gt(0))
processed_df.loc[~np.isfinite(processed_df.price_per_area_analysis),'price_per_area_analysis']=np.nan
display(processed_df[['analytical_price_eligible','analytical_area_eligible','model_base_eligible']].sum().to_frame('rows'))
display(processed_df.price_per_area_analysis.describe().to_frame())
display(Markdown('`price_per_area_analysis` is **TARGET-DERIVED / ANALYSIS-ONLY** and is programmatically forbidden from every modeling feature set.'))"""),
md("## 03 Optional trusted spatial diagnostic"),
code("""REFERENCE_LOCATION=None
processed_df['distance_km_analysis']=np.nan
if REFERENCE_LOCATION is not None:
 required={'latitude','longitude'}
 if not required<=set(REFERENCE_LOCATION): raise ValueError('REFERENCE_LOCATION requires latitude and longitude')
 trusted=processed_df.has_trusted_coordinate.fillna(False)
 processed_df.loc[trusted,'distance_km_analysis']=haversine_distance_km(processed_df.loc[trusted,'map_latitude'],processed_df.loc[trusted,'map_longitude'],REFERENCE_LOCATION['latitude'],REFERENCE_LOCATION['longitude'])
display(pd.Series({'trusted_coordinate_rows':int(processed_df.has_trusted_coordinate.sum()),'distance_rows':int(processed_df.distance_km_analysis.notna().sum())},name='rows').to_frame())"""),
md("## 04 Safe feature contract"),
code("""contract_frame=processed_df.assign(title_length=processed_df.title_clean.astype('string').str.len().astype('Float64'))
SAFE_FEATURE_SETS=build_feature_sets(contract_frame.columns)
for name,features in SAFE_FEATURE_SETS.items(): audit_features(features)
for forbidden in ['price_per_area_analysis',TARGET,'price_amount','rental_post_id','duplicate_candidate_group']:
 try: audit_features(['area_value_clean',forbidden])
 except ValueError: pass
 else: raise AssertionError(f'Leakage guard failed for {forbidden}')
feature_contract=pd.DataFrame([{'Feature Set':name,'Safe Predictors':', '.join(features)} for name,features in SAFE_FEATURE_SETS.items()])
excluded=sorted(FORBIDDEN_PREDICTORS|{'all price_* status/evidence fields','parser/quality fields that encode target validation'})
contract_summary=pd.DataFrame([
 {'Contract Item':'Target','Fields':TARGET},
 {'Contract Item':'Safe candidates','Fields':', '.join(sorted(set(sum(SAFE_FEATURE_SETS.values(),[]))))},
 {'Contract Item':'Grouping key source','Fields':'duplicate_candidate_group, falling back to rental_post_id in Notebook 04'},
 {'Contract Item':'Chronological time','Fields':'latest_observed_at'},
 {'Contract Item':'Analysis-only','Fields':'price_per_area_analysis, distance_km_analysis'},
 {'Contract Item':'Eligibility/audit','Fields':'listing_intent, rental_scope, price_target_trust_status/reason/evidence, price_model_value; not predictors'},
 {'Contract Item':'Excluded/leakage','Fields':', '.join(excluded)},
 {'Contract Item':'Split owner','Fields':'Notebook 04 only'},
])
display(feature_contract); display(contract_summary)
assert 'dataset_split' not in processed_df.columns"""),
md("## 05 Processing Summary"),
code("""summary=pd.Series({'silver_input_rows':len(silver_df),'analytical_rows':len(processed_df),'model_base_eligible_rows':int(processed_df.model_base_eligible.sum()),'safe_feature_sets':len(SAFE_FEATURE_SETS),'legacy_split_columns':int('dataset_split' in processed_df.columns),'persisted_redundant_model_dataset':False},name='value')
assert len(processed_df)==len(silver_df); display(summary.to_frame()); display(Markdown('**Notebook 03 complete. Modeling split, selection, tuning, locking, and TEST evaluation remain exclusively in Notebook 04.**'))""")]

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"RoomBeacon (venv)","language":"python","name":"roombeacon-venv"},"language_info":{"name":"python","version":"3.12.3"}},"nbformat":4,"nbformat_minor":5}
(ROOT/'notebooks'/'03_roombeacon_processing.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
