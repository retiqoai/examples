# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Actor base classes for the examples.

RetiQo calls back into an actor for every event in the execution. MinimalActor implements
every callback so examples only override the ones they use. MemoryActor forwards the
object callbacks to an InstitutionalMemory so the agent's ledger stays current.
"""
from typing import Optional

from retiqo.rti.actor_surrogate import ActorSurrogate


class MinimalActor(ActorSurrogate):
    """Implements every ActorSurrogate callback as a no-op."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        self._base_state = None

    def set_base_state(self, base_state) -> None:
        self._base_state = base_state

    def get_base_state(self):
        return self._base_state

    # State channel management
    async def consensus_point_registration_failed(self, consensus_point_label: str) -> None: pass
    async def consensus_point_registration_succeeded(self, consensus_point_label: str) -> None: pass
    async def announce_consensus_point(self, consensus_point_label: str, user_supplied_tag: bytes) -> None: pass
    async def state_channel_in_consensus(self, consensus_point_label: str, consensus_state) -> None: pass
    async def initiate_actor_save(self, label: str) -> None: pass
    async def state_channel_saved(self) -> None: pass
    async def state_channel_not_saved(self) -> None: pass
    async def request_state_channel_restore_succeeded(self, label: str) -> None: pass
    async def request_state_channel_restore_failed(self, label: str, reason: str) -> None: pass
    async def state_channel_restore_begun(self) -> None: pass
    async def initiate_actor_restore(self, label: str, actor_handle: int) -> None: pass
    async def state_channel_restored(self) -> None: pass
    async def state_channel_not_restored(self) -> None: pass

    # Declaration management
    async def start_registration_for_object_class(self, the_class: int) -> None: pass
    async def stop_registration_for_object_class(self, the_class: int) -> None: pass
    async def turn_interactions_on(self, the_handle: int) -> None: pass
    async def turn_interactions_off(self, the_handle: int) -> None: pass

    # Object management
    async def discover_object_instance(self, the_object: int, the_object_class: int, object_name: str) -> None: pass
    async def reflect_attribute_values(self, the_object: int, the_attributes, user_supplied_tag: bytes) -> None: pass
    async def receive_interaction(self, interaction_class: int, the_interaction, user_supplied_tag: bytes) -> None: pass
    async def remove_object_instance(self, the_object: int, user_supplied_tag: bytes) -> None: pass
    async def attributes_in_scope(self, the_object: int, the_attributes) -> None: pass
    async def attributes_out_of_scope(self, the_object: int, the_attributes) -> None: pass
    async def provide_attribute_value_update(self, the_object: int, the_attributes) -> None: pass
    async def turn_updates_on_for_object_instance(self, the_object: int, the_attributes) -> None: pass
    async def turn_updates_off_for_object_instance(self, the_object: int, the_attributes) -> None: pass

    # Ownership management
    async def request_attribute_ownership_assumption(self, the_object: int, offered_attributes, user_supplied_tag: bytes) -> None: pass
    async def attribute_ownership_divestiture_notification(self, the_object: int, released_attributes) -> None: pass
    async def attribute_ownership_acquisition_notification(self, the_object: int, secured_attributes) -> None: pass
    async def attribute_ownership_unavailable(self, the_object: int, the_attributes) -> None: pass
    async def request_attribute_ownership_release(self, the_object: int, candidate_attributes, user_supplied_tag: bytes) -> None: pass
    async def confirm_attribute_ownership_acquisition_cancellation(self, the_object: int, the_attributes) -> None: pass
    async def inform_attribute_ownership(self, the_object: int, the_attribute: int, the_owner: int) -> None: pass
    async def attribute_is_not_owned(self, the_object: int, the_attribute: int) -> None: pass
    async def attribute_owned_by_rti(self, the_object: int, the_attribute: int) -> None: pass


class MemoryActor(MinimalActor):
    """An actor whose view of decisions, reviews, objections and outcomes stays current."""

    def __init__(self, agent_name: str) -> None:
        super().__init__(agent_name)
        self.memory = None  # set with attach() once the InstitutionalMemory is connected
        self.notifications = []
        # Called with each AgentMessage this actor receives (a dict of its fields).
        self.on_message = None

    def attach(self, memory) -> None:
        self.memory = memory

    async def discover_object_instance(self, the_object: int, the_object_class: int, object_name: str) -> None:
        if self.memory is not None:
            self.memory.on_discover(the_object, the_object_class)

    async def reflect_attribute_values(self, the_object: int, the_attributes, user_supplied_tag: bytes) -> None:
        if self.memory is not None:
            self.memory.on_reflect(the_object, the_attributes)

    async def provide_attribute_value_update(self, the_object: int, the_attributes) -> None:
        if self.memory is not None:
            await self.memory.on_provide(the_object)

    async def receive_interaction(self, interaction_class: int, the_interaction, user_supplied_tag: bytes) -> None:
        tag: Optional[str] = None
        if isinstance(user_supplied_tag, bytes):
            tag = user_supplied_tag.decode("utf-8", errors="replace")
        self.notifications.append(tag)
        if self.memory is not None and self.on_message is not None:
            message = self.memory.decode_message(interaction_class, the_interaction)
            if message is not None:
                self.on_message(message)
