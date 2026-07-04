"""Export routes — CSV exports."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from main import (
    _export_utils,
    _verify_token,
    db,
)

router = APIRouter(prefix="")


@router.get("/api/export/{analysis_id}/csv")
async def export_analysis_csv(analysis_id: str, user_info: dict = Depends(_verify_token)):
    analysis = await db.get_analysis_by_id(analysis_id, user_info["user_id"])
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    csv_content = _export_utils.export_analysis_csv(analysis)
    filename = f"cost-report-{analysis_id[:8]}.csv"

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/export/history/csv")
async def export_history_csv(user_info: dict = Depends(_verify_token)):
    analyses = await db.get_analyses_by_user(user_info["user_id"], limit=500)
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["ID", "Cloud", "Regions", "Services", "Resources", "Issues",
                      "Savings", "Status", "Date"])
    for a in analyses:
        writer.writerow([
            a.get("id", ""),
            a.get("cloud_provider", ""),
            ", ".join(a.get("regions", [])),
            ", ".join(a.get("services", [])),
            a.get("resources_scanned", 0),
            a.get("issues_found", 0),
            a.get("estimated_savings", ""),
            a.get("status", ""),
            a.get("created_at", ""),
        ])

    return StreamingResponse(
        io.StringIO(output.getvalue()),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="cost-detective-history.csv"'},
    )
