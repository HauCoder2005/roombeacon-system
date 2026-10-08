"""Build the auditable RoomBeacon modeling notebook from concise source cells."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def md(text): return {"cell_type":"markdown","metadata":{},"source":text.splitlines(True)}
def code(text): return {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":text.splitlines(True)}

cells = [
md("""# RoomBeacon — Rental Price Benchmark V3: Methodology-Hardened\n\nThis benchmark predicts `price_model_value` from canonical Silver. Model/feature/transform/tuning choices use **development chronological folds only**. The final chronological TEST is sealed until one candidate is locked. No Bronze/Silver logic is changed."""),
md("## 01 Runtime, canonical input, and reproducibility"),
code("""from pathlib import Path
from datetime import datetime, timezone
import json, platform, sys, time
PROJECT_ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'crawler').is_dir() and (p/'analytics').is_dir())
sys.path.insert(0,str(PROJECT_ROOT))
import duckdb,numpy as np,pandas as pd,matplotlib.pyplot as plt
import sklearn,xgboost,lightgbm,catboost
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor
from IPython.display import display,Markdown
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor,GradientBoostingRegressor,HistGradientBoostingRegressor,RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet,LinearRegression,Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder,OrdinalEncoder,StandardScaler
from sklearn.tree import DecisionTreeRegressor
from analytics.duckdb.connection import resolve_runtime_path
from roombeacon_crawler.config.get_env import env
from notebooks.utils.modeling_benchmark import *
from notebooks.utils.modeling_benchmark import prepare_lightgbm_categories
from notebooks.utils.shadow_validation import build_reference_profile,file_sha256,persist_champion_artifact
from notebooks.utils.listing_semantics import BUSINESS_TARGET_DEFINITION,semantic_model_eligibility
SEED=42; np.random.seed(SEED); plt.style.use('seaborn-v0_8-whitegrid')
SILVER_PATH=resolve_runtime_path(env.processing.silver_dir)/'rental_listings.parquet'
METADATA_PATH=resolve_runtime_path(env.processing.silver_dir)/'rental_listings.metadata.json'
with duckdb.connect(':memory:') as con: silver_df=con.execute('select * from read_parquet(?)',[str(SILVER_PATH)]).df()
silver_metadata=json.loads(METADATA_PATH.read_text())
assert len(silver_df)==silver_df.rental_post_id.nunique()==silver_metadata['row_count']
versions={'Python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'scikit-learn':sklearn.__version__,'xgboost':xgboost.__version__,'lightgbm':lightgbm.__version__,'catboost':catboost.__version__}
display(pd.Series(versions,name='Version').to_frame())"""),
md("""## 02 Business target, semantic population, and leakage contract

**Business target:** Predict the asking rental price for an ordinary individual rental listing/unit represented by RoomBeacon.

SALE, TRANSFER, WHOLE_BUILDING, and MULTI_UNIT_BUSINESS evidence is incompatible. UNKNOWN is retained when no conflicting evidence exists; sparse text is not guessed. Semantic labels are eligibility/audit fields and are not predictors."""),
code("""prepared=engineer_safe_features(silver_df)
TRUSTED_PRICE_STATUSES={'TRUSTED_EXISTING','TRUSTED_REPARSED'}
permissive_masks=build_modeling_eligibility(prepared,policy='PERMISSIVE'); strict_masks=build_modeling_eligibility(prepared,policy='STRICT')
eligibility_funnel_permissive=eligibility_funnel(permissive_masks); eligibility_funnel_strict=eligibility_funnel(strict_masks)
numeric_candidate=permissive_masks.numeric_target_candidate; numeric_trusted=permissive_masks.lineage_trusted
semantic_compatible=permissive_masks.rental_compatible; semantic_reason=pd.Series(np.where(semantic_compatible,'SEMANTICALLY_COMPATIBLE','NOT_RENTAL_COMPATIBLE'),index=prepared.index,dtype='string'); prepared['semantic_eligibility_reason']=semantic_reason
eligible=permissive_masks.final_eligible
model_df=prepared.loc[eligible].copy(); model_df[TARGET]=model_df.price_model_value.astype(float); model_df['group_key']=build_group_key(model_df)
FEATURE_SETS=build_feature_sets(model_df.columns)
for features in FEATURE_SETS.values(): audit_features(features)
before=prepared.loc[numeric_candidate,'price_amount_clean'].astype(float); target=model_df[TARGET].astype(float)
semantic_population_summary=eligibility_funnel_permissive.rename(columns={'Stage':'Population'})
prepared['model_exclusion_reason']=np.select([~numeric_candidate,numeric_candidate&~numeric_trusted,numeric_trusted&~permissive_masks.semantic_target_supported,permissive_masks.semantic_target_supported&~permissive_masks.area_supported,permissive_masks.area_supported&~permissive_masks.rental_compatible],['NO_NUMERIC_CANDIDATE','NUMERIC_TARGET_NOT_TRUSTED','PRICE_SEMANTIC_NOT_SUPPORTED','AREA_NOT_SUPPORTED','NOT_RENTAL_COMPATIBLE'],default='MODEL_ELIGIBLE')
semantic_exclusion_summary=prepared.groupby(['model_exclusion_reason','price_target_trust_status','listing_intent','rental_scope','source_code'],dropna=False).size().rename('Rows').reset_index().sort_values('Rows',ascending=False)
target_distribution_comparison=pd.DataFrame([{'Population':'Before numeric-trust filtering','Rows':len(before),'Min':before.min(),'P01':before.quantile(.01),'P05':before.quantile(.05),'P25':before.quantile(.25),'Median':before.median(),'P75':before.quantile(.75),'P95':before.quantile(.95),'P99':before.quantile(.99),'Max':before.max()},{'Population':'Final eligible trusted target','Rows':len(target),'Min':target.min(),'P01':target.quantile(.01),'P05':target.quantile(.05),'P25':target.quantile(.25),'Median':target.median(),'P75':target.quantile(.75),'P95':target.quantile(.95),'P99':target.quantile(.99),'Max':target.max()}])
semantic_exclusion_examples=prepared.loc[prepared.model_exclusion_reason.ne('MODEL_ELIGIBLE'),['rental_post_id','source_code','title_clean','price_amount_clean','price_model_value','price_target_model_value','price_target_trust_status','price_target_trust_reason','listing_intent','rental_scope','model_exclusion_reason']].groupby('model_exclusion_reason',group_keys=False).head(8)
valid_high_price_examples=prepared.loc[eligible,['rental_post_id','source_code','title_clean',TARGET,'area_value_clean','listing_intent','rental_scope']].nlargest(20,TARGET)
display(pd.Series({'Business target':BUSINESS_TARGET_DEFINITION,'UNKNOWN policy':'PERMISSIVE by default; STRICT evaluated separately','Accepted numeric trust statuses':', '.join(sorted(TRUSTED_PRICE_STATUSES))},name='Policy').to_frame()); display(eligibility_funnel_permissive); display(eligibility_funnel_strict); display(prepared.listing_intent.value_counts(dropna=False).to_frame('Rows')); display(prepared.rental_scope.value_counts(dropna=False).to_frame('Rows')); display(prepared.price_target_trust_status.value_counts(dropna=False).to_frame('Rows')); display(prepared.price_model_suitability.value_counts(dropna=False).to_frame('Rows')); display(prepared.area_model_suitability.value_counts(dropna=False).to_frame('Rows')); display(semantic_exclusion_summary); display(target_distribution_comparison); display(semantic_exclusion_examples); display(Markdown('### Valid high-price rows retained by canonical trust evidence')); display(valid_high_price_examples)
display(pd.DataFrame([{'Feature Set':k,'Features':', '.join(v)} for k,v in FEATURE_SETS.items()]))
display(Markdown('**Leakage exclusions:** identifiers, duplicate group keys, raw/canonical price evidence, `price_per_area`, parser/quality fields, and every target-reconstructive field are excluded.'))
q=target.quantile([.01,.5,.95,.99])
fig,ax=plt.subplots(1,2,figsize=(12,4)); ax[0].hist(target.clip(upper=q.loc[.99]),bins=60); ax[1].hist(np.log1p(target),bins=60,color='#F58518'); ax[0].set_title('Target (display clipped at P99)'); ax[1].set_title('Target log1p'); plt.tight_layout(); plt.show()"""),
md("## 03 Group-isolated chronological split using representative group time\\n\\nSplit isolates duplicate groups to avoid leakage and orders by representative group time."),
code("""split_result=group_aware_split(model_df,model_df.group_key,seed=SEED)
model_df['split']=split_result.labels; assert_group_isolation(model_df.group_key,model_df.split); assert_split_chronology(model_df,model_df.group_key,split_result)
development_df=model_df.loc[model_df.split.ne('TEST')].copy(); test_df=model_df.loc[model_df.split.eq('TEST')].copy()
folds=build_expanding_group_time_folds(development_df,development_df.group_key,n_splits=3)
split_report=model_df.groupby('split').agg(Rows=('rental_post_id','size'),Groups=('group_key','nunique'),Target_Median=(TARGET,'median'),Target_P95=(TARGET,lambda x:x.quantile(.95)),Target_Max=(TARGET,'max'),Min_Time=('latest_observed_at','min'),Max_Time=('latest_observed_at','max')).reindex(['TRAIN','VALIDATION','TEST'])
fold_report=pd.DataFrame([{'Fold':f.fold,'Train Rows':len(f.train_index),'Validation Rows':len(f.validation_index),'Train Groups':f.train_groups,'Validation Groups':f.validation_groups,'Train Start':f.train_start,'Train End':f.train_end,'Validation Start':f.validation_start,'Validation End':f.validation_end} for f in folds])
display(pd.Series({'Strategy':split_result.strategy,'Reason':split_result.reason,'Limitation':'Only ~10 days: short-window future evidence, not long-term generalization'},name='Value').to_frame()); display(split_report); display(fold_report)
TEST_ACCESSED_FOR_SELECTION=False"""),
md("## 04 Fair preprocessing and model registry\n\nSklearn models receive fold-fitted one-hot encoding with unknown-category safety. CatBoost uses native strings. LightGBM uses train-defined pandas categories. Every target transform and imputer is learned/applied inside the fold workflow."),
code("""from notebooks.utils.modeling_benchmark import prepare_lightgbm_categories
CATS=['source_code','ward_current','district_text_extracted','province_text_extracted']
MODEL_ORDER=['Linear Regression','Ridge Regression','ElasticNet','Decision Tree Regressor','Random Forest Regressor','Extra Trees Regressor','Gradient Boosting Regressor','HistGradientBoosting Regressor','XGBoost Regressor','LightGBM Regressor','CatBoost Regressor']
BASE_PARAMS={
'Linear Regression':{},'Ridge Regression':{'alpha':100.},'ElasticNet':{'alpha':.001,'l1_ratio':.5},
'Decision Tree Regressor':{'max_depth':12,'min_samples_leaf':30},'Random Forest Regressor':{'n_estimators':80,'max_depth':16,'min_samples_leaf':5,'max_features':.8},
'Extra Trees Regressor':{'n_estimators':80,'max_depth':16,'min_samples_leaf':5,'max_features':.8},'Gradient Boosting Regressor':{'n_estimators':80,'learning_rate':.05,'max_depth':3,'loss':'huber'},
'HistGradientBoosting Regressor':{'max_iter':100,'learning_rate':.07,'max_leaf_nodes':31,'loss':'absolute_error'},
'XGBoost Regressor':{'n_estimators':100,'max_depth':6,'learning_rate':.05,'subsample':.8,'colsample_bytree':.9,'objective':'reg:absoluteerror'},
'LightGBM Regressor':{'n_estimators':120,'num_leaves':31,'learning_rate':.05,'min_child_samples':30,'objective':'mae'},
'CatBoost Regressor':{'iterations':140,'depth':7,'learning_rate':.06,'l2_leaf_reg':5,'loss_function':'MAE'}}

def frames(frame,features,native=False):
 out=frame[features].copy()
 for c in set(features)&set(CATS): out[c]=out[c].astype('string').fillna('__MISSING__') if native else out[c].astype('object').where(out[c].notna(),np.nan)
 return out

def sklearn_pipeline(name,params,features):
 nums=[c for c in features if c not in CATS]; cats=[c for c in features if c in CATS]
 num=[('imputer',SimpleImputer(strategy='median'))]
 if name in ['Linear Regression','Ridge Regression','ElasticNet']: num.append(('scale',StandardScaler()))
 encoder=OrdinalEncoder(handle_unknown='use_encoded_value',unknown_value=-1) if name=='HistGradientBoosting Regressor' else OneHotEncoder(handle_unknown='ignore',sparse_output=True)
 pre=ColumnTransformer([('num',Pipeline(num),nums),('cat',Pipeline([('imputer',SimpleImputer(strategy='constant',fill_value='__MISSING__')),('encoder',encoder)]),cats)],sparse_threshold=1.0)
 kw={'random_state':SEED}
 if name=='Linear Regression': model=LinearRegression(**params)
 elif name=='Ridge Regression': model=Ridge(**params)
 elif name=='ElasticNet': model=ElasticNet(max_iter=3000,**kw,**params)
 elif name=='Decision Tree Regressor': model=DecisionTreeRegressor(**kw,**params)
 elif name=='Random Forest Regressor': model=RandomForestRegressor(n_jobs=-1,**kw,**params)
 elif name=='Extra Trees Regressor': model=ExtraTreesRegressor(n_jobs=-1,**kw,**params)
 elif name=='Gradient Boosting Regressor': model=GradientBoostingRegressor(**kw,**params)
 elif name=='HistGradientBoosting Regressor': model=HistGradientBoostingRegressor(**kw,**params)
 elif name=='XGBoost Regressor': model=XGBRegressor(n_jobs=-1,**kw,**params)
 else: raise ValueError(name)
 return Pipeline([('preprocessor',pre),('model',model)])

def fit_predict(name,params,features,fit,score,transform):
 y=transform_target(fit[TARGET],transform); started=time.perf_counter()
 if name=='CatBoost Regressor':
  model=CatBoostRegressor(random_seed=SEED,verbose=False,allow_writing_files=False,thread_count=-1,**params); X=frames(fit,features,True); model.fit(X,y,cat_features=[c for c in features if c in CATS]); fit_s=time.perf_counter()-started; p=time.perf_counter(); pred=model.predict(frames(score,features,True))
 elif name=='LightGBM Regressor':
  cats=[c for c in features if c in CATS]
  X,Z=prepare_lightgbm_categories(fit[features],score[features],cats)
  model=LGBMRegressor(random_state=SEED,n_jobs=-1,verbosity=-1,**params); model.fit(X,y,categorical_feature=cats); fit_s=time.perf_counter()-started; p=time.perf_counter(); pred=model.predict(Z)
 else:
  model=sklearn_pipeline(name,params,features); model.fit(frames(fit,features),y); fit_s=time.perf_counter()-started; p=time.perf_counter(); pred=model.predict(frames(score,features))
 return model,inverse_target(pred,transform),fit_s,time.perf_counter()-p

def baseline_predict(name,fit,score):
 if name=='Global Median': return np.full(len(score),float(fit[TARGET].median()))
 if name=='Hierarchical Location Median': return hierarchical_location_median(fit,score)
 return hierarchical_segment_median(fit,score)

def evaluate_config(name,params,features,feature_set,transform):
 rows=[]
 for f in folds:
  fit=development_df.loc[f.train_index]; score=development_df.loc[f.validation_index]
  if name in ['Global Median','Hierarchical Location Median','Hierarchical Segment Median']:
   started=time.perf_counter(); pred=baseline_predict(name,fit,score); fit_s=0.; pred_s=time.perf_counter()-started
  else: _,pred,fit_s,pred_s=fit_predict(name,params,features,fit,score,transform)
  rows.append({'Fold':f.fold,'Model':name,'Target Transform':transform,'Feature Set':feature_set,'Parameters':json.dumps(params,sort_keys=True),**regression_metrics(score[TARGET],pred),'Fit Time':fit_s,'Prediction Time':pred_s,'Train Rows':len(fit),'Validation Rows':len(score),'Train Groups':f.train_groups,'Validation Groups':f.validation_groups,'Group Overlap':0,'Train Start':f.train_start,'Train End':f.train_end,'Validation Start':f.validation_start,'Validation End':f.validation_end,'Target Median':score[TARGET].median(),'Target P95':score[TARGET].quantile(.95),'Target Max':score[TARGET].max()})
 return rows"""),
