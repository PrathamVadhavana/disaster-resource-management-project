from fastapi import HTTPException

# Global ML service instance
ml_service = None


def set_ml_service(service):
    """Set the global ML service instance (called at startup)."""
    global ml_service
    ml_service = service


def get_ml_service():
    """Get ML service dependency"""
    if ml_service is None:
        raise HTTPException(status_code=503, detail="ML service not initialized")
    return ml_service
