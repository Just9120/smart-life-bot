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

        sorted_records = sorted(records, key=lambda r: (r.category_raw.casefold(), r.owner_name.casefold(), r.bank_name.casefold()))
        rows = [[f"Кэшбек — {format_month_label(target_month)}"], ["owner", "bank", "category", "percent", "month", "status", "created_at", "updated_at"]]
        for r in sorted_records:
            rows.append([r.owner_name, r.bank_name, r.category_raw, f"{r.percent:g}%", r.target_month, "active", r.created_at.isoformat(), r.updated_at.isoformat()])
        content = _build_xlsx(rows)
        file_name = f"cashback_{target_month}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.xlsx"
        return CashbackExportResult("ok", f"Готово. Выгрузил XLSX за {format_month_label(target_month)}.", file_name=file_name, content=content, target_month=target_month)


def _build_xlsx(rows: list[list[str]]) -> bytes:
    def col_ref(index: int) -> str:
        result = ""
        n = index
        while n > 0:
            n, rem = divmod(n - 1, 26)
            result = chr(65 + rem) + result
        return result

    def c(ref: str, val: str, *, style_id: int | None = None) -> str:
        style = f' s="{style_id}"' if style_id is not None else ""
        return f'<c r="{ref}" t="inlineStr"{style}><is><t>{escape(val)}</t></is></c>'

    sheet_rows = []
    for i, row in enumerate(rows, start=1):
        style_id = 1 if i == 2 else None
        cells = ''.join(c(f"{col_ref(j)}{i}", str(v), style_id=style_id) for j, v in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{i}">{cells}</row>')

    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cols><col min="1" max="1" width="14" customWidth="1"/><col min="2" max="2" width="18" customWidth="1"/>'
        '<col min="3" max="3" width="24" customWidth="1"/><col min="4" max="4" width="10" customWidth="1"/>'
        '<col min="5" max="5" width="12" customWidth="1"/><col min="6" max="6" width="12" customWidth="1"/>'
        '<col min="7" max="8" width="24" customWidth="1"/></cols>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="2" topLeftCell="A3" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        f'<autoFilter ref="A2:H{len(rows)}"/>'
        '</worksheet>'
    )

    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
              '<borders count="1"><border/></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
              '</styleSheet>')

    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Кэшбек" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', worksheet)
        z.writestr('xl/styles.xml', styles)
    return out.getvalue()
