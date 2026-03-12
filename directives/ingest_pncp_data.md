# Ingest PNCP Data

## Goal

Ingest PNCP (Portal Nacional de Contratações Públicas) data into the system via the batch ingestion endpoint.

## Inputs

- **PNCP Data**: JSON array of items with required fields (`numeroControlePNCP`, `objetoCompra`)
- **API Key**: Authentication token for the ingestion endpoint
- **API URL**: Base URL of the FastAPI backend (default: `http://localhost:8000`)

## Tools/Scripts

- **Script**: `execution/ingest_pncp_batch.py`
- **Dependencies**: `requests`, `python-dotenv`
- **API Endpoint**: `POST /ingest/pncp/batch`

## Outputs

- **Success Response**: JSON with counts of created/updated/failed items
- **Log File**: Detailed execution log in `.tmp/ingest_pncp_TIMESTAMP.log`
- **Error Report**: If failures occur, details saved to `.tmp/ingest_errors_TIMESTAMP.json`

## Process

1. Load PNCP data from source (file, API, or stdin)
2. Validate data structure and required fields
3. Authenticate using API key from environment
4. Send batch request to ingestion endpoint
5. Parse response and log results
6. If errors occur, save error details for review

## Edge Cases

- **Missing Required Fields**: Skip items without `numeroControlePNCP` or `objetoCompra`
- **API Rate Limiting**: Implement exponential backoff if rate limited
- **Large Batches**: Split into chunks if payload exceeds size limits
- **Network Failures**: Retry with exponential backoff (max 3 retries)
- **Duplicate Keys**: API handles upsert based on `numeroControlePNCP`

## Error Handling

- **401 Unauthorized**: Check API key in `.env` file
- **422 Validation Error**: Log validation details and continue with valid items
- **500 Server Error**: Retry after delay, log error for investigation
- **Connection Error**: Check if backend is running, retry with backoff

## Notes

- **API Key**: Must be set in `.env` as `API_KEY=your_key_here`
- **Batch Size**: Recommended max 100 items per request for optimal performance
- **Idempotency**: Safe to re-run - API uses upsert based on `numeroControlePNCP`
- **Timing**: Typical processing time is ~50-200ms per item
- **Validation**: API validates required fields server-side, returns detailed errors

## Learnings

- 2026-01-21: Initial directive created based on existing `/ingest/pncp/batch` endpoint
