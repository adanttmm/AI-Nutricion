#!/usr/bin/env bash
# actualizar_menu.sh — parsea dietas y genera menú, recetas, compras y meal prep
# Uso: bash actualizar_menu.sh [--sin-parsear]
#
# NOTA DE SEMANA: crea un archivo nota_semana.txt en esta carpeta con tus
# indicaciones especiales antes de ejecutar (sobras, tiempo libre, equipo, etc.).
# Se aplica automáticamente y se archiva en data/notas_semana/ al terminar.
set -euo pipefail

cd "$(dirname "$0")"
source venv/bin/activate
source scripts/_lib.sh

SIN_PARSEAR=false
for arg in "$@"; do
  case "$arg" in
    --sin-parsear) SIN_PARSEAR=true ;;
  esac
done

# ── Nota de semana ─────────────────────────────────────────────────────────────
NOTA_ARGS=()
if [[ -f "nota_semana.txt" ]]; then
  NOTA_CONTENT=$(cat nota_semana.txt)
  if [[ -n "$NOTA_CONTENT" ]]; then
    NOTA_ARGS=(--nota "$NOTA_CONTENT")
  fi
fi

# ── Cabecera ───────────────────────────────────────────────────────────────────
T_GLOBAL=$(_now_s)
echo ""
echo "════════════════════════════════════════════════"
echo "  🥗  Asistente Nutricional — Menú + Compras"
echo "  $(date '+%A %d/%m/%Y %H:%M')"
echo "════════════════════════════════════════════════"
echo ""
if [[ ${#NOTA_ARGS[@]} -gt 0 ]]; then
  echo "  📋 Nota de semana detectada (nota_semana.txt):"
  # Show first 120 chars of the note
  NOTA_PREVIEW="${NOTA_CONTENT:0:120}"
  [[ ${#NOTA_CONTENT} -gt 120 ]] && NOTA_PREVIEW="${NOTA_PREVIEW}…"
  echo "     ${NOTA_PREVIEW}"
  echo ""
else
  echo "  💡 Sin nota_semana.txt — menú estándar. Para personalizar:"
  echo "     echo 'Tengo poco tiempo, sobras de X, prefiero más sous vide' > nota_semana.txt"
  echo ""
fi

# ── 1. Traer valoraciones sincronizadas por el Worker de Cloudflare ────────────
_paso_git_pull "[1/6]"

# ── 2. Parsear PDFs del nutriólogo ────────────────────────────────────────────
T_STEP=$(_now_s)
if [ "$SIN_PARSEAR" = false ]; then
  PDF_COUNT=$(find Dietas/ -maxdepth 1 -name "*.pdf" 2>/dev/null | wc -l)
  if [ "$PDF_COUNT" -gt 0 ]; then
    echo "▶ [2/6] Parseando dietas ($PDF_COUNT PDF encontrados)..."
    python main.py parsear-dietas
    _record_step "2. Parsear dietas" "$(_elapsed $T_STEP)" "✅"
  else
    echo "⚠  [2/6] Sin PDFs en Dietas/ — saltando parseo."
    _record_step "2. Parsear dietas" "—" "⏭"
  fi
else
  echo "⏭  [2/6] Parseo omitido (--sin-parsear)."
  _record_step "2. Parsear dietas" "—" "⏭"
fi
echo ""

# ── 3. Recoger valoraciones descargadas del navegador ─────────────────────────
T_STEP=$(_now_s)
echo "▶ [3/6] Buscando valoraciones en la carpeta de Descargas..."
COLLECTED=$(_recoger_de_descargas)
if [ "$COLLECTED" -gt 0 ]; then
  _record_step "3. Recoger de Descargas" "$(_elapsed $T_STEP)" "✅"
else
  echo "  ⏭  Nada nuevo en Descargas."
  _record_step "3. Recoger de Descargas" "—" "⏭"
fi
echo ""

# ── 4. Importar valoraciones de semanas anteriores ────────────────────────────
T_STEP=$(_now_s)
RATINGS_COUNT=$(find data/ratings/ -maxdepth 1 -name "ratings_*.json" 2>/dev/null | wc -l)
if [ "$RATINGS_COUNT" -gt 0 ]; then
  echo "▶ [4/6] Importando valoraciones ($RATINGS_COUNT archivo(s) en data/ratings/)..."
  python main.py importar-ratings
  _record_step "4. Importar ratings" "$(_elapsed $T_STEP)" "✅"
else
  echo "⏭  [4/6] Sin valoraciones en data/ratings/ — omitiendo."
  echo "         (Exporta desde el sitio web y coloca el JSON en data/ratings/)"
  _record_step "4. Importar ratings" "—" "⏭"
fi
echo ""

# ── 5. Menú, recetas, compras y meal prep (sin sitio) ─────────────────────────
T_STEP=$(_now_s)
echo "▶ [5/6] Generando semana completa (sin sitio)..."
echo "        menú (+ valoraciones + validación calórica) · recetas · meal prep · compras"
python main.py semana-completa --sin-sitio "${NOTA_ARGS[@]+"${NOTA_ARGS[@]}"}"
_record_step "5. Semana completa" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── 6. Auditar plan de meal prep ──────────────────────────────────────────────
T_STEP=$(_now_s)
echo "▶ [6/6] Auditando plan de meal prep..."
python main.py verificar-prep || true
_record_step "6. Auditar meal prep" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── Archivar nota de semana ────────────────────────────────────────────────────
if [[ ${#NOTA_ARGS[@]} -gt 0 ]]; then
  mkdir -p data/notas_semana
  NOTA_FECHA=$(date +%Y-%m-%d)
  cp nota_semana.txt "data/notas_semana/nota_${NOTA_FECHA}.txt"
  echo "  📁 Nota archivada en data/notas_semana/nota_${NOTA_FECHA}.txt"
  echo "  🗑  Puedes borrar nota_semana.txt cuando quieras (ya fue aplicada)."
  echo ""
fi

# ── Resumen final ─────────────────────────────────────────────────────────────
_imprimir_resumen_final "Menú + valoraciones listos — resumen de ejecución"
echo "  Cuando estés listo, ejecuta:"
echo "    bash actualizar_site.sh"
echo ""
echo "════════════════════════════════════════════════"
echo ""
