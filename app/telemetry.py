import logging
import os
from enum import Enum
from functools import wraps
from typing import List, Optional, Iterable, Callable, Any, Dict, Union
from typing import Sequence

import psutil
from fastapi import FastAPI
from opentelemetry import metrics
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.metrics import Observation, CallbackOptions, Counter
from opentelemetry.sdk._logs import LoggingHandler, LoggerProvider
from opentelemetry.sdk._logs._internal.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
)


class OpenTelemetryGranularity(str, Enum):
    """The granularity of the OpenTelemetry spans."""

    NONE = "none"
    """No spans are emitted."""

    SERVICE = "service"
    """Spans are emitted for all stack layers up to and include the service."""

    DB = "db"
    """Spans are emitted for all stack layers up to and include the DB."""

    API = "api"
    """Spans are emitted only for API calls"""

    ALL = "all"
    """Spans are emitted for almost every method call."""

    def __lt__(self, other: "OpenTelemetryGranularity") -> bool:
        """Compare two granularities."""
        order = [
            OpenTelemetryGranularity.ALL,
            OpenTelemetryGranularity.DB,
            OpenTelemetryGranularity.SERVICE,
            OpenTelemetryGranularity.API,
            OpenTelemetryGranularity.NONE,
        ]
        return order.index(self) < order.index(other)


tracer: Optional[trace.Tracer] = None
granularity: OpenTelemetryGranularity = OpenTelemetryGranularity("none")
meter_provider: Optional[MeterProvider] = None
meter = metrics.get_meter(__name__)


