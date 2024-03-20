import logging
import random
import time

from app.exceptions import ItemNotFoundException, ItemAlreadyExistsException
from app.telemetry import OTELTelemetryClient, OpenTelemetryGranularity

logger = logging.getLogger(__name__)

items = {}


def simulate_slow_db():
    time.sleep(random.randint(1, 3))


class DummyDBService:
    def __init__(self):
        self.items = items

    @OTELTelemetryClient.trace_method("DummyDBService.create_item", OpenTelemetryGranularity.DB)
    def db_create_item(self, item_id, item):
        logger.debug(f"DummyDBService::db_create_item - {item_id}")
        if item_id in self.items:
            raise ItemAlreadyExistsException(f"Item with id {item_id} already exists.")
        self.items[item_id] = {"item_id": item_id, "item": item}
        simulate_slow_db()
        return self.items[item_id]

    @OTELTelemetryClient.trace_method("DummyDBService.read_item", OpenTelemetryGranularity.DB)
    def db_read_item(self, item_id):
        logger.debug(f"DummyDBService::db_read_item - {item_id}")
        if item_id not in self.items:
            raise ItemNotFoundException(f"Item with id {item_id} does not exist.")
        simulate_slow_db()
        return self.items[item_id]

    @OTELTelemetryClient.trace_method("DummyDBService.update_item", OpenTelemetryGranularity.DB)
    def db_update_item(self, item_id, item):
        logger.debug(f"DummyDBService::db_update_item - {item_id}")
        if item_id not in self.items:
            raise ItemNotFoundException(f"Item with id {item_id} does not exist.")
        self.items[item_id] = {"item_id": item_id, "item": item}
        simulate_slow_db()
        return self.items[item_id]

    @OTELTelemetryClient.trace_method("DummyDBService.list_items", OpenTelemetryGranularity.DB)
    def db_list_items(self):
        simulate_slow_db()
        return self.items

    @OTELTelemetryClient.trace_method("DummyDBService.delete_item", OpenTelemetryGranularity.DB)
    def db_delete_item(self, item_id):
        logger.debug(f"DummyDBService::db_delete_item - {item_id}")
        if item_id not in self.items:
            raise ItemNotFoundException(f"Item with id {item_id} does not exist.")
        simulate_slow_db()
        del self.items[item_id]

    def close(self):
        """Close the database connection"""
        pass
