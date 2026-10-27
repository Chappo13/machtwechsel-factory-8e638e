# API Conventions

- FastAPI with async endpoints
- All long-running operations via background tasks
- WebSocket for real-time progress updates
- Response models with Pydantic
- Endpoints prefix: /api/v1/
- Video tasks: POST /api/v1/videos (create), GET /api/v1/videos/{id} (status), GET /api/v1/videos (list)
- Static files served from data/output/ for download
