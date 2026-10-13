<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import { buscador } from '@/nucleo/busqueda'
import { puede } from '@/stores/sesion'
import EstadoBadge from './EstadoBadge.vue'
import Icono from './Icono.vue'

// Búsqueda global y paleta de comandos (Ctrl+K / ⌘K): un número de OC, SKU,
// UPC, estilo, factura, packing list, contenedor, BL/AWB, proveedor o marca
// abre su registro sin saber en qué módulo está. Las mismas reglas de búsqueda
// que las listas; el servidor solo devuelve lo que el usuario puede ver.
const router = useRouter()
const abierta = ref(false)
const texto = ref('')
const resultado = ref({ grupos: [] })
const cargando = ref(false)
const activo = ref(0)
const entrada = ref(null)
const lista = ref(null)
const mac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform || '')

const GRUPOS = {
  ordenes: { nombre: t('Purchase orders'), icono: 'ordenes' },
  productos: { nombre: t('Products'), icono: 'etiqueta' },
  facturas: { nombre: t('Invoices'), icono: 'factura' },
  packing_lists: { nombre: t('Packing lists'), icono: 'caja' },
  embarques: { nombre: t('Shipments'), icono: 'barco' },
  unidades: { nombre: t('Load units'), icono: 'contenedor' },
  proveedores: { nombre: t('Suppliers'), icono: 'usuarios' },
  marcas: { nombre: t('Brands'), icono: 'etiqueta' },
  documentos: { nombre: t('Documents'), icono: 'archivo' },
}

// Acciones y accesos rápidos, solo los que el rol puede usar
const COMANDOS = computed(() => [
  { texto: t('Import purchase orders'), ruta: '/importar', icono: 'importar', permiso: 'oc.importar', clave: 'import load upload po orders' },
  { texto: t('New purchase order'), ruta: '/ordenes/nueva', icono: 'mas', permiso: 'oc.editar', clave: 'new create po order' },
  { texto: t('New shipment'), ruta: '/transporte?nuevo=1', icono: 'barco', permiso: 'transporte.gestionar', clave: 'new create shipment booking' },
  { texto: t('Go to orders'), ruta: '/ordenes', icono: 'ordenes', permiso: 'oc.ver', clave: 'orders po' },
  { texto: t('Go to invoices'), ruta: '/facturas', icono: 'factura', permiso: 'oc.ver', clave: 'invoices' },
  { texto: t('Go to shipments'), ruta: '/transporte', icono: 'barco', permiso: 'transporte.gestionar', clave: 'shipments containers' },
  { texto: t('Go to products'), ruta: '/productos', icono: 'etiqueta', permiso: 'producto.ver', clave: 'products classification' },
  { texto: t('Products pending classification'), ruta: '/productos?estado=revision', icono: 'etiqueta', permiso: 'producto.ver', clave: 'pending classification review' },
  { texto: t('Go to tracking'), ruta: '/seguimiento', icono: 'ruta', permiso: 'seguimiento.ver', clave: 'tracking' },
  { texto: t('Open suppliers'), ruta: '/mantenimiento?catalogo=proveedores', icono: 'usuarios', permiso: 'catalogos.ver', clave: 'suppliers vendors master data' },
  { texto: t('Master data'), ruta: '/mantenimiento', icono: 'base', permiso: 'catalogos.ver', clave: 'items brands plants master' },
  { texto: t('Lead times'), ruta: '/leadtimes', icono: 'reloj', permiso: 'catalogos.ver', clave: 'lead times' },
  { texto: t('Users and access'), ruta: '/admin', icono: 'usuarios', permiso: 'admin', clave: 'users roles access' },
  { texto: t('My profile'), ruta: '/perfil', icono: 'usuario', clave: 'profile preferences' },
].filter((c) => !c.permiso || puede(c.permiso)))

const comandos = computed(() => {
  const coincide = buscador(texto.value)
  return COMANDOS.value.filter((c) => coincide([tx(c.texto), c.clave])).slice(0, texto.value.trim() ? 4 : 8)
})

