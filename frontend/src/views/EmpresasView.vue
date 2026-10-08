<script setup>
import { t, tx } from '../i18n/index.js'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import EstadoVacio from '../components/EstadoVacio.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import { cargarSesion, sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'

// Empresas de la instalación (solo quien administra la plataforma): crear una
// nueva con su administrador inicial y entrar a trabajar en cualquiera.
const router = useRouter()
const lista = ref(null)
const nueva = ref(null)
const creada = ref(null)
const ocupado = ref(false)

async function cargar() {
  try {
    lista.value = await api.get('/organizaciones')
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)

async function crear() {
  ocupado.value = true
  try {
    creada.value = await api.post('/organizaciones', nueva.value)
    nueva.value = null
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function entrar(o) {
  try {
    await api.post(`/organizaciones/${o.id}/entrar`)
    await cargarSesion(true)
    avisar(t('You are now working in {0}.', [o.nombre]))
    router.push('/')
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <header class="pagina-cabeza">
    <div>
      <p class="eyebrow">{{ t('Platform') }}</p>
      <h1>{{ t('Companies') }}</h1>
      <p>{{ t('Each company has its own users, suppliers, orders, invoices, shipments and settings, and never sees the others.') }}</p>
    </div>
    <div class="fila-flex">
      <button class="btn btn-primario" @click="nueva = { codigo: '', nombre: '', pais: '', admin_email: '', admin_nombre: '' }"><Icono nombre="mas" />{{ t('New company') }}</button>
    </div>
  </header>

  <section class="panel">
    <p v-if="!lista" class="ayuda">{{ t('Loading…') }}</p>
    <EstadoVacio v-else-if="!lista.length" icono="base" :titulo="t('No companies yet')" />
    <table v-else class="tabla">
      <thead><tr><th>{{ t('Company') }}</th><th>{{ t('Code') }}</th><th>{{ t('Country') }}</th><th class="num">{{ t('Users') }}</th><th></th></tr></thead>
      <tbody>
        <tr v-for="o in lista" :key="o.id">
          <td>
            <span class="fila-flex" style="gap: 10px; flex-wrap: nowrap">
              <img v-if="o.logo" :src="o.logo" alt="" class="mini-logo" /><span v-else class="mini-logo mini-logo-vacio"><Icono nombre="caja" :tam="14" /></span>
              <b>{{ tx(o.nombre) }}</b>
              <span v-if="o.id === sesion.usuario?.organizacion?.id" class="etiqueta acento">{{ t('Current') }}</span>
            </span>
          </td>
          <td>{{ tx(o.codigo) }}</td>
          <td>{{ tx(o.pais || '—') }}</td>
          <td class="num">{{ tx(o.usuarios) }}</td>
          <td class="texto-derecha">
            <button v-if="o.id !== sesion.usuario?.organizacion?.id" class="btn btn-chico" @click="entrar(o)">{{ t('Work in this company') }}<Icono nombre="derecha" :tam="13" /></button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>

  <Modal v-if="nueva" :titulo="t('New company')" ancho="520px" @cerrar="nueva = null">
    <form id="form-empresa" class="rejilla-campos" @submit.prevent="crear">
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="nueva.nombre" class="entrada" maxlength="200" required /></label>
      <label class="campo"><span class="req">{{ t('Code') }}</span><input v-model="nueva.codigo" class="entrada" maxlength="20" required style="text-transform: uppercase" :placeholder="t('E.g. ACME')" /></label>
      <label class="campo"><span>{{ t('Country') }}</span><input v-model="nueva.pais" class="entrada" maxlength="2" style="text-transform: uppercase" :placeholder="t('E.g. SV')" /></label>
      <label class="campo"><span class="req">{{ t('Administrator email') }}</span><input v-model="nueva.admin_email" type="email" class="entrada" required /></label>
      <label class="campo"><span>{{ t('Administrator name') }}</span><input v-model="nueva.admin_nombre" class="entrada" maxlength="200" /></label>
      <p class="ayuda campo-ancho">{{ t('The company starts with the default roles and this administrator, who sets everything else up from Settings.') }}</p>
    </form>
    <template #pie>
      <button class="btn" @click="nueva = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-empresa" :disabled="ocupado">{{ t('Create company') }}</button>
    </template>
  </Modal>

  <Modal v-if="creada" :titulo="t('Company created')" ancho="480px" @cerrar="creada = null">
    <p>{{ t('Share these sign-in details with the administrator of {0}. They will be asked to change the password the first time.', [creada.nombre]) }}</p>
    <dl class="resumen-datos">
      <dt>{{ t('Email') }}</dt><dd><b>{{ tx(creada.admin_email) }}</b></dd>
      <dt>{{ t('Temporary password') }}</dt><dd><code>{{ tx(creada.clave_temporal) }}</code></dd>
    </dl>
    <template #pie><button class="btn btn-primario" @click="creada = null">{{ t('Done') }}</button></template>
  </Modal>
</template>

<style scoped>
.mini-logo { width: 28px; height: 28px; border-radius: 7px; object-fit: contain; border: 1px solid var(--linea); background: var(--superficie-2); flex: none; }
.mini-logo-vacio { display: grid; place-items: center; color: var(--tinta-3); }
</style>
