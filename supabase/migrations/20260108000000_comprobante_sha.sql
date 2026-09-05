-- Comprobante SHA — detectar doble uso del mismo recibo SINPE (auditoría seguridad 2026-09-05)
-- comprar_ticket() guarda sha256(file_bytes); admin alerta con WHERE comprobante_sha=%s
ALTER TABLE public.entradas ADD COLUMN IF NOT EXISTS comprobante_sha CHAR(64);
CREATE INDEX IF NOT EXISTS idx_entradas_comprobante_sha ON public.entradas (comprobante_sha);
COMMENT ON COLUMN public.entradas.comprobante_sha IS 'SHA256 del comprobante — duplicados = mismo recibo en 2 compras';
