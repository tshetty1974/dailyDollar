"""
Expose the Risk Analyst over the Agent-to-Agent (A2A) protocol.

Every other agent in this system is a Python object: to use one you must
import it, which means sharing a process, a language and a framework.
A2A removes that constraint. This script runs the Risk Analyst as an
HTTP service with a standard contract, so anything that speaks A2A can
send it work -- a Node service, a .NET agent, another team's
orchestrator -- without importing a line of this codebase.

The symmetry with MCP is the point: MCP is how an agent consumes tools,
A2A is how an agent is consumed by other agents. This project does both.

The Risk Analyst was chosen deliberately. It is the most reusable agent
here -- pressure-testing an investment thesis is useful to anyone doing
that kind of analysis, whereas the Synthesis agent is bound to this
system's own output schema.

Run:
    PYTHONPATH=src python3 src/a2a_server.py

Then, from another process:
    PYTHONPATH=src python3 tests/test_a2a.py
"""

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface
from starlette.applications import Starlette

# The package is installed as agent_framework_a2a but is also exposed
# under the agent_framework.a2a namespace depending on the build, so
# both spellings are accepted rather than betting on one.
try:
    from agent_framework_a2a import A2AExecutor
except ImportError:  # pragma: no cover
    from agent_framework.a2a import A2AExecutor

from agents.risk import risk_agent


HOST = "127.0.0.1"
PORT = 9999

BASE_URL = f"http://{HOST}:{PORT}/"


# The agent card is A2A's discovery document: it tells a caller what
# this agent is, what it accepts, and how to reach it. A client can
# fetch it and decide whether this agent is useful without any prior
# knowledge of the implementation.
agent_card = AgentCard(
    name="Risk Analyst",
    description=(
        "Pressure-tests an investment thesis. Identifies business, "
        "valuation, competitive, regulatory and concentration risks, "
        "challenges optimistic assumptions, and describes the downside "
        "scenarios that would invalidate the thesis. Does not give "
        "buy/sell recommendations or position sizes."
    ),
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=True),
    supported_interfaces=[
        AgentInterface(url=BASE_URL, protocol_binding="JSONRPC"),
    ],
    skills=[],
)


# A2AExecutor is the adapter: it takes an Agent Framework agent and makes
# it drivable by the A2A protocol, translating incoming tasks into
# agent.run() calls and the responses back into A2A events.
request_handler = DefaultRequestHandler(
    agent_executor=A2AExecutor(risk_agent, stream=True),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)


app = Starlette(
    routes=[
        # Serves the agent card so callers can discover this agent.
        *create_agent_card_routes(agent_card),
        # Serves the JSON-RPC endpoint that actually runs tasks.
        *create_jsonrpc_routes(request_handler, "/"),
    ],
)


if __name__ == "__main__":

    print(f">>> Risk Analyst available over A2A at {BASE_URL}")
    print(f">>> agent card: {BASE_URL}.well-known/agent-card.json")
    print(">>> stop with Ctrl-C\n")

    uvicorn.run(app, host=HOST, port=PORT)
