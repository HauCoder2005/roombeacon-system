"""Generate Notebook 06: locked-champion shadow validation and monitoring."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(True),
    }


cells = [
    md(
        """# 06 — RoomBeacon Shadow Validation

This notebook validates the already-locked **LightGBM Regressor / RAW / F4** champion under an inference-like contract. It never trains, tunes, benchmarks, or selects a model. Current known data is a `HISTORICAL_DRY_RUN`; only a wholly new post-lock batch may become `FUTURE_SHADOW` evidence."""
    ),
    md(
        """## 01. Purpose and Contract

Responsibility boundary: Notebook 04 owns training and selection; Notebook 06 loads the immutable artifact, constructs the exact target-free F4 matrix, predicts, then—and only then—joins trusted actual rent for monitoring. Historical dry-run results verify mechanics and do not support a production claim."""
    ),
    md("## 02. Runtime Configuration"),
    code(
        """from pathlib import Path
from datetime import datetime, timezone
import json, platform, sys

PROJECT_ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'crawler').is_dir() and (p/'analytics').is_dir())
sys.path.insert(0,str(PROJECT_ROOT))

import duckdb,numpy as np,pandas as pd,matplotlib.pyplot as plt
from IPython.display import display,Markdown
from analytics.duckdb.connection import resolve_runtime_path
from roombeacon_crawler.config.get_env import env
from notebooks.utils.shadow_validation import *
from notebooks.utils.modeling_benchmark import build_modeling_eligibility

SEED=42
np.random.seed(SEED)
plt.style.use('seaborn-v0_8-whitegrid')
BENCHMARK_DIR=PROJECT_ROOT/'data'/'modeling'/'roombeacon_price_benchmark_v3'
SILVER_PATH=resolve_runtime_path(env.processing.silver_dir)/'rental_listings.parquet'
SHADOW_OUTPUT_ROOT=PROJECT_ROOT/'data'/'modeling'/'shadow_validation'
MIN_SUPPORT=100
INFERENCE_TIMESTAMP=datetime.now(timezone.utc).isoformat()
runtime=pd.Series({'Python':platform.python_version(),'Benchmark directory':str(BENCHMARK_DIR),'Silver path':str(SILVER_PATH),'Shadow output':str(SHADOW_OUTPUT_ROOT),'Minimum slice support':MIN_SUPPORT},name='Runtime')
display(runtime.to_frame())"""
    ),
    md("## 03. Load Champion Artifact"),
    code(
        """champion=resolve_champion_artifact(BENCHMARK_DIR)
champion_summary=pd.Series({'model_id':champion.metadata['model_id'],'model family':champion.metadata['model_family'],'target transform':champion.metadata['target_transform'],'feature set':champion.metadata['feature_set'],'feature names':', '.join(champion.metadata['feature_names']),'parameters':json.dumps(champion.metadata['hyperparameters'],sort_keys=True),'random seed':champion.metadata['random_seed'],'artifact SHA-256':champion.metadata['artifact_sha256'],'reference population':champion.reference_profile['population'],'reference rows':champion.reference_profile['row_count'],'reference range':f"{champion.reference_profile['min_observed_at']} → {champion.reference_profile['max_observed_at']}"},name='Locked champion')
display(champion_summary.to_frame())"""
    ),
    md("## 04. Load Canonical Silver / Shadow Batch"),
    code(
        """with duckdb.connect(':memory:') as connection:
    silver_df=connection.execute('SELECT * FROM read_parquet(?)',[str(SILVER_PATH)]).df()
