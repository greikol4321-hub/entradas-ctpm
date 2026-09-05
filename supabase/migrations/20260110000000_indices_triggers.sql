-- Índices + triggers v2 (auditoría DB 2026-09-05)
-- 1. Quitar índice redundante (uq_entradas_numero ya cubre búsquedas por numero)
-- 2. Índice compuesto para listado admin (WHERE estado+ubicacion ORDER BY fecha_compra DESC LIMIT 50)
-- 3. CHECK formato código QR (5 chars alfabeto sin 0/O/I)
-- 4. Trigger máquina de estados (solo transiciones legales)
-- 5. CHECK coherencia fecha_uso <-> estado

-- 1. Redundante
DROP INDEX IF EXISTS public.idx_entradas_numero;

-- 2. Compuesto admin list
CREATE INDEX IF NOT EXISTS idx_entradas_admin_list
  ON public.entradas(estado, ubicacion, fecha_compra DESC);

-- 3. Formato código
ALTER TABLE public.entradas DROP CONSTRAINT IF EXISTS entradas_codigo_check;
ALTER TABLE public.entradas ADD CONSTRAINT entradas_codigo_check
  CHECK (codigo ~ '^[23456789ABCDEFGHJKMNPQRSTVWXYZ]{5}$');

-- 4. Máquina de estados: Pendiente->Aprobada, Aprobada->Usada, Usada->Aprobada
CREATE OR REPLACE FUNCTION public.check_estado_transition() RETURNS TRIGGER AS $$
BEGIN
  IF OLD.estado = NEW.estado THEN RETURN NEW; END IF;
  IF (OLD.estado = 'Pendiente' AND NEW.estado = 'Aprobada')
     OR (OLD.estado = 'Aprobada' AND NEW.estado = 'Usada')
     OR (OLD.estado = 'Usada' AND NEW.estado = 'Aprobada') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Transición ilegal: % -> %', OLD.estado, NEW.estado;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_estado_transition ON public.entradas;
CREATE TRIGGER trg_estado_transition
  BEFORE UPDATE OF estado ON public.entradas
  FOR EACH ROW EXECUTE FUNCTION public.check_estado_transition();

-- 5. fecha_uso NOT NULL <=> estado Usada
ALTER TABLE public.entradas DROP CONSTRAINT IF EXISTS entradas_fecha_uso_check;
ALTER TABLE public.entradas ADD CONSTRAINT entradas_fecha_uso_check
  CHECK ((estado = 'Usada') = (fecha_uso IS NOT NULL));

COMMENT ON INDEX public.idx_entradas_admin_list IS 'Listado admin con ORDER BY — evita sort en memoria';
