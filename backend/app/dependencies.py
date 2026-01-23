from fastapi import HTTPException

# Global ML service instance
ml_service = None


def get_ml_service():
    """Get ML service dependency"""
    if ml_service is None:
        raise HTTPException(status_code=503, detail="ML service not initialized")
    return ml_service