// Secciones (acciones y luego resultados por tipo); cada opción lleva su
// posición en la lista plana para moverse con el teclado
const secciones = computed(() => {
  let i = 0
  const out = []
  if (comandos.value.length) {
    out.push({ clave: 'comandos', titulo: texto.value.trim() ? t('Actions') : t('Quick actions'),
      items: comandos.value.map((c) => ({ ...c, id: c.ruta, i: i++ })) })
  }
  for (const g of resultado.value.grupos) {
    out.push({ clave: g.tipo, titulo: GRUPOS[g.tipo]?.nombre || g.tipo, icono: GRUPOS[g.tipo]?.icono, ver_todos: g.ver_todos,
      items: g.items.map((x) => ({ ...x, i: i++ })) })
  }
  return out
})
const opciones = computed(() => secciones.value.flatMap((s) => s.items))

let temporizador = null
let pedido = 0
watch(texto, (q) => {
  activo.value = 0
  clearTimeout(temporizador)
  if (q.trim().length < 2) {
    resultado.value = { grupos: [] }
    cargando.value = false
    return
  }
  cargando.value = true
  temporizador = setTimeout(async () => {
    const n = ++pedido
    try {
      const r = await api.get('/buscar', { q })
      if (n === pedido) resultado.value = r
    } catch {
      if (n === pedido) resultado.value = { grupos: [] }
    } finally {
      if (n === pedido) cargando.value = false
    }
  }, 220)
})

async function abrir() {
  abierta.value = true
  await nextTick()
  entrada.value?.focus()
  entrada.value?.select()
}
function cerrar() {
  abierta.value = false
}
function ir(o) {
  if (!o) return
  cerrar()
  texto.value = ''
  router.push(o.ruta)
}
function verTodos(g) {
  cerrar()
  router.push(g.ver_todos)
}

async function tecla(e) {
  const n = opciones.value.length
  if (e.key === 'ArrowDown' && n) {
    e.preventDefault()
    activo.value = (activo.value + 1) % n
  } else if (e.key === 'ArrowUp' && n) {
    e.preventDefault()
    activo.value = (activo.value - 1 + n) % n
  } else if (e.key === 'Enter') {
    e.preventDefault()
    ir(opciones.value[activo.value])
    return
  } else if (e.key === 'Escape') {
    cerrar()
    return
  } else {
    return
  }
  await nextTick()
  lista.value?.querySelector('[data-activo="1"]')?.scrollIntoView({ block: 'nearest' })
}

function atajo(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    abierta.value ? cerrar() : abrir()
  } else if (e.key === '/' && !abierta.value && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '')
    && !document.activeElement?.isContentEditable) {
    e.preventDefault()
    abrir()
  }
}
onMounted(() => document.addEventListener('keydown', atajo))
onBeforeUnmount(() => document.removeEventListener('keydown', atajo))
</script>

