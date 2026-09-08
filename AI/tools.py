import json

from agents import function_tool

from api.schema.schema import schema


@function_tool
def call_graphql(query: str) -> str:
    """Ejecuta una query GraphQL contra la API del proyecto y devuelve el JSON de respuesta.

    Usa esto para consultar clients, services o appointments.
    Ejemplo: { clients { id name email phone } }
    """
    print(f"[AGENT] call_graphql → API query={query!r}")
    result = schema.execute_sync(query)
    payload = {
        "data": result.data,
        "errors": [str(e) for e in result.errors] if result.errors else None,
    }
    raw = json.dumps(payload, ensure_ascii=False, default=str)
    if result.errors:
        print(f"[AGENT] call_graphql ← API con errores: {payload['errors']}")
    else:
        print(f"[AGENT] call_graphql ← API ok")
    return raw
