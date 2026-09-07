// Mirrors backend/app/schemas/health.py — keep in sync as fields change.
export interface ComponentHealth {
  name: string;
  status: "ok" | "error" | "not_configured";
  detail?: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app_name: string;
  env: string;
  components: ComponentHealth[];
}
