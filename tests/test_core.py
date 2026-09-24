import os
os.environ["DATABASE_URL"]="sqlite:///./ai_observatory_test.db"
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.models import Brand
from backend.services import DOMAINS, extract_brands, seed_demo

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client

def test_health_and_demo_seed(client):
    r=client.get("/health"); assert r.status_code==200 and r.json()["responses"]>1000

def test_dictionary_extraction_keeps_rank_separate(client):
    db=SessionLocal()
    try:
        brands=db.query(Brand).filter(Brand.domain=="Automobiles").all()
        found=extract_brands("1. Tesla Model 3 — excellent charging network.\n2. Hyundai Ioniq 5 — comfortable seating.",brands)
        tesla=next(x for x in found if x["brand"].canonical_name=="Tesla")
        hyundai=next(x for x in found if x["brand"].canonical_name=="Hyundai")
        assert tesla["mention_order"]==1 and tesla["explicit_rank"]==1
        assert hyundai["mention_order"]==2 and hyundai["explicit_rank"]==2
        unordered=extract_brands("Tesla Model 3 is excellent; Hyundai Ioniq 5 offers comfort.",brands)
        assert unordered[0]["mention_order"]==1 and unordered[0]["explicit_rank"] is None
    finally: db.close()

def test_alias_and_product_names_normalize_to_one_brand(client):
    db=SessionLocal()
    try:
        apple=db.query(Brand).filter(Brand.canonical_name=="Apple").one()
        found=extract_brands("Apple Inc. recommends iPhone for its excellent camera.",[apple])
        assert len(found)==1 and found[0]["brand"].id==apple.id
        assert found[0]["entity_type"]=="brand" and found[0]["product"]=="iPhone"
        assert "excellent camera" in found[0]["evidence"]
    finally:db.close()

def test_overview_rates_are_response_level_and_scoped(client):
    r=client.get("/api/overview?source=demo&domain=Automobiles"); assert r.status_code==200
    d=r.json(); assert d["denominator"]>0 and d["responses"]>=d["denominator"]
    assert all(0<=x["rate"]<=1 for x in d["brands"])

def test_prompt_and_daily_denominators(client):
    d=client.get("/api/analytics/prompt-sensitivity?source=demo&domain=Automobiles").json()
    assert d["by_prompt"] and all(0<=x["rate"]<=1 and x["denominator"]>0 for x in d["by_prompt"])
    assert d["timeline"] and all(0<=x["rate"]<=1 and x["denominator"]>0 for x in d["timeline"])

def test_experiment_create_run_and_repetitions(client):
    prompts=client.get("/api/prompts?domain=Automobiles").json(); models=client.get("/api/models").json()
    body={"name":"test repeat preservation","description":"unit test","domain":"Automobiles","model_ids":[m["id"] for m in models[:2]],"prompt_ids":[p["id"] for p in prompts[:2]],"repetitions":2,"mode":"demo"}
    made=client.post("/api/experiments",json=body);assert made.status_code==200
    run=client.post(f"/api/experiments/{made.json()['id']}/run",json={});assert run.status_code==200
    assert run.json()["completed"]==8 and run.json()["planned"]==8
    results=client.get(f"/api/experiments/{made.json()['id']}/results").json();assert len(results)==8

def test_demo_isolation_and_quality_annotation(client):
    assert client.get("/api/overview?source=live").json()["responses"]==0
    queue=client.get("/api/quality/review-queue?limit=1").json()
    if queue:
        result=client.post("/api/quality/annotations",json={"observation_id":queue[0]["id"],"sentiment":"unknown","note":"test review"})
        assert result.status_code==200
        response=client.get(f"/api/responses/{queue[0]['response_id']}").json()
        obs=next(o for o in response["observations"] if o["id"]==queue[0]["id"])
        assert obs["reviewed"] and obs["human_annotations"][-1]["note"]=="test review"

def test_failures_are_stored_and_export_has_metadata(client):
    education=client.get("/api/responses?source=demo&domain=Education&limit=500").json()
    assert any(r["execution_status"]=="failed" for r in education)
    exps=client.get("/api/experiments").json(); demo=next(e for e in exps if e["name"].startswith("90-day demonstration: Automobiles"))
    export=client.get(f"/api/experiments/{demo['id']}/export?format=json")
    assert export.status_code==200 and export.json()["metadata"]["data_source"]=="demo"
    csv=client.get(f"/api/experiments/{demo['id']}/export?format=csv")
    assert csv.status_code==200 and "response_text" in csv.text

def test_live_and_demo_models_cannot_mix(client):
    prompt=client.get("/api/prompts?domain=Automobiles").json()[0]
    demo_model=client.get("/api/models?mode=demo").json()[0]
    result=client.post("/api/experiments",json={"name":"bad mixed run","domain":"Automobiles","model_ids":[demo_model["id"]],"prompt_ids":[prompt["id"]],"repetitions":1,"mode":"live"})
    assert result.status_code==400
