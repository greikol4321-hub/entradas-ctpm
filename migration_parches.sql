-- CTPM — migración parches auditoría (Postgres Supabase)
-- Aplica con: psql "$DATABASE_URL" -f migration_parches.sql
-- o pega en Supabase Dashboard → SQL Editor

-- 1. Teléfono si falta (idempotente)
ALTER TABLE entradas ADD COLUMN IF NOT EXISTS telefono VARCHAR(20) DEFAULT NULL;

-- 2. Índices para /api/finanzas y /api/entradas (evitan full scan)
CREATE INDEX IF NOT EXISTS idx_estado ON entradas(estado);
CREATE INDEX IF NOT EXISTS idx_estado_ubicacion ON entradas(estado, ubicacion);
CREATE INDEX IF NOT EXISTS idx_fecha_compra ON entradas(fecha_compra DESC);
CREATE INDEX IF NOT EXISTS idx_mesa ON entradas(mesa_numero);
CREATE INDEX IF NOT EXISTS idx_ubicacion_mesa_estado ON entradas(ubicacion, mesa_numero, estado);

-- 3. Constraint lógica: 1 mesa = 1 entrada Pendiente/Aprobada (el código ya hace FOR UPDATE, esto es defensa en DB)
CREATE UNIQUE INDEX IF NOT EXISTS uq_mesa_ocupada ON entradas(mesa_numero) WHERE ubicacion='Mesas' AND estado IN ('Pendiente','Aprobada');

-- 4. Auditoría si no existe (para log_audit)
CREATE TABLE IF NOT EXISTS public.auditoria (
  id SERIAL PRIMARY KEY,
  accion TEXT NOT NULL,
  entradas_id UUID,
  actor TEXT,
  ip TEXT,
  detalle JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auditoria_accion ON public.auditoria(accion);
CREATE INDEX IF NOT EXISTS idx_auditoria_created ON public.auditoria(created_at DESC);

-- Verificación
SELECT 'OK migration_parches.sql aplicado' as status;