class OTELTelemetryClient(object):
    def __init__(self, *, service_name: str, otel_endpoint: str, headers: Optional[Dict[str, str]] = None,
                 trace_granularity: Optional[OpenTelemetryGranularity] = OpenTelemetryGranularity.NONE,
                 app: Optional[FastAPI] = None,
                 excluded_urls: Optional[List[str]] = None):
        self.service_name = service_name
        self.endpoint = otel_endpoint
        self.headers = headers
        self.granularity = trace_granularity
        self.resource = Resource.create({SERVICE_NAME: self.service_name})
        self._trace_init()
        self._metrics_init()
        self._logging_init()
        if app:
            self.instrument_fastapi(app, excluded_urls=excluded_urls)
        self._counters = {}

    def _trace_init(self):
        self.trace_provider = TracerProvider(resource=self.resource)
        self.trace_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=self.endpoint,
                    headers=self.headers,
                )
            )
        )
        trace.set_tracer_provider(self.trace_provider)
        global tracer, granularity
        tracer = trace.get_tracer(__name__)
        granularity = self.granularity

    def _metrics_init(self):
        global meter_provider
        exporter = OTLPMetricExporter(endpoint=self.endpoint,
                                      headers=self.headers,
                                      insecure=True)
        reader = PeriodicExportingMetricReader(exporter=exporter, export_interval_millis=1000)
        self.meter_provider = MeterProvider(resource=self.resource, metric_readers=[reader])
        metrics.set_meter_provider(self.meter_provider)

    def _logging_init(self):
        self.logger_provider = LoggerProvider(resource=self.resource)
        otlp_exporter = OTLPLogExporter(endpoint=self.endpoint,
                                        headers=self.headers,
                                        insecure=True)
        self.logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_exporter))
        handler = LoggingHandler(level=logging.INFO, logger_provider=self.logger_provider)
        logging.getLogger().addHandler(handler)
        uv_log = logging.getLogger("uvicorn")
        uv_log.addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    @staticmethod
    def trace_method(
            trace_name: str,
            trace_granularity: OpenTelemetryGranularity,
            attributes: Optional[
                Dict[
                    str,
                    Union[
                        str,
                        bool,
                        float,
                        int,
                        Sequence[str],
                        Sequence[bool],
                        Sequence[float],
                        Sequence[int],
                    ],
                ]
            ] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """A decorator to wrap methods in traces."""

        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(f)
            def wrapper(*args: Any, **kwargs: Dict[Any, Any]) -> Any:
                global tracer, granularity
                if trace_granularity < granularity:
                    return f(*args, **kwargs)
                if not tracer:
                    return f(*args, **kwargs)
                with tracer.start_as_current_span(trace_name, attributes=attributes):
                    return f(*args, **kwargs)

            return wrapper

        return decorator

    @staticmethod
    def add_attributes_to_current_span(
            attributes: Dict[
                str,
                Union[
                    str,
                    bool,
                    float,
                    int,
                    Sequence[str],
                    Sequence[bool],
                    Sequence[float],
                    Sequence[int],
                ],
            ]
    ) -> None:
        """Add attributes to the current span."""
        global tracer, granularity
        if granularity == OpenTelemetryGranularity.NONE:
            return
        if not tracer:
            return
        span = trace.get_current_span()
        span.set_attributes(attributes)

    @staticmethod
    def get_current_span_id() -> Optional[str]:
        """Get the current span ID."""
        global tracer, granularity
        if granularity == OpenTelemetryGranularity.NONE:
            return None
        if not tracer:
            return None
        ctx = trace.get_current_span().get_span_context()
        return '{trace:032x}'.format(trace=ctx.trace_id)

    def instrument_fastapi(self, app: FastAPI, excluded_urls: Optional[List[str]] = None) -> None:
        """Instrument FastAPI to emit OpenTelemetry spans."""
        FastAPIInstrumentor.instrument_app(
            app, excluded_urls=",".join(excluded_urls) if excluded_urls else None,
            tracer_provider=self.trace_provider,
            meter_provider=self.meter_provider,
        )

    def add_observable_gauge(self, *, name: str, callback: Callable[
        [], Union[Union[int, float], Iterable[Union[int, float]]]],
                             unit: str, description: str) -> None:
        """Add an observable gauge to the metrics.
        :param name: The name of the gauge.
        :param callback: A callback function that returns the value of the gauge.
        :param unit: The unit of the gauge.
        :param description: The description of the gauge.

        Example:
            >>> client.add_observable_gauge("my_gauge", lambda: return psutil.cpu_percent(), "percent", "CPU Usage")
        """

        def cb(_: CallbackOptions) -> Iterable[Observation]:
            value = callback()
            if isinstance(value, (int, float)):
                return [Observation(value, {})]
            else:
                return [Observation(v, {}) for v in value]

        meter.create_observable_gauge(name=name, callbacks=[cb], unit=unit, description=description)

    def add_observable_counter(self, *, name: str, callback: Callable[
        [], Union[Union[int, float], Iterable[Union[int, float]]]],
                                unit: str, description: str) -> None:
        """Add an observable counter to the metrics.
        :param name: The name of the counter.
        :param callback: A callback function that returns the value of the counter.
        :param unit: The unit of the counter.
        :param description: The description of the counter.

        Example:
            >>> client.add_observable_counter("my_counter", lambda: return psutil.net_io_counters().bytes_sent, "bytes", "Bytes out")
        """

        def cb(_: CallbackOptions) -> Iterable[Observation]:
            value = callback()
            if isinstance(value, (int, float)):
                return [Observation(value, {})]
            else:
                return [Observation(v, {}) for v in value]

        meter.create_observable_counter(name=name, callbacks=[cb], unit=unit, description=description)

    def add_counter(self, name: str, unit: str, description: str) -> Counter:
        """Add a counter to the metrics."""

        if name not in self._counters.keys():
            self._counters[name] = meter.create_counter(name=name, unit=unit, description=description)
        return self._counters[name]


telemetry = OTELTelemetryClient(
    service_name=os.environ.get("OTEL_SERVICE_NAME", "item-service"),
    otel_endpoint=os.environ.get("OTEL_ENDPOINT", "http://localhost:4317"),
    trace_granularity=os.environ.get("OTEL_TRACE_GRANULARITY", OpenTelemetryGranularity.ALL),
)
