<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { buscador } from '@/nucleo/busqueda.js'
import { api } from '@/nucleo/api'
import { fmtFecha } from '@/nucleo/utils'
import { cargarSesion, sesion } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { useRouter } from 'vue-router'

// Plataforma: las organizaciones (empresas cliente) de la instalación. Cada una
// ve solo sus datos; desde aquí se crean, se suspenden y se entra a cualquiera
// para darle soporte.
const router = useRouter()
const lista = ref([])
const cargando = ref(true)
const vacia = () => ({ codigo: '', nombre: '', pais: '', admin_email: '', admin_nombre: '', admin_telefono: '' })
const nueva = reactive(vacia())
const modal = ref(null) // 'nueva' | { creada }
const errores = ref({})
const guardando = ref(false)
const q = ref('')
const vista = computed(() => {
  const coincide = buscador(q.value)
  return lista.value.filter((o) => coincide([o.codigo, o.nombre, o.pais]))
})
const columnas = [
  { clave: 'codigo', texto: t('Code'), fija: true, prioridad: 1 },
  { clave: 'nombre', texto: t('Name'), prioridad: 1, filtro: 'texto' },
  { clave: 'pais', texto: t('Country'), prioridad: 3 },
  { clave: 'usuarios', texto: t('Users'), num: true, prioridad: 2 },
  { clave: 'creada_en', texto: t('Created'), prioridad: 3 },
  { clave: 'activa', texto: t('Status'), prioridad: 2, filtro: 'opcion', opciones: [[true, t('Active')], [false, t('Suspended')]] },
]

async function cargar() {
  try {
    lista.value = await api.get('/plataforma/organizaciones')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)

async function crear() {
  guardando.value = true
  errores.value = {}
  try {
    const r = await api.post('/plataforma/organizaciones', { ...nueva, pais: nueva.pais || null, admin_telefono: nueva.admin_telefono || null })
    modal.value = { creada: r }
    Object.assign(nueva, vacia())
    cargar()
  } catch (e) {
    errores.value = Object.fromEntries((e.detalle || []).map((d) => [d.campo, d.mensaje]))
    errorApi(e)
  } finally {
    guardando.value = false
  }
}

async function cambiarEstado(o) {
  try {
    await api.patch(`/plataforma/organizaciones/${o.id}`, { activa: !o.activa })
    avisar(o.activa ? t('Organization suspended: its users can no longer sign in.') : t('Organization reactivated.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

async function entrar(o) {
  try {
    await api.post('/plataforma/entrar', { organizacion_id: o.id })
    await cargarSesion(true)
    avisar(t('You are now working in {0}.', [o.nombre]))
    router.push('/')
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Organizations') }}</h1>
      <p>{{ t('Each organization only sees its own data. Shared reference data (official tariff schedule, classification engine, countries and trade agreements) is maintained here by the platform.') }}</p>
    </div>
    <div class="acciones"><button class="btn btn-primario" type="button" @click="modal = 'nueva'"><Icono nombre="mas" />{{ t('New organization') }}</button></div>
  </div>

  <TablaDatos tabla="organizaciones" :columnas="columnas" :filas="vista" :cargando="cargando" orden-inicial="nombre:asc" :etiqueta="t('Organizations')">
    <template #barra>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search code or name')" :aria-label="t('Search')" /></label>
    </template>
    <template #celda-codigo="{ fila: o }"><strong class="codigo">{{ tx(o.codigo) }}</strong></template>
    <template #celda-nombre="{ fila: o }"><strong>{{ tx(o.nombre) }}</strong><span v-if="o.id === sesion.usuario?.organizacion?.id" class="sub">{{ t('You are working here') }}</span></template>
    <template #celda-creada_en="{ fila: o }">{{ fmtFecha(o.creada_en) }}</template>
    <template #celda-activa="{ fila: o }"><span class="etiqueta ms-0" :class="o.activa ? 'ok' : ''">{{ o.activa ? t('Active') : t('Suspended') }}</span></template>
    <template #acciones="{ fila: o }">
      <div class="acciones-apiladas">
        <button v-if="o.activa && o.id !== sesion.usuario?.organizacion?.id" class="btn btn-chico btn-primario" type="button" @click="entrar(o)">{{ t('Enter') }}</button>
        <button class="btn btn-chico" type="button" @click="cambiarEstado(o)">{{ o.activa ? t('Suspend') : t('Reactivate') }}</button>
      </div>
    </template>
    <template #vacio>{{ q ? t('No records match these filters.') : t('No records yet.') }}</template>
  </TablaDatos>

  <Modal v-if="modal === 'nueva'" :titulo="t('New organization')" ancho="560px" @cerrar="modal = null">
    <form id="form-org" class="rejilla-campos" @submit.prevent="crear">
      <label class="campo"><span>{{ t('Code') }} <b class="req">*</b></span><input v-model="nueva.codigo" required maxlength="20" autocomplete="off" />
        <small class="nota">{{ t('Letters, numbers, - and _. It cannot change later.') }}</small></label>
      <label class="campo"><span>{{ t('Name') }} <b class="req">*</b></span><input v-model="nueva.nombre" required maxlength="200" /></label>
      <label class="campo"><span>{{ t('Country (ISO)') }}</span><input v-model="nueva.pais" maxlength="2" /></label>
      <fieldset class="campo-ancho">
        <legend>{{ t('First administrator') }}</legend>
        <div class="rejilla-campos">
          <label class="campo"><span>{{ t('Email') }} <b class="req">*</b></span><input v-model="nueva.admin_email" type="email" required maxlength="200" /></label>
          <label class="campo"><span>{{ t('Name') }}</span><input v-model="nueva.admin_nombre" maxlength="200" /></label>
          <label class="campo"><span>{{ t('Mobile for two-step verification') }}</span><input v-model="nueva.admin_telefono" placeholder="+50370000000" maxlength="30" />
            <small v-if="errores.admin_telefono" class="nota error">{{ tx(errores.admin_telefono) }}</small></label>
        </div>
      </fieldset>
    </form>
    <template #pie>
      <button type="button" class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button type="submit" form="form-org" class="btn btn-primario" :disabled="guardando">{{ t('Create organization') }}</button>
    </template>
  </Modal>

  <Modal v-else-if="modal?.creada" :titulo="t('Organization created')" ancho="520px" @cerrar="modal = null">
    <p>{{ t('{0} is ready with its factory roles, value lists and release states. Give its administrator this temporary password; it must be changed at the first sign-in.', [modal.creada.nombre]) }}</p>
    <dl class="lista-datos">
      <dt>{{ t('Administrator') }}</dt><dd>{{ tx(modal.creada.admin_email) }}</dd>
      <dt>{{ t('Temporary password') }}</dt><dd class="codigo">{{ tx(modal.creada.password_temporal) }}</dd>
    </dl>
    <template #pie><button type="button" class="btn btn-primario" @click="modal = null">{{ t('Done') }}</button></template>
  </Modal>
</template>

<style scoped>
.campo-ancho { grid-column: 1 / -1; border: 1px solid var(--linea); border-radius: var(--radio); padding: 10px 14px 14px; }
.campo-ancho legend { font-weight: 650; padding: 0 6px; }
.lista-datos { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; }
.lista-datos dd { margin: 0; font-weight: 600; }
</style>
