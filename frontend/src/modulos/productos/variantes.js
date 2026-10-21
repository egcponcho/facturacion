import { t } from '@/i18n/index.js'
import { computed, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import { avisar } from '@/stores/ui'

// Variantes de un producto (de cualquier tipo): se distinguen por los atributos
// de variante de su familia (talla y color, sabor y presentación, concentración
// y envase…) y se escriben fila por fila o se combinan (todos los valores de un
// atributo por todos los de otro). Lo usan el asistente «Nuevo producto» y la
// ficha del producto al agregar variantes.

export const MAX_COMBINACIONES = 500

// "7-10, 12", "6.5-9.5", "S-XL" o "S, M, XL": tramos y valores sueltos
const LETRAS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
export function expandir(texto) {
  const lista = []
  for (const tramo of String(texto || '').split(/[,;]+/).map((x) => x.trim()).filter(Boolean)) {
    const m = tramo.match(/^(\S+)\s*(?:-|to|a)\s*(\S+)$/i)
    const [a, b] = m ? [m[1].toUpperCase(), m[2].toUpperCase()] : []
    if (m && /^\d+(\.5)?$/.test(a) && /^\d+(\.5)?$/.test(b)) {
      const paso = tramo.includes('.5') ? 0.5 : 1
      for (let x = Number(a); x <= Number(b) + 1e-9; x += paso) lista.push(String(x))
    } else if (m && LETRAS.includes(a) && LETRAS.includes(b)) lista.push(...LETRAS.slice(LETRAS.indexOf(a), LETRAS.indexOf(b) + 1))
    else lista.push(tramo)
  }
  return [...new Set(lista)]
}

export const opcionesDe = (a) => (a.opciones || '').split(',').map((x) => x.trim()).filter(Boolean)

// Los atributos que distinguen las variantes: los de la familia (o de su
// antecesora más cercana que los tenga); sin familia ni ejes, todos los activos
export function ejesDeFamilia(familias, id) {
  const porId = Object.fromEntries(familias.map((f) => [String(f.id), f]))
  let f = porId[String(id)]
  const vistos = new Set()
  while (f && !vistos.has(f.id)) {
    vistos.add(f.id)
    if (f.ejes_variante?.length) return f.ejes_variante
    f = porId[String(f.padre_id)]
  }
  return []
}

// g: datos del producto (grupo_producto_id, color); info: el producto existente (al agregar variantes)
export function useVariantes(g, info = ref(null)) {
  const atributos = ref([]) // atributos de variante activos (código, nombre, tipo, opciones, columna)
  const escalas = ref([])
  const familias = ref([])
  const escalaId = ref('')
  const valores = reactive({}) // valores a combinar por atributo (texto con tramos)
  const filas = ref([])
  const pesoTodas = ref('')

  async function cargar() {
    const [atr, grupos, esc] = await Promise.all([
      api.get('/catalogos/atributos_variante', { size: 200 }), api.get('/grupos-producto').catch(() => []),
      api.get('/catalogos/escalas', { size: 200 }).catch(() => ({ items: [] }))])
    atributos.value = (atr.items || []).filter((a) => a.activo !== false).sort((a, b) => (a.orden || 0) - (b.orden || 0))
    familias.value = (grupos || []).filter((x) => x.clase === 'FAMILIA' && x.activa !== false)
    escalas.value = (esc.items || []).filter((e) => e.activo !== false)
  }

  // Un color fijo del producto no es un atributo de sus variantes
  const ejes = computed(() => {
    const codigos = ejesDeFamilia(familias.value, g.grupo_producto_id)
    const lista = codigos.length ? codigos.map((c) => atributos.value.find((a) => a.codigo === c)).filter(Boolean) : atributos.value
    return lista.filter((a) => !(g.color && a.columna === 'color'))
  })
  watch(ejes, (lista) => {
    for (const a of lista) if (!(a.codigo in valores)) valores[a.codigo] = ''
  }, { immediate: true })

  const escalasDe = (a) => escalas.value.filter((e) => (e.atributo || 'TALLA') === a.codigo)
  function usarEscala(a, id) {
    const e = escalas.value.find((x) => String(x.id) === String(id))
    if (!e) return
    valores[a.codigo] = String(e.tallas || '').split(',').map((x) => x.split('=')[0].trim()).filter(Boolean).join(', ')
    escalaId.value = e.id // sus códigos arman los códigos de artículo
  }

  const clave = (v) => ejes.value.map((a) => String(v?.[a.codigo] ?? '').toUpperCase()).join('|')
  const nuevaFila = (vals = {}) => ({ valores: { ...vals }, sufijo: '', sku: '', upc: '', sku_proveedor: '', peso: pesoTodas.value })
  const existentes = computed(() => new Set((info.value?.tallas || []).filter((x) => x.tipo === 'SOLIDO').map((x) => clave(x.valores))))
  const listas = computed(() => ejes.value.map((a) => [a.codigo, expandir(valores[a.codigo])]).filter(([, l]) => l.length))
  const totalCombinaciones = computed(() => (listas.value.length ? listas.value.reduce((n, [, l]) => n * l.length, 1) : 0))

  // Todas las combinaciones de los valores escritos (sin las que ya están en la tabla ni en el producto)
  function combinar() {
    if (!listas.value.length) return 0
    if (totalCombinaciones.value > MAX_COMBINACIONES) {
      avisar(t('That is {0} variants: at most {1} at a time.', [totalCombinaciones.value, MAX_COMBINACIONES]), 'error')
      return 0
    }
    let combos = [{}]
    for (const [codigo, lista] of listas.value) combos = combos.flatMap((c) => lista.map((v) => ({ ...c, [codigo]: v })))
    const ya = new Set(filas.value.map((f) => clave(f.valores)))
    let n = 0
    for (const c of combos) {
      const k = clave(c)
      if (!ya.has(k) && !existentes.value.has(k)) {
        filas.value.push(nuevaFila(c))
        ya.add(k)
        n++
      }
    }
    return n
  }
  function pesoParaTodas() {
    for (const f of filas.value) f.peso = pesoTodas.value
  }
  const vacia = (f) => !Object.values(f.valores).some((v) => String(v || '').trim())
  // Lo que se manda al servidor
  const paraEnviar = () => filas.value.filter((f) => !vacia(f)).map(({ peso, valores: v, ...f }) => ({
    ...f, valores: Object.fromEntries(Object.entries(v).filter(([, x]) => String(x || '').trim())),
    peso_unitario: peso === '' || peso === null ? null : Number(peso),
  }))

  return { atributos, escalas, familias, escalaId, valores, filas, pesoTodas, cargar, ejes, escalasDe, usarEscala, nuevaFila,
    existentes, totalCombinaciones, combinar, pesoParaTodas, vacia, paraEnviar }
}
