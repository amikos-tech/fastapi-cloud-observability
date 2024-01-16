from app.telemetry import OTELTelemetryClient, OpenTelemetryGranularity


class ItemService:
    def __init__(self, db):
        self.db = db

    @OTELTelemetryClient.trace_method("ItemService.create_item", OpenTelemetryGranularity.SERVICE)
    def create_item(self, item):
        # Insert the item into the database
        self.db.insert(item)

    def read_item(self, item_id):
        # Fetch the item from the database
        item = self.db.fetch(item_id)
        return item

    def update_item(self, item_id, item):
        # Update the item in the database
        self.db.update(item_id, item)

    def delete_item(self, item_id):
        # Delete the item from the database
        self.db.delete(item_id)
