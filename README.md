# Meetr Partner SDK

Everything you need to integrate with the [Meetr](https://meetr.io) meeting scheduling API.

## Contents

| Directory | Description |
|-----------|-------------|
| `docs/integration_guide.md` | Full API reference — authentication, endpoints, webhooks, error codes |
| `docs/openapi.yaml` | OpenAPI 3.1 specification (14 public endpoints) |
| `sample_app/` | Complete working partner application (Python/FastAPI) |

## Quick Start

### 1. Register as a partner

```bash
curl -X POST https://meetr.example.com/api/partners/register \
  -H "Content-Type: application/json" \
  -d '{"name": "My Company", "contact_email": "dev@mycompany.com"}'
```

Store the returned `api_key` securely — it is shown only once.

### 2. Authenticate requests

All API requests (except registration) require the key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: mk_abc123..." \
     https://meetr.example.com/api/meetings
```

### 3. Run the sample app

```bash
cd sample_app
cp .env.example .env          # edit with your API key and Meetr URL
pip install -r requirements.txt
python run.py
```

See `sample_app/README.md` for full setup instructions.

## API Documentation

- **Human-readable:** `docs/integration_guide.md`
- **Machine-readable:** `docs/openapi.yaml` — import into Swagger UI, Postman, or any OpenAPI-compatible tool
- **Live docs:** Available at `/redoc` and `/docs` on a running Meetr instance

## Rate Limits

| Scope | Default Limit |
|-------|--------------|
| General | 100 requests/min |
| Meeting creation | 20 requests/min |
| Key rotation | 5 requests/hour |

See the [integration guide](docs/integration_guide.md#rate-limits) for details.

## License

See LICENSE file for details.