assert len(silver_df)==silver_df.rental_post_id.nunique()
evidence_cutoff=champion.metadata['training_reference']['evidence_cutoff']
mode_decision=classify_validation_mode(silver_df.latest_observed_at,evidence_cutoff)
VALIDATION_MODE=mode_decision.mode
CURRENT_SILVER_SHA256=file_sha256(SILVER_PATH)
batch_summary=pd.Series({'Silver rows':len(silver_df),'Distinct rental_post_id':silver_df.rental_post_id.nunique(),'Silver SHA-256':CURRENT_SILVER_SHA256,'Minimum observed at':pd.to_datetime(silver_df.latest_observed_at).min(),'Maximum observed at':pd.to_datetime(silver_df.latest_observed_at).max(),'Model-lock evidence cutoff':evidence_cutoff,'Validation mode':VALIDATION_MODE,'Counts toward production evidence':mode_decision.counts_toward_production,'Mode reason':mode_decision.reason},name='Shadow batch')
display(batch_summary.to_frame())
if CURRENT_SILVER_SHA256==champion.metadata['training_reference']['silver_sha256']:
    assert VALIDATION_MODE=='HISTORICAL_DRY_RUN', 'The champion-development snapshot must remain a historical dry run'"""
    ),
    md("## 05. Validate Inference Schema"),
    code(
        """population=prepare_shadow_population(silver_df,champion.metadata,policy='PERMISSIVE')
display(population.funnel)
display(population.schema_summary)
display(population.all_rows.inference_status.value_counts(dropna=False).rename('Rows').to_frame())
assert len(population.all_rows)==len(silver_df)
assert len(population.ready_rows)==int(population.all_rows.inference_status.eq('READY_FOR_INFERENCE').sum())"""
    ),
    md("## 06. Build F4 Features"),
    code(
        """X_shadow=build_inference_matrix(population.ready_rows,champion.metadata)
feature_contract=pd.DataFrame({'Position':range(1,len(X_shadow.columns)+1),'Feature':X_shadow.columns,'Runtime dtype':[str(dtype) for dtype in X_shadow.dtypes],'Expected type':[champion.metadata['expected_schema'][column] for column in X_shadow.columns]})
display(feature_contract)
assert X_shadow.columns.tolist()==champion.metadata['feature_names']==list(F4_FEATURES)
assert TARGET_COLUMN not in X_shadow.columns
assert len(X_shadow)==len(population.ready_rows)"""
    ),
    md("## 07. Reference vs Shadow Population"),
    code(
        """eval_rows_count=int(build_modeling_eligibility(silver_df,policy='PERMISSIVE').final_eligible.sum())
funnel_df=pd.DataFrame([{'Stage':'1. Silver total snapshot','Rows':len(silver_df),'Context':'Full cleaned crawl dataset'},{'Stage':'2. Inference-ready population','Rows':len(population.ready_rows),'Context':'Target-free physical & rental features'},{'Stage':'3. Evaluation-ready population','Rows':eval_rows_count,'Context':'Full target trust & room-suitability'}])
display(funnel_df)
fig,ax=plt.subplots(figsize=(9,4)); bars=ax.bar(funnel_df['Stage'],funnel_df['Rows'],color=['#4C78A8','#72B7B2','#54A24B'],width=0.55)
for bar in bars:
    height=bar.get_height()
    ax.annotate(f'{int(height):,}',xy=(bar.get_x()+bar.get_width()/2,height),xytext=(0,3),textcoords="offset points",ha='center',va='bottom',fontweight='bold')
ax.set(title=f'Population context — serving funnel (not a drift metric)\\nTotal Silver: {len(silver_df):,} → Inference: {len(population.ready_rows):,} → Evaluation: {eval_rows_count:,}',ylabel='Listings (rows)',xlabel='Serving & Evaluation Stage')
ax.tick_params(axis='x',rotation=12); plt.tight_layout(); plt.show()"""
    ),
    md("## 08. Feature Drift"),
    code(
        """numeric_drift,category_share_drift=feature_drift_report(population.ready_rows,champion.reference_profile)
display(numeric_drift)
reference_area=champion.reference_profile['numeric']['area_value_clean']
shadow_area=population.ready_rows.area_value_clean.astype(float)
quantile_labels=['P25','Median','P75','P95']
reference_quantiles=[reference_area['p25'],reference_area['median'],reference_area['p75'],reference_area['p95']]
shadow_quantiles=[shadow_area.quantile(.25),shadow_area.median(),shadow_area.quantile(.75),shadow_area.quantile(.95)]
fig,ax=plt.subplots(figsize=(8,4)); x=np.arange(len(quantile_labels)); ax.plot(x,reference_quantiles,marker='o',label=f"DEVELOPMENT reference (n={champion.reference_profile['row_count']:,})"); ax.plot(x,shadow_quantiles,marker='o',label=f'{VALIDATION_MODE} (n={len(shadow_area):,})'); ax.set(xticks=x,xticklabels=quantile_labels,title=f'Reference vs shadow area distribution profile — {VALIDATION_MODE}',xlabel='Distribution statistic',ylabel='Area (m²)'); ax.legend(); plt.tight_layout(); plt.show()"""
    ),
    md("## 09. Category Drift"),
    code(
        """category_drift=category_drift_report(population.ready_rows,champion.reference_profile)
