"""Append synthetic CRM and WhatsApp data to the local PAP database."""

import argparse
import os
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from faker import Faker
from psycopg.types.json import Jsonb
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTACT_METHODS = ("email", "phone", "whatsapp")
CLIENT_STATUSES = ("new", "contacted", "active", "closed", "lost", "inactive", "archived")
CLIENT_TYPES = ("buyer", "seller", "renter", "landlord", "investor", "developer", "other", "agent")
LOST_REASONS = ("price", "financing", "no_answer", "competitor", "not_interested", "other")
CONVERSATION_CATEGORIES = ("marketing", "service", "utility", "referral")
INBOUND_MESSAGES = (
    "Hola, me interesa conocer mas sobre una propiedad.",
    "Sigue disponible? Me gustaria agendar una visita.",
    "Me puede compartir informacion sobre el precio y la ubicacion?",
    "Aceptan credito hipotecario?",
)
OUTBOUND_MESSAGES = (
    "Hola, con gusto te comparto la informacion.",
    "Claro, podemos agendar una visita esta semana.",
    "Te envio los detalles de la propiedad para que los revises.",
    "Quedo atento a tus comentarios.",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Agrega contactos, conversaciones y mensajes ficticios a la base local."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=15,
        help="cantidad de contactos nuevos (default: 15)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="semilla para reproducir los datos generados (default: 2026)",
    )
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count debe ser mayor que cero.")
    return args


def get_local_connection():
    load_dotenv(PROJECT_ROOT / ".env")

    host = os.getenv("DB_HOST") or "localhost"
    port = int(os.getenv("DB_PORT") or "5433")
    if host.lower() not in ("localhost", "127.0.0.1", "::1") or port != 5433:
        raise ValueError(
            "Este generador solo se conecta a localhost:5433 para evitar modificar "
            "una base remota o el Postgres de trabajo."
        )

    return psycopg.connect(
        host=host,
        port=port,
        dbname=os.getenv("DB_NAME") or "papdb",
        user=os.getenv("DB_USER") or "pap",
        password=os.getenv("DB_PASSWORD") or "pap",
    )


def get_agency_options(cursor):
    cursor.execute(
        """
        SELECT a.uid, wc.uid, cl.uid
        FROM real_state_agencies AS a
        JOIN whatsapp_connection AS wc
          ON wc.agency_id = a.uid AND wc.is_active = true
        JOIN clients AS cl
          ON EXISTS (
              SELECT 1
              FROM crm_clients AS existing
              WHERE existing.agency_id = a.uid
                AND existing.assigned_to = cl.uid
          )
        WHERE a.is_active = true
        ORDER BY a.uid, wc.uid, cl.uid
        """
    )
    rows = cursor.fetchall()
    options = defaultdict(lambda: {"connections": set(), "agents": set()})
    for agency_id, connection_id, agent_id in rows:
        options[agency_id]["connections"].add(connection_id)
        options[agency_id]["agents"].add(agent_id)

    if not options:
        raise RuntimeError(
            "No hay agencias activas con un numero de WhatsApp activo y un asesor asignado. "
            "Inicializa la base con `docker compose up -d --wait` y vuelve a intentarlo."
        )
    return options


def make_unique_phone(rng, used_phones):
    prefixes = ("33", "55", "81", "664", "656")
    while True:
        prefix = rng.choice(prefixes)
        suffix = "".join(str(rng.randrange(10)) for _ in range(10 - len(prefix)))
        phone = prefix + suffix
        if phone not in used_phones:
            used_phones.add(phone)
            return phone


