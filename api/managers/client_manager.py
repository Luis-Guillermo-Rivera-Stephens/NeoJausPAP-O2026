from typing import List, Optional

from api.managers.db import load_db
from api.schema.client import Client


class ClientManager:
    def __init__(self):
        data = load_db()
        self.clients: dict[int, Client] = {
            client["id"]: Client(**client) for client in data["clients"]
        }

    def get_clients(self) -> List[Client]:
        return list(self.clients.values())

    def get_client_by_id(self, id: int) -> Optional[Client]:
        return self.clients.get(id)
