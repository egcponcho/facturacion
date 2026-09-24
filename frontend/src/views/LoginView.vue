<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { iniciarSesion } from '../stores/sesion'

const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const enviando = ref(false)

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
}
</script>

<template>
  <div class="login">
    <form class="login-caja" @submit.prevent="entrar">
      <div>
        <div class="login-titulo">Workspace de proveedor</div>
        <p class="ayuda">Facturas, packing lists y transporte en un solo lugar.</p>
      </div>
      <label class="campo"><span>Correo</span><input v-model="email" type="email" autocomplete="username" required /></label>
      <label class="campo"><span>Contraseña</span><input v-model="password" type="password" autocomplete="current-password" required /></label>
      <p v-if="error" class="nota error" role="alert">{{ error }}</p>
      <button class="btn btn-primario" type="submit" :disabled="enviando">{{ enviando ? 'Entrando…' : 'Entrar' }}</button>
      <div class="demo">
        Cuentas de prueba (contraseña demo123):
        <button type="button" @click="demo('tnf@demo.com')">tnf@demo.com, proveedor The North Face</button>
        <button type="button" @click="demo('vans@demo.com')">vans@demo.com, proveedor Vans</button>
        <button type="button" @click="demo('interno@demo.com')">interno@demo.com, equipo de importaciones</button>
        <button type="button" @click="demo('admin@demo.com')">admin@demo.com, administrador</button>
      </div>
    </form>
  </div>
</template>
