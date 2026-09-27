# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Write domain records (purchase orders, shipments, payments...) next to the decision record.

Each domain record carries the decisionId that authorized it, so anyone reading the
operational state can trace it back to who decided, who reviewed and why.
"""
from typing import Dict, List

from retiqo.rti.attribute_handle_set import AttributeHandleSetFactory
from retiqo.rti.supplied_attributes import SuppliedAttributesFactory


class DomainRecords:
    def __init__(self, rti) -> None:
        self.rti = rti
        self._classes: Dict[str, int] = {}
        self._attributes: Dict[str, Dict[str, int]] = {}
        self._objects: Dict[str, int] = {}

    async def declare(self, class_name: str, attributes: List[str]) -> None:
        """Publish a domain object class so this agent can write it."""
        handle = await self.rti.get_object_class_handle(f"ObjectRoot.{class_name}")
        self._classes[class_name] = handle
        self._attributes[class_name] = {
            name: await self.rti.get_attribute_handle(name, handle) for name in attributes
        }
        await self.rti.publish_object_class(
            handle, AttributeHandleSetFactory.create(list(self._attributes[class_name].values()))
        )

    async def write(self, class_name: str, object_name: str, values: Dict[str, str]) -> int:
        """Create the record on first write, then update it."""
        if object_name not in self._objects:
            self._objects[object_name] = await self.rti.register_object_instance(
                self._classes[class_name], object_name
            )
        supplied = SuppliedAttributesFactory.create()
        for name, value in values.items():
            supplied.add(self._attributes[class_name][name], str(value).encode("utf-8"))
        await self.rti.update_attribute_values(self._objects[object_name], supplied, class_name.encode())
        return self._objects[object_name]
