<script setup>
import { IDIOMAS, t, tx } from '../i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import Icono from '../components/Icono.vue'
import { guardarPerfil, puede, sesion } from '../stores/sesion'
import { fechaTexto, horaTexto, numeroTexto } from '../stores/preferencias'
import { avisar, errorApi } from '../stores/ui'

// Perfil del usuario: sus datos básicos, su contraseña y sus preferencias
// (idioma, formatos, tema, filas por página y página de inicio). Las
// preferencias se aplican en toda la aplicación y en los PDF, Excel y
// plantillas que genera el servidor para este usuario.
const op = ref(null)
const datos = reactive({ nombre: '', idioma: 'en', formato_fecha: 'MM/DD/YYYY', formato_hora: '12', formato_numero: '1,234.56', tema: 'sistema', filas: 25, inicio: '/' })
const clave = reactive({ actual: '', nueva: '', repetir: '', error: '' })
const ocupado = ref(false)

onMounted(async () => {
  try {
    const r = await api.get('/perfil')
    op.value = r.opciones
    Object.assign(datos, r.preferencias, { nombre: r.nombre })
  } catch (e) {
    errorApi(e)
  }
})

const hoy = new Date()
const isoHoy = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`
const ejemploHora = (f) => horaTexto(new Date(2026, 0, 1, 15, 45), f)
const ejemploNumero = (f) => numeroTexto(1234567.89, 2, f)
const TEMAS = { sistema: t('Same as the system'), claro: t('Light'), oscuro: t('Dark') }
const INICIOS = computed(() => [
  ['/', t('Home'), true], ['/ordenes', t('Purchase orders'), puede('oc.ver')], ['/facturas', t('Invoices'), puede('oc.ver')],
  ['/transporte', t('Shipments'), puede('transporte.gestionar')], ['/productos', t('Products'), puede('producto.ver')],
  ['/seguimiento', t('Tracking'), puede('seguimiento.ver')],
].filter(([, , ok]) => ok))
const iniciales = computed(() => (datos.nombre || sesion.usuario?.email || '?').split(/\s+/).map((x) => x[0]).slice(0, 2).join('').toUpperCase())
const ALCANCE = { admin: t('Administrator'), interno: t('Internal team'), proveedor: t('Supplier user') }

async function guardar() {
  ocupado.value = true
  try {
    await guardarPerfil({ ...datos, filas: Number(datos.filas) })
    avisar(t('Profile saved.'))
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function cambiarClave() {
  clave.error = ''
  if (clave.nueva !== clave.repetir) {
    clave.error = t('The new passwords do not match.')
    return
  }
  try {
    await api.post('/auth/password', { actual: clave.actual, nueva: clave.nueva })
    Object.assign(clave, { actual: '', nueva: '', repetir: '' })
    avisar(t('Password changed. Your other sessions were closed.'))
  } catch (e) {
    clave.error = [e.message, ...(e.detalle || []).map((d) => d.mensaje)].join(' ')
  }
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('My profile') }}</h1>
      <p>{{ t('Your data, your password and how the application shows dates, times and numbers. Your preferences also apply to the PDF, Excel and upload templates you download.') }}</p>
    </div>
  </div>

  <form class="perfil" @submit.prevent="guardar">
    <section class="panel">
      <div class="panel-cabeza"><h2>{{ t('Basic data') }}</h2></div>
      <div class="identidad">
        <span class="avatar grande" aria-hidden="true">{{ tx(iniciales) }}</span>
        <div>
          <b>{{ tx(datos.nombre || sesion.usuario?.nombre) }}</b>
          <span class="sub">{{ tx(sesion.usuario?.email) }}</span>
          <span class="sub">{{ [sesion.usuario?.rol_nombre, sesion.usuario?.proveedor || ALCANCE[sesion.usuario?.rol]].filter(Boolean).map(tx).filter((x, i, a) => a.indexOf(x) === i).join(' · ') }}</span>
        </div>
      </div>
      <div class="rejilla-campos mt-chico">
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="datos.nombre" class="entrada" required minlength="2" maxlength="200" autocomplete="name" /></label>
        <label class="campo"><span>{{ t('Email') }}</span><input :value="sesion.usuario?.email" class="entrada" disabled /></label>
        <label class="campo"><span>{{ t('Registered mobile') }}</span><input :value="sesion.usuario?.telefono || t('Not registered')" class="entrada" disabled />
          <small class="ayuda">{{ t('Used for two-step verification. Ask the administrator to change it.') }}</small></label>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Preferences') }}</h2><p>{{ t('They apply on this and any other device where you sign in.') }}</p></div></div>
      <div class="rejilla-campos">
        <label class="campo"><span>{{ t('Language') }}</span>
          <select v-model="datos.idioma" class="entrada"><option v-for="x in IDIOMAS" :key="x.codigo" :value="x.codigo" :lang="x.codigo">{{ x.nombre }}</option></select>
          <small class="ayuda">{{ t('Changing it reloads the page.') }}</small></label>
        <label class="campo"><span>{{ t('Date format') }}</span>
          <select v-model="datos.formato_fecha" class="entrada">
            <option v-for="f in op?.formatos_fecha || [datos.formato_fecha]" :key="f" :value="f">{{ f }} — {{ fechaTexto(isoHoy, f) }}</option>
          </select>
          <small class="ayuda">{{ t('Used to show dates, to type them and to read the dates of the files you upload.') }}</small></label>
        <label class="campo"><span>{{ t('Time format') }}</span>
          <select v-model="datos.formato_hora" class="entrada">
            <option v-for="f in op?.formatos_hora || ['12', '24']" :key="f" :value="f">{{ f === '12' ? t('12 hours') : t('24 hours') }} — {{ ejemploHora(f) }}</option>
          </select></label>
        <label class="campo"><span>{{ t('Number format') }}</span>
          <select v-model="datos.formato_numero" class="entrada">
            <option v-for="f in op?.formatos_numero || [datos.formato_numero]" :key="f" :value="f">{{ ejemploNumero(f) }}</option>
          </select></label>
        <label class="campo"><span>{{ t('Theme') }}</span>
          <select v-model="datos.tema" class="entrada"><option v-for="(txt, v) in TEMAS" :key="v" :value="v">{{ tx(txt) }}</option></select></label>
        <label class="campo"><span>{{ t('Rows per page') }}</span>
          <select v-model="datos.filas" class="entrada"><option v-for="n in op?.filas || [10, 25, 50, 100]" :key="n" :value="n">{{ n }}</option></select></label>
        <label class="campo"><span>{{ t('Start page') }}</span>
          <select v-model="datos.inicio" class="entrada"><option v-for="[v, txt] in INICIOS" :key="v" :value="v">{{ tx(txt) }}</option></select>
          <small class="ayuda">{{ t('Where you land after signing in.') }}</small></label>
      </div>
    </section>

    <div class="acciones-form">
      <button class="btn btn-primario" type="submit" :disabled="ocupado"><Icono nombre="check" />{{ tx(ocupado ? t('Saving…') : t('Save profile')) }}</button>
    </div>
  </form>

  <section class="panel mt">
    <div class="panel-cabeza"><div><h2>{{ t('Password') }}</h2><p>{{ tx(sesion.usuario?.dos_pasos ? t('Two-step verification on') : t('Password only')) }}</p></div></div>
    <form class="rejilla-campos" @submit.prevent="cambiarClave">
      <label class="campo"><span class="req">{{ t('Current password') }}</span><input v-model="clave.actual" class="entrada" type="password" autocomplete="current-password" required /></label>
      <label class="campo"><span class="req">{{ t('New password') }}</span><input v-model="clave.nueva" class="entrada" type="password" autocomplete="new-password" minlength="10" required />
        <small class="ayuda">{{ t('At least 10 characters, with letters and numbers.') }}</small></label>
      <label class="campo"><span class="req">{{ t('Repeat the new password') }}</span><input v-model="clave.repetir" class="entrada" type="password" autocomplete="new-password" required /></label>
      <p v-if="clave.error" class="nota error campo-ancho" role="alert"><Icono nombre="alerta" />{{ tx(clave.error) }}</p>
      <div class="campo-ancho"><button class="btn" type="submit"><Icono nombre="candado" />{{ t('Change password') }}</button></div>
    </form>
  </section>
</template>

<style scoped>
.perfil { display: flex; flex-direction: column; gap: 16px; }
.identidad { display: flex; align-items: center; gap: 14px; }
.identidad b { display: block; font-size: 1.05rem; }
.avatar.grande { width: 52px; height: 52px; font-size: 1.1rem; }
.acciones-form { display: flex; justify-content: flex-end; }
.campo-ancho { grid-column: 1 / -1; }
@media (max-width: 720px) { .acciones-form .btn { width: 100%; justify-content: center; } }
</style>
