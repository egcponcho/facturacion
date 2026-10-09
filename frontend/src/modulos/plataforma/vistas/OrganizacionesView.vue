<script setup>
import { t, tx } from '@/i18n/index.js'
import { onMounted, reactive, ref } from 'vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import FilasEsqueleto from '@/componentes/FilasEsqueleto.vue'
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
    <button class="btn btn-primario" @click="modal = 'nueva'"><Icono nombre="mas" />{{ t('New organization') }}</button>
  </div>

  <section class="panel">
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Code') }}</th><th>{{ t('Name') }}</th><th>{{ t('Country') }}</th><th class="num">{{ t('Users') }}</th><th>{{ t('Created') }}</th><th>{{ t('Status') }}</th><th></th></tr></thead>
        <tbody>
          <FilasEsqueleto v-if="cargando" :columnas="7" :filas="3" />
          <tr v-for="o in lista" :key="o.id">
            <td class="codigo">{{ tx(o.codigo) }}</td>
            <td><strong>{{ tx(o.nombre) }}</strong><span v-if="o.id === sesion.usuario?.organizacion?.id" class="sub">{{ t('You are working here') }}</span></td>
            <td>{{ tx(o.pais || '—') }}</td>
            <td class="num">{{ tx(o.usuarios) }}</td>
            <td>{{ fmtFecha(o.creada_en) }}</td>
            <td><span class="etiqueta" :class="o.activa ? 'ok' : ''">{{ o.activa ? t('Active') : t('Suspended') }}</span></td>
            <td class="fila-flex">
              <button v-if="o.activa && o.id !== sesion.usuario?.organizacion?.id" class="btn btn-chico" @click="entrar(o)">{{ t('Enter') }}</button>
              <button class="btn btn-chico btn-fantasma" @click="cambiarEstado(o)">{{ o.activa ? t('Suspend') : t('Reactivate') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

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
