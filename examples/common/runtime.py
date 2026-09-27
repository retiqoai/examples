# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Connect agents to a state channel execution, either on a RetiQo instance host or offline.

Online, every agent connects as its own agent (device) registered in your RetiQo
application and joins the execution over an authenticated WebSocket. Offline (`--offline`),
agents share an in-process LocalFederation so you can read and run the flow without a host.

Agent credentials (online only)
-------------------------------
The host only accepts agents that were provisioned in advance: each agent must first be
created in the portal, in your application, with status "Pending".
List their IDs, one per line, in `.retiqo/devices.txt` at the repository root. The first time
an agent slot is used, its device is provisioned: it generates its own key pair and registers
its address with the host. The address and private key are saved to `.retiqo/credentials.json`
(git-ignored) and reused on every later run, so each device is provisioned only once.
Agents take devices in the order they join, so the same pool serves every example.
"""
import argparse
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

from .actor import MemoryActor
from .local import LocalFederation
from .memory import InstitutionalMemory


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class Settings:
    host_url: str = field(default_factory=lambda: os.getenv("RETIQO_HOST_URL", "ws://localhost:8080/ws"))
    app_id: str = field(default_factory=lambda: os.getenv("RETIQO_APP_ID", ""))
    devices_file: Path = field(default_factory=lambda: Path(
        os.getenv("RETIQO_DEVICES_FILE", str(REPO_ROOT / ".retiqo" / "devices.txt"))))
    credentials_file: Path = field(default_factory=lambda: Path(
        os.getenv("RETIQO_CREDENTIALS_FILE", str(REPO_ROOT / ".retiqo" / "credentials.json"))))

    def contract_id(self, example: str) -> str:
        """Optional: the ID of a contract in the portal holding this example's schema.scd.
        Set RETIQO_CONTRACT_ID_<EXAMPLE> (e.g. RETIQO_CONTRACT_ID_OPTIONS_HEDGING), or
        RETIQO_CONTRACT_ID for all. When empty, the schema text is sent with the request."""
        key = "RETIQO_CONTRACT_ID_" + example.upper().replace("-", "_")
        return os.getenv(key) or os.getenv("RETIQO_CONTRACT_ID", "")


def parse_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--offline", action="store_true",
                        help="run against an in-process simulation instead of a RetiQo host")
    return parser.parse_args()


@dataclass
class Agent:
    name: str
    actor: MemoryActor
    rti: object
    memory: InstitutionalMemory
    transport: Optional[object] = None


class ExecutionSession:
    """Creates one execution and joins agents to it."""

    def __init__(self, example_dir: Path, execution_prefix: str, offline: bool,
                 settings: Optional[Settings] = None) -> None:
        self.example = example_dir.name
        self.schema_text = (example_dir / "schema.scd").read_text()
        self.execution_name = f"{execution_prefix}-{uuid.uuid4().hex[:8]}"
        self.offline = offline
        self.settings = settings or Settings()
        self.agents: List[Agent] = []
        self._federation = LocalFederation() if offline else None
        self._created = False
        self._next_slot = 0

    async def join(self, name: str, actor_type: str) -> Agent:
        """Connect a new agent, joining (and on first use creating) the execution."""
        actor = MemoryActor(name)
        transport = None
        if self.offline:
            rti = self._federation.connect()
            public_key = b""
        else:
            rti, transport, public_key = await self._connect_online(name)

        if not self._created:
            source = self.settings.contract_id(self.example) or self.schema_text
            await rti.create_state_channel_execution(self.execution_name, source)
            self._created = True

        await rti.join_state_channel_execution(actor_type, self.execution_name, public_key, actor)
        memory = InstitutionalMemory(rti, name)
        actor.attach(memory)
        await memory.connect()
        agent = Agent(name, actor, rti, memory, transport)
        self.agents.append(agent)
        return agent

    async def leave(self, agent: Agent) -> None:
        """Resign one agent. Records other agents already hold stay in their ledgers."""
        await _resign(agent)
        if agent.transport is not None:
            await _close_online(agent)
        self.agents.remove(agent)

    async def close(self) -> None:
        """Resign every agent, destroy the execution, then disconnect."""
        remaining = list(self.agents)
        for agent in remaining:
            await _resign(agent)
        if self._created:
            closer = self._federation.connect() if self.offline else (remaining[0].rti if remaining else None)
            if closer is not None:
                try:
                    await closer.destroy_state_channel_execution(self.execution_name)
                except Exception as exc:
                    print(f"destroy failed: {exc}")
        for agent in remaining:
            if agent.transport is not None:
                await _close_online(agent)
        self.agents.clear()

    async def _connect_online(self, name: str):
        from retiqo import RTI
        from retiqo.crypto.ec_key import ECKey
        from retiqo.transport import WebSocketTransportProvider
        from retiqo.ws.provisioning import provision_device

        if not self.settings.app_id:
            raise SystemExit(
                "RETIQO_APP_ID is not set. Create an application in the RetiQo portal, put its ID "
                "in .env (see .env.example and the README), or run with --offline."
            )
        device_id = self._device_for_next_slot(name)
        credentials = _load_json(self.settings.credentials_file)
        if device_id in credentials:
            address = credentials[device_id]["address"]
            private_key = bytes.fromhex(credentials[device_id]["private_key"])
        else:
            print(f"[{name}] provisioning agent {device_id} (first use)")
            try:
                address, private_key = await provision_device(self.settings.host_url, self.settings.app_id, device_id)
            except Exception as exc:
                raise SystemExit(
                    f"Provisioning agent {device_id} failed: {exc}\n"
                    "The host only accepts agents provisioned in advance. Check that this ID was created in "
                    f"the portal in application {self.settings.app_id}, with status Pending (not already "
                    "Active), and that the application is deployed to the host at "
                    f"{self.settings.host_url}. An agent that is already Active can only be used with the "
                    "credentials saved when it was first provisioned."
                ) from exc
            credentials[device_id] = {"address": address, "private_key": private_key.hex()}
            _save_json(self.settings.credentials_file, credentials)

        transport = WebSocketTransportProvider(self.settings.host_url, address, private_key)
        await transport.connect()
        rti = await RTI.create_rti_surrogate_async(transport)
        if rti is None:
            raise RuntimeError(f"could not connect {name} to {self.settings.host_url}")
        public_key = ECKey.from_private(private_key).get_public_key_bytes(compressed=False)
        if public_key[:1] == b"\x04":
            public_key = public_key[1:]
        return rti, transport, public_key

    def _device_for_next_slot(self, name: str) -> str:
        path = self.settings.devices_file
        pool = []
        if path.exists():
            pool = [line.strip() for line in path.read_text().splitlines()
                    if line.strip() and not line.strip().startswith("#")]
        if self._next_slot >= len(pool):
            raise SystemExit(
                f"{name} needs agent #{self._next_slot + 1}, but {path} lists {len(pool)} agent ID(s). "
                "Create more agents in the RetiQo portal (status: Pending, in your application) and add "
                "their IDs to that file, one per line. See 'Running against a RetiQo host' in the README."
            )
        device_id = pool[self._next_slot]
        self._next_slot += 1
        return device_id


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    try:
        path.chmod(0o600)  # private keys: readable by you only
    except OSError:
        pass


async def _resign(agent: Agent) -> None:
    """Resign, releasing attributes if the agent still owns any.
    Resign actions: 4 = NO_ACTION, 1 = RELEASE_ATTRIBUTES, 3 = DELETE_OBJECTS_AND_RELEASE_ATTRIBUTES."""
    last_error = None
    for action in (4, 1, 3):
        try:
            await agent.rti.resign_state_channel_execution(action)
            return
        except Exception as exc:
            text = f"{type(exc).__name__} {exc}".lower()
            if "notexecutionmember" in text.replace(" ", "") or "not execution member" in text:
                return
            last_error = exc
    print(f"[{agent.name}] resign failed: {last_error}")


async def _close_online(agent: Agent) -> None:
    from retiqo import RTI
    try:
        RTI.destroy_rti_surrogate(agent.rti)
    except Exception:
        pass
    try:
        await agent.transport.disconnect()
    except Exception:
        pass


def banner(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)
