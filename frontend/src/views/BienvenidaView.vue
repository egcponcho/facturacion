<script setup>
import { IDIOMAS, idioma, t, tx } from '../i18n/index.js'
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import Avatar from '../components/Avatar.vue'
import ClaveSegura from '../components/ClaveSegura.vue'
import Icono from '../components/Icono.vue'
import Seleccion from '../components/Seleccion.vue'
import { cargarSesion, cerrarSesion, guardarPerfil, sesion } from '../stores/sesion'
import { fechaTexto, pref } from '../stores/preferencias'
import { errorApi } from '../stores/ui'
import { reducirImagen } from '../utils'

// Asistente del primer ingreso: mientras el usuario tenga la contraseña
// temporal que le dio la administración, entra aquí. Revisa sus datos, puede
// poner su foto y sus preferencias y, al final, crea su propia contraseña.
const router = useRouter()
const paso = ref(0)
const PASOS = [t('Welcome'), t('Photo'), t('Preferences'), t('Password')]
const prefs = reactive({ idioma, formato_fecha: pref.formato_fecha })
const clave = reactive({ actual: '', nueva: '', valida: false, error: '' })
const archivo = ref(null)
const ocupado = ref(false)
const u = computed(() => sesion.usuario || {})
const hoy = new Date()
const isoHoy = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`
const FORMATOS = ['MM/DD/YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD', 'DD-MMM-YYYY', 'MMM DD, YYYY']

async function foto(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  if (!f) return
  try {
    const r = await api.put('/perfil/foto', { foto: await reducirImagen(f) })
    sesion.usuario.foto = r.foto
  } catch (err) {
    errorApi(err)
  }
}

async function guardarPreferencias() {
  ocupado.value = true
  try {
    // El idioma recarga la página: se guarda al final para no perder el paso
    await guardarPerfil({ formato_fecha: prefs.formato_fecha })
    paso.value = 3
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function terminar() {
  clave.error = ''
  ocupado.value = true
  try {
    await api.post('/auth/password', { actual: clave.actual, nueva: clave.nueva })
    await cargarSesion(true)
    if (prefs.idioma !== idioma) await guardarPerfil({ idioma: prefs.idioma }) // recarga en el idioma elegido
    router.replace(pref.inicio || '/')
  } catch (e) {
    clave.error = [e.message, ...(e.detalle || []).map((d) => d.mensaje)].join(' ')
  } finally {
    ocupado.value = false
  }
}
async function salir() {
  await cerrarSesion()
  router.replace('/login')
}
</script>

<template>
  <div class="bienvenida">
    <div class="tarjeta">
      <ol class="progreso" :aria-label="t('Steps')">
        <li v-for="(p, i) in PASOS" :key="p" :class="{ hecho: i < paso, actual: i === paso }"><span>{{ i + 1 }}</span>{{ tx(p) }}</li>
      </ol>

      <section v-if="paso === 0" class="paso">
        <Avatar :nombre="u.nombre" :foto="u.foto" :tam="72" />
        <h1>{{ t('Welcome, {0}', [u.nombre]) }}</h1>
        <p>{{ t('Your account was created by the administration. Check your data and set up your account in a few steps; at the end you will create your own password.') }}</p>
        <dl class="datos">
          <div><dt>{{ t('Email') }}</dt><dd>{{ tx(u.email) }}</dd></div>
          <div v-if="u.cargo"><dt>{{ t('Job title') }}</dt><dd>{{ tx(u.cargo) }}</dd></div>
          <div v-if="u.empresa || u.proveedor"><dt>{{ t('Company') }}</dt><dd>{{ tx(u.empresa || u.proveedor) }}</dd></div>
          <div><dt>{{ t('Role') }}</dt><dd>{{ tx(u.rol_nombre || '—') }}</dd></div>
        </dl>
        <p class="ayuda">{{ t('If something is wrong, ask the administration to correct it.') }}</p>
        <div class="acciones"><button class="btn" type="button" @click="salir">{{ t('Sign out') }}</button><button class="btn btn-primario" type="button" @click="paso = 1">{{ t('Start') }}<Icono nombre="derecha" :tam="15" /></button></div>
      </section>

      <section v-else-if="paso === 1" class="paso">
        <h1>{{ t('Your photo') }}</h1>
        <p>{{ t('Optional. It helps your team recognize you.') }}</p>
        <button type="button" class="foto-grande" :aria-label="t('Choose a photo')" @click="archivo.click()">
          <Avatar :nombre="u.nombre" :foto="u.foto" :tam="120" />
          <span class="camara"><Icono nombre="camara" :tam="18" /></span>
        </button>
        <input ref="archivo" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="foto" />
        <div class="acciones"><button class="btn" type="button" @click="paso = 0">{{ t('Back') }}</button><button class="btn btn-primario" type="button" @click="paso = 2">{{ tx(u.foto ? t('Next') : t('Skip')) }}<Icono nombre="derecha" :tam="15" /></button></div>
      </section>

      <section v-else-if="paso === 2" class="paso">
        <h1>{{ t('Your preferences') }}</h1>
        <p>{{ t('You can change them any time in your profile.') }}</p>
        <div class="rejilla-campos ancho">
          <label class="campo"><span>{{ t('Language') }}</span>
            <Seleccion v-model="prefs.idioma" class="entrada"><option v-for="x in IDIOMAS" :key="x.codigo" :value="x.codigo">{{ x.nombre }}</option></Seleccion></label>
          <label class="campo"><span>{{ t('Date format') }}</span>
            <Seleccion v-model="prefs.formato_fecha" class="entrada"><option v-for="f in FORMATOS" :key="f" :value="f">{{ f }} — {{ fechaTexto(isoHoy, f) }}</option></Seleccion></label>
        </div>
        <div class="acciones"><button class="btn" type="button" @click="paso = 1">{{ t('Back') }}</button><button class="btn btn-primario" type="button" :disabled="ocupado" @click="guardarPreferencias">{{ t('Next') }}<Icono nombre="derecha" :tam="15" /></button></div>
      </section>

      <form v-else class="paso" @submit.prevent="terminar">
        <h1>{{ t('Create your password') }}</h1>
        <p>{{ t('Replace the temporary password you received with your own. Only you will know it.') }}</p>
        <div class="ancho clave">
          <label class="campo"><span class="req">{{ t('Temporary password') }}</span><input v-model="clave.actual" class="entrada" type="password" autocomplete="current-password" required /></label>
          <ClaveSegura v-model="clave.nueva" :email="u.email" @valida="(v) => (clave.valida = v)" />
          <p v-if="clave.error" class="nota error" role="alert"><Icono nombre="alerta" />{{ tx(clave.error) }}</p>
        </div>
        <div class="acciones"><button class="btn" type="button" @click="paso = 2">{{ t('Back') }}</button>
          <button class="btn btn-primario" type="submit" :disabled="ocupado || !clave.valida || !clave.actual"><Icono nombre="check" :tam="15" />{{ t('Finish and enter') }}</button></div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.bienvenida { min-height: 100vh; display: grid; place-items: center; padding: 24px 16px; background:
  radial-gradient(circle at 15% 10%, color-mix(in srgb, var(--acento) 18%, transparent), transparent 45%), var(--fondo, var(--superficie-2)); }
.tarjeta { width: min(640px, 100%); background: var(--superficie); border: 1px solid var(--linea); border-radius: 16px; box-shadow: var(--sombra-alta, var(--sombra)); padding: 24px; }
.progreso { list-style: none; margin: 0 0 22px; padding: 0; display: flex; gap: 6px; flex-wrap: wrap; }
.progreso li { display: inline-flex; align-items: center; gap: 6px; font-size: 0.82rem; color: var(--tinta-3); padding: 4px 10px 4px 4px; border-radius: 99px; background: var(--superficie-2); }
.progreso li span { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--linea); color: var(--tinta-2); font-weight: 700; font-size: 0.76rem; }
.progreso li.actual { color: var(--acento-texto); background: var(--acento-claro); }
.progreso li.actual span { background: var(--acento); color: #fff; }
.progreso li.hecho span { background: var(--ok); color: #fff; }
.paso { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 10px; }
.paso h1 { margin: 6px 0 0; font-size: 1.45rem; }
.paso > p { margin: 0; color: var(--tinta-2); max-width: 48ch; }
.datos { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; width: 100%; margin: 8px 0 0; text-align: start; }
.datos div { padding: 10px 12px; border-radius: var(--radio); background: var(--superficie-2); }
.datos dt { font-size: 0.76rem; color: var(--tinta-3); }
.datos dd { margin: 2px 0 0; font-weight: 620; overflow-wrap: anywhere; }
.foto-grande { position: relative; border: 0; background: none; cursor: pointer; padding: 6px; border-radius: 50%; }
.foto-grande .camara { position: absolute; inset-inline-end: 6px; bottom: 10px; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--acento); color: #fff; border: 2px solid var(--superficie); }
.ancho { width: 100%; text-align: start; }
.clave { display: flex; flex-direction: column; gap: 12px; }
.acciones { display: flex; justify-content: space-between; gap: 8px; width: 100%; margin-top: 14px; }
</style>
