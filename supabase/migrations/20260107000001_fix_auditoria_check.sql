-- Fix auditoria CHECK — ampliar para acciones de usuarios y revertir (1.5)
-- 20260106000000 solo tenía 7 valores y log_audit para crear/editar/borrar/revertir fallaba silencioso
ALTER TABLE public.auditoria DROP CONSTRAINT IF EXISTS auditoria_accion_check;
ALTER TABLE public.auditoria ADD CONSTRAINT auditoria_accion_check CHECK (accion IN ('aprobar','rechazar','desbloquear','validar','login_ok','login_fail','comprar','crear_usuario','editar_usuario','borrar_usuario','revertir'));
COMMENT ON TABLE public.auditoria IS 'Audit trail — incluye usuarios y revertir (fix 20260107)';
