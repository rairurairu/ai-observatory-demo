"""Research services: deterministic generation, extraction, execution, analytics."""
import random
import re
import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload
from backend.database import Base, engine, SessionLocal
from backend.models import (Annotation, Brand, BrandObservation, ExecutionLog, Experiment,
    ExperimentRun, ExtractionRun, LLMResponse, Model, Prompt, PromptGroup, BrandAlias, Product)
from backend.llm_adapters import ADAPTERS

DOMAINS = {
 "Consumer Electronics": ["Apple", "Samsung", "Google", "Sony", "Xiaomi"],
 "Automobiles": ["Tesla", "BMW", "Toyota", "Hyundai", "BYD"],
 "Health and Wellness": ["Fitbit", "Garmin", "Oura"],
 "Personal Finance": ["Visa", "Mastercard", "American Express"],
 "Education": ["Coursera", "Udemy", "edX"],
}
PRODUCTS = {
 "Apple": ["iPhone", "MacBook"], "Samsung": ["Galaxy", "Galaxy S"], "Google": ["Pixel"], "Sony": ["PlayStation", "WH-1000XM"], "Xiaomi": ["Redmi"],
 "Tesla": ["Model 3", "Model Y"], "BMW": ["i4", "iX"], "Toyota": ["bZ4X", "Prius"], "Hyundai": ["Ioniq 5", "Ioniq 6"], "BYD": ["Seal", "Atto 3"],
 "Fitbit": ["Charge"], "Garmin": ["Venu"], "Oura": ["Ring"], "Visa": ["Visa Infinite"], "Mastercard": ["World Elite"], "American Express": ["Platinum Card"], "Coursera": ["Coursera Plus"], "Udemy": ["Udemy Business"], "edX": ["MicroMasters"],
}
ALIASES = {"Apple": ["Apple Inc.", "iPhone", "iPad", "MacBook", "Mac"], "Samsung": ["Galaxy"], "Google": ["Pixel"], "Tesla": ["Model 3", "Model Y"], "Hyundai": ["Ioniq 5", "Ioniq 6"], "BYD": ["Atto 3", "Seal"], "American Express": ["AmEx", "American Express"], "Mastercard": ["MasterCard"]}
MODELS = [("model-a", "Synthetic Model 1"), ("model-b", "Synthetic Model 2"), ("model-c", "Synthetic Model 3")]
PROMPT_SEEDS = {
 "Consumer Electronics": ["What are the best smartphones under $800?", "Which phone offers the best value?", "What smartphone would you recommend for photography?"],
 "Automobiles": ["What are the best electric cars?", "Which affordable electric cars offer good value?", "What electric cars are best for families?"],
 "Health and Wellness": ["Which fitness trackers would you recommend?", "What wearable is best for health tracking?", "Which tracker has the best battery life?"],
 "Personal Finance": ["Which payment card is best for travel?", "What card offers good everyday rewards?", "Which payment card has low fees?"],
 "Education": ["What online learning platforms suit beginners?", "Which platform offers the best value?", "Where can I learn job-ready skills online?"],
}

def uid(prefix): return f"{prefix}_{uuid.uuid4().hex[:12]}"
def stable_id(value): return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]

def init_db():
    Base.metadata.create_all(bind=engine)

def seed_reference_catalog():
    """Ensure brand entities exist without generating synthetic responses."""
    init_db()
    db=SessionLocal()
    try:
        for domain,names in DOMAINS.items():
            for name in names:
                bid="brand-"+re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                if not db.get(Brand,bid): db.add(Brand(id=bid,canonical_name=name,domain=domain,aliases=ALIASES.get(name,[]),products=PRODUCTS[name]))
        db.commit()
        for domain,names in DOMAINS.items():
            for name in names:
                bid="brand-"+re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                for alias in ALIASES.get(name,[]):
                    if not db.scalar(select(BrandAlias).where(BrandAlias.alias==alias)):
                        db.add(BrandAlias(id=uid("alias"),brand_id=bid,alias=alias))
                for product_name in PRODUCTS[name]:
                    if not db.scalar(select(Product).where(Product.brand_id==bid,Product.canonical_name==product_name)):
                        db.add(Product(id=uid("product"),brand_id=bid,canonical_name=product_name,product_family=product_name.split()[0]))
        db.commit()
    finally:
        db.close()

