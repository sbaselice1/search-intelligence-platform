# Architecture

## Components

### 1) Data ingestion (GSC Data Manager)
- Authenticates to Google Search Console
- Pulls data at configurable grains (query/page/country/device/date)
- Writes normalized outputs to BigQuery tables
- Supports scheduled runs and backfills

### 2) Monitoring (GSC Monitor)
- Tracks run status and freshness
- Surfaces failures and latency between "expected" and "actual" data
- Provides a UI for quickly validating pipeline health

### 3) Analytics UI (SEO Dashboard)
- Queries warehouse tables for reporting
- Provides trend charts, filters, and drilldowns
- Can be extended to include alerts, anomaly detection, and KPI scorecards

## Data flow
GSC API → ingestion jobs → BigQuery → monitoring + dashboard

## Why this design
- Warehouse-first: all reporting and monitoring is driven off BigQuery
- Observable: monitoring makes failures visible and debuggable
- Modular: each component can evolve independently