display(category_drift)
source_share=category_share_drift.loc[category_share_drift.Feature.eq('source_code')].sort_values('Reference Share %',ascending=False)
fig,ax=plt.subplots(figsize=(10,4)); x=np.arange(len(source_share)); width=.38; ax.bar(x-width/2,source_share['Reference Share %'],width,label='DEVELOPMENT reference'); ax.bar(x+width/2,source_share['Shadow Share %'],width,label=VALIDATION_MODE); ax.set(xticks=x,xticklabels=source_share.Category,title=f'Source share: reference vs shadow — {VALIDATION_MODE}\\nInference-ready n={len(population.ready_rows):,}',xlabel='Source',ylabel='Share of rows (%)'); ax.tick_params(axis='x',rotation=35); ax.legend(); plt.tight_layout(); plt.show()"""
    ),
    md("## 10. Run Shadow Inference"),
    code(
        """shadow_predictions=predict_shadow(champion.model,population.ready_rows,champion.metadata,VALIDATION_MODE,INFERENCE_TIMESTAMP)
display(shadow_predictions.head())
display(pd.Series({'Inference-ready rows':len(population.ready_rows),'Prediction rows':len(shadow_predictions),'Model ID':champion.metadata['model_id'],'Validation mode':VALIDATION_MODE,'Actual target present during prediction':TARGET_COLUMN in X_shadow.columns},name='Inference result').to_frame())
assert len(shadow_predictions)==len(population.ready_rows)
assert shadow_predictions.rental_post_id.tolist()==population.ready_rows.rental_post_id.tolist()"""
    ),
    md("## 11. Prediction Sanity"),
    code(
        """sanity_checks=prediction_sanity_report(shadow_predictions,len(population.ready_rows))
prediction_distribution_table=prediction_distribution(shadow_predictions)
reference_prediction=champion.reference_profile.get('prediction') or {}
prediction_reference_comparison=pd.DataFrame([{'Population':'DEVELOPMENT_REFERENCE',**reference_prediction},{'Population':VALIDATION_MODE,**prediction_distribution_table.iloc[0].to_dict()}])
display(sanity_checks); display(prediction_distribution_table); display(prediction_reference_comparison)
assert sanity_checks.Status.eq('PASS').all()
fig,ax=plt.subplots(figsize=(9,4)); ax.hist(shadow_predictions.predicted_monthly_rent/1_000_000,bins=60,color='#4C78A8',alpha=.8); reference_median=reference_prediction.get('median'); reference_p99=reference_prediction.get('p99');
if reference_median is not None: ax.axvline(reference_median/1_000_000,color='#E45756',linestyle='--',label='DEVELOPMENT prediction median')
if reference_p99 is not None: ax.axvline(reference_p99/1_000_000,color='#72B7B2',linestyle=':',label='DEVELOPMENT prediction P99')
ax.set(title=f'Champion prediction distribution — {VALIDATION_MODE}\\nn={len(shadow_predictions):,}; target was not used for inference',xlabel='Predicted monthly rent (million VND)',ylabel='Listings (count)'); ax.legend(); plt.tight_layout(); plt.show()"""
    ),
    md("## 12. Overall Error Metrics"),
    code(
        """evaluation_population=prepare_evaluation_population(shadow_predictions,silver_df,policy='PERMISSIVE',target_column=TARGET_COLUMN)