def make_contact(fake, rng, agency_id, agent_id, used_phones, used_wa_ids, index, now):
    first_name = fake.first_name()
    last_name = fake.last_name()[:32]
    phone = make_unique_phone(rng, used_phones)
    wa_id = f"52{phone}"
    while wa_id in used_wa_ids:
        phone = make_unique_phone(rng, used_phones)
        wa_id = f"52{phone}"
    used_wa_ids.add(wa_id)

    status = rng.choice(CLIENT_STATUSES)
    lost = status == "lost"
    created_at = now - timedelta(days=rng.randint(1, 180))
    return {
        "uid": uuid.uuid4(),
        "created_by": agent_id,
        "assigned_to": agent_id,
        "agency_id": agency_id,
        "first_name": first_name,
        "first_last_name": last_name,
        "preferred_name": first_name,
        "primary_email": f"contacto{index}.{uuid.uuid4().hex[:8]}@example.com",
        "primary_phone": phone,
        "phone_country_code": "52",
        "preferred_contact_method": rng.choice(CONTACT_METHODS),
        "client_status": status,
        "client_type": rng.choice(CLIENT_TYPES),
        "lead_source": rng.choice(
            ("facebook_ads", "portal_inmuebles24", "referido", "google", "whatsapp_directo")
        ),
        "tags": [rng.choice(("nuevo", "interesado", "seguimiento", "referido"))],
        "comments": "Contacto ficticio generado para pruebas.",
        "is_deleted": False,
        "wa_id": wa_id,
        "wa_profile_name": f"{first_name} {last_name}"[:128],
        "is_lost": lost,
        "lost_reason": rng.choice(LOST_REASONS) if lost else None,
        "lost_at": min(now, created_at + timedelta(days=rng.randint(1, 15))) if lost else None,
        "cat": created_at,
        "uat": created_at,
    }


def insert_contacts(cursor, contacts):
    cursor.executemany(
        """
        INSERT INTO crm_clients (
            uid, created_by, assigned_to, agency_id, first_name, first_last_name,
            preferred_name, primary_email, primary_phone, phone_country_code,
            preferred_contact_method, client_status, client_type, lead_source, tags,
            comments, is_deleted, wa_id, wa_profile_name, is_lost, lost_reason,
            lost_at, cat, uat
        ) VALUES (
            %(uid)s, %(created_by)s, %(assigned_to)s, %(agency_id)s, %(first_name)s,
            %(first_last_name)s, %(preferred_name)s, %(primary_email)s, %(primary_phone)s,
            %(phone_country_code)s, %(preferred_contact_method)s::preferred_contact_methods_v1,
            %(client_status)s::crm_client_status_v1, %(client_type)s::crm_client_types_v1,
            %(lead_source)s, %(tags)s, %(comments)s, %(is_deleted)s, %(wa_id)s,
            %(wa_profile_name)s, %(is_lost)s, %(lost_reason)s::lost_reasons_v1,
            %(lost_at)s, %(cat)s, %(uat)s
        )
        """,
        contacts,
    )


def make_conversation(contact, connection_id, rng, now):
    recent = rng.random() < 0.6
    days_ago = rng.randint(0, 6) if recent else rng.randint(8, 45)
    last_activity = now - timedelta(
        days=days_ago,
        hours=rng.randrange(24),
        minutes=rng.randrange(60),
    )
    count = rng.randint(5, 16)
    conversation_id = uuid.uuid4()
    return {
        "uid": conversation_id,
        "agency_id": contact["agency_id"],
        "connection_id": connection_id,
        "client_id": contact["uid"],
        "conversation_category": rng.choice(CONVERSATION_CATEGORIES),
        "window_expires_at": (
            last_activity + timedelta(hours=24)
            if last_activity >= now - timedelta(hours=24)
            else None
        ),
        "last_read_at": last_activity - timedelta(minutes=rng.randrange(60)),
        "cat": last_activity - timedelta(hours=4 * (count - 1)),
        "last_activity": last_activity,
        "message_count": count,
        "agent_id": contact["assigned_to"],
    }


def insert_conversations(cursor, conversations):
    cursor.executemany(
        """
        INSERT INTO whatsapp_conversation (
            uid, agency_id, connection_id, client_id, conversation_category,
            window_expires_at, last_read_at, cat
        ) VALUES (
            %(uid)s, %(agency_id)s, %(connection_id)s, %(client_id)s,
            %(conversation_category)s, %(window_expires_at)s, %(last_read_at)s, %(cat)s
        )
        """,
        conversations,
    )


