-- =============================================================================
-- PAP - Datos dummy
-- =============================================================================
-- TODO es inventado. Ni una fila viene de produccion ni de dev.
--
-- Determinista: no se usa random(). Todo sale de aritmetica sobre el indice de
-- la fila, asi que la base es IDENTICA para todos. Dos alumnos pueden comparar
-- el resultado de una query y debe coincidir al digito.
--
-- Los timestamps son relativos a now(): se anclan al momento en que se creo el
-- volumen. Por eso "la semana pasada" siempre trae datos recien levantada la base.
-- Si con el tiempo se queda vieja: SELECT pap_refresh_timestamps();
-- =============================================================================

-- --- Agencias ----------------------------------------------------------------
INSERT INTO real_state_agencies (uid, name, timezone, cat) VALUES
  ('a0000000-0000-4000-8000-000000000001', 'Inmobiliaria Rio Verde',   'America/Mexico_City', now() - interval '400 days'),
  ('a0000000-0000-4000-8000-000000000002', 'Grupo Costa Pacifico',     'America/Tijuana',     now() - interval '300 days');

-- --- Asesores (usuarios de la plataforma) ------------------------------------
-- agency_id viene de la migración 001; 1-2 Río Verde, 3-4 Costa Pacífico.
INSERT INTO clients (uid, nickname, first_name, first_last_name, email, phone_number, agency_id, cat) VALUES
  ('c0000000-0000-4000-8000-000000000001', 'rgomez',   'Renata',  'Gomez',   'renata@riovere.mx',  '3311110001', 'a0000000-0000-4000-8000-000000000001', now() - interval '390 days'),
  ('c0000000-0000-4000-8000-000000000002', 'jsalas',   'Javier',  'Salas',   'javier@riovere.mx',  '3311110002', 'a0000000-0000-4000-8000-000000000001', now() - interval '380 days'),
  ('c0000000-0000-4000-8000-000000000003', 'mvega',    'Mariana', 'Vega',    'mariana@costapac.mx','6641110003', 'a0000000-0000-4000-8000-000000000002', now() - interval '290 days'),
  ('c0000000-0000-4000-8000-000000000004', 'aduarte',  'Andres',  'Duarte',  'andres@costapac.mx', '6641110004', 'a0000000-0000-4000-8000-000000000002', now() - interval '280 days');

-- --- Numeros de WhatsApp ("mi numero") ---------------------------------------
-- La agencia 1 tiene DOS numeros: por eso un mismo contacto puede tener dos
-- conversaciones distintas (la unique es por connection+client, no por client).
INSERT INTO whatsapp_connection (uid, agency_id, waba_id, phone_number_id, display_phone, phone_e164, name, cat) VALUES
  ('b0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000001',
   '102030405060701', '900000000000001', '+52 33 0000 0001', '+523300000001', 'Ventas Guadalajara', now() - interval '395 days'),
  ('b0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000001',
   '102030405060701', '900000000000002', '+52 33 0000 0002', '+523300000002', 'Soporte Guadalajara', now() - interval '200 days'),
  ('b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000002',
   '102030405060702', '900000000000003', '+52 664 000 0003', '+526640000003', 'Ventas Tijuana', now() - interval '295 days');

-- --- Contactos del CRM (50) --------------------------------------------------
-- Los primeros 32 son de la agencia 1, el resto de la agencia 2.
INSERT INTO crm_clients (
    uid, agency_id, created_by, assigned_to,
    first_name, first_last_name, preferred_name,
    primary_email, primary_phone, phone_country_code,
    preferred_contact_method, client_status, client_type, lead_source,
    tags, comments, wa_id, wa_profile_name, cat, uat)