shadow_output=evaluation_population.all_predictions
evaluation_frame=evaluation_population.evaluation_predictions
display(evaluation_population.funnel)
display(evaluation_population.exclusion_summary)
assert len(shadow_output)==len(shadow_predictions)
assert len(evaluation_frame)==int(evaluation_population.funnel.loc[evaluation_population.funnel.Stage.eq('Final model eligible'),'Rows'].iloc[0])
overall_metrics=pd.DataFrame([evaluate_shadow_predictions(evaluation_frame)])
display(overall_metrics)
evaluated=evaluation_frame.loc[evaluation_frame.actual_monthly_rent.notna()].copy()
sample=evaluated.sample(min(5000,len(evaluated)),random_state=SEED) if len(evaluated) else evaluated
fig,axes=plt.subplots(1,2,figsize=(13,4.5))
limit=evaluated.actual_monthly_rent.quantile(.99) if len(evaluated) else 1
axes[0].scatter(sample.actual_monthly_rent/1_000_000,sample.predicted_monthly_rent/1_000_000,s=8,alpha=.25)
axes[0].plot([0,limit/1_000_000],[0,limit/1_000_000],'--',color='black')
axes[0].set(xlim=(0,limit/1_000_000),ylim=(0,limit/1_000_000),title=f'Actual vs predicted — {VALIDATION_MODE}\\nPlotted sample n={len(sample):,} from evaluation population n={len(evaluated):,}.\\nDisplay limited to actual-price P99 ({limit/1e6:.1f}M) for readability; all rows retained in metrics.',xlabel='Actual monthly rent (million VND)',ylabel='Predicted monthly rent (million VND)')

p01_res=evaluated.residual.quantile(0.01)
p99_res=evaluated.residual.quantile(0.99)
central_mask=evaluated.residual.between(p01_res,p99_res)
central_res=evaluated.loc[central_mask,'residual']
outside_count=len(evaluated)-len(central_res)
axes[1].hist(central_res/1_000_000,bins=60,color='#E45756',alpha=.8)
axes[1].axvline(0,color='black',linestyle='--')
axes[1].set(title=f'Residual distribution — central P01–P99 visualization only\\nResidual = prediction − actual (overprediction > 0); display [{p01_res/1e6:.1f}M, {p99_res/1e6:.1f}M]\\nAll {len(evaluated):,} residuals retained in metrics ({outside_count:,} outside display range)',xlabel='Residual = prediction − actual (million VND)',ylabel='Listings (count)')
plt.tight_layout(); plt.show()
print(f"Residual distribution diagnostics: full min={evaluated.residual.min():,.0f} VND, full max={evaluated.residual.max():,.0f} VND, central P01={p01_res:,.0f} VND, central P99={p99_res:,.0f} VND, outside central display={outside_count:,} rows (all retained in metrics).")"""
    ),
    md("## 13. Price-Bucket Diagnostics"),
    code(
        """price_diagnostics=price_bucket_diagnostics(evaluation_frame)
display(price_diagnostics)
fig,ax=plt.subplots(figsize=(9,4))
x_labels=[f"{row.Segment}\\n(n={row.Rows:,})" for _,row in price_diagnostics.iterrows()]
ax.bar(x_labels,price_diagnostics.MAE/1_000_000,color='#F58518')
ax.set(title=f'MAE by actual-price diagnostic bucket — {VALIDATION_MODE}\\nEvaluation-only routing; logical price order; total evaluated n={int(price_diagnostics.Rows.sum()):,}',xlabel='Actual monthly-rent bucket',ylabel='MAE (million VND)')
ax.tick_params(axis='x',rotation=15); plt.tight_layout(); plt.show()"""
    ),
    md("## 14. Area-Bucket Diagnostics"),
    code(
        """area_diagnostics=area_bucket_diagnostics(evaluation_frame)
display(area_diagnostics)
fig,ax=plt.subplots(figsize=(9,4))
x_labels=[f"{row.Segment}\\n(n={row.Rows:,})" for _,row in area_diagnostics.iterrows()]
ax.bar(x_labels,area_diagnostics.MAE/1_000_000,color='#54A24B')
ax.set(title=f'MAE by supported area bucket — {VALIDATION_MODE}\\nPhysical area order; evaluated n={int(area_diagnostics.Rows.sum()):,}',xlabel='Area bucket',ylabel='MAE (million VND)')
ax.tick_params(axis='x',rotation=15); plt.tight_layout(); plt.show()"""
    ),
    md("## 15. Source Diagnostics"),
    code(
        """source_metrics=source_diagnostics(evaluation_frame,min_support=MIN_SUPPORT)
