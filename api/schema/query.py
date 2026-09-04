from typing import List, Optional

import strawberry

from api.managers.appointment_manager import AppointmentManager
from api.managers.client_manager import ClientManager
from api.managers.service_manager import ServiceManager
from api.schema.appointments import Appointment
from api.schema.client import Client
from api.schema.service import Service


@strawberry.type
class Query:
    @strawberry.field
    def clients(self) -> List[Client]:
        print("[API] Query.clients")
        clients = ClientManager().get_clients()
        print(f"[API] Query.clients → {len(clients)} resultados")
        return clients

    @strawberry.field
    def client(self, id: int) -> Optional[Client]:
        print(f"[API] Query.client id={id}")
        client = ClientManager().get_client_by_id(id)
        print(f"[API] Query.client → {'encontrado' if client else 'None'}")
        return client

    @strawberry.field
    def services(self) -> List[Service]:
        print("[API] Query.services")
        services = ServiceManager().get_services()
        print(f"[API] Query.services → {len(services)} resultados")
        return services

    @strawberry.field
    def service(self, id: int) -> Optional[Service]:
        print(f"[API] Query.service id={id}")
        service = ServiceManager().get_service_by_id(id)
        print(f"[API] Query.service → {'encontrado' if service else 'None'}")
        return service

    @strawberry.field
    def appointments(self) -> List[Appointment]:
        print("[API] Query.appointments")
        appointments = AppointmentManager().get_appointments()
        print(f"[API] Query.appointments → {len(appointments)} resultados")
        return appointments

    @strawberry.field
    def appointment(self, id: strawberry.ID) -> Optional[Appointment]:
        print(f"[API] Query.appointment id={id}")
        appointment = AppointmentManager().get_appointment_by_id(str(id))
        print(f"[API] Query.appointment → {'encontrado' if appointment else 'None'}")
        return appointment
