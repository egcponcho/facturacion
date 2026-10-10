<script setup>
import Icono from '@/componentes/Icono.vue'
import { t, tx } from '@/i18n/index.js'
import { onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import CampoFecha from '@/componentes/CampoFecha.vue'
import Paginacion from '@/componentes/Paginacion.vue'
import FilasEsqueleto from '@/componentes/FilasEsqueleto.vue'
import { api } from '@/nucleo/api'
import { fmtFechaHora } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'

// Bitácora general: quién hizo qué, cuándo y sobre qué registro. Cada cambio
// trae sus valores antes y después; las contraseñas nunca se guardan.
const f = reactive({ entidad: '', usuario_id: '', accion: '', desde: '', hasta: '' })
const datos = ref({ items: [], total: 0 })
const opciones = ref({ entidades: [], usuarios: [] })
const pag = reactive({ page: 1, size: 25 })
const cargando = ref(false)
const abierta = ref(null)

async function cargar() {
  cargando.value = true
  try {
    const params = { ...pag, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '')) }
    datos.value = await api.get('/auditoria', params)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
watch(f, () => { pag.page = 1; cargar() })
onMounted(async () => {
  cargar()
  opciones.value = await api.get('/auditoria/opciones').catch(() => opciones.value)
})
const activos = () => Object.values(f).filter((v) => v !== '').length
function limpiar() {
  Object.assign(f, { entidad: '', usuario_id: '', accion: '', desde: '', hasta: '' })
}

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
  <div>
    <div class="filtros" v-filtros>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model.lazy="f.accion" type="search" :placeholder="t('Action or reason')" :aria-label="t('Action or reason')" />
      </label>
      <Seleccion v-model="f.entidad" :etiqueta="t('Record')">
        <option value="">{{ t('Record: all') }}</option>
        <option v-for="e in opciones.entidades" :key="e.valor" :value="e.valor">{{ tx(e.texto) }}</option>
      </Seleccion>
      <Seleccion v-model="f.usuario_id" :etiqueta="t('User')">
        <option value="">{{ t('User: all') }}</option>
        <option v-for="u in opciones.usuarios" :key="u.valor" :value="u.valor">{{ tx(u.texto) }}</option>
      </Seleccion>
      <CampoFecha v-model="f.desde" :aria-label="t('From')" :title="t('From')" />
      <CampoFecha v-model="f.hasta" :min="f.desde || undefined" :aria-label="t('To')" :title="t('To')" />
      <button v-if="activos()" type="button" class="btn btn-fantasma" @click="limpiar">{{ t('Clear filters') }}</button>
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla" v-tarjetas>
        <thead><tr><th><span class="oculto-visual">{{ t('Detail') }}</span></th><th>{{ t('Date') }}</th><th>{{ t('User') }}</th><th>{{ t('Record') }}</th><th>{{ t('Action') }}</th><th>{{ t('Detail') }}</th></tr></thead>
        <tbody>
          <FilasEsqueleto v-if="cargando && !datos.items.length" :columnas="6" />
          <tr v-else-if="!datos.items.length"><td colspan="6" class="vacio">{{ activos() ? t('Nothing matches these filters. Try other criteria or clear them.') : t('No activity recorded yet.') }}</td></tr>
          <template v-for="h in datos.items" :key="h.id">
            <tr class="clicable" @click="abierta = abierta === h.id ? null : h.id">
              <td class="chk">
                <button class="btn-icono" type="button" :aria-expanded="abierta === h.id" :aria-label="t('Show detail')" @click.stop="abierta = abierta === h.id ? null : h.id">
                  <Icono :nombre="abierta === h.id ? 'abajo' : 'derecha'" :tam="16" />
                </button>
              </td>
              <td class="sin-corte">{{ fmtFechaHora(h.fecha) }}</td>
              <td>{{ tx(h.usuario || t('System')) }}</td>
              <td>{{ tx(h.entidad_txt) }} <span class="sub">#{{ h.entidad_id }}</span></td>
              <td class="codigo">{{ tx(h.accion) }}</td>
              <td class="envolver">{{ tx(resumen(h.detalle)) }}<span v-if="h.motivo" class="sub">{{ t('Reason: {0}', [h.motivo]) }}</span></td>
            </tr>
            <tr v-if="abierta === h.id" class="fila-detalle">
              <td colspan="6">
                <dl v-if="h.detalle && typeof h.detalle === 'object'" class="lista-cambios">
                  <template v-for="(v, k) in h.detalle" :key="k">
                    <dt>{{ tx(k) }}</dt>
                    <dd v-if="esCambio(v)"><s>{{ tx(valor(v.antes)) }}</s> → <b>{{ tx(valor(v.despues)) }}</b></dd>
                    <dd v-else>{{ tx(valor(v)) }}</dd>
                  </template>
                </dl>
                <p v-else class="ayuda">{{ tx(valor(h.detalle)) }}</p>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <Paginacion :page="pag.page" :size="pag.size" :total="datos.total" @cambiar="(p) => { pag.page = p; cargar() }" @tamano="(s) => { pag.size = s; pag.page = 1; cargar() }" />
  </div>
</template>

<style scoped>
.sin-corte { white-space: nowrap; }
.fila-detalle td { background: var(--superficie-2); }
.lista-cambios { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0; }
.lista-cambios dt { color: var(--tinta-3); font-family: var(--mono); font-size: 0.82rem; }
.lista-cambios dd { margin: 0; word-break: break-word; }
.lista-cambios s { color: var(--tinta-3); }
</style>
