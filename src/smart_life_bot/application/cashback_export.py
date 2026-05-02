from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

from smart_life_bot.application.cashback_use_cases import current_year_month, format_month_label


@dataclass(frozen=True, slots=True)
class CashbackExportResult:
    status: str
    text: str
    file_name: str | None = None
    content: bytes | None = None
    target_month: str | None = None


class ExportCashbackCategoriesUseCase:
    def __init__(self, repo, *, now_provider=None) -> None:
        self.repo = repo
        self.now_provider = now_provider or (lambda: datetime.now(UTC).date())

    def execute(self, month: str | None = None) -> CashbackExportResult:
        target_month = month or current_year_month(self.now_provider())
        records = self.repo.list_active(target_month)
        if not records:
            return CashbackExportResult("no_data", f"За {format_month_label(target_month)} активных кэшбек-категорий пока нет.", target_month=target_month)

        rows = [[f"Кэшбек — {format_month_label(target_month)}"], ["owner", "bank", "category", "percent", "month", "status", "created_at", "updated_at"]]
        for r in records:
            rows.append([r.owner_name, r.bank_name, r.category_raw, f"{r.percent:g}%", r.target_month, "active", r.created_at.isoformat(), r.updated_at.isoformat()])
        content = _build_xlsx(rows)
        file_name = f"cashback_{target_month}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.xlsx"
        return CashbackExportResult("ok", f"Готово. Выгрузил XLSX за {format_month_label(target_month)}.", file_name=file_name, content=content, target_month=target_month)


def _build_xlsx(rows: list[list[str]]) -> bytes:
    def c(ref: str, val: str) -> str:
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(val)}</t></is></c>'

    sheet_rows = []
    for i, row in enumerate(rows, start=1):
        cells = ''.join(c(f"{chr(64+j)}{i}", str(v)) for j, v in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{i}">{cells}</row>')
    worksheet = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'

    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Кэшбек" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', worksheet)
    return out.getvalue()
