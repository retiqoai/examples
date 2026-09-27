# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
An in-process stand-in for a RetiQo instance host, used by `--offline` runs and the tests.

It implements the subset of the RTISurrogate API the examples use: handle lookups,
publish/subscribe, object registration, attribute updates with ownership checks,
interactions, and value-update requests. It is a teaching and testing aid, not a
replacement for RetiQo: there is no persistence, signing, consensus or network.
"""
import json
from typing import Dict, List, Optional, Set

from retiqo.rti.reflected_attributes import ReflectedAttributes
from retiqo.rti.received_interaction import ReceivedInteraction


class LocalExecution:
    """One state channel execution shared by every LocalRTI that joins it."""

    def __init__(self, name: str, scd_text: str) -> None:
        self.name = name
        self._next = 1
        self.class_handles: Dict[str, int] = {}
        self.class_attributes: Dict[int, Dict[str, int]] = {}
        self.interaction_handles: Dict[str, int] = {}
        self.interaction_parameters: Dict[int, Dict[str, int]] = {}
        self._load(json.loads(scd_text))
        self.members: List["LocalRTI"] = []
        # object handle -> {class, name, owner, values}
        self.objects: Dict[int, dict] = {}
        self.object_names: Dict[str, int] = {}

    def _handle(self) -> int:
        handle = self._next
        self._next += 1
        return handle

    def _load(self, scd: dict) -> None:
        def walk_entities(entities, prefix, inherited):
            for entity in entities:
                full = f"{prefix}.{entity['name']}" if prefix else entity["name"]
                names = inherited + [a["name"] for a in entity.get("attributes", [])]
                handle = self._handle()
                self.class_handles[full] = handle
                self.class_attributes[handle] = {n: self._handle() for n in names}
                walk_entities(entity.get("entities", []), full, names)

        def walk_interactions(interactions, prefix, inherited):
            for interaction in interactions:
                full = f"{prefix}.{interaction['name']}" if prefix else interaction["name"]
                names = inherited + list(interaction.get("parameters", []))
                handle = self._handle()
                self.interaction_handles[full] = handle
                self.interaction_parameters[handle] = {n: self._handle() for n in names}
                walk_interactions(interaction.get("interactions", []), full, names)

        walk_entities(scd.get("entities", []), "", [])
        walk_interactions(scd.get("interactions", []), "", [])


class LocalFederation:
    """Holds executions by name, like an instance host would."""

    def __init__(self) -> None:
        self.executions: Dict[str, LocalExecution] = {}

    def connect(self) -> "LocalRTI":
        return LocalRTI(self)


class LocalRTI:
    """Per-agent connection to a LocalFederation. Mirrors RTISurrogate method names."""

    def __init__(self, federation: LocalFederation) -> None:
        self.federation = federation
        self.execution: Optional[LocalExecution] = None
        self.actor = None
        self.published: Set[int] = set()
        self.subscribed: Dict[int, Set[int]] = {}
        self.published_interactions: Set[int] = set()
        self.subscribed_interactions: Set[int] = set()

    # ----- execution lifecycle ---------------------------------------------

    async def create_state_channel_execution(self, execution_name: str, scd: str) -> None:
        if execution_name in self.federation.executions:
            raise RuntimeError(f"execution {execution_name} already exists")
        self.federation.executions[execution_name] = LocalExecution(execution_name, scd)

    async def destroy_state_channel_execution(self, execution_name: str) -> None:
        self.federation.executions.pop(execution_name, None)

    async def join_state_channel_execution(self, actor_type: str, state_channel_execution_name: str,
                                           public_key: bytes, actor_reference) -> bytes:
        self.execution = self.federation.executions[state_channel_execution_name]
        self.actor = actor_reference
        self.execution.members.append(self)
        return b""

    async def resign_state_channel_execution(self, resign_action: int) -> None:
        if self.execution and self in self.execution.members:
            self.execution.members.remove(self)

    # ----- handle lookups ----------------------------------------------------

    async def get_object_class_handle(self, name: str) -> int:
        return self.execution.class_handles[name]

    async def get_attribute_handle(self, name: str, the_class: int) -> int:
        return self.execution.class_attributes[the_class][name]

    async def get_interaction_class_handle(self, name: str) -> int:
        return self.execution.interaction_handles[name]

    async def get_parameter_handle(self, name: str, the_interaction: int) -> int:
        return self.execution.interaction_parameters[the_interaction][name]

    async def get_object_instance_name(self, the_object: int) -> str:
        return self.execution.objects[the_object]["name"]

    # ----- declarations ------------------------------------------------------

    async def publish_object_class(self, the_class: int, attribute_list) -> None:
        self.published.add(the_class)

    async def subscribe_object_class_attributes(self, the_class: int, attribute_list) -> None:
        self.subscribed[the_class] = set(attribute_list)
        for handle, obj in list(self.execution.objects.items()):
            if obj["class"] == the_class and obj["owner"] is not self:
                await self.actor.discover_object_instance(handle, the_class, obj["name"])

    async def publish_interaction_class(self, the_interaction: int) -> None:
        self.published_interactions.add(the_interaction)

    async def subscribe_interaction_class(self, the_class: int) -> None:
        self.subscribed_interactions.add(the_class)

    # ----- objects and interactions -----------------------------------------

    async def register_object_instance(self, the_class: int, the_object_name: Optional[str] = None) -> int:
        if the_class not in self.published:
            raise RuntimeError("ObjectClassNotPublished")
        execution = self.execution
        if the_object_name in execution.object_names:
            raise RuntimeError(f"ObjectAlreadyRegistered: {the_object_name}")
        handle = execution._handle()
        name = the_object_name or f"object-{handle}"
        execution.objects[handle] = {"class": the_class, "name": name, "owner": self, "values": {}}
        execution.object_names[name] = handle
        for member in list(execution.members):
            if member is not self and the_class in member.subscribed:
                await member.actor.discover_object_instance(handle, the_class, name)
        return handle

    async def update_attribute_values(self, the_object: int, the_attributes, user_supplied_tag: bytes) -> None:
        obj = self.execution.objects[the_object]
        if obj["owner"] is not self:
            raise PermissionError("AttributeNotOwned")
        for handle, value in the_attributes:
            obj["values"][handle] = value
        for member in list(self.execution.members):
            if member is self or obj["class"] not in member.subscribed:
                continue
            reflected = ReflectedAttributes()
            for handle, value in the_attributes:
                if handle in member.subscribed[obj["class"]]:
                    reflected.add(handle, value)
            if reflected.size():
                await member.actor.reflect_attribute_values(the_object, reflected, user_supplied_tag)

    async def send_interaction(self, the_interaction: int, the_parameters, user_supplied_tag: bytes) -> None:
        if the_interaction not in self.published_interactions:
            raise RuntimeError("InteractionClassNotPublished")
        for member in list(self.execution.members):
            if member is not self and the_interaction in member.subscribed_interactions:
                received = ReceivedInteraction(the_interaction)
                for handle, value in the_parameters:
                    received.add_parameter(handle, value)
                await member.actor.receive_interaction(the_interaction, received, user_supplied_tag)

    async def request_class_attribute_value_update(self, the_class: int, attribute_list) -> None:
        for handle, obj in list(self.execution.objects.items()):
            owner = obj["owner"]
            if obj["class"] == the_class and owner is not self and owner in self.execution.members:
                await owner.actor.provide_attribute_value_update(handle, attribute_list)
