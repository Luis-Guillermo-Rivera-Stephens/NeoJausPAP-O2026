-- Idempotente: vector del nombre para buscar por significado.
-- ponytail: double precision[] y coseno en Python; pgvector si el catálogo deja de caber en memoria.
ALTER TABLE whatsapp_key_topic
    ADD COLUMN IF NOT EXISTS embedding double precision[];
