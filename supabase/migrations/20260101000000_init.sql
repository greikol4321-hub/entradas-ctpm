-- Sistema Entradas CTPM — Supabase Postgres
-- Migración inicial: tablas + índices + triggers + RLS

-- Habilitar pgcrypto para gen_random_uuid() (Supabase ya lo tiene)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Tabla principal: una fila = una entrada. 3 estados del flujo.
CREATE TABLE IF NOT EXISTS public.entradas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre_completo VARCHAR(120) NOT NULL,
    cedula VARCHAR(20) NOT NULL,
    ubicacion VARCHAR(20) NOT NULL CHECK (ubicacion IN ('Gradas','Mesas')),
    telefono VARCHAR(20) DEFAULT NULL,
    comprobante_path VARCHAR(255) NOT NULL,
    qr_path VARCHAR(255) DEFAULT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente','Aprobada','Usada')),
    fecha_compra TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_aprobacion TIMESTAMPTZ DEFAULT NULL,
    fecha_uso TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.entradas IS 'Entradas vendidas — flujo cliente / admin / portero';
COMMENT ON COLUMN public.entradas.id IS 'UUID v4, tambien es el contenido del QR';
COMMENT ON COLUMN public.entradas.telefono IS 'WhatsApp donde se envía el QR';
COMMENT ON COLUMN public.entradas.comprobante_path IS 'ruta relativa en /uploads';
COMMENT ON COLUMN public.entradas.qr_path IS 'ruta relativa en /static/qrcodes';

CREATE INDEX IF NOT EXISTS idx_entradas_estado ON public.entradas(estado);
CREATE INDEX IF NOT EXISTS idx_entradas_cedula ON public.entradas(cedula);
CREATE INDEX IF NOT EXISTS idx_entradas_telefono ON public.entradas(telefono);

-- Trigger para mantener updated_at
CREATE OR REPLACE FUNCTION public.set_updated_at() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_entradas_updated_at ON public.entradas;
CREATE TRIGGER trg_entradas_updated_at
  BEFORE UPDATE ON public.entradas
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Usuarios del panel administrativo
CREATE TABLE IF NOT EXISTS public.usuarios (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL DEFAULT 'admin' CHECK (rol IN ('admin','portero')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.usuarios IS 'Usuarios del panel admin/portero';
CREATE INDEX IF NOT EXISTS idx_usuarios_username ON public.usuarios(username);

DROP TRIGGER IF EXISTS trg_usuarios_updated_at ON public.usuarios;
CREATE TRIGGER trg_usuarios_updated_at
  BEFORE UPDATE ON public.usuarios
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- RLS: lectura por anon, escritura solo por service_role
ALTER TABLE public.entradas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "entradas read all" ON public.entradas;
CREATE POLICY "entradas read all" ON public.entradas
  FOR SELECT USING (true);

DROP POLICY IF EXISTS "entradas write service" ON public.entradas;
CREATE POLICY "entradas write service" ON public.entradas
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "usuarios read self" ON public.usuarios;
CREATE POLICY "usuarios read self" ON public.usuarios
  FOR SELECT TO service_role USING (true);

DROP POLICY IF EXISTS "usuarios write service" ON public.usuarios;
CREATE POLICY "usuarios write service" ON public.usuarios
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Storage: bucket para comprobantes (crear en SQL Editor de Supabase si falla aquí):
-- INSERT INTO storage.buckets (id, name, public) VALUES ('comprobantes', 'comprobantes', false) ON CONFLICT DO NOTHING;