source_metrics=source_metrics.merge(source_share[['Category','Reference Share %','Shadow Share %','Delta pp']],left_on='Segment',right_on='Category',how='left').drop(columns=['Category'])
source_metrics=source_metrics.rename(columns={'Reference Share %':'Inference Reference Share %','Shadow Share %':'Inference Shadow Share %','Rows':'Evaluation Rows','MAE':'Evaluation MAE','MedianAE':'Evaluation MedianAE','Signed Bias':'Evaluation Signed Bias'})
display(source_metrics)
fig,ax=plt.subplots(figsize=(10,4))
ax.bar(source_metrics.Segment,source_metrics['Evaluation MAE']/1_000_000,color='#4C78A8')
ax.set(title=f'Evaluation MAE by sufficiently populated source — {VALIDATION_MODE}\\nMinimum support={MIN_SUPPORT}; total evaluation rows={int(source_metrics[\"Evaluation Rows\"].sum()):,}',xlabel='Source',ylabel='Evaluation MAE (million VND)')
ax.tick_params(axis='x',rotation=35); plt.tight_layout(); plt.show()"""
    ),
    md("## 16. Location Diagnostics"),
    code(
        """ward_metrics=ward_diagnostics(evaluation_frame,min_support=MIN_SUPPORT,include_missing=False)
district_metrics=district_diagnostics(evaluation_frame,min_support=MIN_SUPPORT,include_missing=False)
missing_loc=missing_location_summary(evaluation_frame)
display(Markdown('### High-Support Wards (excluding missing)')); display(ward_metrics.head(15))
display(Markdown('### High-Support Districts (excluding missing)')); display(district_metrics.head(15))
if len(missing_loc): display(Markdown('### Missing Location Diagnostics')); display(missing_loc)
fig,axes=plt.subplots(1,2,figsize=(14,6))
top_wards=ward_metrics.sort_values('Rows',ascending=False).head(15)
axes[0].barh(top_wards.Segment[::-1],(top_wards.MAE/1_000_000)[::-1],color='#72B7B2')
axes[0].set(title=f'MAE for Top 15 Wards by Support — {VALIDATION_MODE}\\nExcluding missing; min support={MIN_SUPPORT}',xlabel='MAE (million VND)',ylabel='Ward')
top_districts=district_metrics.sort_values('Rows',ascending=False).head(15)
axes[1].barh(top_districts.Segment[::-1],(top_districts.MAE/1_000_000)[::-1],color='#4C78A8')
axes[1].set(title=f'MAE for Top 15 Districts by Support — {VALIDATION_MODE}\\nExcluding missing; min support={MIN_SUPPORT}',xlabel='MAE (million VND)',ylabel='District')
plt.tight_layout(); plt.show()"""
    ),
    md("## 17. RENT vs UNKNOWN Diagnostics"),
    code(
        """intent_metrics=intent_diagnostics(evaluation_frame)
display(intent_metrics)
fig,ax=plt.subplots(figsize=(7,4)); ax.bar(intent_metrics.Segment,intent_metrics.MAE/1_000_000,color=['#4C78A8','#F58518','#B9B9B9'][:len(intent_metrics)]); ax.set(title=f'RENT vs UNKNOWN monitoring — {VALIDATION_MODE}\\nPolicy is unchanged; evaluated n={int(intent_metrics.Rows.sum()):,}',xlabel='Canonical listing intent',ylabel='MAE (million VND)'); plt.tight_layout(); plt.show()"""
    ),
    md("## 18. Temporal Monitoring"),
    code(
        """temporal_metrics=temporal_diagnostics(evaluation_frame)