def _seed_catalog(db: Session):
    if not db.get(Model, "model-a"):
        db.add_all([Model(id=i, provider="demo", display_name=n, model_id=n, data_source="demo") for i,n in MODELS])
    for model_id, name in MODELS:
        model = db.get(Model, model_id)
        if model and model.data_source == "demo" and model.display_name in {"Model A", "Model B", "Model C"}:
            model.display_name = name
    for domain, names in DOMAINS.items():
        for name in names:
            bid = "brand-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            if not db.get(Brand, bid): db.add(Brand(id=bid, canonical_name=name, domain=domain, aliases=ALIASES.get(name, []), products=PRODUCTS[name]))
        gid = "group-" + re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-")
        if not db.get(PromptGroup, gid): db.add(PromptGroup(id=gid, name=f"{domain} prompt variants", domain=domain))
        for idx, text in enumerate(PROMPT_SEEDS[domain]):
            pid = f"prompt-{re.sub(r'[^a-z0-9]+','-',domain.lower()).strip('-')}-{idx+1}"
            if not db.get(Prompt, pid): db.add(Prompt(id=pid, text=text, domain=domain, group_id=gid, variant=["baseline", "value", "use-case"][idx]))
    db.commit()
    for domain,names in DOMAINS.items():
        for name in names:
            bid="brand-"+re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            for alias in ALIASES.get(name,[]):
                if not db.scalar(select(BrandAlias).where(BrandAlias.alias==alias)):
                    db.add(BrandAlias(id=uid("alias"),brand_id=bid,alias=alias))
            for product_name in PRODUCTS[name]:
                if not db.scalar(select(Product).where(Product.brand_id==bid,Product.canonical_name==product_name)):
                    db.add(Product(id=uid("product"),brand_id=bid,canonical_name=product_name,product_family=product_name.split()[0]))
    db.commit()

def extract_brands(text: str, brands: list[Brand]):
    """Dictionary extraction. Mention order is kept separate from explicit numbered ranks."""
    findings=[]
    explicit = {}
    for m in re.finditer(r"(?:^|\n)\s*(\d{1,2})[.)]\s*([^\n]+)", text):
        explicit[m.group(2)] = int(m.group(1))
    candidates=[]
    for b in brands:
        for term in [b.canonical_name, *(b.aliases or []), *(b.products or [])]:
            if not term: continue
            for m in re.finditer(r"(?<!\w)"+re.escape(term)+r"(?!\w)", text, re.I):
                if b.canonical_name=="Apple" and term.casefold()=="apple" and re.search(r"\b(fruit|pie|orchard|recipe|cider)\b",text[max(0,m.start()-35):m.end()+35],re.I):
                    continue
                candidates.append((m.start(), m.end(), b, term))
    # Prefer the longest matching entity at a given position (e.g. AmEx over a partial match).
    candidates.sort(key=lambda x:(x[0], -(x[1]-x[0]), 0 if x[3] in (x[2].products or []) else 1))
    kept=[]
    for item in candidates:
        if any(item[0] < e and item[1] > s for s,e,_,_ in kept): continue
        kept.append(item)
    seen=set()
    positive=("excellent", "great", "strong", "reliable", "comfortable", "good", "impressive", "intuitive", "affordable", "versatile", "fast", "accurate")
    negative=("expensive", "limited", "poor", "weak", "unreliable", "costly", "short battery", "concern", "drawback")
    for pos,end,b,term in kept:
        if b.id in seen: continue
        seen.add(b.id)
        left=text.rfind("\n", 0, pos)+1; right=text.find("\n", end)
        if right < 0: right=len(text)
        evidence=text[left:right].strip()
        low=evidence.lower()
        p=any(w in low for w in positive); n=any(w in low for w in negative)
        sentiment="positive" if p and not n else "negative" if n and not p else "unknown"
        product=next((x for x in b.products or [] if re.search(r"(?<!\w)"+re.escape(x)+r"(?!\w)", evidence,re.I)), None)
        rank=None
        for line, r in explicit.items():
            if re.search(r"(?<!\w)"+re.escape(b.canonical_name)+r"(?!\w)", line,re.I): rank=r; break
        attrs=[w for w in ["battery life","camera quality","camera","reliable software","software","design","comfort","charging network","range","safety features","health insights","activity tracking","rewards","fees","instructors","course selection","flexible learning","value","reliability"] if w in low]
        findings.append(dict(brand=b, mention_order=len(findings)+1, explicit_rank=rank, product=product, sentiment=sentiment, attributes=attrs, evidence=evidence, entity_type="product" if term in (b.products or []) else "brand"))
    return findings

