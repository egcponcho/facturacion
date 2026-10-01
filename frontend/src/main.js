import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { vFiltros, vTarjetas } from './directivas'
import MasOpciones from './components/MasOpciones.vue'
import CampoFecha from './components/CampoFecha.vue'
import './styles.css'
import './stores/tema'

import { cargarIdioma } from './i18n/index.js'

cargarIdioma().finally(() => createApp(App).use(router).directive('filtros', vFiltros).directive('tarjetas', vTarjetas).component('MasOpciones', MasOpciones).component('CampoFecha', CampoFecha).mount('#app'))
