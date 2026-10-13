<script setup>
import Icono from '@/componentes/Icono.vue'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import CampoFecha from '@/componentes/CampoFecha.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { api } from '@/nucleo/api'
import { fmtFecha, fmtFechaHora } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'

// Bitácora general: quién hizo qué, cuándo y sobre qué registro. Cada cambio
// trae sus valores antes y después; las contraseñas nunca se guardan. La tabla
// pagina y filtra cada columna por sus valores en el servidor (/auditoria/valores).
const f = reactive({ entidad: '', usuario_id: '', accion: '', desde: '', hasta: '' })
const datos = ref({ items: [], total: 0 })
const opciones = ref({ entidades: [], usuarios: [] })
const cargando = ref(false)
const tabla = ref(null)
const base = () => Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ''))
let ultima = null
async function cargar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/auditoria', { ...base(), orden: c.orden || undefined, page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const valores = (columna, buscar, otros) => api.get('/auditoria/valores', { ...base(), columna, buscar, f: JSON.stringify(otros) })
watch(f, () => {
  if (tabla.value && tabla.value.pagina !== 1) tabla.value.pagina = 1
  else cargar()
})
onMounted(async () => {
  opciones.value = await api.get('/auditoria/opciones').catch(() => opciones.value)
})
const activos = () => Object.values(f).filter((v) => v !== '').length
function limpiar() {
  Object.assign(f, { entidad: '', usuario_id: '', accion: '', desde: '', hasta: '' })
}
const columnas = computed(() => [
  { clave: 'fecha', texto: t('Date'), fija: true, prioridad: 1, textoValor: (v) => fmtFecha(v) },
  { clave: 'usuario', texto: t('User'), prioridad: 1, textoValor: (v) => v || t('System') },
  { clave: 'entidad', texto: t('Record'), prioridad: 2, opciones: opciones.value.entidades.map((e) => [e.valor, e.texto]) },
  { clave: 'accion', texto: t('Action'), prioridad: 2 },
  { clave: 'motivo', texto: t('Reason'), prioridad: 3, inicial: false },
  { clave: 'detalle', texto: t('Detail'), prioridad: 3, filtro: false, ordenable: false },
])

// Un cambio campo por campo ({campo: {antes, despues}}) o un dato suelto
const esCambio = (v) => v && typeof v === 'object' && !Array.isArray(v) && 'despues' in v
const valor = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v))
const resumen = (d) => {
  if (!d || typeof d !== 'object') return valor(d)
  const claves = Object.keys(d)
  return claves.slice(0, 3).join(', ') + (claves.length > 3 ? ` +${claves.length - 3}` : '')
}
</script>

<template>
  <TablaDatos ref="tabla" tabla="admin_bitacora" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              :valores="valores" expandible :externos="{ ...f }" :mas-filtros-activos="[f.desde, f.hasta].filter(Boolean).length" :etiqueta="t('Activity log')"
              @consulta="cargar" @vista="(x) => Object.assign(f, { entidad: x.entidad || '', usuario_id: x.usuario_id || '', accion: x.accion || '', desde: x.desde || '', hasta: x.hasta || '' })"
              @limpiar-externos="limpiar">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model.lazy="f.accion" type="search" :placeholder="t('Action or reason')" :aria-label="t('Action or reason')" />
      </label>
    </template>
    <template #filtros>
      <Seleccion v-model="f.entidad" :etiqueta="t('Record')">
        <option value="">{{ t('Record: all') }}</option>
        <option v-for="e in opciones.entidades" :key="e.valor" :value="e.valor">{{ tx(e.texto) }}</option>
      </Seleccion>
      <Seleccion v-model="f.usuario_id" :etiqueta="t('User')">
        <option value="">{{ t('User: all') }}</option>
        <option v-for="u in opciones.usuarios" :key="u.valor" :value="u.valor">{{ tx(u.texto) }}</option>
      </Seleccion>
    </template>
    <template #mas-filtros>
      <CampoFecha v-model="f.desde" :aria-label="t('From')" :title="t('From')" />
      <CampoFecha v-model="f.hasta" :min="f.desde || undefined" :aria-label="t('To')" :title="t('To')" />
    </template>
    <template #celda-fecha="{ fila: h }"><span class="sin-corte">{{ fmtFechaHora(h.fecha) }}</span></template>
    <template #celda-usuario="{ fila: h }">{{ tx(h.usuario || t('System')) }}</template>
    <template #celda-entidad="{ fila: h }">{{ tx(h.entidad_txt) }} <span class="sub">#{{ h.entidad_id }}</span></template>
    <template #celda-accion="{ fila: h }"><span class="codigo">{{ tx(h.accion) }}</span></template>
    <template #celda-detalle="{ fila: h }"><div class="resumen">{{ tx(resumen(h.detalle)) }}<span v-if="h.motivo" class="sub">{{ t('Reason: {0}', [h.motivo]) }}</span></div></template>
    <template #detalle="{ fila: h }">
      <dl v-if="h.detalle && typeof h.detalle === 'object'" class="lista-cambios">
        <template v-for="(v, k) in h.detalle" :key="k">
          <dt>{{ tx(k) }}</dt>
          <dd v-if="esCambio(v)"><s>{{ tx(valor(v.antes)) }}</s> → <b>{{ tx(valor(v.despues)) }}</b></dd>
          <dd v-else>{{ tx(valor(v)) }}</dd>
        </template>
      </dl>
      <p v-else class="ayuda">{{ tx(valor(h.detalle)) }}</p>
    </template>
    <template #vacio>{{ activos() ? t('Nothing matches these filters. Try other criteria or clear them.') : t('No activity recorded yet.') }}</template>
  </TablaDatos>
</template>

<style scoped>
.sin-corte { white-space: nowrap; }
.resumen { min-width: 200px; max-width: 420px; white-space: normal; }
.lista-cambios { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0; }
.lista-cambios dt { color: var(--tinta-3); font-family: var(--mono); font-size: 0.82rem; }
.lista-cambios dd { margin: 0; word-break: break-word; }
.lista-cambios s { color: var(--tinta-3); }
</style>
