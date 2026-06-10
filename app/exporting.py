"""CSV export helper.

Builds a downloadable text/csv response from a header row and an iterable of
rows. Excel opens these directly; a UTF-8 BOM is included so non-ASCII names
render correctly in Excel.
"""
import csv
import io

from fastapi.responses import Response


def csv_response(filename: str, header, rows) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    if header:
        writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    data = "﻿" + buf.getvalue()   # BOM for Excel
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
