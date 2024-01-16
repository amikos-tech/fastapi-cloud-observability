import logging
import uuid

from app.db import DummyDBService
from app.telemetry import OTELTelemetryClient, OpenTelemetryGranularity

logger = logging.getLogger(__name__)


class ItemService:
    def __init__(self, db):
        self.db: DummyDBService = db

    @OTELTelemetryClient.trace_method("ItemService.create_item", OpenTelemetryGranularity.SERVICE)
    def create_item(self, item):
        logger.info("ItemService::create_item")
        return self.db.db_create_item(str(uuid.uuid4()), item)

    @OTELTelemetryClient.trace_method("ItemService.read_item", OpenTelemetryGranularity.SERVICE)
    def read_item(self, item_id):
        logger.info("ItemService::read_item")
        item = self.db.db_read_item(item_id)
        return item

    @OTELTelemetryClient.trace_method("ItemService.update_item", OpenTelemetryGranularity.SERVICE)
    def update_item(self, item_id, item):
        logger.info("ItemService::update_item")
        return self.db.db_update_item(item_id, item)

    @OTELTelemetryClient.trace_method("ItemService.delete_item", OpenTelemetryGranularity.SERVICE)
    def delete_item(self, item_id):
        logger.info("ItemService::delete_item")
        return self.db.db_delete_item(item_id)

    @OTELTelemetryClient.trace_method("ItemService.list_items", OpenTelemetryGranularity.SERVICE)
    def list_items(self):
        logger.info("ItemService::list_items")
        items = self.db.db_list_items()
        return items
