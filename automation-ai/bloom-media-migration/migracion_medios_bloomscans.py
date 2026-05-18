from __future__ import annotations

import argparse
import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image


IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


@dataclass
class ManifestRow:
    action: str
    status: str
    source_rel: str
    target_rel: str
    old_url: str
    new_url: str
    note: str


def normalize_for_webp(img: Image.Image) -> Image.Image:
    if img.mode in ("P", "LA"):
        return img.convert("RGBA")
    if img.mode in ("L", "CMYK"):
        return img.convert("RGB")
    return img


def rel_to_url(site_base_url: str, rel_path: Path) -> str:
    return site_base_url.rstrip("/") + "/" + rel_path.as_posix()


def convert_lossless_webp(src: Path, dst: Path) -> None:
    with Image.open(src) as img:
        prepared = normalize_for_webp(img)
        dst.parent.mkdir(parents=True, exist_ok=True)
        prepared.save(dst, "WEBP", lossless=True, quality=100, method=6)
    with Image.open(src) as original, Image.open(dst) as converted:
        if original.size != converted.size:
            raise RuntimeError(f"Las dimensiones no coinciden: {src} -> {dst}")


def write_manifest(rows: Iterable[ManifestRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(
            ["action", "status", "source_rel", "target_rel", "old_url", "new_url", "note"]
        )
        for row in rows:
            writer.writerow(
                [
                    row.action,
                    row.status,
                    row.source_rel,
                    row.target_rel,
                    row.old_url,
                    row.new_url,
                    row.note,
                ]
            )


def write_wp_cli_commands(rows: Iterable[ManifestRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    emitted = set()
    with path.open("w", encoding="utf-8") as f:
        f.write("# Ejecutar solo despues de validar archivos y backups.\n")
        f.write("# Estos comandos actualizan referencias en contenido y metadatos.\n\n")
        for row in rows:
            if not row.old_url or not row.new_url or row.old_url == row.new_url:
                continue
            key = (row.old_url, row.new_url)
            if key in emitted:
                continue
            emitted.add(key)
            f.write(
                "wp search-replace "
                f"'{row.old_url}' '{row.new_url}' "
                "wp_posts wp_postmeta --precise --recurse-objects\n"
            )


def load_ai_map(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Renombra archivos con nombres IA y convierte jpg/png a webp de forma segura."
    )
    parser.add_argument("--uploads-root", required=True, help="Ruta local a wp-content/uploads")
    parser.add_argument(
        "--site-base-url",
        default="https://bloomscans.com/wp-content/uploads",
        help="Base URL publica de uploads",
    )
    parser.add_argument(
        "--ai-map",
        default="mapeo_renombres_ia_bloomscans_20260403.tsv",
        help="TSV con relative_path y nuevo_nombre_base",
    )
    parser.add_argument(
        "--mode",
        choices=["safe-copy", "rename-in-place"],
        default="safe-copy",
        help="safe-copy conserva originales; rename-in-place mueve el original",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Si no se indica, solo hace dry-run",
    )
    parser.add_argument(
        "--manifest-out",
        default="manifiesto_migracion_medios.tsv",
        help="TSV de salida con acciones realizadas o simuladas",
    )
    parser.add_argument(
        "--commands-out",
        default="wp_search_replace_medios.sh",
        help="Archivo con comandos wp search-replace",
    )
    args = parser.parse_args()

    uploads_root = Path(args.uploads_root).resolve()
    ai_map_path = Path(args.ai_map).resolve()
    manifest_out = Path(args.manifest_out).resolve()
    commands_out = Path(args.commands_out).resolve()

    if not uploads_root.exists():
        raise SystemExit(f"No existe uploads-root: {uploads_root}")
    if not ai_map_path.exists():
        raise SystemExit(f"No existe ai-map: {ai_map_path}")

    manifest: list[ManifestRow] = []

    # 1. Renombres IA
    for row in load_ai_map(ai_map_path):
        source_rel = Path(row["relative_path"])
        src = uploads_root / source_rel
        if not src.exists():
            manifest.append(
                ManifestRow(
                    action="rename-ai",
                    status="missing",
                    source_rel=source_rel.as_posix(),
                    target_rel="",
                    old_url=row["old_url"],
                    new_url="",
                    note="No se encontro el archivo en uploads-root",
                )
            )
            continue

        target_rel = source_rel.with_name(row["nuevo_nombre_base"] + src.suffix.lower())
        target = uploads_root / target_rel

        if src == target:
            manifest.append(
                ManifestRow(
                    action="rename-ai",
                    status="skipped",
                    source_rel=source_rel.as_posix(),
                    target_rel=target_rel.as_posix(),
                    old_url=row["old_url"],
                    new_url=rel_to_url(args.site_base_url, target_rel),
                    note="Origen y destino son iguales",
                )
            )
            continue

        if target.exists():
            status = "exists"
        elif args.apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            if args.mode == "safe-copy":
                shutil.copy2(src, target)
            else:
                shutil.move(str(src), str(target))
            status = "created"
        else:
            status = "would-create"

        manifest.append(
            ManifestRow(
                action="rename-ai",
                status=status,
                source_rel=source_rel.as_posix(),
                target_rel=target_rel.as_posix(),
                old_url=row["old_url"],
                new_url=rel_to_url(args.site_base_url, target_rel),
                note=f"modo={args.mode}",
            )
        )

    # 2. Conversion a WebP sin perdida adicional
    files = sorted(
        p for p in uploads_root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    for src in files:
        source_rel = src.relative_to(uploads_root)
        target_rel = source_rel.with_suffix(".webp")
        target = uploads_root / target_rel
        old_url = rel_to_url(args.site_base_url, source_rel)
        new_url = rel_to_url(args.site_base_url, target_rel)

        if target.exists():
            status = "exists"
            note = "webp ya existe"
        elif args.apply:
            convert_lossless_webp(src, target)
            status = "created"
            note = "convertido a webp lossless"
        else:
            status = "would-create"
            note = "dry-run webp lossless"

        manifest.append(
            ManifestRow(
                action="convert-webp",
                status=status,
                source_rel=source_rel.as_posix(),
                target_rel=target_rel.as_posix(),
                old_url=old_url,
                new_url=new_url,
                note=note,
            )
        )

    write_manifest(manifest, manifest_out)
    write_wp_cli_commands(
        [row for row in manifest if row.status in {"created", "would-create", "exists"}],
        commands_out,
    )

    created = sum(1 for row in manifest if row.status == "created")
    would_create = sum(1 for row in manifest if row.status == "would-create")
    exists = sum(1 for row in manifest if row.status == "exists")
    missing = sum(1 for row in manifest if row.status == "missing")

    print(f"Uploads root: {uploads_root}")
    print(f"Modo: {args.mode}")
    print(f"Apply: {args.apply}")
    print(f"Manifest: {manifest_out}")
    print(f"WP-CLI commands: {commands_out}")
    print(f"created={created} would-create={would_create} exists={exists} missing={missing}")
    print(
        "Nota: por defecto esta estrategia no borra originales; asi no se rompen URLs viejas."
    )
    print(
        "La conversion usa WebP lossless para evitar perdida adicional de calidad sobre JPG o PNG."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
