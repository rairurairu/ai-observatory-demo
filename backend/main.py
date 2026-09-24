from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import csv, io, json
from fastapi import FastAPI, Depends, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Annotation, Brand, BrandAlias, BrandObservation, ExecutionLog, Experiment, ExperimentRun, ExtractionRun, LLMResponse, Model, Prompt
from backend.services import init_db, seed_demo, seed_reference_catalog, demo_run, live_run, response_dict, analytics, DOMAINS, uid
from backend.llm_adapters import available_live_models, configured_providers, ADAPTERS
from backend.config import APP_MODE

@asynccontextmanager
async def lifespan(_app):
    init_db(); seed_reference_catalog()
    if APP_MODE=="demo": seed_demo()
    yield

app=FastAPI(title="AI Observatory API",description="Research platform for studying brand recommendations. Demo observations are synthetic.",version="1.0.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

class PromptIn(BaseModel): text:str=Field(min_length=8,max_length=1000); domain:str
class ExperimentIn(BaseModel):
    name:str=Field(min_length=2,max_length=200); description:str=""; domain:str
    model_ids:list[str]=Field(min_length=1); prompt_ids:list[str]=Field(min_length=1); repetitions:int=Field(default=1,ge=1,le=50)
    mode:str="live"; search_enabled:bool=False
class AnnotationIn(BaseModel): observation_id:str; sentiment:str|None=None; rank:int|None=None; note:str=""
class RunIn(BaseModel): confirm_live_cost_unavailable:bool=False
class BrandAliasesIn(BaseModel): aliases:list[str]=Field(max_length=40)

@app.get("/health")
def health(db:Session=Depends(get_db)): return {"status":"ok","database":"connected","responses":db.scalar(select(func.count(LLMResponse.id))) or 0}
@app.get("/api/overview")
def overview(source:str="live",domain:str|None=None,model:str|None=None,start:datetime|None=None,end:datetime|None=None,brand_id:str|None=None,db:Session=Depends(get_db)):
    return analytics(db,source,domain,model,start,end,brand_id)
@app.get("/api/domains")
def domains(db:Session=Depends(get_db)):
    return [{"name":name,"brand_count":db.scalar(select(func.count(Brand.id)).where(Brand.domain==name)) or 0,"prompt_count":db.scalar(select(func.count(Prompt.id)).where(Prompt.domain==name,Prompt.is_custom==True)) or 0} for name in DOMAINS]
@app.get("/api/brands")
def brands(domain:str|None=None,db:Session=Depends(get_db)):
    q=select(Brand).order_by(Brand.domain,Brand.canonical_name)
    if domain:q=q.where(Brand.domain==domain)
    return [{"id":b.id,"name":b.canonical_name,"domain":b.domain,"aliases":b.aliases,"products":b.products} for b in db.scalars(q)]
@app.put("/api/brands/{brand_id}/aliases")
def update_aliases(brand_id:str,body:BrandAliasesIn,db:Session=Depends(get_db)):
    b=db.get(Brand,brand_id)
    if not b:raise HTTPException(404,"Brand not found")
    aliases=list(dict.fromkeys(a.strip() for a in body.aliases if a.strip() and a.strip().lower()!=b.canonical_name.lower()))
    b.aliases=aliases
    for record in db.scalars(select(BrandAlias).where(BrandAlias.brand_id==brand_id)).all():db.delete(record)
    db.flush()
    for alias in aliases:db.add(BrandAlias(id=uid("alias"),brand_id=brand_id,alias=alias))
    db.commit()
    return {"id":b.id,"name":b.canonical_name,"aliases":b.aliases,"note":"Historical raw responses and extraction rows were preserved."}
@app.get("/api/models")
def models(mode:str|None=None,db:Session=Depends(get_db)):
    mode=mode or APP_MODE
    if mode=="demo" and APP_MODE=="demo": return [{"id":m.id,"name":m.display_name,"provider":m.provider,"data_source":m.data_source} for m in db.scalars(select(Model).where(Model.data_source=="demo").order_by(Model.display_name))]
    if mode!="live":raise HTTPException(400,"Only live provider models are available")
    for provider,model_id,label in available_live_models():
        mid=f"live:{provider}:{model_id}"; m=db.get(Model,mid)
        if not m: m=Model(id=mid,provider=provider,display_name=label,model_id=model_id,data_source="live");db.add(m);db.commit()
    return [{"id":m.id,"name":m.display_name,"provider":m.provider,"data_source":m.data_source} for m in db.scalars(select(Model).where(Model.data_source=="live").order_by(Model.display_name))]
@app.get("/api/providers")
def providers():
    return {"configured":configured_providers(),"models":[{"provider":provider,"id":model_id,"name":label} for provider,model_id,label in available_live_models()],"search_supported":False,"pricing_configured":False}
@app.get("/api/prompts")
def prompts(domain:str|None=None,db:Session=Depends(get_db)):
    q=select(Prompt).where(Prompt.is_custom==True).order_by(Prompt.domain,Prompt.id)
    if domain:q=q.where(Prompt.domain==domain)
    if APP_MODE=="demo": q=select(Prompt).order_by(Prompt.domain,Prompt.id)
    return [{"id":p.id,"text":p.text,"domain":p.domain,"group_id":p.group_id,"variant":p.variant,"custom":p.is_custom} for p in db.scalars(q)]
@app.post("/api/prompts")
def create_prompt(body:PromptIn,db:Session=Depends(get_db)):
    if body.domain not in DOMAINS: raise HTTPException(400,"Unsupported domain")
    p=Prompt(id=uid("prompt"),text=body.text,domain=body.domain,is_custom=True,variant="custom")
    db.add(p);db.commit();return {"id":p.id,"text":p.text,"domain":p.domain,"custom":True}
@app.get("/api/experiments")
def experiments(mode:str|None=None,db:Session=Depends(get_db)):
    selected_mode=mode or APP_MODE
    return [{"id":e.id,"name":e.name,"domain":e.domain,"mode":e.mode,"status":e.status,"created_at":e.created_at.isoformat() if e.created_at else None} for e in db.scalars(select(Experiment).where(Experiment.mode==selected_mode).order_by(desc(Experiment.created_at)))]
@app.post("/api/experiments")
def create_experiment(body:ExperimentIn,db:Session=Depends(get_db)):
    if body.domain not in DOMAINS:raise HTTPException(400,"Unsupported consumer domain")
    if body.mode not in ({"live","demo"} if APP_MODE=="demo" else {"live"}):raise HTTPException(400,"Only live provider experiments are supported")
    if any(not db.get(Model,m) for m in body.model_ids):raise HTTPException(400,"Unknown model")
    expected=body.mode
    if any(db.get(Model,m).data_source!=expected for m in body.model_ids):raise HTTPException(400,"Do not mix provider and demo models")
    if body.mode=="live" and body.search_enabled:raise HTTPException(400,"Search-enabled execution is not currently exposed by these provider adapters")
    if any(not db.get(Prompt,p) or db.get(Prompt,p).domain!=body.domain for p in body.prompt_ids):raise HTTPException(400,"Prompt must exist and match selected domain")
    e=Experiment(id=uid("exp"),name=body.name,description=body.description,domain=body.domain,mode=body.mode,config={"model_ids":body.model_ids,"prompt_ids":body.prompt_ids,"repetitions":body.repetitions,"search_enabled":body.search_enabled,"version":1},status="created")
    db.add(e);db.commit();return {"id":e.id,"status":e.status,"planned_requests":len(body.model_ids)*len(body.prompt_ids)*body.repetitions}
@app.get("/api/experiments/{experiment_id}")
def experiment_detail(experiment_id:str,db:Session=Depends(get_db)):
    e=db.get(Experiment,experiment_id)
    if not e:raise HTTPException(404,"Experiment not found")
    runs=db.scalars(select(ExperimentRun).where(ExperimentRun.experiment_id==e.id).order_by(desc(ExperimentRun.started_at))).all()
    return {"id":e.id,"name":e.name,"description":e.description,"domain":e.domain,"mode":e.mode,"status":e.status,"config":e.config,"runs":[{"id":r.id,"status":r.status,"planned":r.planned,"completed":r.completed,"failed":r.failed,"started_at":r.started_at.isoformat() if r.started_at else None} for r in runs]}
@app.post("/api/experiments/{experiment_id}/run")
def run_experiment(experiment_id:str,body:RunIn=RunIn(),db:Session=Depends(get_db)):
    e=db.get(Experiment,experiment_id)
    if not e:raise HTTPException(404,"Experiment not found")
    if e.mode=="demo":
        if APP_MODE!="demo":raise HTTPException(400,"Demo execution is disabled; use a live provider experiment")
        run=demo_run(db,e)
    else:
        if not body.confirm_live_cost_unavailable:raise HTTPException(400,"Live requests may incur provider charges. Pricing is not configured; explicit confirmation is required.")
        for mid in e.config["model_ids"]:
            model=db.get(Model,mid)
            if not configured_providers().get(model.provider):raise HTTPException(400,f"Missing {model.provider} API key")
        run=live_run(db,e)
    finished_at=run.completed_at;started_at=run.started_at
    if finished_at and started_at:
        if finished_at.tzinfo is None:finished_at=finished_at.replace(tzinfo=timezone.utc)
        if started_at.tzinfo is None:started_at=started_at.replace(tzinfo=timezone.utc)
    duration_ms=(finished_at-started_at).total_seconds()*1000 if finished_at and started_at else None
    run_responses=db.scalars(select(LLMResponse).where(LLMResponse.run_id==run.id)).all(); per_model={}
    for response in run_responses:
        slot=per_model.setdefault(response.model_id,{"completed":0,"failed":0,"excluded":0})
        slot["completed" if response.execution_status=="success" else "excluded" if response.execution_status=="excluded" else "failed"]+=1
    model_completion=[{"model_id":mid,"model":db.get(Model,mid).display_name if db.get(Model,mid) else mid,**counts} for mid,counts in per_model.items()]
    return {"run_id":run.id,"status":run.status,"planned":run.planned,"completed":run.completed,"failed":run.failed,"duration_ms":duration_ms,"model_completion":model_completion}
@app.get("/api/experiments/{experiment_id}/results")
def results(experiment_id:str,limit:int=Query(500,le=2000),db:Session=Depends(get_db)):
    if not db.get(Experiment,experiment_id):raise HTTPException(404,"Experiment not found")
    rows=db.scalars(select(LLMResponse).where(LLMResponse.experiment_id==experiment_id).order_by(desc(LLMResponse.timestamp)).limit(limit)).all()
    return [response_dict(r,db) for r in rows]
@app.get("/api/experiments/{experiment_id}/export")
def export_experiment(experiment_id:str,format:str="json",db:Session=Depends(get_db)):
    e=db.get(Experiment,experiment_id)
    if not e:raise HTTPException(404,"Experiment not found")
    rows=db.scalars(select(LLMResponse).where(LLMResponse.experiment_id==e.id).order_by(LLMResponse.timestamp)).all()
    records=[response_dict(r,db) for r in rows]
    versions=sorted({v for v in db.scalars(select(ExtractionRun.pipeline_version).join(LLMResponse,LLMResponse.id==ExtractionRun.response_id).where(LLMResponse.experiment_id==e.id))})
    model_names=[{"id":mid,"name":db.get(Model,mid).display_name if db.get(Model,mid) else mid} for mid in e.config.get("model_ids",[])]
    prompt_defs=[db.get(Prompt,pid) for pid in e.config.get("prompt_ids",[])]
    metadata={"exported_at":datetime.now(timezone.utc).isoformat(),"data_source":e.mode,"experiment_id":e.id,"experiment_name":e.name,"domain":e.domain,"configuration":e.config,"selected_models":model_names,"selected_prompts":[{"id":p.id,"text":p.text,"version":p.version} for p in prompt_defs if p],"date_range":{"start":rows[0].timestamp.isoformat() if rows else None,"end":rows[-1].timestamp.isoformat() if rows else None},"extraction_pipeline_versions":versions}
    if format.lower()=="json":
        from fastapi.responses import JSONResponse
        return JSONResponse({"metadata":metadata,"responses":records},headers={"Content-Disposition":f"attachment; filename={e.id}-snapshot.json"})
    if format.lower()=="csv":
        stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=["response_id","experiment_id","run_id","prompt_id","prompt","model_id","model","timestamp","data_source","execution_status","response_text","token_usage","observations"],extrasaction="ignore");writer.writeheader()
        for r in records:writer.writerow({"response_id":r["id"],**r,"token_usage":json.dumps(r["token_usage"]),"observations":json.dumps(r["observations"],ensure_ascii=False)})
        return Response(stream.getvalue(),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename={e.id}-responses.csv"})
    raise HTTPException(400,"format must be json or csv")
@app.get("/api/runs/{run_id}")
def run_detail(run_id:str,db:Session=Depends(get_db)):
    r=db.get(ExperimentRun,run_id)
    if not r:raise HTTPException(404,"Run not found")
    return {"id":r.id,"status":r.status,"planned":r.planned,"completed":r.completed,"failed":r.failed,"started_at":r.started_at.isoformat()}
@app.get("/api/responses")
def responses(source:str="live",model:str|None=None,domain:str|None=None,brand_id:str|None=None,search:str|None=None,start:datetime|None=None,end:datetime|None=None,limit:int=Query(100,le=500),offset:int=0,db:Session=Depends(get_db)):
    q=select(LLMResponse).where(LLMResponse.data_source==source)
    if model:q=q.where(LLMResponse.model_id==model)
    if domain:q=q.join(Experiment,Experiment.id==LLMResponse.experiment_id).where(Experiment.domain==domain)
    if brand_id:q=q.join(BrandObservation).where(BrandObservation.brand_id==brand_id)
    if search:q=q.where(LLMResponse.response_text.contains(search))
    if start:q=q.where(LLMResponse.timestamp>=start)
    if end:q=q.where(LLMResponse.timestamp<=end)
    q=q.order_by(desc(LLMResponse.timestamp)).offset(offset).limit(limit)
    return [response_dict(r,db) for r in db.scalars(q).unique()]
@app.get("/api/responses/{response_id}")
def response_detail(response_id:str,db:Session=Depends(get_db)):
    r=db.get(LLMResponse,response_id)
    if not r:raise HTTPException(404,"Response not found")
    return response_dict(r,db)
@app.get("/api/analytics/brand-visibility")
@app.get("/api/analytics/model-comparison")
@app.get("/api/analytics/historical-trends")
@app.get("/api/analytics/prompt-sensitivity")
def analytics_endpoint(source:str="live",domain:str|None=None,model:str|None=None,brand_id:str|None=None,db:Session=Depends(get_db)):return analytics(db,source,domain,model,brand_id=brand_id)
@app.get("/api/analytics/drift-alerts")
def drift(source:str="live",domain:str|None=None,model:str|None=None,db:Session=Depends(get_db)):
    now=datetime.now(timezone.utc);cut=now-timedelta(days=14)
    previous=analytics(db,source,domain,model,now-timedelta(days=28),cut)
    recent=analytics(db,source,domain,model,cut,now)
    before={x["brand"]:x for x in previous["brands"]};after={x["brand"]:x for x in recent["brands"]}
    changes=[]
    for name in before.keys()|after.keys():
        old=before.get(name,{"rate":0,"mentions":0});new=after.get(name,{"rate":0,"mentions":0})
        delta=new["rate"]-old["rate"]
        if abs(delta)>=0.15 and previous["denominator"]>=20 and recent["denominator"]>=20:
            changes.append({"brand":name,"previous_rate":old["rate"],"recent_rate":new["rate"],"difference":delta,"previous_n":previous["denominator"],"recent_n":recent["denominator"],"source":source,"window_days":14})
    return sorted(changes,key=lambda x:abs(x["difference"]),reverse=True)
@app.get("/api/quality/summary")
def quality(source:str="live",db:Session=Depends(get_db)):
    total=db.scalar(select(func.count(BrandObservation.id)).join(LLMResponse).where(LLMResponse.data_source==source,LLMResponse.execution_status=="success")) or 0
    pending=db.scalar(select(func.count(BrandObservation.id)).join(LLMResponse).where(BrandObservation.reviewed==False,LLMResponse.data_source==source,LLMResponse.execution_status=="success")) or 0
    failed=db.scalar(select(func.count(LLMResponse.id)).where(LLMResponse.execution_status=="failed",LLMResponse.data_source==source)) or 0
    return {"observations":total,"pending_review":pending,"responses_failed":failed}
@app.get("/api/quality/review-queue")
def review_queue(source:str="live",limit:int=100,db:Session=Depends(get_db)):
    rows=db.execute(select(BrandObservation,LLMResponse,Brand).join(LLMResponse).join(Brand).where(BrandObservation.reviewed==False,LLMResponse.data_source==source,LLMResponse.execution_status=="success").limit(min(limit,500))).all()
    return [{"id":o.id,"brand":b.canonical_name,"evidence":o.evidence,"sentiment":o.sentiment,"response_id":r.id} for o,r,b in rows]
@app.post("/api/quality/annotations")
def annotate(body:AnnotationIn,db:Session=Depends(get_db)):
    o=db.get(BrandObservation,body.observation_id)
    if not o:raise HTTPException(404,"Observation not found")
    a=Annotation(id=uid("ann"),observation_id=o.id,corrected_sentiment=body.sentiment,corrected_rank=body.rank,note=body.note)
    o.reviewed=True; db.add(a); db.commit();return {"id":a.id,"observation_id":o.id,"saved":True}
@app.get("/api/system/metrics")
def metrics(source:str="live",model:str|None=None,start:datetime|None=None,end:datetime|None=None,db:Session=Depends(get_db)):
    q=select(LLMResponse).where(LLMResponse.data_source==source)
    if model:q=q.where(LLMResponse.model_id==model)
    if start:q=q.where(LLMResponse.timestamp>=start)
    if end:q=q.where(LLMResponse.timestamp<=end)
    rows=db.scalars(q).all();success=[r for r in rows if r.execution_status=="success"]
    excluded=sum(r.execution_status=="excluded" for r in rows)
    latency=[r.latency_ms for r in success if r.latency_ms is not None]
    token_rows=[r.token_usage for r in success if r.token_usage]
    tokens={"input":sum(t.get("input_tokens",0) for t in token_rows),"output":sum(t.get("output_tokens",0) for t in token_rows)} if token_rows else "Unavailable"
    return {"total_requests":len(rows),"successful":len(success),"failed":sum(r.execution_status=="failed" for r in rows),"excluded":excluded,"avg_latency_ms":sum(latency)/len(latency) if latency else None,"tokens":tokens,"estimated_cost":"Cost estimate unavailable","active_experiments":db.scalar(select(func.count(Experiment.id)).where(Experiment.status=="running")) or 0}
@app.get("/api/system/logs")
def logs(limit:int=100,db:Session=Depends(get_db)):
    return [{"time":x.created_at.isoformat(),"level":x.level,"message":x.message} for x in db.scalars(select(ExecutionLog).order_by(desc(ExecutionLog.created_at)).limit(min(limit,500)))]