def _demo_response(domain, prompt, brand_names, model_idx, repetition):
    templates=["For {need}, {brand} {product} stands out for its {attr}. {brand2} {product2} is another option with {attr2}.", "Consider {brand} {product}, which offers {attr}. {brand2} {product2} may suit buyers who value {attr2}.", "1. {brand} {product} — {attr}.\n2. {brand2} {product2} — {attr2}.\n{brand3} is also worth comparing."]
    attrs={"Consumer Electronics":["camera quality","battery life","reliable software","an intuitive design"],"Automobiles":["a strong charging network","comfortable seating","good range","advanced safety features"],"Health and Wellness":["accurate activity tracking","helpful health insights","long battery life"],"Personal Finance":["useful travel rewards","reliable acceptance","a broad set of benefits"],"Education":["a broad course selection","clear beginner lessons","flexible learning options"]}[domain]
    rng=random.Random(f"{brand_names}-{model_idx}-{repetition}-{prompt}")
    if len(brand_names)<2: brand_names=brand_names*2
    if len(brand_names)<3: templates=templates[:2]
    a,b=brand_names[:2]; c=brand_names[2] if len(brand_names)>2 else b
    products=lambda name: rng.choice(PRODUCTS[name])
    tpl=templates[rng.randrange(len(templates))]
    return tpl.format(need=prompt.lower().replace("what are ","").rstrip("?"),brand=a,product=products(a),attr=rng.choice(attrs),brand2=b,product2=products(b),attr2=rng.choice(attrs),brand3=c)

