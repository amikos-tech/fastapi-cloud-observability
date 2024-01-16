import os
from enum import Enum
from functools import wraps
from typing import List, Optional, Iterable, Callable, Any, Dict, Union
from typing import Sequence

import psutil
from fastapi import FastAPI
from opentelemetry import metrics
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.metrics import Observation, CallbackOptions, Counter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
)


class OpenTelemetryGranularity(Enum):
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

    def __lt__(self, other: Any) -> bool:
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
        self._trace_init()
        self._metrics_init()
        self._logging_init()
        if app:
            self.instrument_fastapi(app, excluded_urls=excluded_urls)
            self.instrument_fastapi_metrics(app, excluded_urls=excluded_urls)
        self._counters = {}

    def _trace_init(self):
        resource = Resource(attributes={SERVICE_NAME: str(self.service_name)})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=self.endpoint,
                    headers=self.headers,
                )
            )
        )
        trace.set_tracer_provider(provider)

        global tracer, granularity
        tracer = trace.get_tracer(__name__)
        granularity = self.granularity

    def _metrics_init(self):
        global meter_provider
        exporter = OTLPMetricExporter(endpoint=self.endpoint, headers=self.headers,
                                      insecure=True)
        # Setup MeterProvider with OTLP exporter and auto-instrumentation
        resource = Resource.create({SERVICE_NAME: self.service_name})
        reader = PeriodicExportingMetricReader(exporter=exporter, export_interval_millis=1000)
        self.meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(self.meter_provider)

    def _logging_init(self):
        pass

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

    def instrument_fastapi(self, app: FastAPI, excluded_urls: Optional[List[str]] = None) -> None:
        """Instrument FastAPI to emit OpenTelemetry spans."""
        FastAPIInstrumentor.instrument_app(
            app, excluded_urls=",".join(excluded_urls) if excluded_urls else None
        )

    def instrument_fastapi_metrics(self, app: FastAPI,
                                   excluded_urls: Optional[List[str]] = None) -> None:
        """Instrument FastAPI to emit OpenTelemetry metrics."""
        FastAPIInstrumentor.instrument_app(
            app, excluded_urls=",".join(excluded_urls) if excluded_urls else None, meter_provider=self.meter_provider
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

    def add_counter(self, name: str, unit: str, description: str) -> Counter:
        """Add a counter to the metrics."""

        if name not in self._counters.keys():
            self._counters[name] = meter.create_counter(name=name, unit=unit, description=description)
        return self._counters[name]

#
# # Define the observable gauge callback functions
# # Define the callback functions for the metrics
# def system_cpu_usage_callback(_: CallbackOptions) -> Iterable[Observation]:
#     cpu_usage = psutil.cpu_percent()
#     return [Observation(cpu_usage, {})]
#
#
# def system_memory_usage_callback(_: CallbackOptions) -> Iterable[Observation]:
#     memory_usage = psutil.virtual_memory().used
#     return [Observation(memory_usage, {})]
#
#
# def process_memory_usage_callback(_: CallbackOptions) -> Iterable[Observation]:
#     memory_usage = psutil.Process().memory_info().rss
#     return [Observation(memory_usage, {})]
#
#
# def process_cpu_usage_callback(_: CallbackOptions) -> Iterable[Observation]:
#     cpu_usage = psutil.Process().cpu_percent()
#     return [Observation(cpu_usage, {})]
#
#
# # open file handles for the process
# def process_open_file_handles_callback(_: CallbackOptions) -> Iterable[Observation]:
#     open_file_handles = psutil.Process().open_files()
#     return [Observation(len(open_file_handles), {})]
#
#
# # Create observable gauges with the callbacks
# meter.create_observable_gauge(name="system_cpu_usage", callbacks=[system_cpu_usage_callback], unit="percent",
#                               description="System CPU Usage")
# meter.create_observable_gauge(name="system_memory_usage", callbacks=[system_memory_usage_callback], unit="bytes",
#                               description="System Memory Usage")
#
# meter.create_observable_gauge(name="process_cpu_usage", callbacks=[process_cpu_usage_callback], unit="percent",
#                               description="CPU Usage")
# meter.create_observable_gauge(name="process_memory_usage", callbacks=[process_memory_usage_callback], unit="bytes",
#                               description="Memory Usage")
# meter.create_observable_gauge(name="process_open_file_handles", callbacks=[process_open_file_handles_callback],
#                               unit="count", description="Open File Handles")
#
# counters = {}
#
#
# # TODO we don't necessarily need the below
# def method_counter(
#         counter_name: Union[str, List[str]],
#         unit: str = "count",
#         description: str = "Method Counter",
# ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
#     """A decorator that traces a method."""
#     meter = metrics.get_meter(__name__)
#
#     if isinstance(counter_name, str) and counter_name not in counters.keys():
#         counters[counter_name] = meter.create_counter(name=counter_name,
#                                                       unit=unit,
#                                                       description=description)
#     elif isinstance(counter_name, list):
#         for name in counter_name:
#             if name not in counters.keys():
#                 counters[name] = meter.create_counter(name=name,
#                                                       unit=unit,
#                                                       description=description)
#
#     def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
#         @wraps(f)
#         def wrapper(*args: Any, **kwargs: Dict[Any, Any]) -> Any:
#             counters[counter_name].add(1)
#             return f(*args, **kwargs)
#
#         return wrapper
#
#     return decorator


telemetry = OTELTelemetryClient(
    service_name=os.environ.get("OTEL_SERVICE_NAME", "item-service"),
    otel_endpoint=os.environ.get("OTEL_ENDPOINT", "http://localhost:4317"),
    trace_granularity=os.environ.get("OTEL_TRACE_GRANULARITY", OpenTelemetryGranularity.ALL),
)
