"""Q5 shared-track event library with intersection-aware outer scoring."""
from __future__ import annotations
import argparse, hashlib, itertools, json, math, platform, sys, time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from src.q3 import selection_pilot as q3  # noqa:E402

SPEC_ID="Q5-CANDIDATE-PILOT-2.0";RESULT_ID="Q5-INTERSECTION-REBIND-PILOT-WORKING-002"
EXPECTED={"data/A题.pdf":"a37f6aad30b16ea09da9cb320ce194b12d3a28874008cf9ff19549f6c6079447","data/附件/result3.xlsx":"b648c82d63e459ba6e6b3711ae79875e373521cd543b45571c4d8ff1ad5ec54a","planning/28_q5_scope_problem_and_evidence_plan.md":"3debeb5f008d22de4348b3ac2b946fd2f0edef2d847ca51562ecc1921a4af9c8","planning/29_q5_candidate_set.md":"7bd9e9bf826e8f2dfb6adc208c39de28a82ce2feba0d7972eb22f1946686698f"}
MN=("M1","M2","M3");UN=("FY1","FY2","FY3","FY4","FY5")
MISSILES=np.array([[20000.,0.,2000.],[19000.,600.,2100.],[18000.,-600.,1900.]])
ORIGINS=np.array([[17800.,0.,1800.],[12000.,1400.,1400.],[6000.,-3000.,700.],[11000.,2000.,1800.],[13000.,-2000.,1300.]])
AGES=(0.,.5,1.5,3.,6.,10.,15.);FRACS=(.08,.18,.32,.48,.65,.82,.94)
PSTEP=.1;SSTEP=.1;TRACK_LIMIT=20;EVENT_LIMIT=10;PLAN_LIMIT=24;COMBO_LIMIT=80;BEAM_WIDTHS=(24,160,480,960,1600);TOL=1e-9

class PilotError(RuntimeError):
    def __init__(self,code,message):super().__init__(message);self.code=code
@dataclass(frozen=True)
class Event:
    platform:int;label:int;heading:float;speed:float;observation:float;age:float;fraction:float;release:float;fuse:float;explosion:float;height:float;source:str
@dataclass(frozen=True)
class Track:
    platform:int;heading:float;speed:float;source_label:int;anchor:Event
