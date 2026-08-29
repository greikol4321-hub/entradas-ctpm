-- Código corto fácil de escribir — 6 caracteres base32 sin 0/O/1/I/L
ALTER TABLE public.entradas
  ADD COLUMN IF NOT EXISTS codigo VARCHAR(6) UNIQUE;

COMMENT ON COLUMN public.entradas.codigo IS 'Código corto 6 chars (ej: A7K9P2) — usado en QR y validación manual, fácil de escribir';

CREATE INDEX IF NOT EXISTS idx_entradas_codigo ON public.entradas(codigo);
