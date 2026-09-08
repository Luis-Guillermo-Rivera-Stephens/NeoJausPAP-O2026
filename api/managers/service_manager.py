from typing import List, Optional

from api.managers.db import load_db
from api.schema.service import Service


class ServiceManager:
    def __init__(self):
        data = load_db()
        self.services: dict[int, Service] = {
            service["id"]: Service(**service) for service in data["services"]
        }

    def get_services(self) -> List[Service]:
        return list(self.services.values())

    def get_service_by_id(self, id: int) -> Optional[Service]:
        return self.services.get(id)
