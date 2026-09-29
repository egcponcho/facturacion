import { ref, watch } from 'vue'

// Tema de la interfaz: 'sistema' sigue al sistema operativo; 'claro' y
// 'oscuro' lo fijan. Se recuerda en este navegador.
function leer() {
  try {
    return localStorage.getItem('tema') || 'sistema'
  } catch {
    return 'sistema'
  }
}

export const tema = ref(leer())

export function aplicarTema(valor) {
  const raiz = document.documentElement
  if (valor === 'sistema') delete raiz.dataset.theme
  else raiz.dataset.theme = valor === 'oscuro' ? 'dark' : 'light'
  try {
    localStorage.setItem('tema', valor)
  } catch {
    // sin almacenamiento: el tema vale solo para esta visita
  }
}

watch(tema, aplicarTema, { immediate: true })
