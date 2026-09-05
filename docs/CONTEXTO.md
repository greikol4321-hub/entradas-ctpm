# Contexto del proyecto — Entradas CTPM

> Última actualización: 2026-09-05. Sesión de auditoría + quema + limpieza.

## Estado actual
- Deploy en Vercel (`https://entradas-ctpm.vercel.app`) verificado y parchado.
- BD limpia: 0 entradas, correlativo `entradas_numero_seq` en 1 (próxima venta = N°1),
  auditoría en 0, 12 mesas libres. Usuarios: `grei:admin`, `Meli:admin`.
- Repo limpio: sin docs de agente, sin temporales. Head: ver `git log`.

## Fixes aplicados (ya en prod)
1. `GET /static/qrcodes/*` y `/qrcodes/*` exigen login + rol admin (cierra oráculo QR).
2. Advertencia de comprobante duplicado genérica al comprador (detalle en auditoría).
3. Sin credenciales en README/CLAUDE (este último eliminado con AGENTS.md).
4. `ProxyFix(x_for=1, x_proto=1)` para IP real tras proxy de Vercel.
5. Log `mesa_conflicto` en rama de mesa ocupada.

## Decisiones del dueño
- Password mínimo: **4** (se rechazó subirlo a 12).
- Lockout 5 intentos / 15 min se mantiene.
- Sesión 8h y CSRF determinístico: residual aceptado.

## Pendientes (no bloquean la venta)
- [ ] Rotar **anon key** Supabase (se filtró una en historial, commits `e0585c7`→`c6c426c`; rol anon, RLS ya restringido).
- [ ] Cambiar clave de **Meli** (se compartió por chat).
- [ ] Confirmar `UPSTASH_*` en env de Vercel (rate-limit distribuido).
- [ ] Borrar 2 PNG + 2 QR de prueba del bucket privado (lo hace el dueño).
- [ ] Repo GitHub es **PÚBLICO**: el historial aún muestra `admin123` (ya no funciona en prod).

## Notas operativas
- El admin **no** puede validar en puerta (solo rol `portero`); crear usuario portero el día del evento.
- `uploads/` y `static/qrcodes/` están en `.gitignore`; en Vercel viven en `/tmp` + Supabase Storage.
- Auditoría del API solo expone `aprobar/validar/revertir`; el resto vive en BD.
