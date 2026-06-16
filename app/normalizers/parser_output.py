def create_parser_output(
    job_id,
    parser_mode,
    status,
    document,
    outputs,
    confidence=None,
    warnings=None,
):
    return {
        "success": True,
        "jobId": job_id,
        "parserMode": parser_mode,
        "status": status,
        "document": document,
        "outputs": outputs,
        "confidence": confidence or {},
        "warnings": warnings or [],
    }