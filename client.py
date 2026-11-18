"""Inventory client: select either replica for reads; write to the Primary."""


class InventoryClient:
    def __init__(self, inventory):
        self._inventory = inventory

    def read(self, replica="primary"):
        return self._inventory.read(replica)

    def update(self, stock):
        return self._inventory.update(stock)
