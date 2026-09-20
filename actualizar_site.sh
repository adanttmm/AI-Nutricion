#!/usr/bin/env bash
# actualizar_site.sh — genera el sitio web y lo publica en GitHub Pages
# Uso: bash actualizar_site.sh [--sin-push]
set -euo pipefail

cd "$(dirname "$0")"
source venv/bin/activate
source scripts/_lib.sh

SIN_PUSH=false
for arg in "$@"; do
  case "$arg" in
    --sin-push) SIN_PUSH=true ;;
  esac
done

# ── Cabecera ───────────────────────────────────────────────────────────────────
T_GLOBAL=$(_now_s)
echo ""
echo "════════════════════════════════════════════════"
echo "  🌐  Asistente Nutricional — Publicar Sitio"
echo "  $(date '+%A %d/%m/%Y %H:%M')"
echo "════════════════════════════════════════════════"
echo ""

# ── 1. Traer valoraciones sincronizadas por el Worker de Cloudflare ────────────
_paso_git_pull "[1/5]"

# ── 2. Recoger valoraciones descargadas del navegador ──────────────────────────
T_STEP=$(_now_s)
echo "▶ [2/5] Buscando valoraciones en la carpeta de Descargas..."
COLLECTED=$(_recoger_de_descargas)
if [ "$COLLECTED" -gt 0 ]; then
  _record_step "2. Recoger de Descargas" "$(_elapsed $T_STEP)" "✅"
else
  echo "  ⏭  Nada nuevo en Descargas."
  _record_step "2. Recoger de Descargas" "—" "⏭"
fi
echo ""

# ── 3. Importar valoraciones auto-guardadas ────────────────────────────────────
T_STEP=$(_now_s)
echo "▶ [3/5] Importando valoraciones desde data/ratings/..."
python main.py importar-ratings
_record_step "3. Importar ratings" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── 4. Generar sitio estático ──────────────────────────────────────────────────
T_STEP=$(_now_s)
echo "▶ [4/5] Generando sitio estático en docs/..."
python main.py generar-sitio
_record_step "4. Generar sitio" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── 5. Publicar en GitHub Pages ────────────────────────────────────────────────
T_STEP=$(_now_s)
if [ "$SIN_PUSH" = false ]; then
  echo "▶ [5/5] Publicando en GitHub Pages..."
  git add docs/
  git add outputs/recipes/ outputs/menus/
  if git diff --cached --quiet; then
    echo "  Sin cambios — nada que publicar."
    _record_step "5. Publicar (git push)" "—" "⏭"
  else
    git commit -m "actualizar semana $(date +%Y-%m-%d)"
    git push origin master
    echo ""
    echo "✅ Publicado — https://adanttmm.github.io/AI-Nutricion/"
    _record_step "5. Publicar (git push)" "$(_elapsed $T_STEP)" "✅"
  fi
else
  echo "⏭  [5/5] Push omitido (--sin-push)."
  _record_step "5. Publicar (git push)" "—" "⏭"
fi
echo ""

# ── Resumen final ─────────────────────────────────────────────────────────────
_imprimir_resumen_final "Sitio listo — resumen de ejecución"
echo "════════════════════════════════════════════════"
echo ""
