from agents import Agent

from AI.tools import call_graphql

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
