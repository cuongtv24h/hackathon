"""HTTP boundary for the MVP Mock HIS service.

Run separately from the Hospital API:
``py -m uvicorn apps.mock_his.main:app --host 127.0.0.1 --port 8001``.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from apps.mock_his.service import MockHISStore


def create_app(store=None):
    app = FastAPI(title="Hospital Assistant Mock HIS", version="1.0.0")
    app.state.store = store or MockHISStore()

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "mock-his", "is_mock": True}

    @app.get("/mock-his/specialties")
    def list_specialties():
        return {"specialties": app.state.store.specialties()}

    @app.get("/mock-his/doctors")
    def list_doctors():
        return {"doctors": app.state.store.doctors()}

    @app.get("/mock-his/slots")
    def list_slots():
        return {"slots": app.state.store.slots()}

    @app.post("/mock-his/appointments")
    def create_appointment(request: dict):
        required = {
            "doctor_id", "slot_id", "patient_name", "patient_phone", "patient_dob",
            "has_insurance", "visit_reason", "visit_type", "confirmation_token",
        }
        missing = sorted(field for field in required if request.get(field) in (None, ""))
        if missing:
            return JSONResponse(
                status_code=422,
                content={"error_code": "INVALID_REQUEST", "missing_fields": missing},
            )
        if request["visit_type"] not in {"first_visit", "follow_up"}:
            return JSONResponse(status_code=422, content={"error_code": "INVALID_REQUEST"})
        appointment, error_code = app.state.store.create_appointment(request)
        if error_code:
            status_code = 409 if error_code == "SLOT_UNAVAILABLE" else 422
            return JSONResponse(status_code=status_code, content={"error_code": error_code})
        return JSONResponse(status_code=201, content=appointment)

    @app.get("/mock-his/appointments/{appointment_id}")
    def get_appointment(appointment_id: str):
        appointment = app.state.store.appointment(appointment_id)
        if not appointment:
            return JSONResponse(status_code=404, content={"error_code": "APPOINTMENT_NOT_FOUND"})
        return appointment

    return app


app = create_app()