def make_messages(conversations, rng):
    messages = []
    for conversation in conversations:
        for index in range(conversation["message_count"]):
            inbound = index == 0 or rng.random() < 0.55
            direction = "inbound" if inbound else "outbound"
            message_type = rng.choices(
                ("text", "image", "audio", "document"),
                weights=(82, 9, 6, 3),
                k=1,
            )[0]
            text = rng.choice(INBOUND_MESSAGES if inbound else OUTBOUND_MESSAGES)
            if message_type == "image":
                content = {"caption": text, "media_id": f"fake-{uuid.uuid4().hex}"}
            elif message_type == "audio":
                content = {"transcription": text, "media_id": f"fake-{uuid.uuid4().hex}"}
            elif message_type == "document":
                content = {"body": text, "filename": "ficha-inmueble-demo.pdf"}
            else:
                content = {"body": text}

            message_at = conversation["last_activity"]
            if index < conversation["message_count"] - 1:
                message_at -= timedelta(
                    hours=3 * (conversation["message_count"] - index - 1),
                    minutes=rng.randrange(60),
                )
            if direction == "inbound":
                status = rng.choice(("read", "read", "delivered"))
                sent_by = None
            else:
                status = rng.choice(("sent", "delivered", "read"))
                sent_by = conversation["agent_id"]

            messages.append(
                (
                    uuid.uuid4(),
                    conversation["uid"],
                    conversation["connection_id"],
                    f"wamid.fake.{uuid.uuid4().hex}",
                    direction,
                    message_type,
                    Jsonb(content),
                    status,
                    sent_by,
                    message_at,
                )
            )
    return messages


def insert_messages(cursor, messages):
    cursor.executemany(
        """
        INSERT INTO whatsapp_message (
            uid, conversation_id, connection_id, wamid, direction, message_type,
            content, m_status, sent_by, cat
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        messages,
    )


def make_episodes(conversations, rng):
    episodes = []
    for conversation in conversations:
        if rng.random() >= 0.2:
            continue
        window_to = conversation["last_activity"]
        episodes.append(
            (
                conversation["uid"],
                window_to - timedelta(days=3),
                window_to,
                "Resumen ficticio: el contacto solicito informacion y seguimiento.",
                Jsonb(["disponibilidad", "precio", "seguimiento"]),
                "demo-faker",
                rng.randint(100, 3000),
                window_to,
            )
        )
    return episodes


def insert_episodes(cursor, episodes):
    cursor.executemany(
        """
        INSERT INTO whatsapp_conversation_episode (
            conversation_id, window_from, window_to, summary, key_topics,
            model, cost_usd_micros, cat
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        episodes,
    )


def main():
    args = parse_args()
    rng = random.Random(args.seed)
    fake = Faker("es_MX")
    fake.seed_instance(args.seed)
    now = datetime.now(timezone.utc)

    with get_local_connection() as conn:
        with conn.cursor() as cursor:
            agency_options = get_agency_options(cursor)
            agency_ids = list(agency_options)
            cursor.execute(
                """
                SELECT agency_id, primary_phone, wa_id
                FROM crm_clients
                WHERE agency_id = ANY(%s)
                """,
                (agency_ids,),
            )
            used_phones = defaultdict(set)
            used_wa_ids = defaultdict(set)
            for agency_id, phone, wa_id in cursor.fetchall():
                if phone:
                    used_phones[agency_id].add(phone)
                if wa_id:
                    used_wa_ids[agency_id].add(wa_id)

            contacts = []
            conversations = []
            for index in range(1, args.count + 1):
                agency_id = rng.choice(agency_ids)
                options = agency_options[agency_id]
                agent_id = rng.choice(sorted(options["agents"], key=str))
                contact = make_contact(
                    fake,
                    rng,
                    agency_id,
                    agent_id,
                    used_phones[agency_id],
                    used_wa_ids[agency_id],
                    index,
                    now,
                )
                connection_id = rng.choice(sorted(options["connections"], key=str))
                contacts.append(contact)
                conversations.append(make_conversation(contact, connection_id, rng, now))

            messages = make_messages(conversations, rng)
            episodes = make_episodes(conversations, rng)

            insert_contacts(cursor, contacts)
            insert_conversations(cursor, conversations)
            insert_messages(cursor, messages)
            insert_episodes(cursor, episodes)

    print(
        f"Datos ficticios agregados: {len(contacts)} contactos, "
        f"{len(conversations)} conversaciones, {len(messages)} mensajes "
        f"y {len(episodes)} resumenes."
    )


if __name__ == "__main__":
    main()