md("## 05 F1–F5 development comparison and F4 vs F5 decision"),
code("""feature_rows=[]
for feature_set,features in FEATURE_SETS.items(): feature_rows+=evaluate_config('LightGBM Regressor',BASE_PARAMS['LightGBM Regressor'],features,feature_set,'LOG1P')
for feature_set in ['F4 — AREA + SOURCE + LOCATION','F5 — FULL SAFE TABULAR']: feature_rows+=evaluate_config('CatBoost Regressor',BASE_PARAMS['CatBoost Regressor'],FEATURE_SETS[feature_set],feature_set,'LOG1P')
for feature_set in ['F4 — AREA + SOURCE + LOCATION','F5 — FULL SAFE TABULAR']: feature_rows+=evaluate_config('LightGBM Regressor',BASE_PARAMS['LightGBM Regressor'],FEATURE_SETS[feature_set],feature_set,'RAW')
feature_fold_results=pd.DataFrame(feature_rows); feature_summary=summarize_development(feature_fold_results)
f45=feature_summary.loc[feature_summary['Feature Set'].isin(['F4 — AREA + SOURCE + LOCATION','F5 — FULL SAFE TABULAR'])].copy(); display(feature_summary); display(f45)
f45_rows=[]
for (model,transform),g in f45.groupby(['Model','Target Transform']):
 f4=g.loc[g['Feature Set'].str.startswith('F4')].iloc[0]; f5=g.loc[g['Feature Set'].str.startswith('F5')].iloc[0]
 f45_rows.append({'Model':model,'Target Transform':transform,'F4 MAE':f4.MAE_Mean,'F5 MAE':f5.MAE_Mean,'F5 absolute improvement':f4.MAE_Mean-f5.MAE_Mean,'F5 improvement %':(f4.MAE_Mean-f5.MAE_Mean)/f4.MAE_Mean*100,'F5 better':f5.MAE_Mean<f4.MAE_Mean})
f45_decision=pd.DataFrame(f45_rows); consistent=bool(f45_decision['F5 better'].all()); aggregate_gain=f45_decision['F5 absolute improvement'].sum()/f45_decision['F4 MAE'].sum()*100
SELECTED_FEATURE_SET='F5 — FULL SAFE TABULAR' if consistent and aggregate_gain>=1.0 else 'F4 — AREA + SOURCE + LOCATION'; SELECTED_FEATURES=FEATURE_SETS[SELECTED_FEATURE_SET]
display(f45_decision); display(pd.Series({'F5 consistently better':consistent,'Aggregate F5 improvement %':aggregate_gain,'Decision':SELECTED_FEATURE_SET},name='Value').to_frame())"""),
md("## 06 Development-only broad RAW vs LOG1P comparison"),
code("""development_rows=[]
for baseline in ['Global Median','Hierarchical Location Median','Hierarchical Segment Median']: development_rows+=evaluate_config(baseline,{},SELECTED_FEATURES,'TRAIN-ONLY BASELINE','RAW')
for name in MODEL_ORDER:
 for transform in ['RAW','LOG1P']: development_rows+=evaluate_config(name,BASE_PARAMS[name],SELECTED_FEATURES,SELECTED_FEATURE_SET,transform)
development_fold_results=pd.DataFrame(development_rows); development_comparison=summarize_development(development_fold_results)
display(development_comparison); assert not TEST_ACCESSED_FOR_SELECTION
fig,ax=plt.subplots(figsize=(12,7)); plot=development_comparison.sort_values('MAE_Mean',ascending=False); ax.barh(plot.Model+' / '+plot['Target Transform'],plot.MAE_Mean,xerr=plot.MAE_Std); ax.set_title('Development chronological-fold MAE'); plt.tight_layout(); plt.show()"""),
md("## 07 Small bounded tuning and candidate lock\n\nOnly the best development configuration per family enters a small bounded refinement. No TEST identities or metrics are accessed."),
code("""best_family=development_comparison.sort_values('MAE_Mean').drop_duplicates('Model'); ml_shortlist=best_family.loc[~best_family.Model.isin(['Global Median','Hierarchical Location Median','Hierarchical Segment Median'])].head(3)
TUNING={
'CatBoost Regressor':[BASE_PARAMS['CatBoost Regressor'],{**BASE_PARAMS['CatBoost Regressor'],'depth':6,'iterations':200}],
'LightGBM Regressor':[BASE_PARAMS['LightGBM Regressor'],{**BASE_PARAMS['LightGBM Regressor'],'num_leaves':63,'n_estimators':180}],
'XGBoost Regressor':[BASE_PARAMS['XGBoost Regressor'],{**BASE_PARAMS['XGBoost Regressor'],'max_depth':5,'n_estimators':160}],
'HistGradientBoosting Regressor':[BASE_PARAMS['HistGradientBoosting Regressor'],{**BASE_PARAMS['HistGradientBoosting Regressor'],'max_iter':160,'max_leaf_nodes':63}],
'Random Forest Regressor':[BASE_PARAMS['Random Forest Regressor'],{**BASE_PARAMS['Random Forest Regressor'],'n_estimators':140}],
'Extra Trees Regressor':[BASE_PARAMS['Extra Trees Regressor'],{**BASE_PARAMS['Extra Trees Regressor'],'n_estimators':140}]}
tuning_rows=[]
for _,row in ml_shortlist.iterrows():
 transform='RAW' if row['Model']=='LightGBM Regressor' else row['Target Transform']
 for params in TUNING.get(row['Model'],[BASE_PARAMS[row['Model']]]): tuning_rows+=evaluate_config(row['Model'],params,SELECTED_FEATURES,SELECTED_FEATURE_SET,transform)
tuning_fold_results=pd.DataFrame(tuning_rows); tuning_summary=summarize_development(tuning_fold_results)
candidate_pool=pd.concat([development_comparison.loc[development_comparison.Model.str.contains('Median')],tuning_summary],ignore_index=True)
COMPLEXITY={'Global Median':0,'Hierarchical Location Median':1,'Hierarchical Segment Median':2,'Linear Regression':3,'Ridge Regression':4,'ElasticNet':5,'Decision Tree Regressor':6,'HistGradientBoosting Regressor':7,'Gradient Boosting Regressor':8,'Random Forest Regressor':9,'Extra Trees Regressor':10,'LightGBM Regressor':11,'XGBoost Regressor':12,'CatBoost Regressor':13}
LOCKED_CANDIDATE=lock_candidate(candidate_pool,COMPLEXITY,tolerance=.01)
LOCKED_MODEL=LOCKED_CANDIDATE.Model; LOCKED_TRANSFORM=LOCKED_CANDIDATE['Target Transform']; LOCKED_PARAMS=json.loads(LOCKED_CANDIDATE.Parameters)
assert not TEST_ACCESSED_FOR_SELECTION
locked_fold_report=tuning_fold_results.loc[(tuning_fold_results.Model.eq(LOCKED_MODEL))&(tuning_fold_results.Parameters.eq(json.dumps(LOCKED_PARAMS,sort_keys=True)))].sort_values('Fold')
assert locked_fold_report['Group Overlap'].eq(0).all()
display(tuning_summary); display(locked_fold_report[['Fold','Train Start','Train End','Validation Start','Validation End','Train Rows','Validation Rows','Train Groups','Validation Groups','Group Overlap','Target Median','Target P95','Target Max','MAE']]); display(LOCKED_CANDIDATE.to_frame('Locked development decision')); display(Markdown(f'### Locked before TEST: **{LOCKED_MODEL} / {LOCKED_TRANSFORM}**'))"""),
md("## 08 Source ablation and leave-one-source-out diagnostics (development only)"),
code("""ablation_rows=[]
NO_SOURCE_FEATURES=[f for f in SELECTED_FEATURES if f!='source_code']
for label,features in [('Without source_code',NO_SOURCE_FEATURES),('With source_code',SELECTED_FEATURES)]: ablation_rows+=evaluate_config(LOCKED_MODEL,LOCKED_PARAMS,features,label,LOCKED_TRANSFORM)
source_ablation=summarize_development(pd.DataFrame(ablation_rows)); without=source_ablation.loc[source_ablation['Feature Set'].eq('Without source_code')].iloc[0]; with_source=source_ablation.loc[source_ablation['Feature Set'].eq('With source_code')].iloc[0]
SOURCE_ABLATION_ABSOLUTE=without.MAE_Mean-with_source.MAE_Mean; SOURCE_ABLATION_PERCENT=SOURCE_ABLATION_ABSOLUTE/with_source.MAE_Mean*100
display(source_ablation); display(pd.Series({'Absolute MAE degradation':SOURCE_ABLATION_ABSOLUTE,'MAE degradation %':SOURCE_ABLATION_PERCENT},name='Value').to_frame())
loso=[]
for source in sorted(development_df.source_code.dropna().unique()):
 train=development_df.loc[development_df.source_code.ne(source)]; score=development_df.loc[development_df.source_code.eq(source)]
 if len(score)<100: continue
 if LOCKED_MODEL in ['Global Median','Hierarchical Location Median','Hierarchical Segment Median']: pred=baseline_predict(LOCKED_MODEL,train,score)
 else: _,pred,_,_=fit_predict(LOCKED_MODEL,LOCKED_PARAMS,SELECTED_FEATURES,train,score,LOCKED_TRANSFORM)
 base=baseline_predict('Global Median',train,score); metrics=regression_metrics(score[TARGET],pred)
 loso.append({'Held-out Source':source,'Rows':len(score),'Target Median':score[TARGET].median(),'Target P95':score[TARGET].quantile(.95),'Target Max':score[TARGET].max(),**metrics,'Global Median MAE':regression_metrics(score[TARGET],base)['MAE'],'Baseline Beats Locked':regression_metrics(score[TARGET],base)['MAE']<metrics['MAE']})
leave_one_source_out=pd.DataFrame(loso).sort_values('MAE'); display(leave_one_source_out)"""),
md("## 08b UNKNOWN sensitivity — PERMISSIVE vs STRICT (development only)"),
code("""def evaluate_sensitivity_population(policy):
 masks=build_modeling_eligibility(prepared,policy=policy)
 population=prepared.loc[masks.final_eligible].copy(); population[TARGET]=population.price_model_value.astype(float); population['group_key']=build_group_key(population)
 population_split=group_aware_split(population,population.group_key,seed=SEED); population['split']=population_split.labels
 development=population.loc[population['split'].ne('TEST')].copy(); population_folds=build_expanding_group_time_folds(development,development.group_key,n_splits=3)
 rows=[]
 for fold in population_folds:
  fit=development.loc[fold.train_index]; score=development.loc[fold.validation_index]
  configurations=[('Hierarchical Segment Median','RAW',{}),(LOCKED_MODEL,LOCKED_TRANSFORM,LOCKED_PARAMS)]
  for name,transform,params in configurations:
   if name=='Hierarchical Segment Median': pred=hierarchical_segment_median(fit,score)
   else: _,pred,_,_=fit_predict(name,params,SELECTED_FEATURES,fit,score,transform)
   metrics=regression_metrics(score[TARGET],pred); threshold=fit[TARGET].quantile(.99); squared=(score[TARGET].to_numpy(float)-pred)**2; extreme=score[TARGET].to_numpy(float)>threshold
   rows.append({'Policy':policy,'Population Rows':len(population),'Development Rows':len(development),'Fold':fold.fold,'Train Rows':len(fit),'Validation Rows':len(score),'Model':name,'Target Transform':transform,**metrics,'Extreme Tail Squared Error %':float(squared[extreme].sum()/squared.sum()*100) if squared.sum() else 0.0})
 stats={'Policy':policy,'Population Rows':len(population),'Development Rows':len(development),'Target Median':population[TARGET].median(),'Target P95':population[TARGET].quantile(.95),'Target P99':population[TARGET].quantile(.99),'Area Median':population.area_value_clean.median(),'Area P95':population.area_value_clean.quantile(.95),'Area P99':population.area_value_clean.quantile(.99),'UNKNOWN Rows':int(population.listing_intent.eq('UNKNOWN').sum())}
 return rows,stats

sensitivity_rows=[]; sensitivity_populations=[]; sensitivity_source_rows=[]
for policy in ['PERMISSIVE','STRICT']:
 rows,stats=evaluate_sensitivity_population(policy); sensitivity_rows.extend(rows); sensitivity_populations.append(stats)
 m=build_modeling_eligibility(prepared,policy=policy); sub=prepared.loc[m.final_eligible]; counts=sub.source_code.value_counts(); pcts=sub.source_code.value_counts(normalize=True)*100
 for src in counts.index: sensitivity_source_rows.append({'Policy':policy,'Source':src,'Rows':int(counts[src]),'Share %':round(float(pcts[src]),2)})
unknown_sensitivity_sources=pd.DataFrame(sensitivity_source_rows)
unknown_sensitivity_fold_results=pd.DataFrame(sensitivity_rows)
unknown_sensitivity_summary=unknown_sensitivity_fold_results.groupby(['Policy','Population Rows','Development Rows','Model','Target Transform'],as_index=False).agg(Folds=('Fold','nunique'),MAE=('MAE','mean'),MAE_Std=('MAE','std'),MedianAE=('Median AE','mean'),RMSE=('RMSE','mean'),RMSLE=('RMSLE','mean'),R2=('R²','mean'),Tail_Squared_Error_Pct=('Extreme Tail Squared Error %','mean'))
baseline_mae=unknown_sensitivity_summary.loc[unknown_sensitivity_summary.Model.eq('Hierarchical Segment Median'),['Policy','MAE']].rename(columns={'MAE':'Baseline MAE'})
unknown_sensitivity_summary=unknown_sensitivity_summary.merge(baseline_mae,on='Policy',how='left'); unknown_sensitivity_summary['Baseline Improvement %']=(unknown_sensitivity_summary['Baseline MAE']-unknown_sensitivity_summary.MAE)/unknown_sensitivity_summary['Baseline MAE']*100
unknown_sensitivity_population=pd.DataFrame(sensitivity_populations)
display(unknown_sensitivity_population); display(unknown_sensitivity_sources); display(unknown_sensitivity_summary); assert not TEST_ACCESSED_FOR_SELECTION"""),
md("## 09 FINAL TEST — ONE-TIME EVALUATION\n\nThe candidate above is immutable. It is now retrained on all development rows and evaluated once on the sealed future TEST. Baselines are evaluated on the identical TEST rows."),
code("""assert LOCKED_MODEL and not TEST_ACCESSED_FOR_SELECTION
TEST_ACCESSED_FOR_SELECTION=True
test_predictions=pd.DataFrame({'rental_post_id':test_df.rental_post_id.to_numpy(),'group_key':test_df.group_key.to_numpy(),'actual_price':test_df[TARGET].to_numpy(float),'source_code':test_df.source_code.to_numpy(),'ward_current':test_df.ward_current.to_numpy(),'district_text_extracted':test_df.district_text_extracted.to_numpy(),'province_text_extracted':test_df.province_text_extracted.to_numpy(),'area_value_clean':test_df.area_value_clean.to_numpy(),'ward_mapping_status':test_df.ward_mapping_status.to_numpy(),'parse_status':test_df.parse_status.to_numpy(),'title_clean':test_df.title_clean.to_numpy(),'latest_observed_at':test_df.latest_observed_at.to_numpy()})
final_rows=[]; final_model=None
for name in ['Global Median','Hierarchical Location Median','Hierarchical Segment Median']:
 pred=baseline_predict(name,development_df,test_df); test_predictions[name]=pred; final_rows.append({'Model':name,'Target Transform':'RAW',**regression_metrics(test_df[TARGET],pred)})
if LOCKED_MODEL in ['Global Median','Hierarchical Location Median','Hierarchical Segment Median']:
 locked_pred=baseline_predict(LOCKED_MODEL,development_df,test_df)
else:
 final_model,locked_pred,fit_s,pred_s=fit_predict(LOCKED_MODEL,LOCKED_PARAMS,SELECTED_FEATURES,development_df,test_df,LOCKED_TRANSFORM)
 test_predictions[LOCKED_MODEL]=locked_pred; final_rows.append({'Model':LOCKED_MODEL,'Target Transform':LOCKED_TRANSFORM,**regression_metrics(test_df[TARGET],locked_pred),'Fit Time':fit_s,'Prediction Time':pred_s})
final_test=pd.DataFrame(final_rows).drop_duplicates('Model').sort_values('MAE'); display(final_test)
assert len(test_predictions)==len(test_df)==test_predictions.rental_post_id.nunique()"""),
md("## 10 Tail, segment, prediction-sanity, and largest-error diagnostics"),
code("""baseline_name='Hierarchical Segment Median'; names=list(dict.fromkeys([baseline_name,LOCKED_MODEL])); dev_p95=development_df[TARGET].quantile(.95); dev_p99=development_df[TARGET].quantile(.99)
diagnostics=[]
for name in names:
 pred=test_predictions[name]; actual=test_predictions.actual_price; ae=(actual-pred).abs(); se=(actual-pred)**2
 regions=[('Central ≤ dev P95',actual<=dev_p95)]
 if dev_p99>dev_p95: regions.append(('Upper P95–P99',(actual>dev_p95)&(actual<=dev_p99)))
 regions.append(('Extreme > dev P99',actual>dev_p99))
 for region,mask in regions:
  diagnostics.append({'Model':name,'Region':region,'Count':int(mask.sum()),'MAE':ae[mask].mean(),'RMSE':np.sqrt(se[mask].mean()),'Squared Error Contribution %':se[mask].sum()/se.sum()*100})
tail_diagnostics=pd.DataFrame(diagnostics); display(tail_diagnostics)
price_band,price_edges=unique_price_bands(development_df[TARGET],test_predictions.actual_price); _,_,area_edges=add_train_only_area_band(development_df,test_df); area_band=pd.cut(test_predictions.area_value_clean,area_edges,include_lowest=True); location_resolution=np.where(test_predictions.ward_current.notna(),'WARD_RESOLVED',np.where(test_predictions.district_text_extracted.notna(),'DISTRICT_ONLY','UNRESOLVED'))
segments=[]
segment_dimensions={'Price Band':price_band,'Source':test_predictions.source_code,'Area Band':area_band,'Location Resolution':location_resolution}
for dimension,values in segment_dimensions.items():
 for segment,idx in pd.Series(values,index=test_predictions.index).groupby(values,dropna=False,observed=False).groups.items():
  small=len(idx)<100
  base=(test_predictions.loc[idx,'actual_price']-test_predictions.loc[idx,baseline_name]).abs().mean(); ml=(test_predictions.loc[idx,'actual_price']-test_predictions.loc[idx,LOCKED_MODEL]).abs().mean()
  segments.append({'Dimension':dimension,'Segment':str(segment),'Count':len(idx),'Small Sample (<100)':small,'Baseline MAE':base,'Locked MAE':ml,'Baseline Beats Locked':base<ml})
segment_diagnostics=pd.DataFrame(segments); display(segment_diagnostics.sort_values(['Dimension','Locked MAE']))
plausible_min,plausible_max=100_000,100_000_000
sanity=pd.DataFrame([{'Model':n,'Pred Min':test_predictions[n].min(),'Pred Median':test_predictions[n].median(),'Pred P95':test_predictions[n].quantile(.95),'Pred P99':test_predictions[n].quantile(.99),'Pred Max':test_predictions[n].max(),'Actual Min':test_predictions.actual_price.min(),'Actual Max':test_predictions.actual_price.max(),'Negative':int((test_predictions[n]<0).sum()),'Zero':int((test_predictions[n]==0).sum()),'Outside 100k–100m':int(((test_predictions[n]<plausible_min)|(test_predictions[n]>plausible_max)).sum())} for n in names]); display(sanity)
largest=test_predictions.assign(predicted_price=test_predictions[LOCKED_MODEL],absolute_error=(test_predictions.actual_price-test_predictions[LOCKED_MODEL]).abs()).nlargest(25,'absolute_error'); display(largest[['rental_post_id','actual_price','predicted_price','absolute_error','source_code','area_value_clean','ward_current','district_text_extracted','title_clean']])
fig,ax=plt.subplots(figsize=(6,5)); sample=test_predictions.sample(min(5000,len(test_predictions)),random_state=SEED); limit=test_predictions.actual_price.quantile(.99); ax.scatter(sample.actual_price,sample[LOCKED_MODEL],s=8,alpha=.25); ax.plot([0,limit],[0,limit],'--'); ax.set(xlim=(0,limit),ylim=(0,limit),xlabel='Actual',ylabel='Predicted',title=f'Final TEST — {LOCKED_MODEL}'); plt.tight_layout(); plt.show()"""),
md("## 11 Locked-model feature importance and final verdict"),
code("""if LOCKED_MODEL=='LightGBM Regressor':
 feature_importance=lightgbm_gain_importance(final_model,SELECTED_FEATURES)
else:
 feature_importance=pd.DataFrame({'Feature':SELECTED_FEATURES,'Gain':np.nan,'Split Count':np.nan,'Gain %':np.nan})
display(feature_importance)
if feature_importance.Gain.notna().any():
 plot=feature_importance.sort_values('Gain'); fig,ax=plt.subplots(figsize=(8,4)); ax.barh(plot.Feature,plot.Gain,color='#4C78A8'); ax.set(title=f'Locked Candidate Gain Importance — {LOCKED_MODEL}',xlabel='Gain (descriptive, not causal)'); plt.tight_layout(); plt.show()
final_locked=final_test.loc[final_test.Model.eq(LOCKED_MODEL)].iloc[0]
baseline_metrics={name:final_test.loc[final_test.Model.eq(name)].iloc[0] for name in ['Global Median','Hierarchical Location Median','Hierarchical Segment Median']}
locked_dev=candidate_pool.loc[(candidate_pool.Model.eq(LOCKED_MODEL))&(candidate_pool.Parameters.eq(json.dumps(LOCKED_PARAMS,sort_keys=True)))].sort_values('MAE_Mean').iloc[0]
tail_locked=tail_diagnostics.loc[tail_diagnostics.Model.eq(LOCKED_MODEL)]; extreme=tail_locked.loc[tail_locked.Region.str.startswith('Extreme')].iloc[0]; central=tail_locked.loc[tail_locked.Region.str.startswith('Central')].iloc[0]
readiness='experimental/prototype-ready; not production-ready' if (locked_dev.MAE_Std/locked_dev.MAE_Mean>.15 or (model_df.latest_observed_at.max()-model_df.latest_observed_at.min()).days<30 or extreme['Squared Error Contribution %']>50) else 'production-candidate pending operational validation'
verdict=pd.DataFrame([
 ['Locked candidate',LOCKED_MODEL],['Target transform',LOCKED_TRANSFORM],['Feature set',SELECTED_FEATURE_SET],['TEST MAE',final_locked.MAE],['TEST MedianAE',final_locked['Median AE']],['TEST RMSE',final_locked.RMSE],['TEST RMSLE',final_locked.RMSLE],['TEST R²',final_locked['R²']],
 ['Improvement vs Global Median %',(baseline_metrics['Global Median'].MAE-final_locked.MAE)/baseline_metrics['Global Median'].MAE*100],['Improvement vs Location Median %',(baseline_metrics['Hierarchical Location Median'].MAE-final_locked.MAE)/baseline_metrics['Hierarchical Location Median'].MAE*100],['Improvement vs Strong Segment Median %',(baseline_metrics['Hierarchical Segment Median'].MAE-final_locked.MAE)/baseline_metrics['Hierarchical Segment Median'].MAE*100],
 ['Development MAE mean',locked_dev.MAE_Mean],['Development MAE median',locked_dev.MAE_Median],['Development MAE std',locked_dev.MAE_Std],['Source ablation degradation %',SOURCE_ABLATION_PERCENT],['Extreme-tail squared error share %',extreme['Squared Error Contribution %']],['Central-population MAE',central.MAE],['Readiness',readiness],['Limitation','~10-day short-horizon temporal evidence only']
 ],columns=['Criterion','Current Runtime Result']); display(verdict)"""),
