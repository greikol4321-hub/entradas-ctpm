-- Mejoras ponytail 2026-08-29: integridad + performance + RLS
-- telefono y codigo NOT NULL, monto sin 0, mesa 1..12, chk ubicacion, indices fecha/estado, RLS restringido
ALTER TABLE public.entradas ALTER COLUMN telefono SET NOT NULL;
ALTER TABLE public.entradas ALTER COLUMN codigo SET NOT NULL;
DROP INDEX IF EXISTS public.idx_entradas_codigo;
ALTER TABLE public.entradas DROP CONSTRAINT IF EXISTS entradas_monto_check;
ALTER TABLE public.entradas ADD CONSTRAINT entradas_monto_check CHECK (monto IN (5000,10000));
ALTER TABLE public.entradas DROP CONSTRAINT IF EXISTS entradas_mesa_numero_check;
ALTER TABLE public.entradas ADD CONSTRAINT entradas_mesa_numero_check CHECK (mesa_numero BETWEEN 1 AND 12);
ALTER TABLE public.entradas ADD CONSTRAINT chk_mesa_ubicacion CHECK (
  (ubicacion='Gradas' AND mesa_numero IS NULL) OR (ubicacion='Mesas' AND mesa_numero IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_entradas_fecha ON public.entradas(fecha_compra DESC);
CREATE INDEX IF NOT EXISTS idx_entradas_estado_ubicacion ON public.entradas(estado, ubicacion);
DROP POLICY IF EXISTS "entradas read all" ON public.entradas;
CREATE POLICY "entradas read restricted" ON public.entradas FOR SELECT TO authenticated, service_role USING (true);
