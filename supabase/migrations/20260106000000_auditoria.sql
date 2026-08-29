-- Auditoria para acciones críticas (aprobar/rechazar/desbloquear/validar/login)
CREATE TABLE IF NOT EXISTS public.auditoria (
  id BIGSERIAL PRIMARY KEY,
  accion TEXT NOT NULL CHECK (accion IN ('aprobar','rechazar','desbloquear','validar','login_ok','login_fail','comprar')),
  entradas_id UUID REFERENCES public.entradas(id) ON DELETE SET NULL,
  actor TEXT,
  ip TEXT,
  detalle JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auditoria_accion ON public.auditoria(accion);
CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON public.auditoria(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_entradas ON public.auditoria(entradas_id);
ALTER TABLE public.auditoria ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "auditoria read restricted" ON public.auditoria;
CREATE POLICY "auditoria read restricted" ON public.auditoria FOR SELECT TO authenticated, service_role USING (true);
DROP POLICY IF EXISTS "auditoria write service" ON public.auditoria;
CREATE POLICY "auditoria write service" ON public.auditoria FOR ALL TO service_role USING (true) WITH CHECK (true);
COMMENT ON TABLE public.auditoria IS 'Audit trail para acciones críticas del sistema';
