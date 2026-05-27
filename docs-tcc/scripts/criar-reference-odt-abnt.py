"""Gera docs/abnt-ufsc-reference.odt a partir do reference.odt padrão do Pandoc."""
from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
OUT = DOCS / "abnt-ufsc-reference.odt"
TMP = DOCS / "_pandoc-default-reference.odt"


def _patch_styles(styles_xml: str) -> str:
    styles_xml = re.sub(
        r'(<style:page-layout-properties[^>]*?)fo:margin-top="[^"]*"',
        r'\1fo:margin-top="3cm"',
        styles_xml,
    )
    styles_xml = re.sub(
        r'(<style:page-layout-properties[^>]*?)fo:margin-bottom="[^"]*"',
        r'\1fo:margin-bottom="2cm"',
        styles_xml,
    )
    styles_xml = re.sub(
        r'(<style:page-layout-properties[^>]*?)fo:margin-left="[^"]*"',
        r'\1fo:margin-left="3cm"',
        styles_xml,
    )
    styles_xml = re.sub(
        r'(<style:page-layout-properties[^>]*?)fo:margin-right="[^"]*"',
        r'\1fo:margin-right="2cm"',
        styles_xml,
    )

    if 'style:name="Times New Roman"' not in styles_xml:
        styles_xml = styles_xml.replace(
            "</office:font-face-decls>",
            '    <style:font-face style:name="Times New Roman" svg:font-family="&apos;Times New Roman&apos;" style:font-family-generic="roman" style:font-pitch="variable"/>\n  </office:font-face-decls>',
            1,
        )

    def patch_paragraph_style(name: str, *, indent: str | None = None, bold: bool = False) -> None:
        nonlocal styles_xml
        pattern = rf'(<style:style[^>]*style:name="{re.escape(name)}"[^>]*style:family="paragraph"[^>]*>)(.*?)(</style:style>)'

        def repl(match: re.Match[str]) -> str:
            head, body, tail = match.group(1), match.group(2), match.group(3)
            if "style:paragraph-properties" in body:
                body = re.sub(
                    r'(<style:paragraph-properties[^>]*?)fo:line-height="[^"]*"',
                    r'\1fo:line-height="150%"',
                    body,
                )
                if indent:
                    if 'fo:text-indent="' in body:
                        body = re.sub(
                            r'fo:text-indent="[^"]*"',
                            f'fo:text-indent="{indent}"',
                            body,
                        )
                    else:
                        body = body.replace(
                            "<style:paragraph-properties",
                            f'<style:paragraph-properties fo:text-indent="{indent}"',
                            1,
                        )
            else:
                attrs = ' fo:line-height="150%"'
                if indent:
                    attrs += f' fo:text-indent="{indent}"'
                body = body.replace(
                    "<style:style>",
                    f"<style:paragraph-properties{attrs}/>",
                    1,
                )
            if "style:text-properties" in body:
                body = re.sub(
                    r'(<style:text-properties[^>]*?)style:font-name="[^"]*"',
                    r'\1style:font-name="Times New Roman"',
                    body,
                )
                if bold:
                    if 'fo:font-weight="bold"' not in body:
                        body = body.replace(
                            "<style:text-properties",
                            '<style:text-properties fo:font-weight="bold"',
                            1,
                        )
            else:
                bold_attr = ' fo:font-weight="bold"' if bold else ""
                insert = (
                    f'<style:text-properties style:font-name="Times New Roman" '
                    f'fo:font-size="12pt"{bold_attr}/>'
                )
                body = insert + body
            return head + body + tail

        styles_xml = re.sub(pattern, repl, styles_xml, count=1, flags=re.DOTALL)

    for style_name in ("Standard", "Text body", "First paragraph", "Quotations"):
        patch_paragraph_style(style_name, indent="1.25cm")
    for level in range(1, 4):
        patch_paragraph_style(f"Heading {level}", indent="0cm", bold=True)
    patch_paragraph_style("Title", indent="0cm", bold=True)
    patch_paragraph_style("Subtitle", indent="0cm")
    return styles_xml


def main() -> int:
    with TMP.open("wb") as handle:
        subprocess.run(
            ["pandoc", "--print-default-data-file", "reference.odt"],
            check=True,
            stdout=handle,
        )

    with zipfile.ZipFile(TMP, "r") as zin, zipfile.ZipFile(OUT, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "styles.xml":
                text = data.decode("utf-8")
                data = _patch_styles(text).encode("utf-8")
            zout.writestr(item, data)

    TMP.unlink(missing_ok=True)
    print(f"Referência ABNT salva em: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