display(temporal_metrics)
temporal_order=temporal_metrics.sort_values('Segment')
fig,ax=plt.subplots(figsize=(11,4)); ax.plot(temporal_order.Segment,temporal_order.MAE/1_000_000,marker='o')
ax.set(title=f'Historical dry-run daily error — {VALIDATION_MODE}\\nIntegration diagnostic only — not out-of-sample temporal evidence (evaluated n={int(temporal_order.Rows.sum()):,})',xlabel='Observation date',ylabel='MAE (million VND)')
ax.tick_params(axis='x',rotation=45); plt.tight_layout(); plt.show()"""
    ),
    md("## 19. Prediction Compression Monitoring"),
    code(
        """compression_metrics=prediction_compression_report(evaluation_frame)
display(compression_metrics)
fig,ax=plt.subplots(figsize=(9,4)); positions=np.arange(len(compression_metrics)); width=.25
ax.bar(positions-width,compression_metrics.p01/1_000_000,width,label='P01')
ax.bar(positions,compression_metrics['median']/1_000_000,width,label='Median')
ax.bar(positions+width,compression_metrics.p99/1_000_000,width,label='P99')
ax.set(xticks=positions,xticklabels=compression_metrics.Population,title=f'Actual vs prediction distribution compression — {VALIDATION_MODE}\\nRaw VND quantiles; evaluation n={len(evaluated):,}',xlabel='Population',ylabel='Monthly rent (million VND)')
ax.legend(); plt.tight_layout(); plt.show()
pred_row=compression_metrics.loc[compression_metrics.Population.eq('PREDICTION')].iloc[0]
act_row=compression_metrics.loc[compression_metrics.Population.eq('ACTUAL')].iloc[0]
print(f"On this observed batch, predictions were concentrated within [{pred_row.p01/1e6:.2f}M, {pred_row.p99/1e6:.2f}M] VND (median {pred_row['median']/1e6:.2f}M VND), while actual rent spans [{act_row.p01/1e6:.2f}M, {act_row.p99/1e6:.2f}M] VND (median {act_row['median']/1e6:.2f}M VND).")"""
    ),
    md("## 20. Production Readiness Gate"),
    code(
        """area_row=numeric_drift.iloc[0]
max_source_shift=category_share_drift.loc[category_share_drift.Feature.eq('source_code'),'Delta pp'].abs().max()
max_unseen_pct=category_drift['Unseen Row %'].max()
drift_within_threshold=bool(abs(area_row['Median Shift'])<=max(PROVISIONAL_AREA_MEDIAN_SHIFT_MAX_M2,PROVISIONAL_AREA_MEDIAN_SHIFT_PCT*area_row['Reference Median']) and abs(area_row['Missing Shift pp'])<=PROVISIONAL_AREA_MISSING_SHIFT_PP and max_source_shift<=PROVISIONAL_MAX_SOURCE_SHIFT_PP and max_unseen_pct<=PROVISIONAL_MAX_UNSEEN_CATEGORY_PCT)
def segment_calibrated(table,label):
    row=table.loc[table.Segment.eq(label)]
    return bool(len(row) and abs(row.iloc[0]['Signed Bias'])<=PROVISIONAL_TAIL_BIAS_RATIO_MAX*max(row.iloc[0]['Actual Median'],1))
