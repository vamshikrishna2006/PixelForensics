# API

- POST /api/auth/register {username,email,password,confirm_password} -> {access_token,user}
- POST /api/auth/login {identifier,password} -> {access_token,user}
- GET /api/auth/me (Bearer) -> user
- POST /api/analyze (multipart file) -> ReportOut {analysis,detectors,breakdown,explanation,regions,artifacts,image_info}
- GET /api/analysis/history -> list[AnalysisOut] (own only)
- GET /api/analysis/{id} -> ReportOut (own only)
- DELETE /api/analysis/{id} (own only)
- POST /api/compare (2-4 files) -> {pairs,mean_correlation,verdict,note}
- GET /api/report/{id}/json, /api/report/{id}/pdf (own only)
- GET /api/admin/statistics, /api/admin/users, /api/admin/system-health (ADMIN only)
- GET /api/health (public)

Interactive docs: http://localhost:8000/docs
