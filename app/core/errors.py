def create_engine_error_response(message, code="DOCUMENT_ENGINE_ERROR", extra=None):
    response = {
        "success": False,
        "message": message,
        "code": code,
    }

    if extra:
        response["extra"] = extra

    return response
