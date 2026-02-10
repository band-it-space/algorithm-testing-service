from fastapi import APIRouter
from app.services.sheets_service import SheetsService

router = APIRouter(prefix="/api/v1/sheets", tags=["sheets"])


@router.get("/health")
async def check_sheets_connection():
    """Check Google Sheets connection and return configuration."""
    try:
        service = SheetsService()
        read_ok = service.check_read_permission()
        write_ok = service.check_write_permission()
        config = service.get_sheet_config()
        
        return {
            "connected": True,
            "read": read_ok,
            "write": write_ok,
            "config": config,
            "error": None
        }
    except Exception as e:
        return {
            "connected": False,
            "read": False,
            "write": False,
            "config": None,
            "error": str(e)
        }