def seed_demo(reset=False):
    init_db(); db=SessionLocal()
    try:
        _seed_catalog(db)
        if db.scalar(select(func.count(LLMResponse.id))) and not reset: return {"seeded":False,"reason":"demo observations already exist"}
        if reset:
            for model in [BrandObservation, ExtractionRun, LLMResponse, ExperimentRun, Experiment, Annotation, ExecutionLog]: db.query(model).delete()
            db.commit()
        rng=random.Random(82344)
        brands=db.scalars(select(Brand)).all()
        for domain,names in DOMAINS.items():
            expid="demo-"+stable_id(domain)
            if not db.get(Experiment, expid): db.add(Experiment(id=expid,name=f"90-day demonstration: {domain}",description="Deterministic synthetic observations for interface demonstration.",domain=domain,mode="demo",status="complete",config={"seed":82344,"synthetic":True}))
        db.commit()
        prompts_by_domain={d:db.scalars(select(Prompt).where(Prompt.domain==d).order_by(Prompt.id)).all() for d in DOMAINS}
        models=db.scalars(select(Model).where(Model.data_source=="demo")).all()
        for day in range(89,-1,-1):
            date=datetime.now(timezone.utc)-timedelta(days=day)
            for domain,names in DOMAINS.items():
                expid="demo-"+stable_id(domain)
                for mi, model in enumerate(models):
                    # One independent response per model/domain/day; prompt variant rotates over time.
                    prompt=prompts_by_domain[domain][(day+mi)%3]
                    drift_boost=(day<12 and names[(mi+1)%len(names)] in names)
                    local=random.Random(f"{82344}:{day}:{domain}:{mi}")
                    ranked=sorted(names,key=lambda n: (local.random() + (0.28 if n==names[(mi+day//20)%len(names)] else 0) + (0.15 if day<12 and n==names[(mi+2)%len(names)] else 0)),reverse=True)
                    chosen=ranked[:local.choice([2,3])]
                    response_text=_demo_response(domain,prompt.text,chosen,mi,day)
                    # Simulated failures are retained as audit records.
                    failed=(day==61 and mi==2 and domain=="Education")
                    runid=uid("run")
                    if not db.get(ExperimentRun,runid): db.add(ExperimentRun(id=runid,experiment_id=expid,status="complete",started_at=date,completed_at=date+timedelta(seconds=1),planned=1,completed=0 if failed else 1,failed=1 if failed else 0))
                    rid=uid("resp")
                    response=LLMResponse(id=rid,experiment_id=expid,run_id=runid,prompt_id=prompt.id,model_id=model.id,repetition=1,timestamp=date,response_text="" if failed else response_text,token_usage={},latency_ms=None,execution_status="failed" if failed else "success",error_message="Illustrative synthetic timeout" if failed else None,data_source="demo",model_configuration={"temperature":0.4+mi*.2},search_enabled=False)
                    db.add(response)
                    if not failed:
                        xr=ExtractionRun(id=uid("extract"),response_id=rid,method="dictionary",pipeline_version="1.0.0")
                        db.add(xr)
                        for f in extract_brands(response_text,brands):
                            db.add(BrandObservation(id=uid("obs"),response_id=rid,brand_id=f["brand"].id,extraction_run_id=xr.id,mention_order=f["mention_order"],explicit_rank=f["explicit_rank"],product=f["product"],sentiment=f["sentiment"],attributes=f["attributes"],evidence=f["evidence"],entity_type=f["entity_type"]))
            if day%10==0: db.commit()
        db.commit()
        db.add(ExecutionLog(id=uid("log"),level="INFO",message="Seeded deterministic synthetic demonstration observations.")); db.commit()
        return {"seeded":True,"responses":db.scalar(select(func.count(LLMResponse.id)))}
    finally: db.close()

def demo_run(db: Session, experiment: Experiment):
    run=ExperimentRun(id=uid("run"),experiment_id=experiment.id,status="running")
    db.add(run); db.commit()
    prompts=[db.get(Prompt,p) for p in experiment.config["prompt_ids"]]
    models=[db.get(Model,m) for m in experiment.config["model_ids"]]
    reps=int(experiment.config["repetitions"]); run.planned=len(prompts)*len(models)*reps
    brands=db.scalars(select(Brand).where(Brand.domain==experiment.domain)).all()
    for prompt in prompts:
      if not prompt: continue
      for mi,model in enumerate(models):
        if not model: continue
        for rep in range(reps):
          names=DOMAINS[experiment.domain]
          rng=random.Random(f"{experiment.id}:{prompt.id}:{model.id}:{rep}")
          selected=rng.sample(names,min(3,len(names)))
          raw=_demo_response(experiment.domain,prompt.text,selected,mi,rep)
          rid=uid("resp"); xr=ExtractionRun(id=uid("extract"),response_id=rid,method="dictionary",pipeline_version="1.0.0")
          resp=LLMResponse(id=rid,experiment_id=experiment.id,run_id=run.id,prompt_id=prompt.id,model_id=model.id,repetition=rep+1,response_text=raw,data_source="demo",execution_status="success",model_configuration={"temperature":0.7},search_enabled=False)
          db.add_all([xr,resp]); db.flush()
          for f in extract_brands(raw,brands): db.add(BrandObservation(id=uid("obs"),response_id=rid,brand_id=f["brand"].id,extraction_run_id=xr.id,mention_order=f["mention_order"],explicit_rank=f["explicit_rank"],product=f["product"],sentiment=f["sentiment"],attributes=f["attributes"],evidence=f["evidence"],entity_type=f["entity_type"]))
          run.completed+=1
    run.status="complete" if run.failed==0 else "partial"; run.completed_at=datetime.now(timezone.utc); experiment.status="complete"
    db.add(ExecutionLog(id=uid("log"),experiment_id=experiment.id,run_id=run.id,message=f"Demo execution completed: {run.completed}/{run.planned} requests.")); db.commit()
    return run

def live_run(db: Session, experiment: Experiment):
    """Explicit live collection; resume a persisted running run after interruption."""
    run=db.scalars(select(ExperimentRun).where(
        ExperimentRun.experiment_id==experiment.id,
        ExperimentRun.status=="running",
    ).order_by(ExperimentRun.started_at.desc())).first()
    if run is None:
        run=ExperimentRun(id=uid("run"),experiment_id=experiment.id,status="running")
        db.add(run);db.commit()
    prompts=[db.get(Prompt,p) for p in experiment.config["prompt_ids"]]
    models=[db.get(Model,m) for m in experiment.config["model_ids"]]
    reps=int(experiment.config["repetitions"]);run.planned=len(prompts)*len(models)*reps
    existing=db.scalars(select(LLMResponse).where(LLMResponse.run_id==run.id)).all()
    completed_keys={(r.prompt_id,r.model_id,r.repetition) for r in existing}
    run.completed=sum(r.execution_status=="success" for r in existing)
    run.failed=sum(r.execution_status=="failed" for r in existing)
    db.commit()
    brands=db.scalars(select(Brand).where(Brand.domain==experiment.domain)).all()
    for prompt in prompts:
      for model in models:
        provider=model.provider; adapter=ADAPTERS[provider]()
        for rep in range(reps):
          if (prompt.id,model.id,rep+1) in completed_keys: continue
          rid=uid("resp"); started=datetime.now(timezone.utc); raw=""; usage={}; latency=None; status="success"; error=None
          try:
            result=adapter.generate(prompt.text,model.model_id)
            raw=result.response_text;usage=result.token_usage;latency=result.latency_ms
          except Exception as exc:
            status="failed"; error=f"{type(exc).__name__}: {str(exc)[:500]}"
          response=LLMResponse(id=rid,experiment_id=experiment.id,run_id=run.id,prompt_id=prompt.id,model_id=model.id,repetition=rep+1,timestamp=started,response_text=raw,token_usage=usage,latency_ms=latency,execution_status=status,error_message=error,data_source="live",model_configuration={"provider":provider,"search_supported":False},search_enabled=False)
          db.add(response)
          if status=="success":
            xr=ExtractionRun(id=uid("extract"),response_id=rid,method="dictionary",pipeline_version="1.0.0");db.add(xr);db.flush()
            for f in extract_brands(raw,brands):db.add(BrandObservation(id=uid("obs"),response_id=rid,brand_id=f["brand"].id,extraction_run_id=xr.id,mention_order=f["mention_order"],explicit_rank=f["explicit_rank"],product=f["product"],sentiment=f["sentiment"],attributes=f["attributes"],evidence=f["evidence"],entity_type=f["entity_type"]))
            run.completed+=1
          else:run.failed+=1
          db.commit()
    run.status="complete" if run.failed==0 else "partial" if run.completed else "failed";run.completed_at=datetime.now(timezone.utc);experiment.status=run.status
    db.add(ExecutionLog(id=uid("log"),experiment_id=experiment.id,run_id=run.id,message=f"Live execution finished: {run.completed} succeeded, {run.failed} failed."));db.commit()
    return run

def response_dict(r: LLMResponse, db: Session):
    p=db.get(Prompt,r.prompt_id); m=db.get(Model,r.model_id)
    obs=[] if r.execution_status=="excluded" else db.scalars(select(BrandObservation).where(BrandObservation.response_id==r.id)).all()
    out=[]
    for o in obs:
        annotations=db.scalars(select(Annotation).where(Annotation.observation_id==o.id).order_by(Annotation.created_at.desc())).all()
        out.append({"id":o.id,"brand_id":o.brand_id,"brand":db.get(Brand,o.brand_id).canonical_name,"mention_order":o.mention_order,"explicit_rank":o.explicit_rank,"product":o.product,"sentiment":o.sentiment,"attributes":o.attributes,"evidence":o.evidence,"reviewed":o.reviewed,"human_annotations":[{"sentiment":a.corrected_sentiment,"rank":a.corrected_rank,"note":a.note,"created_at":a.created_at.isoformat() if a.created_at else None} for a in annotations]})
    return {"id":r.id,"experiment_id":r.experiment_id,"run_id":r.run_id,"prompt_id":r.prompt_id,"prompt":p.text if p else "","model_id":r.model_id,"model":m.display_name if m else r.model_id,"timestamp":r.timestamp.isoformat() if r.timestamp else None,"response_text":r.response_text,"token_usage":r.token_usage,"latency_ms":r.latency_ms,"execution_status":r.execution_status,"error_message":r.error_message,"data_source":r.data_source,"model_configuration":r.model_configuration,"search_enabled":r.search_enabled,"observations":out}

def analytics(db: Session, source="live", domain=None, model=None, start=None, end=None, brand_id=None):
    q=select(LLMResponse).where(LLMResponse.data_source==source)
    if domain: q=q.join(Experiment,Experiment.id==LLMResponse.experiment_id).where(Experiment.domain==domain)
    if model: q=q.where(LLMResponse.model_id==model)
    if start: q=q.where(LLMResponse.timestamp>=start)
    if end: q=q.where(LLMResponse.timestamp<=end)
    responses=[r for r in db.scalars(q).all() if r.execution_status!="excluded"]
    ids=[r.id for r in responses]; denominator=sum(1 for r in responses if r.execution_status=="success")
    if not ids: return {"responses":0,"denominator":0,"latest_success":None,"model_count":0,"domain_count":0,"brands":[],"timeline":[],"by_model":[],"by_prompt":[],"rank_distribution":[]}
    successful_ids=[r.id for r in responses if r.execution_status=="success"]
    rows=db.execute(select(BrandObservation,Brand.canonical_name,LLMResponse.model_id,LLMResponse.timestamp,Prompt.id,Prompt.text).join(Brand).join(LLMResponse).join(Prompt).where(BrandObservation.response_id.in_(successful_ids))).all() if successful_ids else []
    if brand_id: rows=[row for row in rows if row[0].brand_id==brand_id]
    by=defaultdict(set); mods=defaultdict(set); days=defaultdict(set); ranks=defaultdict(int); prompt_by=defaultdict(set)
    date_denoms=defaultdict(int)
    for r in responses:
        if r.execution_status=="success":date_denoms[r.timestamp.strftime("%Y-%m-%d")]+=1
    for o,name,mid,ts,pid,ptext in rows:
        by[name].add(o.response_id); mods[(mid,name)].add(o.response_id); days[(ts.strftime("%Y-%m-%d"),name)].add(o.response_id)
        prompt_by[(pid,ptext,name,mid)].add(o.response_id)
        if o.explicit_rank is not None: ranks[o.explicit_rank]+=1
    prompt_denoms=defaultdict(int)
    for r in responses:
        if r.execution_status=="success":prompt_denoms[(r.prompt_id,r.model_id)]+=1
    latest=max((r.timestamp for r in responses if r.execution_status=="success" and r.timestamp),default=None)
    domain_count=db.scalar(select(func.count(func.distinct(Experiment.domain))).join(LLMResponse,LLMResponse.experiment_id==Experiment.id).where(LLMResponse.id.in_(ids))) or 0
    return {"responses":len(responses),"denominator":denominator,"latest_success":latest.isoformat() if latest else None,"model_count":len({r.model_id for r in responses if r.execution_status=="success"}),"domain_count":domain_count,"brands":[{"brand":n,"mentions":len(s),"rate":len(s)/denominator if denominator else 0} for n,s in sorted(by.items(),key=lambda x:-len(x[1]))],"timeline":[{"date":d,"brand":n,"mentions":len(s),"denominator":date_denoms[d],"rate":len(s)/date_denoms[d] if date_denoms[d] else 0} for (d,n),s in sorted(days.items())],"by_model":[{"model_id":m,"brand":n,"mentions":len(s)} for (m,n),s in mods.items()],"by_prompt":[{"prompt_id":pid,"prompt":text,"brand":name,"model_id":mid,"mentions":len(s),"denominator":prompt_denoms[(pid,mid)],"rate":len(s)/prompt_denoms[(pid,mid)] if prompt_denoms[(pid,mid)] else 0} for (pid,text,name,mid),s in prompt_by.items()],"rank_distribution":[{"rank":k,"count":v} for k,v in sorted(ranks.items())]}