@dataclass
class Plan:
    platform:int;track:Track;events:tuple[Event,...];masks:tuple[np.ndarray,np.ndarray,np.ndarray];intersection:float;score:float;minimum:float;pattern:tuple[int,...]

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def ready(v):
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    if isinstance(v,dict):return {k:ready(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [ready(x) for x in v]
    return v
def p():return q3.base_parameters()
def arrival(j):return float(np.linalg.norm(MISSILES[j])/p().missile_speed)
def missile(j,t):
    x=np.asarray(t,float);return (1-p().missile_speed*x/np.linalg.norm(MISSILES[j]))[...,None]*MISSILES[j]
def target():return p().target_base_center+np.array([0.,0.,.5*p().target_height])

def anchor(i,j,t,age,fraction):
    et=t-age
    if not 0<et<=t<arrival(j):return None
    m=missile(j,t);g=m+fraction*(target()-m);ez=float(g[2]+p().smoke_sink_speed*age)
    if not 0<=ez<=ORIGINS[i,2]:return None
    fuse=math.sqrt(max(0,2*(ORIGINS[i,2]-ez)/p().gravity));release=et-fuse
    if release<-TOL:return None
    d=g[:2]-ORIGINS[i,:2];speed=float(np.linalg.norm(d)/et)
    if not 70<=speed<=140:return None
    heading=float(math.atan2(d[1],d[0])%(2*math.pi))
    return Event(i,j,heading,speed,t,age,fraction,max(0.,release),fuse,et,ez,"anchor")
def curve(track,j,t):
    m=missile(j,t);sight=target()[:2]-m[:2];d=np.array([math.cos(track.heading),math.sin(track.heading)])
    a=np.column_stack((track.speed*d,-sight))
    if abs(np.linalg.det(a))<1e-9:return None
    et,fraction=np.linalg.solve(a,m[:2]-ORIGINS[track.platform,:2]);et,fraction=float(et),float(fraction);age=t-et
    if not 0<fraction<1 or not 0<=age<=p().smoke_duration or not 0<et<=t:return None
    g=m+fraction*(target()-m);ez=float(g[2]+p().smoke_sink_speed*age)
    if not 0<=ez<=ORIGINS[track.platform,2]:return None
    fuse=math.sqrt(max(0,2*(ORIGINS[track.platform,2]-ez)/p().gravity));release=et-fuse
    if release<-TOL:return None
    return Event(track.platform,j,track.heading,track.speed,t,age,fraction,max(0.,release),fuse,et,ez,"curve")
def explosion(e):
    d=np.array([math.cos(e.heading),math.sin(e.heading),0.]);x=ORIGINS[e.platform]+e.speed*e.explosion*d;x[2]=e.height;return x
def clouds(e,times):
    x=np.repeat(explosion(e).reshape(1,3),len(times),axis=0);x[:,2]-=p().smoke_sink_speed*(times-e.explosion);return x
def proxy_masks(e,times):
    centers=clouds(e,times);active=(times>=e.explosion-TOL)&(times<=e.explosion+p().smoke_duration+TOL);out=[];outer=math.hypot(p().target_radius,.5*p().target_height)
    for j in range(3):
        ms=missile(j,times);v=target()-ms;lam=np.clip(np.einsum("ij,ij->i",centers-ms,v)/np.einsum("ij,ij->i",v,v),0,1);near=ms+lam[:,None]*v
        out.append(active&(times<=arrival(j)+TOL)&(np.linalg.norm(centers-near,axis=1)+lam*outer-p().smoke_radius<=0))
    return tuple(out)

def tracks(i,times):
    raw={};generated=0
    for j in range(3):
      for t in np.arange(.5,arrival(j),1.):
       for age in AGES:
        if age>=t:continue
        for f in FRACS:
         e=anchor(i,j,float(t),age,f)
         if e is None:continue
         generated+=1;m=proxy_masks(e,times);score=(int(np.sum(m[j])),int(sum(np.sum(x) for x in m)));k=(round(e.heading/.001),round(e.speed/.25));tr=Track(i,e.heading,e.speed,j,e)
         if k not in raw or score>raw[k][1]:raw[k]=(tr,score)
    if not raw:raise PilotError("Q5_TRAJECTORY_ANCHOR_EMPTY",UN[i])
    # If the registered (t, age, q) anchors undersample a narrow reachable
    # corridor, add deterministic heading-speed guards through the same 2x2
    # service-curve inversion.  They are coverage seeds, not another solver.
    guard_count=0
    if len(raw)<TRACK_LIMIT:
     seed=next(iter(raw.values()))[0].anchor
     for j in range(3):
      centres=(math.atan2(target()[1]-ORIGINS[i,1],target()[0]-ORIGINS[i,0]),math.atan2(MISSILES[j,1]-ORIGINS[i,1],MISSILES[j,0]-ORIGINS[i,0]))
      for centre in centres:
       for offset in np.linspace(-.35,.35,15):
        for speed in np.linspace(70.,140.,8):
         heading=float((centre+offset)%(2*math.pi));trial=Track(i,heading,float(speed),j,seed);best=None
         for t in np.arange(.25,arrival(j),.5):
          e=curve(trial,j,float(t))
          if e is None:continue
          m=proxy_masks(e,times);score=(int(np.sum(m[j])),int(sum(np.sum(x) for x in m)))
          if best is None or score>best[1]:best=(e,score)
         if best is not None:
          e,score=best;tr=Track(i,e.heading,e.speed,j,e);k=(round(e.heading/.001),round(e.speed/.25));guard_count+=1
          if k not in raw or score>raw[k][1]:raw[k]=(tr,score)
    ordered=sorted(raw.values(),key=lambda x:x[1],reverse=True);chosen={}
    for j in range(3):
     for tr,_ in [x for x in ordered if x[0].source_label==j][:4]:chosen[(round(tr.heading/.001),round(tr.speed/.25))]=tr
    for tr,_ in ordered:
     chosen[(round(tr.heading/.001),round(tr.speed/.25))]=tr
     if len(chosen)>=TRACK_LIMIT:break
    result=list(chosen.values())[:TRACK_LIMIT]
    return result,{"platform":UN[i],"raw_anchor_count":generated,"guard_track_count":guard_count,"unique_track_count":len(raw),"selected_track_count":len(result)}
def event_items(tr,times):
    candidates=[tr.anchor]
    for j in range(3):candidates.extend(e for e in (curve(tr,j,float(t)) for t in np.arange(.25,arrival(j),.5)) if e is not None)
    raw={}
    for e in candidates:
     masks=proxy_masks(e,times);item={"event":e,"masks":masks,"own":int(np.sum(masks[e.label])),"total":int(sum(np.sum(x) for x in masks))};k=(e.label,round(e.release/.05),round(e.fuse/.05))
     if k not in raw or (item["own"],item["total"])>(raw[k]["own"],raw[k]["total"]):raw[k]=item
    selected=[]
    for j in range(3):selected.extend(sorted((x for x in raw.values() if x["event"].label==j),key=lambda x:(x["own"],x["total"]),reverse=True)[:EVENT_LIMIT])
    return selected,{"raw_event_count":len(candidates),"unique_event_count":len(raw),"selected_event_count":len(selected)}
def make_plan(tr,items):
    events=tuple(sorted((x["event"] for x in items),key=lambda e:e.release));masks=tuple(np.logical_or.reduce([x["masks"][j] for x in items]) for j in range(3));counts=[int(np.sum(x)) for x in masks]
    common=int(np.sum(np.logical_and.reduce(masks)))
    return Plan(tr.platform,tr,events,masks,common*PSTEP,sum(counts)*PSTEP,min(counts)*PSTEP,tuple(e.label for e in events))
def track_plans(tr,items):
    same=[];mixed=[]
    for size in (1,2,3):
     for c in itertools.combinations(items,size):
      ev=sorted((x["event"] for x in c),key=lambda e:e.release)
      if any(b.release-a.release<1-TOL for a,b in zip(ev[:-1],ev[1:])):continue
      plan=make_plan(tr,c);mixed.append(plan)
      if len(set(plan.pattern))==1:same.append(plan)
    def shortlist(values,limit):
     out=[];seen=set();quota=max(1,limit//3)
     orders=(lambda x:(x.intersection,x.minimum,x.score,len(x.events)),lambda x:(x.minimum,x.score,x.intersection,len(x.events)),lambda x:(x.score,x.minimum,x.intersection,len(x.events)))
     for key in orders:
      for x in sorted(values,key=key,reverse=True)[:quota]:
       sig=tuple((round(e.release,6),round(e.fuse,6),e.label) for e in x.events)
       if sig not in seen:out.append(x);seen.add(sig)
     for x in sorted(values,key=orders[0],reverse=True):
      sig=tuple((round(e.release,6),round(e.fuse,6),e.label) for e in x.events)
      if sig not in seen:out.append(x);seen.add(sig)
      if len(out)>=limit:break
     return out[:limit]
    return shortlist(same,12),shortlist(mixed,18)
def platform_plans(i,trs,times):
    same=[];mixed=[];stats=[]
    for tr in trs:
     items,s=event_items(tr,times);stats.append(s);a,b=track_plans(tr,items);same.extend(a);mixed.extend(b)
    if not same or not mixed:raise PilotError("Q5_EVENT_LIBRARY_EMPTY",UN[i])
    def select(values):
     out=[];seen=set();quota=max(1,PLAN_LIMIT//4)
     orders=(lambda x:(x.intersection,x.minimum,x.score,len(x.events)),lambda x:(x.minimum,x.score,x.intersection,len(x.events)),lambda x:(x.score,x.minimum,x.intersection,len(x.events)))
     for key in orders:
      for x in sorted(values,key=key,reverse=True)[:quota]:
       k=(round(x.track.heading/.002),round(x.track.speed/.5),x.pattern,tuple(round(e.release/.25) for e in x.events))
       if k not in seen:out.append(x);seen.add(k)
     for x in sorted(values,key=orders[0],reverse=True):
      k=(round(x.track.heading/.002),round(x.track.speed/.5),x.pattern,tuple(round(e.release/.25) for e in x.events))
      if k not in seen:out.append(x);seen.add(k)
      if len(out)>=PLAN_LIMIT:break
     return out[:PLAN_LIMIT]
    a=select(same);b=select(mixed+same)
    return a,b,{"platform":UN[i],"raw_same":len(same),"raw_mixed":len(mixed),"selected_same":len(a),"selected_mixed":len(b),"events":stats}
def combine(libraries):
    length=len(libraries[0][0].masks[0]);zero=tuple(np.zeros(length,dtype=bool) for _ in range(3));states=[{"plans":(),"masks":zero,"proxy_intersection":0.,"proxy":0.,"proxy_min":0.,"ordinal":0}];ordinal=0
    for level,library in enumerate(libraries):
     expanded=[]
     for state in states:
      for plan in library:
       masks=tuple(np.logical_or(state["masks"][j],plan.masks[j]) for j in range(3));counts=[int(np.sum(x)) for x in masks];common=int(np.sum(np.logical_and.reduce(masks)));ordinal+=1
       expanded.append({"plans":state["plans"]+(plan,),"masks":masks,"proxy_intersection":common*PSTEP,"proxy":sum(counts)*PSTEP,"proxy_min":min(counts)*PSTEP,"ordinal":ordinal})
     width=BEAM_WIDTHS[min(level,len(BEAM_WIDTHS)-1)];ranked=sorted(expanded,key=lambda x:(x["proxy_intersection"],x["proxy_min"],x["proxy"],-x["ordinal"]),reverse=True);chosen=ranked[:max(1,int(.75*width))];seen={(tuple(p.pattern for p in x["plans"]),tuple(round(np.mean([e.release for e in p.events])/.5) for p in x["plans"])) for x in chosen}
     for x in ranked[len(chosen):]:
      key=(tuple(p.pattern for p in x["plans"]),tuple(round(np.mean([e.release for e in p.events])/.5) for p in x["plans"]))
      if key not in seen:chosen.append(x);seen.add(key)
      if len(chosen)>=width:break
     states=chosen[:width]
    return [{k:v for k,v in x.items() if k!="masks"} for x in sorted(states,key=lambda x:(x["proxy_intersection"],x["proxy_min"],x["proxy"],-x["ordinal"]),reverse=True)[:COMBO_LIMIT]]
def events(candidate):return tuple(e for x in candidate["plans"] for e in x.events)

def margins(evs,j,times,mesh):
    ms=missile(j,times);visible=q3.visibility_mask(ms,mesh);best=np.full((len(times),len(mesh.points)),np.inf)
    for e in evs:
     active=(times>=e.explosion-TOL)&(times<=min(e.explosion+p().smoke_duration,arrival(j))+TOL)
     if np.any(active):
      d=q3._distance_to_segments(clouds(e,times),ms,mesh);d[~active]=np.inf;best=np.minimum(best,d)
    value=best-p().smoke_radius;value[~visible]=-np.inf;out=np.max(value,axis=1);out[~np.any(visible,axis=1)]=np.inf;return out
def intervals(evs,j,mesh):
    windows=q3.merge_intervals([[e.explosion,min(e.explosion+p().smoke_duration,arrival(j))] for e in evs if e.explosion<=arrival(j)]);values=[]
    for a,b in windows:values.extend(np.linspace(a,b,max(1,math.ceil((b-a)/SSTEP))+1))
    grid=np.array(sorted(set(float(t) for t in values)))
    if not len(grid):return {"intervals_s":[],"duration_s":0.,"scan_count":0,"minimum_margin_m":math.inf}
    ms=margins(evs,j,grid,mesh);inside=ms<=0
    def root(a,b):
     fa=float(margins(evs,j,np.array([a]),mesh)[0]);fb=float(margins(evs,j,np.array([b]),mesh)[0])
     if not math.isfinite(fa) or not math.isfinite(fb) or fa*fb>0:return a if fa<=0 else b
     for _ in range(40):
      c=(a+b)/2;fc=float(margins(evs,j,np.array([c]),mesh)[0])
      if b-a<=2e-6:return c
      if fa*fc<=0:b,fb=c,fc
      else:a,fa=c,fc
     return (a+b)/2
    found=[];k=0;gap=SSTEP*1.01
    while k<len(grid):
     if not inside[k]:k+=1;continue
     first=k
     while k+1<len(grid) and inside[k+1] and grid[k+1]-grid[k]<=gap:k+=1
     last=k;a=float(grid[first]) if first==0 or grid[first]-grid[first-1]>gap else root(float(grid[first-1]),float(grid[first]));b=float(grid[last]) if last==len(grid)-1 or grid[last+1]-grid[last]>gap else root(float(grid[last]),float(grid[last+1]));found.append([a,b]);k+=1
    merged=q3.merge_intervals(found);return {"intervals_s":merged,"duration_s":q3.interval_measure(merged),"scan_count":len(grid),"minimum_margin_m":float(np.min(ms))}
def intersect_intervals(groups):
    if any(not x for x in groups):return []
    idx=[0,0,0];out=[]
    while all(idx[j]<len(groups[j]) for j in range(3)):
     current=[groups[j][idx[j]] for j in range(3)];left=max(x[0] for x in current);right=min(x[1] for x in current)
     if right-left>TOL:out.append([left,right])
     for j in range(3):
      if current[j][1]<=right+TOL:idx[j]+=1
    return q3.merge_intervals(out)
def strict(candidate,mesh):
    evs=events(candidate);by=[intervals(evs,j,mesh) for j in range(3)];ds=[x["duration_s"] for x in by];common=intersect_intervals([x["intervals_s"] for x in by]);return {"plans":candidate["plans"],"proxy_intersection":candidate.get("proxy_intersection",0.),"proxy":candidate["proxy"],"proxy_min":candidate["proxy_min"],"by":by,"durations":ds,"intersection_intervals_s":common,"objective":q3.interval_measure(common),"sum_duration_missile_s":float(sum(ds))}
def event_record(e):
    r=asdict(e);r["platform"]=UN[e.platform];r["label"]=MN[e.label];r["heading_deg"]=math.degrees(e.heading)%360;d=np.array([math.cos(e.heading),math.sin(e.heading),0.]);r["release_point_m"]=(ORIGINS[e.platform]+e.speed*e.release*d).tolist();r["explosion_point_m"]=explosion(e).tolist();return r
def final_record(x,mesh):
    evs=events(x);label_only=[]
    for j in range(3):
     subset=tuple(e for e in evs if e.label==j);label_only.append(intervals(subset,j,mesh)["duration_s"] if subset else 0.)
    gaps=[b.release-a.release for plan in x["plans"] for a,b in zip(plan.events[:-1],plan.events[1:])]
    raw_cross=float(x["sum_duration_missile_s"]-sum(label_only))
    return {"objective_s":x["objective"],"intersection_intervals_s":x["intersection_intervals_s"],"sum_duration_missile_s":x["sum_duration_missile_s"],"durations_s":x["durations"],"by_missile":x["by"],"proxy_intersection_s":x.get("proxy_intersection",0.),"proxy_score_missile_s":x["proxy"],"active_bomb_count":len(evs),"minimum_release_gap_s":min(gaps) if gaps else None,"label_only_durations_s":label_only,"cross_label_gain_raw_missile_s":raw_cross,"cross_label_gain_missile_s":max(0.,raw_cross),"cross_label_monotonicity_within_tolerance":raw_cross>=-5e-6,"platforms":[{"platform":UN[z.platform],"heading_rad":z.track.heading,"heading_deg":math.degrees(z.track.heading)%360,"speed_mps":z.track.speed,"label_pattern":[MN[j] for j in z.pattern],"events":[event_record(e) for e in z.events]} for z in x["plans"]]}

def run(output):
    started=time.perf_counter();identities={k:sha(ROOT/k) for k in EXPECTED};bad={k:(EXPECTED[k],identities[k]) for k in EXPECTED if EXPECTED[k]!=identities[k]}
    if bad:raise PilotError("Q5_IDENTITY_MISMATCH",str(bad))
    pt=np.arange(0,max(arrival(j) for j in range(3))+PSTEP/2,PSTEP);track_lib=[];track_stats=[]
    for i in range(5):x,s=tracks(i,pt);track_lib.append(x);track_stats.append(s)
    same=[];mixed=[];plan_stats=[]
    for i in range(5):a,b,s=platform_plans(i,track_lib[i],pt);same.append(a);mixed.append(b);plan_stats.append(s)
    sc=combine(same);mc=combine(mixed);mesh=q3.surface_mesh(64,7);ss=[strict(x,mesh) for x in sc];ss.sort(key=lambda x:(x["objective"],x["sum_duration_missile_s"]),reverse=True);base=ss[0]
    mc.append({"plans":base["plans"],"proxy_intersection":base.get("proxy_intersection",0.),"proxy":base["proxy"],"proxy_min":base["proxy_min"],"ordinal":-1});ms=[strict(x,mesh) for x in mc];ms.sort(key=lambda x:(x["objective"],x["sum_duration_missile_s"]),reverse=True);best=ms[0]
    if best["objective"]+1e-8<base["objective"]:raise PilotError("Q5_MIXED_DOMINANCE_FAILURE","embedded baseline lost")
    result={"schema_version":"2.0","spec_id":SPEC_ID,"result_id":RESULT_ID,"status":"working_selection_evidence","generated_at":datetime.now(timezone.utc).isoformat(),"objective":"measure of the intersection of the three per-missile strict obscuration sets","pilot_role":"budget and coverage diagnostic, not formal Q5 result","budget":{"proxy_step_s":PSTEP,"strict_step_s":SSTEP,"surface_n_theta":64,"surface_n_levels":7,"track_limit":TRACK_LIMIT,"events_per_label":EVENT_LIMIT,"plans_per_platform":PLAN_LIMIT,"strict_combination_limit":COMBO_LIMIT,"beam_widths":BEAM_WIDTHS},"generation":{"tracks":track_stats,"plans":plan_stats,"same_strict_count":len(ss),"mixed_strict_count":len(ms)},"same_primary_best":final_record(base,mesh),"mixed_primary_best":final_record(best,mesh),"comparison":{"mixed_minus_same_objective_s":best["objective"]-base["objective"],"finite_library_dominance_pass":best["objective"]+1e-8>=base["objective"],"selected_architecture":"trajectory-conditioned mixed-primary event scheduling with intersection outer score","single_primary_role":"embedded allocation baseline and seed","direct_40d_role":"coverage guard and post-selection refinement only"},"identity":identities,"software":{"python":platform.python_version(),"numpy":np.__version__},"elapsed_s":time.perf_counter()-started,"claims":{"formal_solution":False,"global_optimality":False,"labels_filter_physical_clouds":False,"all_three_missiles_positive_required":False}}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(ready(result),ensure_ascii=False,indent=2),encoding="utf-8");return result
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,default=ROOT/"docs/q5_selection_pilot.json");a=parser.parse_args()
    try:r=run(a.output.resolve())
    except PilotError as e:print(json.dumps({"status":"fail","code":e.code,"message":str(e)},ensure_ascii=False));return 2
    print(json.dumps({"status":"pass","same_primary_s":r["same_primary_best"]["objective_s"],"mixed_primary_s":r["mixed_primary_best"]["objective_s"],"elapsed_s":r["elapsed_s"]},ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
