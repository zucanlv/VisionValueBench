from pathlib import Path
from collections import defaultdict,Counter
import gzip,json,csv,hashlib
import numpy as np
P=Path(__file__).resolve().parent;OUT=P/'recomputed';OUT.mkdir(exist_ok=True)
SRC=P/'votes.json.gz';data=json.loads(gzip.open(SRC,'rt').read())
DIMS=['PDI','IDV','MAS','UAI','LTO','IVR'];METHODS=['scenario','image'];MODELS=['mai26flash','gptimage2','nanobanana2','flux2_upsampler','hidream_refiner','ideogram4_magic','flux2','hidream'];MAIN=MODELS[:6]
meta={'screening':{'scenario-set-960-filtered.json':json.loads((P/'scenario_screening.json').read_text())['final_sampling']}};sidlist=['cdeval_'+x for x in meta['screening']['scenario-set-960-filtered.json']['ids']];sidlist=sorted(sidlist);assert len(set(sidlist))==960
si={s:i for i,s in enumerate(sidlist)};conditions=sorted({tuple(r['id'].split('__')[2:]) for r in data['rows']});SHARED=[(l,c) for l in ['en_us','zh_cn'] for c in ['none','us','cn']]
idx={};votes={};invalid=[]
for r in data['rows']:
 m,s,l,c=r['id'].split('__');assert s in si
 v=np.asarray(r['votes'],dtype=np.int8);votes[m,s,l,c]=v;idx[m,s,l,c]=(v.sum(axis=1)>=2).reshape(2,6,2)
B=5000;rng=np.random.default_rng(20260925);W=np.zeros((B,960),dtype=np.float64)
for dim in ['pdi','idv','mas','uai','lto','ivr']:
 ii=[i for i,s in enumerate(sidlist) if s.split('_')[1]==dim];assert len(ii)==160
 W[:,ii]=rng.multinomial(160,np.ones(160)/160,size=B)
# Joint draws preserve matching across configurations, methods, dimensions and repeated conditions.
arrays=[];records=[];lookup={}
def register(model,conds,cohort,tag):
 key=(model,tuple(conds),tuple(cohort))
 if key in lookup:return lookup[key]
 a=np.zeros((960,2,6,4),dtype=np.int16)
 for s in cohort:
  for l,c in conds:
   v=idx.get((model,s,l,c))
   if v is None:continue
   st=v[:,:,0].astype(int)+2*v[:,:,1].astype(int)
   for mi in range(2):
    for di in range(6):a[si[s],mi,di,st[mi,di]]+=1
 j=len(arrays);lookup[key]=j;arrays.append(a);records.append((model,tag,len(cohort)))
 return j
profile_keys={};condition_keys={}
for m in MODELS:
 ss=sorted({s for mm,s,l,c in idx if mm==m and (l,c) in SHARED});profile_keys[m]=register(m,SHARED,ss,'pooled')
 for lc in conditions:
  ss=sorted({s for mm,s,l,c in idx if mm==m and (l,c)==lc})
  if ss:condition_keys[m,lc]=register(m,[lc],ss,'__'.join(lc))
def frozen_csv(name):
 rows=list(csv.DictReader((P/name).open()))
 for r in rows:
  r['delta']=float(r['delta']);r['n_pairs']=int(r['n_pairs'])
 return rows
old_effects=frozen_csv('paired_effects.csv')
effects={'rows':old_effects,'contrasts':list({r['id']:{k:r[k] for k in ['id','model','family','fixed','baseline','target','n_pairs']} for r in old_effects}.values())};effect_arms={};original_effect_rows=len(old_effects)
# Recover conditions from documented contrast definitions (inspect data fields rather than title parsing).
for con in effects['contrasts']:
 m=con['model'];family=con['family'];fixed=con['fixed'];base=con['baseline'];target=con['target']
 lc0=(base,fixed) if family=='language' else (fixed,base);lc1=(target,fixed) if family=='language' else (fixed,target)
 # stored labels use canonical language/condition keys
 ss=sorted({s for mm,s,l,c in idx if mm==m and (l,c)==lc0}&{s for mm,s,l,c in idx if mm==m and (l,c)==lc1})
 assert len(ss)==con['n_pairs'],(con,lc0,lc1,len(ss))
 effect_arms[con['id']]=(register(m,[lc0],ss,'paired'),register(m,[lc1],ss,'paired'),ss)
refdata={'rows':frozen_csv('refinement.csv')};refarms={}
for base,target in [('hidream','hidream_refiner'),('flux2','flux2_upsampler')]:
 ss=[s for s in sidlist if all((m,s,*lc) in idx for m in [base,target] for lc in SHARED)]
 for key,conds in [('pooled',SHARED)]+[('__'.join(lc),[lc]) for lc in SHARED]:refarms[base,key]=(register(base,conds,ss,key),register(target,conds,ss,key))
