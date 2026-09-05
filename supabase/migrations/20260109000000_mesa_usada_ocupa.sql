-- Mesa Usada sigue ocupada — no se revende (cambio regla negocio 2026-09-05)
-- Antes: solo Pendiente/Aprobada bloqueaban, Usada liberaba la mesa
DROP INDEX IF EXISTS public.uq_mesa_ocupada;
CREATE UNIQUE INDEX uq_mesa_ocupada ON public.entradas(mesa_numero)
  WHERE ubicacion='Mesas' AND mesa_numero IS NOT NULL AND estado IN ('Pendiente','Aprobada','Usada');
COMMENT ON INDEX public.uq_mesa_ocupada IS 'Mesa ocupada incluye Usada — no reventa post-uso';
