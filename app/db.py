from app.telemetry import OTELTelemetryClient, OpenTelemetryGranularity


class DummyDBService:
    def __init__(self):
        self.items = {}

    @OTELTelemetryClient.trace_method("DummyDBService.create_item", OpenTelemetryGranularity.DB)
    def create_item(self, item_id, item):
        if item_id in self.items:
            raise Exception(f"Item with id {item_id} already exists.")
        self.items[item_id] = item

    @OTELTelemetryClient.trace_method("DummyDBService.read_item", OpenTelemetryGranularity.DB)
    def read_item(self, item_id):
        if item_id not in self.items:
            raise Exception(f"Item with id {item_id} does not exist.")
        return self.items[item_id]

    @OTELTelemetryClient.trace_method("DummyDBService.update_item", OpenTelemetryGranularity.DB)
    def update_item(self, item_id, item):
        if item_id not in self.items:
            raise Exception(f"Item with id {item_id} does not exist.")
        self.items[item_id] = item

    @OTELTelemetryClient.trace_method("DummyDBService.delete_item", OpenTelemetryGranularity.DB)
    def delete_item(self, item_id):
        if item_id not in self.items:
            raise Exception(f"Item with id {item_id} does not exist.")
        del self.items[item_id]
