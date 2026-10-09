import { t } from '@/i18n/index.js'

// Capa adaptable común a todas las vistas. En pantallas chicas los filtros
// secundarios se pliegan detrás de un botón y las tablas se leen como tarjetas
// con el nombre de cada columna; en escritorio no cambia nada.

// v-filtros: el primer control (normalmente el buscador) queda siempre a la
// vista; el resto se abre con «Filtros». El botón indica cuántos están activos.
function activos(el) {
  let n = 0
  for (const hijo of [...el.children].slice(1)) {
    if (hijo.classList.contains('filtros-toggle')) continue
    for (const c of hijo.matches('input, select') ? [hijo] : hijo.querySelectorAll('input, select')) {
      if (c.type === 'checkbox' || c.type === 'radio' ? c.checked : c.value) { n++; break }
    }
  }
  return n
}

function prepararFiltros(el) {
  const hijos = [...el.children].filter((h) => !h.classList.contains('filtros-toggle'))
  let boton = el.querySelector(':scope > .filtros-toggle')
  if (hijos.length < 3) {
    el.classList.remove('filtros-plegables')
    boton?.remove()
    return
  }
  el.classList.add('filtros-plegables')
  if (!boton) {
    boton = document.createElement('button')
    boton.type = 'button'
    boton.className = 'btn btn-chico filtros-toggle'
    boton.addEventListener('click', () => {
      const abierto = el.classList.toggle('abiertos')
      boton.setAttribute('aria-expanded', String(abierto))
    })
    boton.setAttribute('aria-expanded', 'false')
    el.addEventListener('change', () => rotular(el, boton))
    // Al final: el patrón de Vue inserta antes de sus propios nodos y no lo mueve.
    el.appendChild(boton)
  }
  rotular(el, boton)
}

function rotular(el, boton) {
  const n = activos(el)
  boton.textContent = n ? t('Filters ({0})', [n]) : t('Filters')
  boton.classList.toggle('con-activos', n > 0)
}

export const vFiltros = {
  mounted: prepararFiltros,
  updated: prepararFiltros,
}

// v-tarjetas: copia el título de cada columna en data-label de sus celdas,
// respetando colspan y encabezados en varias filas (se toma el más específico).
// Un <th class="col-sec"> marca la columna como secundaria en todas sus celdas.
function titulos(tabla) {
  const filas = tabla.tHead ? [...tabla.tHead.rows] : []
  const rejilla = []
  filas.forEach((fila, r) => {
    rejilla[r] ||= []
    let c = 0
    for (const th of fila.cells) {
      while (rejilla[r][c] !== undefined) c++
      const texto = { t: th.dataset.label ?? th.textContent.trim().replace(/\s+/g, ' '), sec: th.classList.contains('col-sec') }
      for (let i = 0; i < th.rowSpan; i++) {
        rejilla[r + i] ||= []
        for (let j = 0; j < th.colSpan; j++) rejilla[r + i][c + j] = texto
      }
      c += th.colSpan
    }
  })
  const ancho = Math.max(0, ...rejilla.map((f) => f.length))
  const res = []
  for (let c = 0; c < ancho; c++) {
    let texto = { t: '', sec: false }
    for (let r = rejilla.length - 1; r >= 0; r--) if (rejilla[r][c]?.t) { texto = rejilla[r][c]; break }
    res.push(texto)
  }
  return res
}

function rotularTabla(tabla, valor) {
  if (valor === false) { tabla.classList.remove('tarjetas'); return }
  tabla.classList.add('tarjetas')
  const cols = titulos(tabla)
  // El pie (totales) no sigue las columnas: se muestra como una línea de resumen sin rótulos.
  for (const td of tabla.tFoot ? tabla.tFoot.querySelectorAll('td') : []) td.dataset.label = ''
  for (const cuerpo of tabla.tBodies) {
    for (const fila of cuerpo.rows) {
      let c = 0
      const celdas = fila.cells
      // Fila que ocupa casi todo el ancho (vacío, detalle desplegado): sin rótulos.
      fila.classList.toggle('fila-completa', celdas.length === 1 || [...celdas].some((td) => td.colSpan >= cols.length - 1 && cols.length > 2))
      for (const td of celdas) {
        if (!td.hasAttribute('data-label') || td.dataset.auto) {
          td.dataset.label = td.colSpan > 1 ? '' : (cols[c]?.t || '')
          td.dataset.auto = '1'
        }
        // Columna secundaria marcada en su encabezado: la celda se oculta con ella.
        if (td.colSpan === 1) td.classList.toggle('col-sec', !!cols[c]?.sec)
        c += td.colSpan
      }
    }
  }
}

// Las filas pueden venir de componentes hijos: se vuelve a rotular cuando cambian.
export const vTarjetas = {
  mounted(el, b) {
    el._valorTarjetas = b.value
    rotularTabla(el, b.value)
    let pendiente = false
    el._obsTarjetas = new MutationObserver(() => {
      if (pendiente) return
      pendiente = true
      queueMicrotask(() => { pendiente = false; rotularTabla(el, el._valorTarjetas) })
    })
    el._obsTarjetas.observe(el, { childList: true, subtree: true })
  },
  updated(el, b) {
    el._valorTarjetas = b.value
    rotularTabla(el, b.value)
  },
  unmounted: (el) => el._obsTarjetas?.disconnect(),
}