md("## 12 Persist auditable benchmark evidence"),
code("""ARTIFACT_DIR=PROJECT_ROOT/'data'/'modeling'/'roombeacon_price_benchmark_v3'; ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
tables={'eligibility_funnel_permissive.csv':eligibility_funnel_permissive,'eligibility_funnel_strict.csv':eligibility_funnel_strict,'semantic_population_summary.csv':semantic_population_summary,'semantic_exclusion_summary.csv':semantic_exclusion_summary,'semantic_exclusion_examples.csv':semantic_exclusion_examples,'target_distribution_comparison.csv':target_distribution_comparison,'valid_high_price_examples.csv':valid_high_price_examples,'development_fold_results.csv':development_fold_results,'development_comparison.csv':development_comparison,'feature_fold_results.csv':feature_fold_results,'feature_summary.csv':feature_summary,'f4_f5_decision.csv':f45_decision,'tuning_fold_results.csv':tuning_fold_results,'tuning_summary.csv':tuning_summary,'source_ablation.csv':source_ablation,'leave_one_source_out.csv':leave_one_source_out,'unknown_sensitivity_population.csv':unknown_sensitivity_population,'unknown_sensitivity_sources.csv':unknown_sensitivity_sources,'unknown_sensitivity_fold_results.csv':unknown_sensitivity_fold_results,'unknown_sensitivity_summary.csv':unknown_sensitivity_summary,'final_test.csv':final_test,'tail_diagnostics.csv':tail_diagnostics,'segment_diagnostics.csv':segment_diagnostics,'prediction_sanity.csv':sanity,'feature_importance.csv':feature_importance,'final_verdict.csv':verdict}
for filename,table in tables.items(): table.to_csv(ARTIFACT_DIR/filename,index=False)
with duckdb.connect(':memory:') as con: con.register('_pred',test_predictions); con.execute('copy _pred to ? (format parquet)',[str(ARTIFACT_DIR/'test_predictions.parquet')])
generated_at=datetime.now(timezone.utc).astimezone().isoformat()
metadata={'benchmark':'roombeacon_price_benchmark_v3','generated_at':generated_at,'versions':versions,'hardware':{'platform':platform.platform(),'processor':platform.processor(),'cpu_count':__import__('os').cpu_count()},'seed':SEED,'silver_path':str(SILVER_PATH),'silver_sha256':file_sha256(SILVER_PATH),'silver_metadata':silver_metadata,'business_target_definition':BUSINESS_TARGET_DEFINITION,'semantic_eligibility_policy':'PERMISSIVE default keeps unresolved UNKNOWN absent strong conflict; STRICT is development-only sensitivity evidence','numeric_trust_policy':sorted(TRUSTED_PRICE_STATUSES),'price_model_suitability_policy':['SUPPORTED'],'area_model_suitability_policy':['SUPPORTED'],'eligible_rows':len(model_df),'numeric_untrusted_rows':int((numeric_candidate&~numeric_trusted).sum()),'intent_distribution':prepared.listing_intent.value_counts(dropna=False).to_dict(),'scope_distribution':prepared.rental_scope.value_counts(dropna=False).to_dict(),'trust_distribution':prepared.price_target_trust_status.value_counts(dropna=False).to_dict(),'price_suitability_distribution':prepared.price_model_suitability.value_counts(dropna=False).to_dict(),'area_suitability_distribution':prepared.area_model_suitability.value_counts(dropna=False).to_dict(),'split_strategy':split_result.strategy,'folds':fold_report.astype(str).to_dict('records'),'selected_feature_set':SELECTED_FEATURE_SET,'feature_names':SELECTED_FEATURES,'locked_candidate':LOCKED_MODEL,'locked_transform':LOCKED_TRANSFORM,'locked_parameters':LOCKED_PARAMS,'categorical_strategy':'LightGBM train-defined pandas categories with explicit __MISSING__/__UNKNOWN__; CatBoost native strings; sklearn fold-fitted unknown-safe encoders','selection_rule':'Development fold MAE mean/median/variability; within 1% prefer lower complexity; then MedianAE/RMSLE/runtime','historical_test_previously_observed':True,'test_used_for_current_selection':False,'readiness':readiness,'limitations':['~10-day temporal window','historical temporal test range has already been observed and is not a fresh unbiased champion-comparison window','group-level chronology uses representative max timestamp and does not claim row-level isolation','source mix is dataset representation, not market share']}
assert LOCKED_MODEL=='LightGBM Regressor' and LOCKED_TRANSFORM=='RAW' and SELECTED_FEATURE_SET=='F4 — AREA + SOURCE + LOCATION'
champion_cats=[c for c in SELECTED_FEATURES if c in CATS]
reference_matrix,_,champion_vocabularies=prepare_lightgbm_categories(development_df[SELECTED_FEATURES],development_df[SELECTED_FEATURES],champion_cats,return_vocabularies=True)
reference_predictions=inverse_target(final_model.predict(reference_matrix),LOCKED_TRANSFORM)
reference_profile=build_reference_profile(development_df,reference_predictions,target_column=TARGET,population_name='DEVELOPMENT',uses_test=False)
training_reference={'population':'DEVELOPMENT','row_count':len(development_df),'group_count':development_df.group_key.nunique(),'min_observed_at':development_df.latest_observed_at.min().isoformat(),'max_observed_at':development_df.latest_observed_at.max().isoformat(),'training_cutoff':development_df.latest_observed_at.max().isoformat(),'evidence_cutoff':silver_df.latest_observed_at.max().isoformat(),'uses_test':False,'silver_sha256':metadata['silver_sha256'],'source_snapshot_id':silver_metadata.get('source_snapshot',{}).get('snapshot_id')}
champion_metadata=persist_champion_artifact(final_model,ARTIFACT_DIR,model_family=LOCKED_MODEL,target_transform=LOCKED_TRANSFORM,feature_set=SELECTED_FEATURE_SET,feature_names=SELECTED_FEATURES,hyperparameters=LOCKED_PARAMS,random_seed=SEED,categorical_vocabularies=champion_vocabularies,training_reference=training_reference,expected_schema={'area_value_clean':'numeric','source_code':'categorical','ward_current':'categorical','district_text_extracted':'categorical'},reference_profile=reference_profile,created_at=generated_at)
metadata['training_reference']=training_reference
metadata['model_version']=champion_metadata['model_id']
metadata['champion']={'model_id':champion_metadata['model_id'],'artifact_path':champion_metadata['artifact_path'],'metadata_path':'champion_metadata.json','reference_profile_path':'champion_reference_profile.json','artifact_sha256':champion_metadata['artifact_sha256']}
(ARTIFACT_DIR/'experiment_metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
display(pd.DataFrame([{'Artifact':p.name,'Bytes':p.stat().st_size} for p in sorted(ARTIFACT_DIR.iterdir())])); display(Markdown('**Benchmark V3 complete. Candidate was locked before the one-time final TEST evaluation.**'))""")]

notebook={"cells":cells,"metadata":{"kernelspec":{"display_name":"RoomBeacon (venv)","language":"python","name":"roombeacon-venv"},"language_info":{"name":"python","version":"3.12.3"}},"nbformat":4,"nbformat_minor":5}
(ROOT/'notebooks'/'04_roombeacon_modeling.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=1),encoding='utf-8')
