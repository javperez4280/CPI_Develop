#!/usr/bin/env python3
"""
Transforma proyectos SAP Cloud Integration para la variante QA.

Reglas:
- Agrega exactamente un sufijo (por defecto _QA).
- Renombra la carpeta raíz del proyecto.
- Actualiza .project.
- Actualiza campos específicos de META-INF/MANIFEST.MF.
- Renombra los archivos .iflw sin modificar su contenido BPMN.
- Es idempotente: puede ejecutarse varias veces.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

MANIFEST_KEYS = {
    "Bundle-Name",
    "Bundle-SymbolicName",
    "Origin-Bundle-Name",
    "Origin-Bundle-SymbolicName",
}


def normalize_suffix(value: str, suffix: str) -> str:
    """Elimina sufijos repetidos y deja exactamente uno."""
    if not value:
        return value

    escaped = re.escape(suffix)
    base = re.sub(rf"(?:{escaped})+$", "", value, flags=re.IGNORECASE)
    return f"{base}{suffix}"


def replace_project_name(project_file: Path, suffix: str) -> tuple[str, str]:
    content = project_file.read_text(encoding="utf-8")
    match = re.search(r"<name>(.*?)</name>", content, flags=re.DOTALL)

    if not match:
        raise ValueError(f"No se encontró <name>...</name> en {project_file}")

    old_name = match.group(1).strip()
    new_name = normalize_suffix(old_name, suffix)

    updated = content[: match.start(1)] + new_name + content[match.end(1) :]
    if updated != content:
        project_file.write_text(updated, encoding="utf-8")

    return old_name, new_name


def update_manifest(manifest_file: Path, suffix: str) -> None:
    lines = manifest_file.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines: list[str] = []

    for line in lines:
        match = re.match(r"^([^:\r\n]+):\s*(.*?)(\r?\n)?$", line)
        if match and match.group(1) in MANIFEST_KEYS:
            key = match.group(1)
            value = match.group(2).strip()
            newline = match.group(3) or ""
            line = f"{key}: {normalize_suffix(value, suffix)}{newline}"
        updated_lines.append(line)

    updated = "".join(updated_lines)
    original = "".join(lines)

    if updated != original:
        manifest_file.write_text(updated, encoding="utf-8")


def rename_iflw_files(project_dir: Path, suffix: str) -> None:
    for source in sorted(project_dir.rglob("*.iflw")):
        target = source.with_name(f"{normalize_suffix(source.stem, suffix)}{source.suffix}")

        if source == target:
            continue

        if target.exists():
            raise FileExistsError(
                f"No se puede renombrar {source} porque ya existe {target}"
            )

        source.rename(target)
        print(f"Archivo IFlow: {source} -> {target}")


def transform_project(project_dir: Path, suffix: str) -> Path:
    project_file = project_dir / ".project"
    manifest_file = project_dir / "META-INF" / "MANIFEST.MF"

    old_project_name, new_project_name = replace_project_name(project_file, suffix)
    update_manifest(manifest_file, suffix)
    rename_iflw_files(project_dir, suffix)

    new_dir_name = normalize_suffix(project_dir.name, suffix)
    target_dir = project_dir.with_name(new_dir_name)

    if target_dir != project_dir:
        if target_dir.exists():
            raise FileExistsError(
                f"No se puede renombrar {project_dir}: ya existe {target_dir}. "
                "Revisá si quedaron dos versiones del mismo iFlow."
            )
        project_dir.rename(target_dir)
        print(f"Proyecto: {project_dir.name} -> {target_dir.name}")
    else:
        target_dir = project_dir

    print(f"Metadata: {old_project_name} -> {new_project_name}")
    return target_dir


def discover_projects(repo_root: Path) -> list[Path]:
    projects: list[Path] = []

    for project_file in repo_root.rglob(".project"):
        project_dir = project_file.parent

        # Evita procesar metadata interna o carpetas ocultas de herramientas.
        if any(part in {".git", ".github"} for part in project_dir.parts):
            continue

        manifest_file = project_dir / "META-INF" / "MANIFEST.MF"
        if manifest_file.is_file():
            projects.append(project_dir)

    # Primero los proyectos más profundos, por seguridad ante renombres.
    return sorted(set(projects), key=lambda p: len(p.parts), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=".",
        help="Raíz del repositorio. Valor predeterminado: directorio actual.",
    )
    parser.add_argument(
        "--suffix",
        default="_QA",
        help="Sufijo de ambiente. Valor predeterminado: _QA",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    projects = discover_projects(repo_root)

    if not projects:
        print("No se encontraron proyectos CPI con .project y META-INF/MANIFEST.MF.")
        return 0

    print(f"Proyectos CPI encontrados: {len(projects)}")
    for project in projects:
        transform_project(project, args.suffix)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
