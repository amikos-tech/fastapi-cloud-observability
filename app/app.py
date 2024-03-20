import logging
from typing import Callable, Any

import psutil
from fastapi import FastAPI, Depends
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.db import DummyDBService
from app.exceptions import ItemNotFoundException, ItemAlreadyExistsException
from app.service import ItemService
from app.telemetry import OpenTelemetryGranularity, telemetry, OTELTelemetryClient, tracer


async def exception_middleware(
        req: Request, call_next: Callable[[Request], Any]
) -> Response:
    with tracer.start_as_current_span("API.middleware") as span:
        try:
            return await call_next(req)
        except ItemNotFoundException as e:
            exc = e
            error_code = 404
        except ItemAlreadyExistsException as e:
            exc = e
            error_code = 409
        except Exception as e:
            exc = e
            error_code = 500
        logger.error(f"API::exception_middleware - {repr(exc)}")
        trace_id = telemetry.get_current_span_id()
        span.set_attribute("http_status_code", error_code)
        return JSONResponse(content={"error": repr(exc), "trace-id": trace_id}, status_code=error_code,
                            headers={"Trace-Id": trace_id})


app = FastAPI()
app.middleware('http')(exception_middleware)
telemetry.instrument_fastapi(app, excluded_urls=["/healthz"])
logger = logging.getLogger(__name__)


def get_db():
    db = DummyDBService()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    telemetry.add_observable_gauge(name="system_cpu_usage", description="system cpu usage", unit="percent",
                                   callback=lambda: psutil.cpu_percent())
    telemetry.add_observable_gauge(name="system_memory_usage", description="system memory usage", unit="percent",
                                   callback=lambda: psutil.virtual_memory().percent)
    telemetry.add_observable_gauge(name="system_disk_usage", description="system disk usage", unit="percent",
                                   callback=lambda: psutil.disk_usage('/').percent)
    telemetry.add_observable_gauge(name="process_cpu_usage", description="process cpu usage", unit="percent",
                                   callback=lambda: psutil.Process().cpu_percent())
    telemetry.add_observable_gauge(name="process_memory_usage", description="process memory usage", unit="percent",
                                   callback=lambda: psutil.Process().memory_percent())
    telemetry.add_observable_counter(name="network_out", callback=lambda: psutil.net_io_counters().bytes_sent,
                                     unit="bytes", description="Bytes out")

    logger.info("API::startup_complete")


@app.post("/items/")
@OTELTelemetryClient.trace_method("API.create_item", OpenTelemetryGranularity.API)
def create_item(item: str, db=Depends(get_db)):
    logger.debug("API::create_item")
    item_service = ItemService(db)
    created_item = item_service.create_item(item)
    return JSONResponse(status_code=201, content={"item": created_item},
                        headers={"Trace-Id": telemetry.get_current_span_id()})


@app.get("/items/{item_id}")
@OTELTelemetryClient.trace_method("API.read_item", OpenTelemetryGranularity.API)
def read_item(item_id: str, db=Depends(get_db)):
    logger.debug("API::read_item")
    item_service = ItemService(db)
    item = item_service.read_item(item_id)
    return JSONResponse(status_code=200, content={"item": item},
                        headers={"Trace-Id": telemetry.get_current_span_id()})


@app.put("/items/{item_id}")
@OTELTelemetryClient.trace_method("API.update_item", OpenTelemetryGranularity.API)
def update_item(item_id: str, item: str, db=Depends(get_db)):
    logger.debug("API::update_item")
    item_service = ItemService(db)
    updated_item = item_service.update_item(item_id, item)
    return JSONResponse(status_code=200, content={"item": updated_item},
                        headers={"Trace-Id": telemetry.get_current_span_id()})


@app.delete("/items/{item_id}")
@OTELTelemetryClient.trace_method("API.delete_item", OpenTelemetryGranularity.API)
def delete_item(item_id: str, db=Depends(get_db)):
    logger.debug("API::delete_item")
    item_service = ItemService(db)
    deleted_item = item_service.delete_item(item_id)
    return JSONResponse(status_code=200, content={"item": deleted_item},
                        headers={"Trace-Id": telemetry.get_current_span_id()})


@app.get("/items/")
@OTELTelemetryClient.trace_method("API.list_items", OpenTelemetryGranularity.API)
def list_items(db=Depends(get_db)):
    logger.debug("API::list_items")
    item_service = ItemService(db)
    items = item_service.list_items()
    return JSONResponse(status_code=200, content={"items": items},
                        headers={"Trace-Id": telemetry.get_current_span_id()})


@app.get("/healthz")
def healthz():
    logger.info("API::healthz")
    return {"status": "ok"}
