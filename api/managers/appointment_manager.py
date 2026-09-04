from datetime import datetime
from typing import List, Optional

from api.managers.db import load_db
from api.schema.appointments import Appointment


class AppointmentManager:
    def __init__(self):
        data = load_db()
        self.appointments: dict[str, Appointment] = {
            item["id"]: Appointment(
                id=item["id"],
                fecha_hora=datetime.fromisoformat(item["fecha_hora"]),
                cliente_id=item["cliente_id"],
                servicio_id=item["servicio_id"],
            )
            for item in data["appointments"]
        }

    def get_appointments(self) -> List[Appointment]:
        return list(self.appointments.values())

    def get_appointment_by_id(self, id: str) -> Optional[Appointment]:
        return self.appointments.get(str(id))

    def get_by_client_id(self, client_id: int) -> List[Appointment]:
        return [a for a in self.appointments.values() if a.cliente_id == client_id]

    def get_by_service_id(self, service_id: int) -> List[Appointment]:
        return [a for a in self.appointments.values() if a.servicio_id == service_id]
