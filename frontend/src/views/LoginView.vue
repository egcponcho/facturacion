<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icono from '../components/Icono.vue'
import SelectorTema from '../components/SelectorTema.vue'
import { iniciarSesion } from '../stores/sesion'

const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const enviando = ref(false)

const DEMO = [
  ['tnf@demo.com', 'Proveedor', 'The North Face'],
  ['vans@demo.com', 'Proveedor', 'Vans'],
  ['interno@demo.com', 'Importaciones', 'Equipo interno'],
  ['admin@demo.com', 'Administrador', 'Acceso total'],
]

async function entrar() {
  error.value = ''
  enviando.value = true
  try {
    await iniciarSesion(email.value, password.value)
    router.push(route.query.volver || '/')
  } catch (e) {
    error.value = e.message
  } finally {
    enviando.value = false
  }
}

function demo(correo) {
  email.value = correo
  password.value = 'demo123'
  entrar()
}
</script>

<template>
  <div class="login">
    <section class="login-arte">
      <div class="marca" style="padding: 0">
        <span class="marca-logo"><Icono nombre="caja" :tam="20" /></span>
        <span class="marca-texto">Workspace<span>Facturas, empaque y embarques</span></span>
      </div>
      <div>
        <h1>De la orden de compra al contenedor, sin hojas sueltas.</h1>
        <p>Factura desde tus OCs, empaca con plantillas y sigue cada embarque hasta la bodega.</p>
      </div>
      <ul class="login-pasos">
        <li><span><Icono nombre="factura" /></span>Factura OCs completas o por partes</li>
        <li><span><Icono nombre="caja" /></span>Empaca todo en un paso con tus plantillas de caja</li>
        <li><span><Icono nombre="barco" /></span>Asigna a contenedores y sigue el tránsito</li>
      </ul>
    </section>
    <div class="login-lado">
      <div style="position: absolute; top: 18px; right: 18px"><SelectorTema /></div>
      <form class="login-caja" @submit.prevent="entrar">
        <div>
          <div class="login-titulo">Inicia sesión</div>
          <p class="ayuda">Usa tu correo de proveedor o del equipo de importaciones.</p>
        </div>
        <label class="campo"><span class="req">Correo</span><input v-model="email" type="email" autocomplete="username" required /></label>
        <label class="campo"><span class="req">Contraseña</span><input v-model="password" type="password" autocomplete="current-password" required /></label>
        <p v-if="error" class="nota error" role="alert"><Icono nombre="alerta" />{{ error }}</p>
        <button class="btn btn-primario btn-grande" type="submit" :disabled="enviando">{{ enviando ? 'Entrando…' : 'Entrar' }}</button>
        <div class="demo">
          <span>Cuentas de prueba (contraseña demo123). Un clic para entrar:</span>
          <div class="demo-cuentas">
            <button v-for="[correo, rol, nombre] in DEMO" :key="correo" type="button" @click="demo(correo)">
              <b>{{ nombre }}</b>{{ rol }}
            </button>
          </div>
        </div>
      </form>
    </div>
  </div>
</template>
