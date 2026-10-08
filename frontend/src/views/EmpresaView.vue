<script setup>
import { t, tx, IDIOMAS } from '../i18n/index.js'
import { onMounted, ref } from 'vue'
import { api } from '../api'
import Icono from '../components/Icono.vue'
import Interruptor from '../components/Interruptor.vue'
import SelectBusqueda from '../components/SelectBusqueda.vue'
import Seleccion from '../components/Seleccion.vue'
import { cargarSesion } from '../stores/sesion'
import { avisar, errorApi, guardando } from '../stores/ui'
import { reducirImagen } from '../utils'

// Empresa de la instalación: datos generales, logo, preferencias y reglas de
// negocio. Solo la administración los cambia.
const o = ref(null)
const datos = ref(null)
const ocupado = ref(false)
// Monedas y zonas horarias: las listas ISO del navegador; países: el catálogo de países
const MONEDAS = Intl.supportedValuesOf ? Intl.supportedValuesOf('currency') : ['USD', 'EUR']
const ZONAS = Intl.supportedValuesOf ? Intl.supportedValuesOf('timeZone') : ['UTC']
const paises = ref([])
const FORMATOS = ['MM/DD/YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD']
// Textos de las reglas (el servidor manda la clave; aquí, cómo se lee)
const REGLAS = {
  PROVEEDOR_PUEDE_FINALIZAR: t('Suppliers can finalize their invoices and packing lists'),
  POSICION_EN_VARIAS_FACTURAS: t('A PO line can be split across several active invoices'),
  FACTURA_EN_UNA_SOLA_UNIDAD: t('All packing lists of an invoice must travel in the same load unit'),
  REQUERIR_DATOS_ADUANA: t('Country of origin and HS code are required per line to finalize'),
  DIAS_ALERTA_BORRADOR: t('Days before warning about drafts that still reserve quantities'),
  DIAS_MARGEN_RIESGO: t('Minimum margin (days) before the required date to be on time'),
  PAIS_BASE_CLASIF: t('Country whose national code completes the suggested HS code'),
  COMPATIBILIDAD_BLOQUEANTE: t('PO data that cannot be mixed in one invoice'),
  COMPATIBILIDAD_ADVERTENCIA: t('PO data that only warns when mixed in one invoice'),
}

function copiar(x) {
  datos.value = {
    nombre: x.nombre, razon_social: x.razon_social || '', id_fiscal: x.id_fiscal || '', pais: x.pais || '', logo: x.logo,
    preferencias: { ...x.preferencias },
    reglas: Object.fromEntries(x.reglas.map((r) => [r.clave, Array.isArray(r.valor) ? [...r.valor] : r.valor])),
  }
}

async function cargar() {
  try {
    o.value = await api.get('/organizacion')
    copiar(o.value)
  } catch (e) {
    errorApi(e)
  }
}
onMounted(() => {
  cargar()
  api.get('/catalogos/paises/opciones').then((r) => { paises.value = r.map((p) => ({ valor: p.codigo, texto: p.texto, sub: p.codigo })) }).catch(() => {})
})

async function subirLogo(ev) {
  try {
    datos.value.logo = await reducirImagen(ev.target.files[0], 320)
  } catch (e) {
    errorApi(e)
  } finally {
    ev.target.value = ''
  }
}