SELECT
    ('d0000000-0000-4000-8000-' || lpad(i::text, 12, '0'))::uuid,
    CASE WHEN i <= 32 THEN 'a0000000-0000-4000-8000-000000000001'::uuid
                      ELSE 'a0000000-0000-4000-8000-000000000002'::uuid END,
    agente, agente,
    nombre, apellido, nombre,
    lower(translate(nombre, 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU')) || '.' ||
        lower(translate(apellido, 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU')) || i::text || '@example.mx',
    tel, '52',
    (ARRAY['whatsapp','whatsapp','phone','email']::preferred_contact_methods_v1[])[1 + (i % 4)],
    (ARRAY['new','contacted','active','active','closed','lost','inactive']::crm_client_status_v1[])[1 + (i % 7)],
    (ARRAY['buyer','renter','seller','landlord','investor','other','buyer','renter']::crm_client_types_v1[])[1 + (i % 8)],
    (ARRAY['facebook_ads','portal_inmuebles24','referido','google','whatsapp_directo'])[1 + (i % 5)],
    -- Un CASE y no un ARRAY anidado: las listas tienen largos distintos y
    -- Postgres no admite arrays 2-D irregulares.
    CASE (i % 5)
        WHEN 0 THEN ARRAY['caliente']
        WHEN 1 THEN ARRAY['tibio']
        WHEN 2 THEN ARRAY['frio']
        WHEN 3 THEN ARRAY['caliente','credito_infonavit']
        ELSE        ARRAY['referido']
    END,
    'Contacto de prueba generado para el PAP. Registro ' || i || '.',
    '52' || tel,
    nombre || ' ' || apellido,
    now() - ((120 - (i * 2)) || ' days')::interval,
    now() - ((120 - (i * 2)) || ' days')::interval
FROM (
    SELECT i,
        (ARRAY['Ana','Luis','Maria','Carlos','Sofia','Miguel','Valentina','Jorge','Regina','Diego',
               'Paola','Andres','Fernanda','Ricardo','Daniela','Emilio','Ximena','Rodrigo','Alejandra','Mauricio',
               'Camila','Hector','Lucia','Javier','Renata'])[1 + (i % 25)] AS nombre,
        (ARRAY['Garcia','Martinez','Lopez','Hernandez','Gonzalez','Ramirez','Torres','Flores','Rivera','Morales',
               'Ortiz','Castillo','Vargas','Mendoza','Guerrero','Dominguez','Cortes','Navarro','Ibarra','Rojas'])[1 + (i % 20)] AS apellido,
        lpad((3310000000 + i * 13717)::text, 10, '0') AS tel,
        CASE WHEN i <= 32
             THEN (ARRAY['c0000000-0000-4000-8000-000000000001',
                         'c0000000-0000-4000-8000-000000000002'])[1 + (i % 2)]::uuid
             ELSE (ARRAY['c0000000-0000-4000-8000-000000000003',
                         'c0000000-0000-4000-8000-000000000004'])[1 + (i % 2)]::uuid
        END AS agente
    FROM generate_series(1, 50) AS i
) AS base;

-- Unos cuantos marcados como perdidos, para que is_lost / lost_reason no esten vacios.
UPDATE crm_clients
   SET is_lost = true,
       lost_reason = (ARRAY['price','no_answer','competitor','not_interested','financing']::lost_reasons_v1[])[1 + (abs(hashtext(uid::text)) % 5)],
       lost_at = cat + interval '20 days'
 WHERE client_status = 'lost';

-- --- Especificacion de conversaciones ----------------------------------------
-- Tabla temporal: describe las 66 conversaciones con un indice k estable, para
-- poder generar los mensajes de forma determinista a partir de el.
CREATE TEMP TABLE conv_spec AS
-- 1 conversacion por contacto, en el numero principal de su agencia
SELECT
    i AS k,
    ('e0000000-0000-4000-8000-' || lpad(i::text, 12, '0'))::uuid AS conv_uid,
    ('d0000000-0000-4000-8000-' || lpad(i::text, 12, '0'))::uuid AS client_uid,
    CASE WHEN i <= 32 THEN 'b0000000-0000-4000-8000-000000000001'::uuid
                      ELSE 'b0000000-0000-4000-8000-000000000003'::uuid END AS connection_uid,
    CASE WHEN i <= 32 THEN 'a0000000-0000-4000-8000-000000000001'::uuid
                      ELSE 'a0000000-0000-4000-8000-000000000002'::uuid END AS agency_uid
FROM generate_series(1, 50) AS i
UNION ALL
-- Los contactos pares de la agencia 1 escriben tambien al segundo numero
SELECT
    50 + (i / 2) AS k,
    ('e0000000-0000-4000-8000-' || lpad((50 + (i / 2))::text, 12, '0'))::uuid,
    ('d0000000-0000-4000-8000-' || lpad(i::text, 12, '0'))::uuid,
    'b0000000-0000-4000-8000-000000000002'::uuid,
    'a0000000-0000-4000-8000-000000000001'::uuid
FROM generate_series(2, 32, 2) AS i;

-- Cuantos mensajes tiene cada conversacion (10..40) y cuando fue la ultima
-- actividad. Un tercio de las conversaciones esta activo en los ultimos 7 dias:
-- eso es lo que hace que la query estrella devuelva algo interesante.
ALTER TABLE conv_spec ADD COLUMN n_msg int;
ALTER TABLE conv_spec ADD COLUMN last_days numeric;
UPDATE conv_spec
   SET n_msg    = 10 + ((k * 7) % 31),
       last_days = CASE WHEN k % 3 = 0
                        THEN ((k * 5) % 7)::numeric            -- 0..6 dias: reciente
                        ELSE 7 + ((k * 13) % 83)::numeric      -- 7..89 dias: viejo
                   END;

INSERT INTO whatsapp_conversation (uid, agency_id, connection_id, client_id, conversation_category, window_expires_at, last_read_at, cat)
SELECT conv_uid, agency_uid, connection_uid, client_uid,
       (ARRAY['marketing','service','utility','referral'])[1 + (k % 4)],
       -- La ventana de 24h de WhatsApp: solo sigue abierta en las conversaciones recientes.
       CASE WHEN last_days < 1 THEN now() + interval '18 hours' ELSE NULL END,
       now() - (last_days || ' days')::interval + interval '1 hour',
       now() - (last_days || ' days')::interval - ((10 + ((k * 7) % 31)) * interval '3 hours')
FROM conv_spec;

-- --- Mensajes (~1,500) -------------------------------------------------------
-- j = 1 es el mas viejo de la conversacion, j = n_msg el mas reciente.
-- El mensaje 1 siempre es inbound: el contacto es quien inicia.
INSERT INTO whatsapp_message (uid, conversation_id, connection_id, wamid, direction, message_type, content, m_status, sent_by, cat)
SELECT
    ('f0000000-0000-4000-' || lpad((8000 + (s.k % 1000))::text, 4, '0') || '-' ||
     lpad((s.k * 1000 + s.j)::text, 12, '0'))::uuid,
    s.conv_uid,
    s.connection_uid,
    'wamid.HBgMNTIx' || lpad(s.k::text, 4, '0') || lpad(s.j::text, 4, '0'),
    s.direction,
    CASE WHEN (s.k + s.j) % 17 = 0 THEN 'image'
         WHEN (s.k + s.j) % 23 = 0 THEN 'audio'
         WHEN (s.k + s.j) % 31 = 0 THEN 'document'
         ELSE 'text' END,
    jsonb_build_object(
        'body',
        CASE WHEN s.direction = 'inbound' THEN
            (ARRAY[
              'Hola, vi la publicacion del departamento. Sigue disponible?',
              'Buenas tardes, cuanto es el deposito?',
              'Me interesa agendar una visita este fin de semana',
              'Aceptan credito Infonavit?',
              'Cuantas recamaras tiene?',
              'El precio es negociable?',
              'Incluye estacionamiento?',
              'Puede enviarme mas fotos por favor',
              'Que colonia es exactamente?',
              'Gracias, lo comento con mi esposa y le aviso',
              'Sigue en pie la cita de manana?',
              'Cual es el costo de mantenimiento?'
            ])[1 + ((s.k * 5 + s.j * 3) % 12)]
        ELSE
            (ARRAY[
              'Hola! Si, sigue disponible. Le comparto la ficha completa',
              'Buenas tardes, el deposito es de un mes mas la renta adelantada',
              'Claro, tengo espacio el sabado a las 11:00. Le funciona?',
              'Si, manejamos Infonavit y Fovissste. Le paso los requisitos',
              'Son 2 recamaras, 2 banos completos y balcon',
              'Hay margen de negociacion, deje lo consulto con el propietario',
              'Si, incluye un cajon techado',
              'Por supuesto, le envio el album ahora mismo',
              'Esta en Providencia, a dos calles de Av. Pablo Neruda',
              'Perfecto, quedo atento a sus comentarios',
              'Confirmado para manana. Le comparto la ubicacion',
              'El mantenimiento son $1,800 al mes e incluye seguridad'
            ])[1 + ((s.k * 7 + s.j * 5) % 12)]
        END),
    CASE WHEN s.direction = 'outbound' THEN (ARRAY['sent','delivered','read','read'])[1 + ((s.k + s.j) % 4)]
         -- Algunos entrantes quedan sin leer: eso alimenta el indice idx_wa_unread_lookup
         WHEN (s.k + s.j) % 11 = 0 THEN 'delivered'
         ELSE 'read' END,
    CASE WHEN s.direction = 'outbound' THEN s.agent_uid ELSE NULL END,
    -- El mensaje mas nuevo cae en last_days; los anteriores van hacia atras ~3h,
    -- con un desfase deterministico en minutos para que no queden en rejilla exacta.
    now()
      - (s.last_days || ' days')::interval
      - ((s.n_msg - s.j) * interval '3 hours')
      - (((s.k * s.j) % 97) * interval '1 minute')
FROM (
    SELECT c.k, c.conv_uid, c.connection_uid, c.n_msg, c.last_days, j,
           cc.assigned_to AS agent_uid,
           CASE WHEN j = 1 THEN 'inbound'
                WHEN (j * 7 + c.k) % 9 < 5 THEN 'inbound'
                ELSE 'outbound' END AS direction
    FROM conv_spec c
    JOIN crm_clients cc ON cc.uid = c.client_uid
    CROSS JOIN LATERAL generate_series(1, c.n_msg) AS j
) AS s;

-- --- Episodios (resumenes de IA) ---------------------------------------------
INSERT INTO whatsapp_conversation_episode (conversation_id, window_from, window_to, summary, key_topics, model, cost_usd_micros, cat)
SELECT c.conv_uid,
       now() - (c.last_days || ' days')::interval - interval '3 days',
       now() - (c.last_days || ' days')::interval,
       'El contacto pregunto por disponibilidad y condiciones de pago. Se le compartio '
         || 'la ficha del inmueble y se acordo dar seguimiento. Interes medio-alto.',
       (ARRAY['["disponibilidad","precio"]','["credito","infonavit"]','["visita","agenda"]',
              '["mantenimiento","amenidades"]'])[1 + (c.k % 4)]::jsonb,
       'gpt-4o-mini',
       1200 + (c.k * 37),
       now() - (c.last_days || ' days')::interval
FROM conv_spec c
WHERE c.k % 7 = 0;

DROP TABLE conv_spec;

ANALYZE;
