import uvicorn

# we need to import the telemetry prior to running the app so that we can get the proper FastAPI instrumentation
from app.telemetry import telemetry as _  # noqa: F401

if __name__ == "__main__":
    uvicorn.run("app.app:app", host="0.0.0.0", port=8080, workers=1, timeout_keep_alive=30, proxy_headers=True)
