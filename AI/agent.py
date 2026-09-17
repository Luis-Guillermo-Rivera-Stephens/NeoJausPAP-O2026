from agents import Agent, set_tracing_disabled
from openai import AsyncOpenAI
import os

from AI.tools import call_graphql

client = AsyncOpenAI(base_url=os.getenv("AI_BASE_URL"), api_key=os.getenv("AI_API_KEY"))
set_tracing_disabled(disabled=True)

agent = Agent(
    name="GraphQL Agent",
    instructions=(
        "Consultas la API GraphQL con call_graphql. Queries válidas, camelCase (fechaHora). "
        "Raíces: clients, client(id), services, service(id), appointments, appointment(id). "
        "Client: id name email phone appointments | Service: id name description appointments | "
        "Appointment: id fechaHora cliente servicio. "
        "Solo campos necesarios; si falla, corrige y reintenta. Español, conciso."
    ),
    tools=[call_graphql],
    model="gpt-4o-mini",
)