A=np.stack(arrays,axis=1);counts=A.sum(axis=0);N=counts.sum(axis=-1);U=counts[:,:,:,1:].sum(axis=-1);num=counts[:,:,:,1]-counts[:,:,:,2]
S=np.divide(num,U,out=np.full(U.shape,np.nan),where=U>0);numscene=(A[:,:,:,:,1]-A[:,:,:,:,2]).reshape(960,-1).astype(float);denscene=A[:,:,:,:,1:].sum(axis=-1).reshape(960,-1).astype(float)
print('bootstrap matrix',numscene.shape,flush=True)
bnum=W@numscene;bden=W@denscene;BOOT=np.divide(bnum,bden,out=np.full(bnum.shape,np.nan),where=bden>0).reshape(B,len(arrays),2,6)
def interval(b):
 good=np.isfinite(b);return [float(x) for x in np.quantile(b[good],[.025,.975])] if good.mean()>=.95 else [None,None]
def stats(j,mi,di):
 c=counts[j,mi,di];u=int(U[j,mi,di]);n=int(N[j,mi,di]);return dict(n=n,a_only=int(c[1]),b_only=int(c[2]),both=int(c[3]),neither=int(c[0]),supported=u,score=float(S[j,mi,di]) if u else None,prevalence=u/n if n else None)
def writecsv(name,rs):
 fields=list(dict.fromkeys(k for r in rs for k in r))
 with (OUT/name).open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rs)
 return rs
profiles=[];boots=[]
for m,j in profile_keys.items():
 for mi,method in enumerate(METHODS):
  for di,dim in enumerate(DIMS):
   lo,hi=interval(BOOT[:,j,mi,di]);profiles.append(dict(model=m,method=method,dimension=dim,**stats(j,mi,di),ci_low=lo,ci_high=hi));boots.append(BOOT[:,j,mi,di])
# Approximate simultaneous bootstrap bands, max standardized centered deviation within explicitly named families.
def simultaneous(rs,bootrows,familyfn):
 groups=defaultdict(list)
 for i,r in enumerate(rs):groups[familyfn(r)].append(i)
 for key,ii in groups.items():
  est=np.array([rs[i].get('delta',rs[i].get('score')) for i in ii],float);bb=np.array([bootrows[i] for i in ii]).T;se=np.nanstd(bb,axis=0,ddof=1);ok=np.isfinite(est)&(se>0)&(np.isfinite(bb).mean(axis=0)>=.95)
  z=np.abs((bb[:,ok]-est[ok])/se[ok]);valid=np.all(np.isfinite(z),axis=1);crit=float(np.quantile(z[valid].max(axis=1),.95)) if ok.any() else 0
  for col,i in enumerate(ii):
   r=rs[i];r['simultaneous_family']=str(key);r['family_size']=len(ii);r['simultaneous_critical']=crit
   r['sim_low']=float(est[col]-crit*se[col]) if ok[col] else None;r['sim_high']=float(est[col]+crit*se[col]) if ok[col] else None
simultaneous(profiles,boots,lambda r:(r['method'],'main' if r['model'] in MAIN else 'controls'))
writecsv('profiles.csv',profiles)
condrows=[]
for (m,lc),j in condition_keys.items():
 for mi,method in enumerate(METHODS):
  for di,dim in enumerate(DIMS):
   lo,hi=interval(BOOT[:,j,mi,di]);condrows.append(dict(model=m,language=lc[0],cue=lc[1],method=method,dimension=dim,**stats(j,mi,di),ci_low=lo,ci_high=hi))
writecsv('condition_profiles.csv',condrows)
erows=[];eboot=[]
for old in effects['rows']:
 a,b,ss=effect_arms[old['id']];mi=METHODS.index(old['method']);di=DIMS.index(old['dimension']);d=float(S[b,mi,di]-S[a,mi,di]);assert 'delta' not in old or abs(d-old['delta'])<1e-12
 boot=BOOT[:,b,mi,di]-BOOT[:,a,mi,di];lo,hi=interval(boot)
 r={k:old[k] for k in ['model','family','fixed','baseline','target','id','n_pairs','method','dimension']};r.update(delta=d,ci_low=lo,ci_high=hi)
 for arm,j in [('baseline',a),('target',b)]:r.update({arm+'_'+k:v for k,v in stats(j,mi,di).items()})
 erows.append(r);eboot.append(boot)
simultaneous(erows,eboot,lambda r:(r['method'],r['family'],r['fixed'],r['baseline'],r['target'],'main' if r['model'] in MAIN else 'controls'))
writecsv('paired_effects.csv',erows)
refrows=[];rb=[]
for old in refdata['rows']:
 base=old['base_model'];mi=METHODS.index(old['method']);di=DIMS.index(old['dimension'])
 if old['kind']=='direct':
  a,b=refarms[base,old['setting']];boot=BOOT[:,b,mi,di]-BOOT[:,a,mi,di];d=float(S[b,mi,di]-S[a,mi,di]);r={k:old[k] for k in ['base_model','refined_model','kind','setting','method','dimension','n_pairs']}
  for arm,j in [('baseline',a),('target',b)]:r.update({arm+'_'+k:v for k,v in stats(j,mi,di).items()})
 else:
  first,last={'language_none':('en_us__none','zh_cn__none'),'cue_en':('en_us__us','en_us__cn'),'cue_zh':('zh_cn__us','zh_cn__cn')}[old['setting']]
  a,b=refarms[base,first];c,e=refarms[base,last];boot=(BOOT[:,e,mi,di]-BOOT[:,b,mi,di])-(BOOT[:,c,mi,di]-BOOT[:,a,mi,di]);before=float(S[c,mi,di]-S[a,mi,di]);after=float(S[e,mi,di]-S[b,mi,di]);d=after-before;r={k:old[k] for k in ['base_model','refined_model','kind','setting','method','dimension','n_pairs']};r.update(baseline_score=before,target_score=after)
 assert abs(d-old['delta'])<1e-12
 lo,hi=interval(boot);r.update(delta=d,ci_low=lo,ci_high=hi);refrows.append(r);rb.append(boot)
