-- Mesas y finanzas — extender entradas para soportar numeración de mesas y monto
ALTER TABLE public.entradas
  ADD COLUMN IF NOT EXISTS mesa_numero SMALLINT NULL CHECK (mesa_numero BETWEEN 1 AND 20),
  ADD COLUMN IF NOT EXISTS monto INTEGER NOT NULL DEFAULT 0 CHECK (monto IN (0, 5000, 10000));

COMMENT ON COLUMN public.entradas.mesa_numero IS 'NULL si Gradas, 1..20 si Mesas';
COMMENT ON COLUMN public.entradas.monto IS '5000 Gradas, 10000 Mesas';

CREATE INDEX IF NOT EXISTS idx_entradas_mesa ON public.entradas(mesa_numero) WHERE ubicacion='Mesas';
CREATE INDEX IF NOT EXISTS idx_entradas_monto ON public.entradas(monto);

-- Índice parcial para bloquear mesa ocupada (solo Pendiente/Aprobada bloquean, Usada libera)
CREATE UNIQUE INDEX IF NOT EXISTS uq_mesa_ocupada ON public.entradas(mesa_numero)
  WHERE ubicacion='Mesas' AND mesa_numero IS NOT NULL AND estado IN ('Pendiente','Aprobada');
