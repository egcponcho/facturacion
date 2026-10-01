<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icono from '../components/Icono.vue'
import SelectorIdioma from '../components/SelectorIdioma.vue'
import SelectorTema from '../components/SelectorTema.vue'
import { iniciarSesion, reenviarCodigo, verificarCodigo } from '../stores/sesion'

// Two steps: password, then the one-time code sent by SMS to the user's
// registered mobile. The session lives in an httpOnly cookie.
const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const codigo = ref('')
const desafio = ref(null)
const error = ref('')
const enviando = ref(false)
const espera = ref(0)
const campoCodigo = ref(null)
let reloj = null

const DEMO_PASSWORD = t('Supplier2026')
const DEMO = [
  [t('tnf@demo.com'), t('Supplier'), t('The North Face')],
  [t('vans@demo.com'), t('Supplier'), t('Vans')],
  [t('interno@demo.com'), t('Imports'), t('Internal team')],
  [t('admin@demo.com'), t('Administrator'), t('Full access')],
]
const expirada = computed(() => route.query.expirada === '1')

function contar(segundos) {
  espera.value = segundos
  clearInterval(reloj)
  reloj = setInterval(() => {
    espera.value = Math.max(0, espera.value - 1)
    if (!espera.value) clearInterval(reloj)
  }, 1000)
}

function continuar() {
  router.push(route.query.volver || '/')
}

async function entrar() {
  error.value = ''
  enviando.value = true
  try {
    const r = await iniciarSesion(email.value, password.value)
    if (!r) return continuar()
    desafio.value = r
    codigo.value = ''
    contar(r.reenviar_en)
    await nextTick()
    campoCodigo.value?.focus()
  } catch (e) {
    error.value = e.message
  } finally {
    enviando.value = false
  }
}

async function verificar() {
  error.value = ''
  enviando.value = true
  try {
    await verificarCodigo(desafio.value.desafio, codigo.value)
    continuar()
  } catch (e) {
    error.value = e.message
    codigo.value = ''
    if (e.codigo === 'desafio_invalido') volver()
  } finally {
    enviando.value = false
  }
}

async function reenviar() {
  error.value = ''
  try {
    desafio.value = await reenviarCodigo(desafio.value.desafio)
    contar(desafio.value.reenviar_en)
  } catch (e) {
    error.value = e.message
    if (e.codigo === 'demasiados_envios' || e.codigo === 'desafio_invalido') volver()
  }
}

function volver() {
  desafio.value = null
  codigo.value = ''
  password.value = ''
}

// Six digits: submit on its own when complete
function alEscribir() {
  codigo.value = codigo.value.replace(/\D/g, '').slice(0, 6)
  if (codigo.value.length === 6 && !enviando.value) verificar()
}

function demo(correo) {
  email.value = correo
  password.value = DEMO_PASSWORD
  entrar()
}

onBeforeUnmount(() => clearInterval(reloj))
</script>

<template>
  <div class="login">
    <section class="login-arte">
      <div class="marca" style="padding: 0">
        <span class="marca-logo"><Icono nombre="caja" :tam="20" /></span>
        <span class="marca-texto">{{ t('Workspace') }}<span>{{ t('Invoicing, packing and shipments') }}</span></span>
      </div>
      <div>
        <h1>{{ t('From purchase order to container, with no loose spreadsheets.') }}</h1>
        <p>{{ t('Invoice from your POs, pack with templates and follow every shipment to the warehouse.') }}</p>
      </div>
      <ul class="login-pasos">
        <li><span><Icono nombre="factura" /></span>{{ t('Invoice full POs or in parts') }}</li>
        <li><span><Icono nombre="caja" /></span>{{ t('Pack by casepack, inner pack or prepack in one step') }}</li>
        <li><span><Icono nombre="barco" /></span>{{ t('Load containers and track transit') }}</li>
      </ul>
    </section>
    <div class="login-lado">
      <div class="login-ajustes"><SelectorIdioma /><SelectorTema /></div>

      <form v-if="!desafio" class="login-caja" @submit.prevent="entrar">
        <div>
          <div class="login-titulo">{{ t('Sign in') }}</div>
          <p class="ayuda">{{ t('Use your supplier or import team email.') }}</p>
        </div>
        <p v-if="expirada && !error" class="nota aviso" role="status"><Icono nombre="reloj" />{{ t('Your session expired due to inactivity. Sign in again.') }}</p>
        <label class="campo"><span class="req">{{ t('Email') }}</span><input v-model="email" type="email" autocomplete="username" required /></label>
        <label class="campo"><span class="req">{{ t('Password') }}</span><input v-model="password" type="password" autocomplete="current-password" required /></label>
        <p v-if="error" class="nota error" role="alert"><Icono nombre="alerta" />{{ tx(error) }}</p>
        <button class="btn btn-primario btn-grande" type="submit" :disabled="enviando">{{ tx(enviando ? t('Checking…') : t('Continue')) }}</button>
        <p class="ayuda login-seguridad"><Icono nombre="candado" :tam="13" />{{ t('Two-step verification: we send a code to your registered mobile.') }}</p>
        <div class="demo">
          <span>{{ t('Demo accounts (password {0}). One click to sign in:', [DEMO_PASSWORD]) }}</span>
          <div class="demo-cuentas">
            <button v-for="[correo, rol, nombre] in DEMO" :key="correo" type="button" @click="demo(correo)">
              <b>{{ tx(nombre) }}</b>{{ tx(rol) }}
            </button>
          </div>
        </div>
      </form>

      <form v-else class="login-caja" @submit.prevent="verificar">
        <div>
          <div class="login-titulo">{{ t('Check your phone') }}</div>
          <p class="ayuda">{{ t('We sent a 6-digit code by SMS to') }} <b>{{ tx(desafio.telefono) }}</b>. {{ t('It expires in {0} minutes.', [Math.round(desafio.expira_en / 60)]) }}</p>
        </div>
        <label class="campo"><span class="req">{{ t('Verification code') }}</span>
          <input ref="campoCodigo" v-model="codigo" class="codigo-verificacion" inputmode="numeric" autocomplete="one-time-code"
                 pattern="\d{6}" maxlength="6" placeholder="••••••" required aria-describedby="ayuda-codigo" @input="alEscribir" />
        </label>
        <p v-if="desafio.codigo_demo" id="ayuda-codigo" class="nota info"><Icono nombre="info" /><span>{{ t('Demo without real SMS: your code is') }} <b class="codigo">{{ tx(desafio.codigo_demo) }}</b></span></p>
        <p v-if="error" class="nota error" role="alert"><Icono nombre="alerta" />{{ tx(error) }}</p>
        <button class="btn btn-primario btn-grande" type="submit" :disabled="enviando || codigo.length !== 6">{{ tx(enviando ? t('Verifying…') : t('Verify and sign in')) }}</button>
        <div class="fila-flex" style="justify-content: space-between">
          <button type="button" class="btn btn-fantasma btn-chico" @click="volver"><Icono nombre="atras" :tam="14" />{{ t('Use another account') }}</button>
          <button type="button" class="btn btn-fantasma btn-chico" :disabled="espera > 0" @click="reenviar">
            {{ tx(espera > 0 ? t('Resend code in {0} s', [espera]) : t('Resend code')) }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-ajustes { position: absolute; top: 18px; inset-inline-end: 18px; display: flex; gap: 8px; align-items: center; }
.codigo-verificacion { font-size: 1.6rem; letter-spacing: 0.5em; text-align: center; font-variant-numeric: tabular-nums; }
.login-seguridad { display: flex; align-items: center; gap: 6px; margin: 0; }
</style>
