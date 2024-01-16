import os

import psutil
from fastapi import FastAPI, Depends

from app.service import ItemService
from app.telemetry import OTELTelemetryClient, OpenTelemetryGranularity, telemetry

app = FastAPI()


def get_db():
    db = "db"
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    telemetry.instrument_fastapi(app, excluded_urls=["/healthz"])
    telemetry.instrument_fastapi_metrics(app, excluded_urls=["/healthz"])
    telemetry.add_observable_gauge(name="system_cpu_usage", description="system cpu usage", unit="percent",
                                   callback=lambda: psutil.cpu_percent())
    telemetry.add_observable_gauge(name="system_memory_usage", description="system memory usage", unit="percent",
                                   callback=lambda: psutil.virtual_memory().percent)
    telemetry.add_observable_gauge(name="system_disk_usage", description="system disk usage", unit="percent",
                                   callback=lambda: psutil.disk_usage('/').percent)
    telemetry.add_observable_gauge(name="system_network_usage", description="system network usage", unit="percent",
                                   callback=lambda: psutil.net_io_counters().bytes_sent)


@app.post("/items/")
@telemetry.trace_method("API.create_item", OpenTelemetryGranularity.API)
def create_item(item: str, db=Depends(get_db)):
    item_service = ItemService(db)
    item_service.create_item(item)
    return {"item": item}


@app.get("/items/{item_id}")
@telemetry.trace_method("API.read_item", OpenTelemetryGranularity.API)
def read_item(item_id: int, db=Depends(get_db)):
    item_service = ItemService(db)
    item = item_service.read_item(item_id)
    return {"item_id": item_id, "item": item}


@app.put("/items/{item_id}")
@telemetry.trace_method("API.update_item", OpenTelemetryGranularity.API)
def update_item(item_id: int, item: str, db=Depends(get_db)):
    item_service = ItemService(db)
    item_service.update_item(item_id, item)
    return {"item_id": item_id, "item": item}


@app.delete("/items/{item_id}")
@telemetry.trace_method("API.delete_item", OpenTelemetryGranularity.API)
def delete_item(item_id: int, db=Depends(get_db)):
    item_service = ItemService(db)
    item_service.delete_item(item_id)
    return {"result": "item deleted"}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
