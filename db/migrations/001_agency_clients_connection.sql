-- Idempotente: bases ya levantadas antes de meter agency_id en 01_schema.sql
ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS agency_id uuid REFERENCES real_state_agencies (uid);

UPDATE clients SET agency_id = 'a0000000-0000-4000-8000-000000000001'
WHERE uid IN (
    'c0000000-0000-4000-8000-000000000001',
    'c0000000-0000-4000-8000-000000000002'
) AND agency_id IS NULL;

UPDATE clients SET agency_id = 'a0000000-0000-4000-8000-000000000002'
WHERE uid IN (
    'c0000000-0000-4000-8000-000000000003',
    'c0000000-0000-4000-8000-000000000004'
) AND agency_id IS NULL;