core_rows=price_diagnostics.loc[price_diagnostics.Segment.isin(['2.5M–<4.0M','4.0M–<6.0M'])].copy()
core_market_error_stable=bool(len(core_rows)==2 and (core_rows.MAE/core_rows['Actual Median'].clip(lower=1)).max()<=PROVISIONAL_CORE_MAE_RATIO_MAX and (core_rows['Signed Bias'].abs()/core_rows['Actual Median'].clip(lower=1)).max()<=PROVISIONAL_CORE_BIAS_RATIO_MAX)
budget_calibration_acceptable=segment_calibrated(price_diagnostics,'< 2.5M')
upper_tail_calibration_acceptable=segment_calibrated(price_diagnostics,'> 10.0M')
source_stability=bool(len(source_metrics) and (source_metrics['Evaluation Signed Bias'].abs()/source_metrics['Actual Median'].clip(lower=1)).max()<=PROVISIONAL_SOURCE_BIAS_RATIO_MAX)
location_stability=bool(len(ward_metrics) and (ward_metrics['Signed Bias'].abs()/ward_metrics['Actual Median'].clip(lower=1)).median()<=PROVISIONAL_LOCATION_BIAS_RATIO_MAX)
observed=pd.to_datetime(population.ready_rows.latest_observed_at,errors='coerce'); temporal_coverage_days=(observed.max()-observed.min()).total_seconds()/86400 if observed.notna().any() else 0
readiness_scorecard,readiness_decision=build_readiness_scorecard(validation_mode=VALIDATION_MODE,sample_rows=len(shadow_predictions),temporal_coverage_days=temporal_coverage_days,artifact_loaded=True,inference_contract_valid=True,no_leakage=TARGET_COLUMN not in X_shadow.columns,unknown_categories_safe=True,prediction_sanity_pass=sanity_checks.Status.eq('PASS').all(),drift_within_threshold=drift_within_threshold,core_market_error_stable=core_market_error_stable,budget_calibration_acceptable=budget_calibration_acceptable,upper_tail_calibration_acceptable=upper_tail_calibration_acceptable,source_stability=source_stability,location_stability=location_stability)
display(readiness_scorecard); display(pd.Series(readiness_decision,name='Decision').to_frame())
readiness_context='Historical dry run verifies mechanics only; cannot promote candidate model' if VALIDATION_MODE=='HISTORICAL_DRY_RUN' else 'Automated checks never promote directly to production'
fig,ax=plt.subplots(figsize=(9,5)); colors=readiness_scorecard.Status.map({'PASS':'#54A24B','NOT MET':'#E45756'}); ax.barh(readiness_scorecard.Dimension[::-1],np.ones(len(readiness_scorecard)),color=colors[::-1]); ax.set(xlim=(0,1),xticks=[],title=f'Production readiness scorecard — {VALIDATION_MODE}\\n{readiness_context}',xlabel='PASS / NOT MET',ylabel='Readiness dimension'); plt.tight_layout(); plt.show()
if VALIDATION_MODE=='HISTORICAL_DRY_RUN':
    assert readiness_decision['production_evidence']=='INSUFFICIENT'
    assert readiness_decision['model_readiness']=='CANDIDATE'
    assert readiness_decision['deployment_lifecycle']=='SHADOW'"""
    ),
    md("## 21. Persist Shadow Artifacts"),
    code(
        """RUN_ID=make_shadow_run_id(VALIDATION_MODE,INFERENCE_TIMESTAMP)
