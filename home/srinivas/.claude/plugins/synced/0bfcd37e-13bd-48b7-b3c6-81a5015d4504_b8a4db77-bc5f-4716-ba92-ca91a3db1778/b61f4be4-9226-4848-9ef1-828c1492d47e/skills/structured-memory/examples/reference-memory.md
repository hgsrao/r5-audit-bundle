---
name: reference-oncall-dashboard
description: Grafana oncall latency dashboard — check when editing request-path code
type: reference
---

The oncall latency dashboard is at `grafana.internal/d/api-latency`. This is what
the oncall engineer watches during incidents.

When editing request handling code, API middleware, or database query paths,
consider how changes might affect the metrics on this dashboard. Significant
latency regressions will page the oncall team.