simultaneous(refrows,rb,lambda r:(r['method'],r['kind'],r['setting']))
writecsv('refinement.csv',refrows)
# Coverage and sensitivity can be computed exactly from the frozen votes.
coverage=[]
for m in MODELS:
 for lc in conditions:
  present=[s for mm,s,l,c in idx if mm==m and (l,c)==lc]
  if present:coverage.append(dict(model=m,language=lc[0],cue=lc[1],design_scenarios=960,complete_images=len(present),unavailable_variants=960-len(present)))
writecsv('coverage.csv',coverage)
sensitivity=[];subsets=[];vd=[]
for m in MODELS:
 keys=[k for k in votes if k[0]==m and k[2:] in SHARED];vv=np.stack([votes[k] for k in keys]);src=np.array([k[1].split('_')[1].upper() for k in keys]);scenes=[k[1] for k in keys]
 for mi,method in enumerate(METHODS):
  for rule,sup in [('majority',vv[:,mi].sum(axis=1)>=2),('unanimous',vv[:,mi].sum(axis=1)==3),('any',vv[:,mi].sum(axis=1)>=1)]+[(j,vv[:,mi,ji].astype(bool)) for ji,j in enumerate(data['verifier_order'])]:
   sup=sup.reshape(-1,6,2);st=sup[:,:,0].astype(int)+2*sup[:,:,1].astype(int)
   for di,dim in enumerate(DIMS):
    c=np.bincount(st[:,di],minlength=4);u=int(c[1:].sum());s=float((c[1]-c[2])/u) if u else None
    sensitivity.append(dict(model=m,method=method,rule=rule,dimension=dim,n=len(st),a_only=int(c[1]),b_only=int(c[2]),both=int(c[3]),neither=int(c[0]),supported=u,score=s,prevalence=u/len(st)))
  st=(vv[:,mi].sum(axis=1)>=2).reshape(-1,6,2);states=st[:,:,0].astype(int)+2*st[:,:,1].astype(int)
  for di,dim in enumerate(DIMS):
   for label,mask in [('source',src==dim),('other',src!=dim)]:
    c=np.bincount(states[mask,di],minlength=4);u=int(c[1:].sum());subsets.append(dict(model=m,method=method,dimension=dim,subset=label,n=int(mask.sum()),supported=u,score=float((c[1]-c[2])/u) if u else None))
  for ji,j in enumerate(data['verifier_order']):
   v=vv[:,mi,ji].astype(bool);ma=vv[:,mi].sum(axis=1)>=2;op=(vv[:,mi].sum(axis=1)==1)|(vv[:,mi].sum(axis=1)==2)
   vd.append(dict(model=m,method=method,verifier=j,slots=int(v.size),supported=int(v.sum()),split_decisions=int(op.sum()),sole_dissent=int(((v!=ma)&op).sum())))
writecsv('verifier_sensitivity.csv',sensitivity);writecsv('source_stratum_sensitivity.csv',subsets);writecsv('verifier_diagnostics.csv',vd)
# All-condition final counts preserve original profile point estimates at the proper scope.
old=list(csv.DictReader((P/'profiles.csv').open()));matched=0
for r in profiles:
 o=next(x for x in old if x['model']==r['model'] and x['method']==r['method'] and x['dimension']==r['dimension']);assert abs(float(o['score'])-r['score'])<1e-12;matched+=1
qa={'source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'snapshot':data['finished_at'],'images':len(idx),'scenarios':len(si),'profile_point_estimates_matched':matched,'paired_point_estimates_matched':original_effect_rows,'new_cued_language_rows':len(erows)-original_effect_rows,'refinement_point_estimates_matched':len(refrows),'bootstrap_replicates':B,'seed':20260925,'bootstrap_unit':'Joint 960 scenario clusters, stratified by six source dimensions (160 draws each); all model/condition/method records move together. A contrast uses only available pairs in each sampled cluster.','simultaneous_bands':'95% bootstrap max absolute standardized centered deviation; main profile family=36 cells per method; contrast family=up to36 cells per method/contrast, controls separate; refinement family=12 cells per method/setting. Approximate simultaneous coverage within named family, not whole-paper coverage.','array_count':len(arrays)}
(OUT/'quantitative_qa.json').write_text(json.dumps(qa,indent=2));print(json.dumps(qa),flush=True)
