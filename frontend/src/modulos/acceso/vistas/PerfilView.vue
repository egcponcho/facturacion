<script setup>
import { IDIOMAS, t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import Avatar from '@/componentes/Avatar.vue'
import ClaveSegura from '@/modulos/acceso/componentes/ClaveSegura.vue'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { guardarPerfil, puede, sesion } from '@/stores/sesion'
import { fechaTexto, horaTexto, numeroTexto } from '@/stores/preferencias'
import { avisar, errorApi } from '@/stores/ui'
import { fmtFechaHora, reducirImagen } from '@/nucleo/utils'

// Perfil: foto, datos del usuario, lo que puede hacer y sus preferencias.
// Nombre, foto y preferencias los cambia el usuario; correo, cargo, área,
// empresa, rol, proveedor y celular los administra la administración.
const perfil = ref(null)
const datos = reactive({ nombre: '', idioma: 'es', idioma_documentos: '', formato_fecha: 'MM/DD/YYYY', formato_hora: '12', formato_numero: '1,234.56', tema: 'sistema', filas: 25, inicio: '/' })
const clave = reactive({ actual: '', nueva: '', valida: false, error: '' })
const ocupado = ref(false)
const archivo = ref(null)
const seccion = ref('datos')

async function cargar() {
  try {
    perfil.value = await api.get('/perfil')
    Object.assign(datos, perfil.value.preferencias, { nombre: perfil.value.nombre })
    datos.idioma_documentos = perfil.value.preferencias.idioma_documentos || ''
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)

const hoy = new Date()
const isoHoy = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`
const ejemploHora = (f) => horaTexto(new Date(2026, 0, 1, 15, 45), f)
const ejemploNumero = (f) => numeroTexto(1234567.89, 2, f)
const TEMAS = { sistema: t('Same as the system'), claro: t('Light'), oscuro: t('Dark') }
const INICIOS = computed(() => [
  ['/', t('Home'), true], ['/ordenes', t('Purchase orders'), puede('oc.ver')], ['/facturas', t('Invoices'), puede('factura.ver')],
  ['/transporte', t('Shipments'), puede('transporte.gestionar')], ['/productos', t('Products'), puede('producto.ver')],
  ['/seguimiento', t('Tracking'), puede('seguimiento.ver')],
].filter(([, , ok]) => ok))
const ALCANCE = { admin: t('Administrator'), interno: t('Internal team'), proveedor: t('Supplier user') }
const subtitulo = computed(() => [perfil.value?.cargo, perfil.value?.area, perfil.value?.empresa].filter(Boolean).join(' · '))
const SECCIONES = [['datos', t('Personal information'), 'usuario'], ['acceso', t('Access and permissions'), 'candado'],
  ['preferencias', t('Preferences'), 'engrane'], ['seguridad', t('Security'), 'alerta']]
const FIJOS = [['email', t('Email')], ['cargo', t('Job title')], ['area', t('Area')], ['empresa', t('Company')], ['telefono', t('Registered mobile')]]

async function cambiarFoto(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  if (!f) return
  try {
    const foto = await reducirImagen(f)
    const r = await api.put('/perfil/foto', { foto })
    perfil.value.foto = sesion.usuario.foto = r.foto
    avisar(t('Profile photo updated.'))
  } catch (err) {
    errorApi(err)
  }
}
async function quitarFoto() {
  try {
    await api.put('/perfil/foto', { foto: null })
    perfil.value.foto = sesion.usuario.foto = null
  } catch (err) {
    errorApi(err)
  }
}

async function guardar() {
  ocupado.value = true
  try {
    const r = await guardarPerfil({ ...datos, filas: Number(datos.filas), idioma_documentos: datos.idioma_documentos || null })
    perfil.value.nombre = r.nombre
    avisar(t('Profile saved.'))
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function cambiarClave() {
  clave.error = ''
  try {
    await api.post('/auth/password', { actual: clave.actual, nueva: clave.nueva })
    Object.assign(clave, { actual: '', nueva: '', valida: false })
    avisar(t('Password changed. Your other sessions were closed.'))
    cargar()
  } catch (e) {
    clave.error = [e.message, ...(e.detalle || []).map((d) => d.mensaje)].join(' ')
  }
}
</script>

<template>
  <template v-if="perfil">
    <section class="perfil-portada">
      <div class="portada-fondo" aria-hidden="true"></div>
      <div class="portada-cuerpo">
        <div class="foto-marco">
          <Avatar :nombre="perfil.nombre" :foto="perfil.foto" :tam="104" />
          <button type="button" class="foto-boton" :title="t('Change photo')" :aria-label="t('Change photo')" @click="archivo.click()"><Icono nombre="camara" :tam="16" /></button>
          <input ref="archivo" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="cambiarFoto" />
        </div>
        <div class="portada-texto">
          <h1>{{ tx(perfil.nombre) }}</h1>
          <p v-if="subtitulo" class="portada-sub">{{ tx(subtitulo) }}</p>
          <div class="fila-flex perfil-etiquetas">
            <span class="etiqueta ms-0"><Icono nombre="candado" :tam="13" />{{ tx(perfil.rol_nombre || '—') }}</span>
            <span class="etiqueta ms-0"><Icono nombre="usuarios" :tam="13" />{{ tx(perfil.proveedor || ALCANCE[perfil.rol]) }}</span>
            <span class="etiqueta ms-0" :class="perfil.dos_pasos ? 'ok' : ''"><Icono nombre="check" :tam="13" />{{ tx(perfil.dos_pasos ? t('Two-step verification on') : t('Password only')) }}</span>
          </div>
        </div>
        <div class="portada-acciones">
          <button v-if="perfil.foto" type="button" class="btn btn-chico" @click="quitarFoto">{{ t('Remove photo') }}</button>
        </div>
      </div>
      <nav class="pestanas perfil-pestanas" role="tablist" :aria-label="t('Profile sections')">
        <button v-for="[k, txt, ic] in SECCIONES" :key="k" type="button" class="pestana" role="tab" :aria-selected="seccion === k" @click="seccion = k"><Icono :nombre="ic" :tam="15" />{{ tx(txt) }}</button>
      </nav>
    </section>

    <section v-if="seccion === 'datos'" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Personal information') }}</h2><p>{{ t('You can change your name and photo. The fields with a lock are managed by the administration.') }}</p></div></div>
      <form class="rejilla-campos" @submit.prevent="guardar">
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="datos.nombre" class="entrada" required minlength="2" maxlength="200" autocomplete="name" /></label>
        <div v-for="[k, txt] in FIJOS" :key="k" class="campo dato-fijo" :title="t('Managed by the administration')">
          <span>{{ tx(txt) }} <Icono nombre="candado" :tam="12" /></span>
          <div class="valor-fijo">{{ tx(perfil[k] || '—') }}</div>
        </div>
        <div class="campo-ancho fila-acciones"><button class="btn btn-primario" type="submit" :disabled="ocupado"><Icono nombre="check" />{{ t('Save profile') }}</button></div>
      </form>
    </section>

    <section v-else-if="seccion === 'acceso'" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Access and permissions') }}</h2><p>{{ t('Given by your role; the administration changes them.') }}</p></div></div>
      <div class="accesos">
        <div class="acceso-resumen">
          <div><span>{{ t('Role') }}</span><b>{{ tx(perfil.rol_nombre || '—') }}</b></div>
          <div><span>{{ t('Data you see') }}</span><b>{{ tx(perfil.proveedor ? t('Only {0}', [perfil.proveedor]) : t('Every supplier')) }}</b></div>
          <div><span>{{ t('Last sign-in') }}</span><b>{{ tx(perfil.ultimo_acceso ? fmtFechaHora(perfil.ultimo_acceso) : '—') }}</b></div>
        </div>
        <div class="modulos">
          <div v-for="m in perfil.accesos" :key="m.modulo" class="modulo">
            <b>{{ tx(m.modulo) }}</b>
            <ul><li v-for="p in m.permisos" :key="p"><Icono nombre="check" :tam="12" />{{ tx(p) }}</li></ul>
          </div>
        </div>
      </div>
    </section>

    <section v-else-if="seccion === 'preferencias'" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Preferences') }}</h2><p>{{ t('They apply on this and any other device where you sign in.') }}</p></div></div>
      <form class="rejilla-campos" @submit.prevent="guardar">
        <label class="campo"><span>{{ t('Language') }}</span>
          <Seleccion v-model="datos.idioma" class="entrada"><option v-for="x in IDIOMAS" :key="x.codigo" :value="x.codigo">{{ x.nombre }}</option></Seleccion>
          <small class="ayuda">{{ t('Changing it reloads the page.') }}</small></label>
        <label class="campo"><span>{{ t('Language of documents') }}</span>
          <Seleccion v-model="datos.idioma_documentos" class="entrada">
            <option value="">{{ t('Same as the screen') }}</option>
            <option v-for="x in IDIOMAS" :key="x.codigo" :value="x.codigo">{{ x.nombre }}</option>
          </Seleccion>
          <small class="ayuda">{{ t('Invoices, packing lists, technical sheets and reports you download (PDF and Excel).') }}</small></label>
        <label class="campo"><span>{{ t('Date format') }}</span>
          <Seleccion v-model="datos.formato_fecha" class="entrada">
            <option v-for="f in perfil.opciones.formatos_fecha" :key="f" :value="f">{{ f }} — {{ fechaTexto(isoHoy, f) }}</option>
          </Seleccion>
          <small class="ayuda">{{ t('Used to show dates, to type them and to read the dates of the files you upload.') }}</small></label>
        <label class="campo"><span>{{ t('Time format') }}</span>
          <Seleccion v-model="datos.formato_hora" class="entrada">
            <option v-for="f in perfil.opciones.formatos_hora" :key="f" :value="f">{{ f === '12' ? t('12 hours') : t('24 hours') }} — {{ ejemploHora(f) }}</option>
          </Seleccion></label>
        <label class="campo"><span>{{ t('Number format') }}</span>
          <Seleccion v-model="datos.formato_numero" class="entrada">
            <option v-for="f in perfil.opciones.formatos_numero" :key="f" :value="f">{{ ejemploNumero(f) }}</option>
          </Seleccion></label>
        <label class="campo"><span>{{ t('Theme') }}</span>
          <Seleccion v-model="datos.tema" class="entrada"><option v-for="(txt, v) in TEMAS" :key="v" :value="v">{{ tx(txt) }}</option></Seleccion></label>
        <label class="campo"><span>{{ t('Rows per page') }}</span>
          <Seleccion v-model="datos.filas" class="entrada"><option v-for="n in perfil.opciones.filas" :key="n" :value="n">{{ n }}</option></Seleccion></label>
        <label class="campo"><span>{{ t('Start page') }}</span>
          <Seleccion v-model="datos.inicio" class="entrada"><option v-for="[v, txt] in INICIOS" :key="v" :value="v">{{ tx(txt) }}</option></Seleccion>
          <small class="ayuda">{{ t('Where you land after signing in.') }}</small></label>
        <div class="campo-ancho fila-acciones"><button class="btn btn-primario" type="submit" :disabled="ocupado"><Icono nombre="check" />{{ t('Save profile') }}</button></div>
      </form>
    </section>

    <section v-else class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Security') }}</h2>
        <p>{{ tx(perfil.password_cambiado_en ? t('Password last changed on {0}.', [fmtFechaHora(perfil.password_cambiado_en)]) : t('You have not changed your password yet.')) }}</p></div></div>
      <form class="seguridad" @submit.prevent="cambiarClave">
        <label class="campo"><span class="req">{{ t('Current password') }}</span><input v-model="clave.actual" class="entrada" type="password" autocomplete="current-password" required /></label>
        <ClaveSegura v-model="clave.nueva" :email="perfil.email" @valida="(v) => (clave.valida = v)" />
        <p v-if="clave.error" class="nota error" role="alert"><Icono nombre="alerta" />{{ tx(clave.error) }}</p>
        <div><button class="btn btn-primario" type="submit" :disabled="!clave.valida || !clave.actual"><Icono nombre="candado" />{{ t('Change password') }}</button></div>
      </form>
    </section>
  </template>
</template>

<style scoped>
.perfil-portada { background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio-panel); box-shadow: var(--sombra); overflow: hidden; margin-bottom: 16px; }
.portada-fondo { height: 120px; background: linear-gradient(120deg, var(--acento) 0%, color-mix(in srgb, var(--acento) 55%, #22c1c3) 100%); }
.portada-cuerpo { display: flex; align-items: flex-start; gap: 18px; padding: 0 24px 16px; margin-top: -52px; flex-wrap: wrap; }
.foto-marco { position: relative; border-radius: 50%; padding: 4px; background: var(--superficie); }
.foto-boton { position: absolute; inset-inline-end: 2px; bottom: 6px; width: 32px; height: 32px; border-radius: 50%; border: 2px solid var(--superficie);
  background: var(--acento); color: #fff; display: grid; place-items: center; cursor: pointer; }
.portada-texto { flex: 1; min-width: 220px; margin-top: 62px; }
.portada-texto h1 { margin: 0; font-size: 1.6rem; }
.portada-sub { margin: 2px 0 8px; color: var(--tinta-2); }
.perfil-etiquetas { gap: 6px; }
.portada-acciones { margin-top: 62px; }
.perfil-pestanas { margin: 0; padding: 0 16px; border-bottom: 0; border-top: 1px solid var(--linea-suave); }
.dato-fijo span { display: inline-flex; align-items: center; gap: 4px; }
.valor-fijo { padding: 9px 12px; border: 1px dashed var(--linea); border-radius: var(--radio); background: var(--superficie-2); color: var(--tinta-2); min-height: 40px; overflow-wrap: anywhere; }
.campo-ancho { grid-column: 1 / -1; }
.fila-acciones { display: flex; justify-content: flex-end; }
.accesos { display: flex; flex-direction: column; gap: 16px; }
.acceso-resumen { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.acceso-resumen div { display: flex; flex-direction: column; gap: 2px; padding: 12px; border-radius: var(--radio); background: var(--superficie-2); }
.acceso-resumen span { font-size: 0.78rem; color: var(--tinta-3); }
.modulos { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
.modulo { border: 1px solid var(--linea); border-radius: var(--radio); padding: 10px 12px; }
.modulo ul { list-style: none; margin: 6px 0 0; padding: 0; display: flex; flex-direction: column; gap: 3px; font-size: 0.84rem; color: var(--tinta-2); }
.modulo li { display: flex; align-items: flex-start; gap: 6px; }
.modulo li :deep(svg) { color: var(--ok); margin-top: 3px; flex: none; }
.seguridad { display: flex; flex-direction: column; gap: 12px; max-width: 640px; }
@media (max-width: 720px) {
  .portada-cuerpo { padding: 0 16px 14px; }
  .portada-texto h1 { font-size: 1.3rem; }
  .portada-texto, .portada-acciones { margin-top: 0; flex-basis: 100%; }
  .fila-acciones .btn { width: 100%; justify-content: center; }
}
</style>
