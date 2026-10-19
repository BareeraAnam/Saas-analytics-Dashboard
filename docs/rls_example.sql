-- EXAMPLE ONLY. This project does not run this file.
-- Isolation is one Postgres schema per tenant, not row-level security.
-- The statements below show how a shared table would hide other tenants' rows.
CREATE TABLE IF NOT EXISTS public.usage_summary (
    id BIGSERIAL PRIMARY KEY,
    tenant_schema TEXT NOT NULL,
    day DATE NOT NULL,
    calls BIGINT NOT NULL DEFAULT 0
);
ALTER TABLE public.usage_summary ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_summary FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.usage_summary
    USING (tenant_schema = current_setting('app.current_tenant', true));
-- Per request: SET LOCAL app.current_tenant = 'acme';
-- The application role must not be a superuser, or Postgres skips these policies.