model_eligible_rows=int(evaluation_population.funnel.loc[evaluation_population.funnel.Stage.eq('Final model eligible'),'Rows'].iloc[0])
run_metadata={'run_id':RUN_ID,'model_id':champion.metadata['model_id'],'model_family':champion.metadata['model_family'],'feature_set':champion.metadata['feature_set'],'feature_names':champion.metadata['feature_names'],'target_transform':champion.metadata['target_transform'],'artifact_sha256':champion.metadata['artifact_sha256'],'validation_mode':VALIDATION_MODE,'counts_toward_production_evidence':mode_decision.counts_toward_production,'mode_reason':mode_decision.reason,'silver_sha256':CURRENT_SILVER_SHA256,'data_min_observed_at':mode_decision.min_observed_at,'data_max_observed_at':mode_decision.max_observed_at,'model_lock_evidence_cutoff':mode_decision.evidence_cutoff,'silver_rows':len(silver_df),'inference_ready_rows':len(shadow_predictions),'model_eligible_rows':model_eligible_rows,'evaluation_rows':len(evaluation_frame),'excluded_from_inference_rows':len(silver_df)-len(shadow_predictions),'excluded_from_evaluation_rows':len(silver_df)-model_eligible_rows,'temporal_coverage_days':temporal_coverage_days,'feature_drift_summary':numeric_drift.iloc[0].to_dict(),'category_drift_summary':category_drift.to_dict('records'),'prediction_distribution':prediction_distribution_table.iloc[0].to_dict(),'overall_metrics':overall_metrics.iloc[0].to_dict(),'provisional_monitoring_thresholds':{'minimum_sample_rows':PROVISIONAL_MIN_SAMPLE_ROWS,'minimum_future_days':PROVISIONAL_MIN_FUTURE_DAYS,'area_median_shift':f'<= max({PROVISIONAL_AREA_MEDIAN_SHIFT_MAX_M2}m², {int(PROVISIONAL_AREA_MEDIAN_SHIFT_PCT*100)}% of reference median)','area_missing_shift_pp':PROVISIONAL_AREA_MISSING_SHIFT_PP,'source_share_shift_pp':PROVISIONAL_MAX_SOURCE_SHIFT_PP,'unseen_category_rows_pct':PROVISIONAL_MAX_UNSEEN_CATEGORY_PCT,'budget_and_upper_tail_absolute_bias_pct':int(PROVISIONAL_TAIL_BIAS_RATIO_MAX*100),'source_and_location_bias_pct':int(PROVISIONAL_SOURCE_BIAS_RATIO_MAX*100)},'model_readiness':readiness_decision['model_readiness'],'deployment_lifecycle':readiness_decision['deployment_lifecycle'],'production_evidence':readiness_decision['production_evidence'],'recommended_status':readiness_decision['recommended_status'],'inference_timestamp':INFERENCE_TIMESTAMP}
artifact_tables={'inference_population_funnel':population.funnel,'evaluation_population_funnel':evaluation_population.funnel,'evaluation_exclusion_summary':evaluation_population.exclusion_summary,'schema_validation':population.schema_summary,'numeric_feature_drift':numeric_drift,'category_share_drift':category_share_drift,'category_drift':category_drift,'prediction_distribution':prediction_distribution_table,'prediction_reference_comparison':prediction_reference_comparison,'prediction_sanity':sanity_checks,'overall_metrics':overall_metrics,'price_bucket_metrics':price_diagnostics,'area_bucket_metrics':area_diagnostics,'source_metrics':source_metrics,'ward_metrics':ward_metrics,'district_metrics':district_metrics,'missing_location_metrics':missing_loc,'intent_metrics':intent_metrics,'temporal_metrics':temporal_metrics,'prediction_compression':compression_metrics,'readiness_scorecard':readiness_scorecard}
RUN_DIR=persist_shadow_run(SHADOW_OUTPUT_ROOT,RUN_ID,run_metadata,shadow_output,artifact_tables)
display(pd.DataFrame([{'Artifact':path.name,'Bytes':path.stat().st_size} for path in sorted(RUN_DIR.iterdir()) if path.is_file()]))
display(Markdown(f'Append-only shadow evidence written to `{RUN_DIR}`.'))"""
    ),
    md("## 22. Final Summary"),
    code(
        """final_summary=pd.Series({'Champion artifact':'PASS','Inference contract':'PASS','Shadow pipeline':'PASS','Validation mode':VALIDATION_MODE,'Historical dry run':'PASS' if VALIDATION_MODE=='HISTORICAL_DRY_RUN' else 'NOT APPLICABLE','Future shadow evidence':'AVAILABLE' if mode_decision.counts_toward_production else 'NOT YET AVAILABLE','Model readiness':readiness_decision['model_readiness'],'Deployment lifecycle':readiness_decision['deployment_lifecycle'],'Production evidence':readiness_decision['production_evidence'],'Recommended status':readiness_decision['recommended_status'],'Silver rows':len(silver_df),'Target-free inference rows':len(shadow_predictions),'Model-evaluation eligible rows':model_eligible_rows,'Evaluated rows':int(overall_metrics.iloc[0]['Rows']),'Model ID':champion.metadata['model_id'],'Run ID':RUN_ID,'Run directory':str(RUN_DIR)},name='Result')
display(final_summary.to_frame())
display(Markdown('**Current evidence remains insufficient for production. Required next evidence: 30–60 days of untouched post-lock multi-crawl observations, with stable source/location error and explicit low-price overprediction and upper-tail underprediction monitoring.**'))"""
    ),
]


notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "RoomBeacon (venv)",
            "language": "python",
            "name": "roombeacon-venv",
        },
        "language_info": {"name": "python", "version": "3.12.3"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

(ROOT / "notebooks" / "06_roombeacon_shadow_validation.ipynb").write_text(
    json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8"
)
