-- Numeración secuencial + buckets Supabase
-- 1) Numeración: cada entrada tiene número correlativo empezando en 1
CREATE SEQUENCE IF NOT EXISTS public.entradas_numero_seq;

ALTER TABLE public.entradas
  ADD COLUMN IF NOT EXISTS numero INTEGER;

-- backfill existentes ordenados por fecha_compra (correlativo real)
WITH ordered AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY fecha_compra ASC, created_at ASC) AS rn
  FROM public.entradas
  WHERE numero IS NULL
)
UPDATE public.entradas SET numero = ordered.rn
FROM ordered WHERE public.entradas.id = ordered.id;

-- sincronizar secuencia al max actual
SELECT setval('public.entradas_numero_seq', (SELECT COALESCE(MAX(numero),0) FROM public.entradas), true);

-- default para nuevas filas
ALTER TABLE public.entradas ALTER COLUMN numero SET DEFAULT nextval('public.entradas_numero_seq');
-- no ponemos NOT NULL de golpe si hay filas viejas sin numero (ya backfill), ahora sí
ALTER TABLE public.entradas ALTER COLUMN numero SET NOT NULL;

-- índice único para correlativo
CREATE UNIQUE INDEX IF NOT EXISTS uq_entradas_numero ON public.entradas(numero);
CREATE INDEX IF NOT EXISTS idx_entradas_numero ON public.entradas(numero);

COMMENT ON COLUMN public.entradas.numero IS 'Correlativo secuencial desde 1, visible en ticket — N° 1, 2, 3...';

-- 2) Buckets Supabase Storage
-- Comprobantes SINPE (privado, solo backend/service_role)
INSERT INTO storage.buckets (id, name, public)
VALUES ('comprobantes', 'comprobantes', false)
ON CONFLICT (id) DO NOTHING;

-- QRs (privado, servido por backend)
INSERT INTO storage.buckets (id, name, public)
VALUES ('qrcodes', 'qrcodes', false)
ON CONFLICT (id) DO NOTHING;

-- Políticas storage: service_role bypass RLS, pero para anon/auth crear policies si no existen
-- Permitir service_role todo (bypass igual, pero dejamos explícito)
DO $$
BEGIN
  -- comprobantes: solo service_role puede gestionar, anon no
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='storage' AND tablename='objects' AND policyname='comprobantes_service_all') THEN
    CREATE POLICY "comprobantes_service_all" ON storage.objects FOR ALL TO service_role USING (bucket_id='comprobantes') WITH CHECK (bucket_id='comprobantes');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='storage' AND tablename='objects' AND policyname='qrcodes_service_all') THEN
    CREATE POLICY "qrcodes_service_all" ON storage.objects FOR ALL TO service_role USING (bucket_id='qrcodes') WITH CHECK (bucket_id='qrcodes');
  END IF;
END $$;