async function guardar() {
  ocupado.value = true
  try {
    o.value = await guardando(api.put('/organizacion', datos.value))
    copiar(o.value)
    await cargarSesion(true) // nombre y logo en el menú, reglas en toda la app
    avisar(t('Company settings saved.'))
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <header class="pagina-cabeza">
    <div>
      <p class="eyebrow">{{ t('Settings') }}</p>
      <h1>{{ t('Company') }}</h1>
      <p>{{ t('Name, logo, preferences and business rules of your company.') }}</p>
    </div>
    <div class="fila-flex">
      <button class="btn btn-primario" :disabled="ocupado || !datos" @click="guardar"><Icono nombre="check" />{{ t('Save changes') }}</button>
    </div>
  </header>

  <template v-if="datos">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('General information') }}</h2><p>{{ t('It appears in the menu and in the documents you issue.') }}</p></div></div>
      <div class="empresa-general">
        <div class="empresa-logo">
          <img v-if="datos.logo" :src="datos.logo" :alt="t('Company logo')" />
          <span v-else class="empresa-logo-vacio"><Icono nombre="caja" :tam="28" /></span>
          <label class="btn btn-chico"><Icono nombre="importar" :tam="14" />{{ t('Upload logo') }}<input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="subirLogo" /></label>
          <button v-if="datos.logo" type="button" class="btn btn-chico btn-fantasma" @click="datos.logo = null">{{ t('Remove') }}</button>
        </div>
        <div class="rejilla-campos">
          <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="datos.nombre" class="entrada" maxlength="200" required /></label>
          <label class="campo"><span>{{ t('Legal name') }}</span><input v-model="datos.razon_social" class="entrada" maxlength="200" /></label>
          <label class="campo"><span>{{ t('Tax ID') }}</span><input v-model="datos.id_fiscal" class="entrada" maxlength="40" /></label>
          <div class="campo"><span>{{ t('Country') }}</span><SelectBusqueda v-model="datos.pais" :opciones="paises" :vacio="t('None')" :prefijo="false" /></div>
          <div class="campo"><span>{{ t('Company code') }}</span><div class="valor-fijo">{{ tx(o.codigo) }}</div></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Preferences') }}</h2><p>{{ t('Defaults for new users and documents. Each person can still choose their own language and formats.') }}</p></div></div>
      <div class="rejilla-campos">
        <label class="campo"><span>{{ t('Default language') }}</span>
          <Seleccion v-model="datos.preferencias.idioma" class="entrada"><option v-for="x in IDIOMAS" :key="x.codigo" :value="x.codigo">{{ x.nombre }}</option></Seleccion></label>
        <div class="campo"><span>{{ t('Base currency') }}</span><SelectBusqueda v-model="datos.preferencias.moneda" :opciones="MONEDAS" :prefijo="false" /></div>
        <label class="campo"><span>{{ t('Date format') }}</span>
          <Seleccion v-model="datos.preferencias.formato_fecha" class="entrada"><option v-for="f in FORMATOS" :key="f" :value="f">{{ f }}</option></Seleccion></label>
        <div class="campo"><span>{{ t('Time zone') }}</span><SelectBusqueda v-model="datos.preferencias.zona_horaria" :opciones="ZONAS" :prefijo="false" /></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Business rules') }}</h2><p>{{ t('How your company works. They apply to everyone in it right after saving.') }}</p></div></div>
      <ul class="lista-reglas">
        <li v-for="r in o.reglas" :key="r.clave">
          <span>{{ tx(REGLAS[r.clave] || r.texto) }}</span>
          <div v-if="Array.isArray(r.valor)" class="regla-lista">
            <label v-for="c in o.campos_compatibilidad" :key="c.clave" class="check">
              <input type="checkbox" :checked="datos.reglas[r.clave].includes(c.clave)"
                     @change="datos.reglas[r.clave] = datos.reglas[r.clave].includes(c.clave) ? datos.reglas[r.clave].filter((x) => x !== c.clave) : [...datos.reglas[r.clave], c.clave]" />{{ tx(c.texto) }}
            </label>
          </div>
          <Interruptor v-else-if="typeof r.valor === 'boolean'" v-model="datos.reglas[r.clave]" :etiqueta="tx(REGLAS[r.clave] || r.texto)" />
          <input v-else-if="typeof r.valor === 'number'" v-model.number="datos.reglas[r.clave]" type="number" min="0" max="365" class="entrada regla-numero"
                 :aria-label="tx(REGLAS[r.clave] || r.texto)" />
          <SelectBusqueda v-else v-model="datos.reglas[r.clave]" class="regla-pais" :opciones="paises" :prefijo="false" :etiqueta="tx(REGLAS[r.clave] || r.texto)" />
        </li>
      </ul>
    </section>
  </template>
</template>

<style scoped>
.panel + .panel { margin-top: 16px; }
.empresa-general { display: grid; grid-template-columns: 180px 1fr; gap: 24px; align-items: start; }
.empresa-logo { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.empresa-logo img, .empresa-logo-vacio { width: 120px; height: 120px; border-radius: var(--radio-panel); border: 1px solid var(--linea); object-fit: contain; background: var(--superficie-2); }
.empresa-logo-vacio { display: grid; place-items: center; color: var(--tinta-3); }
.lista-reglas { list-style: none; margin: 0; padding: 0; }
.lista-reglas li { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--linea-suave); }
.lista-reglas li:last-child { border-bottom: 0; }
.regla-numero { width: 90px; flex: none; }
@media (max-width: 720px) { .empresa-general { grid-template-columns: 1fr; } }
.regla-pais { min-width: 220px; }
.regla-lista { display: flex; flex-wrap: wrap; gap: 4px 14px; justify-content: flex-end; max-width: 520px; }
</style>
