-- =============================================================================
-- PAP - Utilidades
-- =============================================================================

-- Re-ancla TODO el dataset a hoy.
--
-- Los datos se sembraron relativos al momento en que se creo el volumen. Si la
-- base lleva semanas levantada, "la semana pasada" empieza a salir vacia porque
-- el dataset se quedo atras. Esta funcion desplaza todos los timestamps hacia
-- adelante para que el mensaje mas reciente vuelva a ser de hace un momento.
-- Conserva intactas las distancias entre eventos, asi que las queries siguen
-- dando resultados equivalentes.
--
--   SELECT pap_refresh_timestamps();
--
-- La alternativa (mas lenta) es reconstruir: docker compose down -v && docker compose up -d
CREATE OR REPLACE FUNCTION pap_refresh_timestamps()
RETURNS text
LANGUAGE plpgsql
AS $fn$
DECLARE
    newest  timestamptz;
    shift   interval;
BEGIN
    SELECT max(cat) INTO newest FROM whatsapp_message;

    IF newest IS NULL THEN
        RETURN 'No hay mensajes: nada que re-anclar.';
    END IF;

    shift := now() - newest;

    IF shift < interval '1 hour' THEN
        RETURN 'El dataset ya esta al dia (desfase < 1 hora). No se hizo nada.';
    END IF;

    UPDATE real_state_agencies SET cat = cat + shift, uat = uat + shift;
    UPDATE clients             SET cat = cat + shift, uat = uat + shift;
    UPDATE whatsapp_connection SET cat = cat + shift, uat = uat + shift;

    UPDATE crm_clients
       SET cat = cat + shift, uat = uat + shift,
           lost_at = lost_at + shift;             -- NULL + interval sigue siendo NULL

    UPDATE whatsapp_conversation
       SET cat = cat + shift,
           window_expires_at = window_expires_at + shift,
           last_read_at = last_read_at + shift;

    UPDATE whatsapp_message SET cat = cat + shift;

    UPDATE whatsapp_conversation_episode
       SET cat = cat + shift, window_from = window_from + shift, window_to = window_to + shift;

    ANALYZE;

    RETURN format('Dataset recorrido %s hacia adelante. El mensaje mas reciente es de ahora.',
                  justify_interval(shift));
END;
$fn$;


-- Resumen rapido del contenido de la base. Util para confirmar que sembro bien.
--   SELECT * FROM pap_resumen();
CREATE OR REPLACE FUNCTION pap_resumen()
RETURNS TABLE (tabla text, filas bigint)
LANGUAGE sql
AS $fn$
    SELECT 'real_state_agencies',           count(*) FROM real_state_agencies
    UNION ALL SELECT 'clients (asesores)',  count(*) FROM clients
    UNION ALL SELECT 'crm_clients',         count(*) FROM crm_clients
    UNION ALL SELECT 'whatsapp_connection', count(*) FROM whatsapp_connection
    UNION ALL SELECT 'whatsapp_conversation', count(*) FROM whatsapp_conversation
    UNION ALL SELECT 'whatsapp_message',    count(*) FROM whatsapp_message
    UNION ALL SELECT 'whatsapp_conversation_episode', count(*) FROM whatsapp_conversation_episode;
$fn$;