<template>
  <button type="button" class="bg-disparador" :aria-label="t('Search everything')" @click="abrir">
    <Icono nombre="lupa" :tam="16" />
    <span class="bg-placeholder">{{ t('Search PO, SKU, invoice, container…') }}</span>
    <kbd class="bg-kbd">{{ mac ? '⌘' : 'Ctrl' }} K</kbd>
  </button>
  <Teleport to="body">
    <div v-if="abierta" class="bg-fondo" @mousedown.self="cerrar">
      <div class="bg-panel" role="dialog" aria-modal="true" :aria-label="t('Search everything')">
        <div class="bg-entrada">
          <Icono nombre="lupa" :tam="18" />
          <input ref="entrada" v-model="texto" type="search" role="combobox" aria-autocomplete="list" :aria-expanded="opciones.length > 0"
                 aria-controls="bg-lista" :aria-activedescendant="opciones.length ? `bg-op-${activo}` : undefined"
                 :placeholder="t('Search PO, SKU, UPC, style, invoice, PL, container, B/L, supplier… or type a command')" @keydown="tecla" />
          <span v-if="cargando" class="bg-cargando" aria-hidden="true"></span>
          <kbd class="bg-kbd">Esc</kbd>
        </div>
        <div id="bg-lista" ref="lista" class="bg-lista" role="listbox">
          <section v-for="sec in secciones" :key="sec.clave" class="bg-grupo">
            <h3>
              {{ tx(sec.titulo) }}
              <button v-if="sec.ver_todos" type="button" class="bg-ver-todos" @click="verTodos(sec)">{{ t('See all') }}</button>
            </h3>
            <button v-for="x in sec.items" :id="`bg-op-${x.i}`" :key="x.id" type="button" role="option" class="bg-item"
                    :data-activo="activo === x.i ? 1 : 0" :aria-selected="activo === x.i" @mousemove="activo = x.i" @click="ir(x)">
              <span class="bg-icono"><Icono :nombre="x.icono || sec.icono || 'info'" :tam="16" /></span>
              <span class="bg-textos"><b>{{ tx(x.texto || x.titulo) }}</b><small v-if="x.sub">{{ tx(x.sub) }}</small></span>
              <EstadoBadge v-if="x.estado" :estado="x.estado" />
              <Icono v-else-if="sec.clave === 'comandos'" nombre="flecha" :tam="14" class="bg-ir" />
            </button>
          </section>
          <p v-if="texto.trim().length >= 2 && !cargando && !resultado.grupos.length" class="bg-nada">
            {{ t('Nothing found for “{0}”. Try a PO, SKU, UPC, style, invoice, container or supplier.', [texto.trim()]) }}
          </p>
          <p v-if="!texto.trim()" class="bg-ayuda">{{ t('Tip: paste several PO numbers separated by spaces to find them all.') }}</p>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.bg-disparador { display: inline-flex; align-items: center; gap: 8px; min-width: 0; height: 36px; padding: 0 8px 0 10px; border: 1px solid var(--linea);
  border-radius: var(--radio); background: var(--superficie-2); color: var(--tinta-3); cursor: pointer; font: inherit; font-size: 0.86rem; }
.bg-disparador:hover { border-color: var(--borde-hover); color: var(--tinta-2, var(--tinta-3)); }
.bg-placeholder { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 240px; }
.bg-kbd { font: inherit; font-size: 0.72rem; padding: 1px 6px; border: 1px solid var(--linea); border-radius: 5px; background: var(--superficie); color: var(--tinta-3); white-space: nowrap; }
.bg-fondo { position: fixed; inset: 0; background: var(--velo); z-index: 60; display: flex; justify-content: center; align-items: flex-start; padding: 10vh 16px 16px; }
.bg-panel { width: 100%; max-width: 640px; background: var(--superficie); border-radius: 14px; box-shadow: var(--sombra-flotante); display: flex; flex-direction: column; max-height: 75vh; overflow: hidden; }
.bg-entrada { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--linea-suave); color: var(--tinta-3); }
.bg-entrada input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; font: inherit; font-size: 1rem; color: var(--tinta, inherit); }
.bg-cargando { width: 14px; height: 14px; border: 2px solid var(--linea); border-top-color: var(--acento); border-radius: 50%; animation: bg-giro 0.7s linear infinite; }
@keyframes bg-giro { to { transform: rotate(360deg); } }
.bg-lista { overflow-y: auto; padding: 6px 8px 10px; }
.bg-grupo h3 { display: flex; justify-content: space-between; align-items: center; margin: 10px 8px 4px; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--tinta-3); }
.bg-ver-todos { border: 0; background: none; color: var(--acento-texto); font: inherit; font-size: 0.72rem; text-transform: none; letter-spacing: 0; cursor: pointer; }
.bg-item { width: 100%; display: flex; align-items: center; gap: 10px; padding: 8px 10px; border: 0; border-radius: var(--radio); background: none; text-align: start; font: inherit; color: inherit; cursor: pointer; }
.bg-item[data-activo="1"] { background: var(--acento-claro); }
.bg-icono { display: inline-flex; width: 28px; height: 28px; align-items: center; justify-content: center; border-radius: 7px; background: var(--superficie-2); color: var(--tinta-3); flex: none; }
.bg-textos { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.bg-textos b { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bg-textos small { color: var(--tinta-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bg-ir { color: var(--tinta-3); }
.bg-nada, .bg-ayuda { margin: 14px 10px; color: var(--tinta-3); font-size: 0.88rem; }
@media (max-width: 900px) { .bg-placeholder, .bg-disparador .bg-kbd { display: none; } .bg-disparador { width: 36px; justify-content: center; padding: 0; } }
</style>
