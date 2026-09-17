"""
db.py
Pool de 5 conexiones para PostgreSQL.

Dependencia:
    pip install "psycopg[binary,pool]"

Variables de entorno esperadas:
    DB_HOST
    DB_PORT
    DB_NAME
    DB_USER
    DB_PASSWORD
"""

import os
from psycopg_pool import ConnectionPool


DATABASE_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '5433')}"
    f"/{os.getenv('DB_NAME')}"
)

# Pool fijo de 5 conexiones.
# min_size=5: mantiene 5 conexiones disponibles.
# max_size=5: nunca tendrá más de 5 conexiones simultáneas.
pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=5,
    max_size=5,
    open=True,
)


def get_connection():
    """
    Obtiene una conexión disponible del pool.

    Uso:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
    """
    return pool.connection()


def close_pool():
    """Cierra todas las conexiones del pool."""
    pool.close()


def check_connection():
    """Comprueba que PostgreSQL sea accesible."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()

        return True

    except Exception as error:
        print(f"Error conectando a PostgreSQL: {error}")
        return False


if __name__ == "__main__":
    if check_connection():
        print("OK: PostgreSQL conectado correctamente.")
        print("Pool configurado con 5 conexiones.")
    else:
        print("ERROR: No fue posible conectarse a PostgreSQL.")
