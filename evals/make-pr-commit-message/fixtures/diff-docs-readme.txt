diff --git a/docs/architecture.md b/docs/architecture.md
new file mode 100644
index 0000000..f1e2d3c
--- /dev/null
+++ b/docs/architecture.md
@@ -0,0 +1,18 @@
+# Architecture Overview
+
+This document describes the high-level architecture of the system.
+
+## Components
+
+- **API gateway** — terminates TLS, applies rate limiting, forwards to services
+- **Auth service** — issues JWTs and validates session tokens
+- **Job runner** — picks up enqueued background jobs from Redis
+
+## Data flow
+
+1. Client sends a request to the API gateway
+2. Gateway authenticates via the auth service
+3. Authenticated requests are routed to the appropriate downstream service
+
+See `services/` for per-component READMEs.
